import calendar
from datetime import date, datetime, timedelta
from uuid import uuid4
from decimal import Decimal, InvalidOperation

from django.core.paginator import Paginator
from django.db import transaction as db_transaction
from django.db.models import Q, Sum
from django.db.models.functions import (
    Abs,
    TruncDay,
    TruncMonth,
    TruncQuarter,
    TruncWeek,
    TruncYear,
)
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.http import HttpResponse
from fincore.models import (
    Account,
    Bill,
    BillItem,
    Category,
    Invoice,
    InvoiceItem,
    Transaction,
    TransferGroup,
    Vendor,
)
from fincore.views.utils import selectable_accounts


def _render_transfer_list(request, category=None):
    # Get filter parameters
    date_range = (request.GET.get("date_range") or "this_year").strip()
    date_from = (request.GET.get("date_from") or "").strip()
    date_to = (request.GET.get("date_to") or "").strip()
    vendor_id = (request.GET.get("vendor_id") or "").strip()
    account_id = (request.GET.get("account_id") or "").strip()

    date_range, start_date, end_date = _resolve_report_range(date_range, date_from, date_to)

    # Get filter lists
    vendor_kind = "payer" if category.kind == "income" else "payee"
    vendors = list(
        Vendor.objects.filter(is_active=True, kind=vendor_kind).order_by("name")
    )
    all_accounts = list(Account.objects.filter(is_active=True).select_related("parent").order_by("name"))
    all_accounts = list(
        Account.objects.filter(is_active=True).select_related("parent").order_by("name")
    )
    accounts = list(selectable_accounts())
    vendor_ids = {v.id for v in vendors}
    account_ids = {a.id for a in accounts}

    # Normalize vendor_id and account_id
    try:
        vendor_id_int = int(vendor_id) if vendor_id.isdigit() else None
    except (ValueError, TypeError):
        vendor_id_int = None
    if vendor_id_int not in vendor_ids:
        vendor_id_int = None

    try:
        account_id_int = int(account_id) if account_id.isdigit() else None
    except (ValueError, TypeError):
        account_id_int = None
    if account_id_int not in account_ids:
        account_id_int = None

    groups = (
        TransferGroup.objects.prefetch_related(
            "transactions__account",
            "transactions__vendor",
            "transactions__category",
        )
        .order_by("-created_at")
    )

    # Apply filters to transactions through the groups
    if start_date or end_date or vendor_id_int or account_id_int:
        # Filter groups based on their transactions
        filtered_group_ids = set()
        for group in groups:
            txns = list(group.transactions.all())
            if not txns:
                continue
            # Check if any transaction matches filters
            matches = False
            for txn in txns:
                date_match = True
                if start_date and txn.date < start_date:
                    date_match = False
                if end_date and txn.date > end_date:
                    date_match = False
                vendor_match = (not vendor_id_int) or (txn.vendor_id == vendor_id_int)
                account_match = (not account_id_int) or (txn.account_id == account_id_int)
                if date_match and vendor_match and account_match:
                    matches = True
                    break
            if matches:
                filtered_group_ids.add(group.id)
        groups = groups.filter(id__in=filtered_group_ids)

    page_size = 25
    try:
        page_size = int(request.GET.get("page_size") or page_size)
    except (TypeError, ValueError):
        page_size = 25
    paginator = Paginator(groups, page_size)
    try:
        page_number = int(request.GET.get("page") or 1)
    except (TypeError, ValueError):
        page_number = 1
    page_obj = paginator.get_page(page_number)
    rows = []
    for group in page_obj.object_list:
        txns = list(group.transactions.all())
        if not txns:
            continue
        txns.sort(key=lambda t: (t.amount, t.id))
        txn_out = next((t for t in txns if t.amount < 0), txns[0])
        txn_in = next((t for t in txns if t.amount > 0), txns[-1])
        rows.append(
            {
                "group": group,
                "txn_out": txn_out,
                "txn_in": txn_in,
                "count": len(txns),
            }
        )

    # Build query params for pagination
    query_params = request.GET.copy()
    query_params.pop("page", None)

    return render(
        request,
        "fincore/transactions/transfers.html",
        {
            "category": category,
            "page_obj": page_obj,
            "rows": rows,
            "date_range": date_range,
            "date_from": date_from,
            "date_to": date_to,
            "vendor_id": vendor_id_int,
            "account_id": account_id_int,
            "report_ranges": REPORT_RANGE_OPTIONS,
            "vendors": vendors,
            "accounts": accounts,
            "filter_query": query_params.urlencode(),
        },
    )


REPORT_RANGE_OPTIONS = [
    ("this_year", "This year"),
    ("last_year", "Last year"),
    ("this_month", "This month"),
    ("last_month", "Last month"),
    ("this_quarter", "This quarter"),
    ("custom", "Custom dates"),
]
REPORT_RANGE_KEYS = {value for value, _label in REPORT_RANGE_OPTIONS}

DISPLAY_BY_OPTIONS = [
    ("days", "Days"),
    ("weeks", "Weeks"),
    ("months", "Months"),
    ("quarters", "Quarters"),
    ("years", "Years"),
    ("customer", "Customer"),
    ("vendor", "Vendor"),
    ("product", "Product / Service"),
]
DISPLAY_BY_KEYS = {value for value, _label in DISPLAY_BY_OPTIONS}


def _parse_date(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _month_bounds(year_value, month_value):
    last_day = calendar.monthrange(year_value, month_value)[1]
    return date(year_value, month_value, 1), date(year_value, month_value, last_day)


def _quarter_bounds(year_value, quarter_key):
    mapping = {"q1": (1, 3), "q2": (4, 6), "q3": (7, 9), "q4": (10, 12)}
    start_month, end_month = mapping[quarter_key]
    _, end_day = calendar.monthrange(year_value, end_month)
    return date(year_value, start_month, 1), date(year_value, end_month, end_day)


def _resolve_report_range(date_range, date_from, date_to):
    date_range = (date_range or "this_year").strip()
    if date_range not in REPORT_RANGE_KEYS:
        date_range = "this_year"
    today = date.today()
    start_date = None
    end_date = None
    if date_range == "this_month":
        start_date, end_date = _month_bounds(today.year, today.month)
    elif date_range == "last_month":
        last_month = today.month - 1 or 12
        year_value = today.year - 1 if today.month == 1 else today.year
        start_date, end_date = _month_bounds(year_value, last_month)
    elif date_range == "last_year":
        start_date = date(today.year - 1, 1, 1)
        end_date = date(today.year - 1, 12, 31)
    elif date_range == "this_year":
        start_date = date(today.year, 1, 1)
        end_date = date(today.year, 12, 31)
    elif date_range == "this_quarter":
        quarter_key = f"q{((today.month - 1) // 3) + 1}"
        start_date, end_date = _quarter_bounds(today.year, quarter_key)
    elif date_range == "custom":
        start_date = _parse_date(date_from)
        end_date = _parse_date(date_to)
    return date_range, start_date, end_date


def _build_goto_range(date_range, date_from, date_to):
    today = date.today()
    goto_date_range = date_range
    goto_date_from = date_from
    goto_date_to = date_to
    if date_range == "this_quarter":
        goto_date_range = f"q{((today.month - 1) // 3) + 1}"
        goto_date_from = ""
        goto_date_to = ""
    elif date_range in {"this_year", "this_month", "last_month"}:
        goto_date_from = ""
        goto_date_to = ""
    return goto_date_range, goto_date_from, goto_date_to


def _default_date_bounds(date_range):
    today = date.today()
    if date_range == "this_month":
        return _month_bounds(today.year, today.month)
    if date_range == "last_month":
        last_month = today.month - 1 or 12
        year_value = today.year - 1 if today.month == 1 else today.year
        return _month_bounds(year_value, last_month)
    if date_range == "last_year":
        return date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)
    if date_range == "this_quarter":
        quarter_key = f"q{((today.month - 1) // 3) + 1}"
        return _quarter_bounds(today.year, quarter_key)
    return date(today.year, 1, 1), date(today.year, 12, 31)


def _iter_months(start_date, end_date):
    current = date(start_date.year, start_date.month, 1)
    end_marker = date(end_date.year, end_date.month, 1)
    while current <= end_marker:
        yield current
        year = current.year + (current.month // 12)
        month = 1 if current.month == 12 else current.month + 1
        current = date(year, month, 1)


def _iter_quarters(start_date, end_date):
    quarter = ((start_date.month - 1) // 3) + 1
    start_month = (quarter - 1) * 3 + 1
    current = date(start_date.year, start_month, 1)
    while current <= end_date:
        yield current
        year = current.year + (1 if current.month >= 10 else 0)
        month = 1 if current.month >= 10 else current.month + 3
        current = date(year, month, 1)


def _iter_years(start_date, end_date):
    current = date(start_date.year, 1, 1)
    while current <= end_date:
        yield current
        current = date(current.year + 1, 1, 1)


def _iter_weeks(start_date, end_date):
    current = start_date - timedelta(days=start_date.weekday())
    while current <= end_date:
        yield current
        current = current + timedelta(days=7)


def _iter_days(start_date, end_date):
    current = start_date
    while current <= end_date:
        yield current
        current = current + timedelta(days=1)


def _build_time_columns(display_by, start_date, end_date):
    if display_by == "days":
        period_iter = list(_iter_days(start_date, end_date))
        fmt = "%b %-d, %Y"
    elif display_by == "weeks":
        period_iter = list(_iter_weeks(start_date, end_date))
        fmt = "Wk of %b %-d"
    elif display_by == "quarters":
        period_iter = list(_iter_quarters(start_date, end_date))
        fmt = "Q%q %Y"
    elif display_by == "years":
        period_iter = list(_iter_years(start_date, end_date))
        fmt = "%Y"
    else:
        period_iter = list(_iter_months(start_date, end_date))
        fmt = "%b %Y"

    columns = []
    for period_start in period_iter:
        if display_by == "quarters":
            quarter = ((period_start.month - 1) // 3) + 1
            label = f"Q{quarter} {period_start.year}"
            start = date(period_start.year, (quarter - 1) * 3 + 1, 1)
            end = _quarter_bounds(period_start.year, f"q{quarter}")[1]
        elif display_by == "years":
            label = period_start.strftime(fmt)
            start = date(period_start.year, 1, 1)
            end = date(period_start.year, 12, 31)
        elif display_by == "weeks":
            label = period_start.strftime(fmt)
            start = period_start
            end = period_start + timedelta(days=6)
        elif display_by == "days":
            label = period_start.strftime(fmt)
            start = period_start
            end = period_start
        else:
            label = period_start.strftime(fmt)
            start = period_start
            end = _month_bounds(period_start.year, period_start.month)[1]
        columns.append({"key": period_start, "label": label, "start": start, "end": end})
    return columns


def _build_dimension_columns(values):
    labels = sorted({value or "Unassigned" for value in values})
    return [{"key": label, "label": label} for label in labels]


def category_report(request, pk):
    category = get_object_or_404(Category, pk=pk)
    if category.kind == "transfer":
        return _render_transfer_list(request, category=category)

    date_range = (request.GET.get("date_range") or "this_year").strip()
    date_from = (request.GET.get("date_from") or "").strip()
    date_to = (request.GET.get("date_to") or "").strip()
    vendor_id = (request.GET.get("vendor_id") or "").strip()
    account_id = (request.GET.get("account_id") or "").strip()

    date_range, start_date, end_date = _resolve_report_range(date_range, date_from, date_to)

    # Get filter lists
    vendors = list(Vendor.objects.filter(is_active=True).order_by("name"))
    accounts = list(selectable_accounts())
    vendor_ids = {v.id for v in vendors}
    account_ids = {a.id for a in accounts}

    # Normalize vendor_id and account_id
    try:
        vendor_id_int = int(vendor_id) if vendor_id.isdigit() else None
    except (ValueError, TypeError):
        vendor_id_int = None
    if vendor_id_int not in vendor_ids:
        vendor_id_int = None

    try:
        account_id_int = int(account_id) if account_id.isdigit() else None
    except (ValueError, TypeError):
        account_id_int = None
    if account_id_int not in account_ids:
        account_id_int = None

    goto_date_range, goto_date_from, goto_date_to = _build_goto_range(
        date_range, date_from, date_to
    )

    txn_qs = (
        Transaction.objects.select_related("account", "vendor")
        .filter(category=category)
        .order_by("-date", "-id")
    )
    if category.kind == "income":
        txn_qs = txn_qs.filter(invoice_payments__isnull=True)
    if category.kind in {"expense", "payroll"}:
        txn_qs = txn_qs.filter(bill_payments__isnull=True)

    if start_date:
        txn_qs = txn_qs.filter(date__gte=start_date)
    if end_date:
        txn_qs = txn_qs.filter(date__lte=end_date)
    if vendor_id_int:
        txn_qs = txn_qs.filter(vendor_id=vendor_id_int)
    if account_id_int:
        txn_qs = txn_qs.filter(account_id=account_id_int)

    invoice_items = []
    if category.kind == "income":
        invoice_qs = (
            InvoiceItem.objects.select_related(
                "invoice",
                "invoice__account",
                "invoice__customer",
            )
            .filter(category=category)
            .order_by("-invoice__date", "-id")
        )
        if start_date:
            invoice_qs = invoice_qs.filter(invoice__date__gte=start_date)
        if end_date:
            invoice_qs = invoice_qs.filter(invoice__date__lte=end_date)
        if vendor_id_int:
            invoice_qs = invoice_qs.filter(invoice__customer_id=vendor_id_int)
        if account_id_int:
            invoice_qs = invoice_qs.filter(invoice__account_id=account_id_int)
        invoice_items = list(invoice_qs)

    bill_items = []
    if category.kind in {"expense", "payroll"}:
        bill_qs = (
            BillItem.objects.select_related(
                "bill",
                "bill__account",
                "bill__vendor",
            )
            .filter(category=category)
            .order_by("-bill__date", "-id")
        )
        if start_date:
            bill_qs = bill_qs.filter(bill__date__gte=start_date)
        if end_date:
            bill_qs = bill_qs.filter(bill__date__lte=end_date)
        if vendor_id_int:
            bill_qs = bill_qs.filter(bill__vendor_id=vendor_id_int)
        if account_id_int:
            bill_qs = bill_qs.filter(bill__account_id=account_id_int)
        bill_items = list(bill_qs)

    rows = []
    for txn in txn_qs:
        rows.append(
            {
                "row_date": txn.date,
                "row_id": txn.id,
                "date": txn.date,
                "vendor_name": txn.vendor.name if txn.vendor else "-",
                "description": txn.description or "-",
                "account_name": txn.account.name,
                "amount": txn.amount,
                "source": "transaction",
                "goto_url": reverse("fincore:transaction_list")
                + f"?account_id={txn.account_id}&category={category.id}"
                + f"&date_range={goto_date_range}"
                + (f"&date_from={goto_date_from}" if goto_date_from else "")
                + (f"&date_to={goto_date_to}" if goto_date_to else ""),
            }
        )

    for item in invoice_items:
        rows.append(
            {
                "row_date": item.invoice.date,
                "row_id": item.id,
                "date": item.invoice.date,
                "vendor_name": item.invoice.customer.name,
                "description": item.description or "-",
                "account_name": item.invoice.account.name,
                "amount": item.amount,
                "source": "invoice_item",
                "goto_url": reverse("fincore:sales_invoice_detail", args=[item.invoice_id]),
            }
        )

    for item in bill_items:
        rows.append(
            {
                "row_date": item.bill.date,
                "row_id": item.id,
                "date": item.bill.date,
                "vendor_name": item.bill.vendor.name if item.bill.vendor else "-",
                "description": item.description or "-",
                "account_name": item.bill.account.name,
                "amount": item.amount,
                "source": "bill_item",
                "goto_url": reverse("fincore:bill_detail", args=[item.bill_id]),
            }
        )

    rows.sort(key=lambda row: (row["row_date"], row["row_id"]), reverse=True)

    total_amount = sum((row["amount"] for row in rows), Decimal("0.00"))

    page_size = 25
    try:
        page_number = int(request.GET.get("page") or 1)
    except (TypeError, ValueError):
        page_number = 1
    paginator = Paginator(rows, page_size)
    page_obj = paginator.get_page(page_number)

    query_params = request.GET.copy()
    query_params.pop("page", None)

    return render(
        request,
        "fincore/categories/report.html",
        {
            "category": category,
            "page_obj": page_obj,
            "page_size": page_size,
            "date_range": date_range,
            "date_from": date_from,
            "date_to": date_to,
            "vendor_id": vendor_id_int,
            "account_id": account_id_int,
            "goto_date_range": goto_date_range,
            "goto_date_from": goto_date_from,
            "goto_date_to": goto_date_to,
            "filter_query": query_params.urlencode(),
            "report_ranges": REPORT_RANGE_OPTIONS,
            "vendors": vendors,
            "accounts": accounts,
            "total_amount": total_amount,
        },
    )


def _profit_loss_context(request):
    date_range = (request.GET.get("date_range") or "this_year").strip()
    date_from = (request.GET.get("date_from") or "").strip()
    date_to = (request.GET.get("date_to") or "").strip()
    account_id = (request.GET.get("account_id") or "").strip()
    vendor_id = (request.GET.get("vendor_id") or "").strip()
    category_id = (request.GET.get("category_id") or "").strip()
    kind = (request.GET.get("kind") or "all").strip()
    display_by = (request.GET.get("display_by") or "months").strip()

    if display_by not in DISPLAY_BY_KEYS:
        display_by = "months"

    date_range, start_date, end_date = _resolve_report_range(date_range, date_from, date_to)
    pnl_kinds = ["income", "expense", "payroll", "cogs"]
    if kind not in pnl_kinds:
        kind = "all"

    account_id = account_id if account_id.isdigit() else ""
    vendor_id = vendor_id if vendor_id.isdigit() else ""
    category_id = category_id if category_id.isdigit() else ""

    if not start_date or not end_date:
        start_date, end_date = _default_date_bounds(date_range)

    columns = []
    if display_by in {"days", "weeks", "months", "quarters", "years"}:
        columns = _build_time_columns(display_by, start_date, end_date)

    def build_rows(data_rows, column_list):
        rows = []
        for category_id_key, entry in data_rows.items():
            cells = []
            row_total = Decimal("0.00")
            for column in column_list:
                key = column["key"]
                value = entry["values"].get(key, Decimal("0.00"))
                cells.append({"value": value, "column": column})
                row_total += value
            rows.append(
                {"name": entry["name"], "cells": cells, "total": row_total, "category_id": category_id_key}
            )
        rows.sort(key=lambda r: r["name"])
        return rows

    income_rows = []
    cogs_rows = []
    payroll_rows = []
    expense_rows = []

    income_total = Decimal("0.00")
    cogs_total = Decimal("0.00")
    payroll_total = Decimal("0.00")
    expense_total = Decimal("0.00")
    income_dim_values = []
    expense_dim_values = []
    income_data_rows = {}
    expense_data_rows = {"cogs": {}, "payroll": {}, "expense": {}}
    income_column_totals = []
    cogs_column_totals = []
    payroll_column_totals = []
    expense_column_totals = []
    gross_profit_column_totals = []
    net_operating_income_column_totals = []
    net_income_column_totals = []

    if kind in {"all", "income"}:
        # ── Invoice-based income (from InvoiceItems) ──
        invoice_items = InvoiceItem.objects.select_related(
            "category", "invoice", "invoice__account", "invoice__customer"
        ).filter(category__kind="income")
        if account_id:
            invoice_items = invoice_items.filter(invoice__account_id=int(account_id))
        if vendor_id:
            invoice_items = invoice_items.filter(invoice__customer_id=int(vendor_id))
        if category_id:
            invoice_items = invoice_items.filter(category_id=int(category_id))
        if start_date:
            invoice_items = invoice_items.filter(invoice__date__gte=start_date)
        if end_date:
            invoice_items = invoice_items.filter(invoice__date__lte=end_date)

        # ── Transaction-based income (imports, manual) ──
        income_txn_qs = (
            Transaction.objects.select_related("category", "account", "vendor")
            .filter(category__isnull=False, kind="income")
            .exclude(invoice_payments__isnull=False)
        )
        if account_id:
            income_txn_qs = income_txn_qs.filter(account_id=int(account_id))
        if vendor_id:
            income_txn_qs = income_txn_qs.filter(vendor_id=int(vendor_id))
        if category_id:
            income_txn_qs = income_txn_qs.filter(category_id=int(category_id))
        if start_date:
            income_txn_qs = income_txn_qs.filter(date__gte=start_date)
        if end_date:
            income_txn_qs = income_txn_qs.filter(date__lte=end_date)

        if display_by in {"days", "weeks", "months", "quarters", "years"}:
            trunc_map_inv = {
                "days": TruncDay("invoice__date"),
                "weeks": TruncWeek("invoice__date"),
                "months": TruncMonth("invoice__date"),
                "quarters": TruncQuarter("invoice__date"),
                "years": TruncYear("invoice__date"),
            }
            trunc_map_txn = {
                "days": TruncDay("date"),
                "weeks": TruncWeek("date"),
                "months": TruncMonth("date"),
                "quarters": TruncQuarter("date"),
                "years": TruncYear("date"),
            }

            # Invoice items
            inv_grouped = (
                invoice_items.annotate(period=trunc_map_inv[display_by])
                .values("category_id", "category__name", "period")
                .annotate(total=Sum("amount"))
            )
            data_rows = {}
            for row in inv_grouped:
                category_id_key = row["category_id"]
                period_key = row["period"].date() if hasattr(row["period"], "date") else row["period"]
                if category_id_key not in data_rows:
                    data_rows[category_id_key] = {"name": row["category__name"], "values": {}}
                data_rows[category_id_key]["values"][period_key] = row["total"] or Decimal("0.00")

            # Income transactions
            txn_grouped = (
                income_txn_qs.annotate(period=trunc_map_txn[display_by])
                .values("category_id", "category__name", "period")
                .annotate(total=Sum("amount"))
            )
            for row in txn_grouped:
                category_id_key = row["category_id"]
                period_key = row["period"].date() if hasattr(row["period"], "date") else row["period"]
                if category_id_key not in data_rows:
                    data_rows[category_id_key] = {"name": row["category__name"], "values": {}}
                existing = data_rows[category_id_key]["values"].get(period_key, Decimal("0.00"))
                data_rows[category_id_key]["values"][period_key] = existing + (row["total"] or Decimal("0.00"))

            income_rows = build_rows(data_rows, columns)
        else:
            dimension_field_inv = "category__name" if display_by == "product" else "invoice__customer__name"
            dimension_field_txn = "category__name" if display_by == "product" else "vendor__name"

            inv_grouped = (
                invoice_items.values("category_id", "category__name", dimension_field_inv)
                .annotate(total=Sum("amount"))
            )
            dim_values = []
            data_rows = {}
            for row in inv_grouped:
                dim_value = row.get(dimension_field_inv) or "Unassigned"
                dim_values.append(dim_value)
                category_id_key = row["category_id"]
                if category_id_key not in data_rows:
                    data_rows[category_id_key] = {"name": row["category__name"], "values": {}}
                data_rows[category_id_key]["values"][dim_value] = row["total"] or Decimal("0.00")

            txn_grouped = (
                income_txn_qs.values("category_id", "category__name", dimension_field_txn)
                .annotate(total=Sum("amount"))
            )
            for row in txn_grouped:
                dim_value = row.get(dimension_field_txn) or "Unassigned"
                dim_values.append(dim_value)
                category_id_key = row["category_id"]
                if category_id_key not in data_rows:
                    data_rows[category_id_key] = {"name": row["category__name"], "values": {}}
                existing = data_rows[category_id_key]["values"].get(dim_value, Decimal("0.00"))
                data_rows[category_id_key]["values"][dim_value] = existing + (row["total"] or Decimal("0.00"))

            income_data_rows = data_rows
            income_dim_values = dim_values

        income_total = sum((row["total"] for row in income_rows), Decimal("0.00"))

    if kind in {"all", "cogs", "expense", "payroll"}:
        txn_kinds = ["cogs", "expense", "payroll"] if kind == "all" else [kind]
        txn_qs = (
            Transaction.objects.select_related("category", "account", "vendor")
            .filter(category__isnull=False, kind__in=txn_kinds)
            .exclude(invoice_payments__isnull=False)
        )
        if account_id:
            txn_qs = txn_qs.filter(account_id=int(account_id))
        if vendor_id:
            txn_qs = txn_qs.filter(vendor_id=int(vendor_id))
        if category_id:
            txn_qs = txn_qs.filter(category_id=int(category_id))
        if start_date:
            txn_qs = txn_qs.filter(date__gte=start_date)
        if end_date:
            txn_qs = txn_qs.filter(date__lte=end_date)

        if display_by in {"days", "weeks", "months", "quarters", "years"}:
            trunc_map = {
                "days": TruncDay("date"),
                "weeks": TruncWeek("date"),
                "months": TruncMonth("date"),
                "quarters": TruncQuarter("date"),
                "years": TruncYear("date"),
            }
            grouped = (
                txn_qs.annotate(period=trunc_map[display_by])
                .values("category_id", "category__name", "category__kind", "period")
                .annotate(total=Sum("amount"))
            )
            data_rows = {"cogs": {}, "payroll": {}, "expense": {}}
            for row in grouped:
                kind_key = row["category__kind"]
                category_id_key = row["category_id"]
                period_key = row["period"].date() if hasattr(row["period"], "date") else row["period"]
                if category_id_key not in data_rows[kind_key]:
                    data_rows[kind_key][category_id_key] = {
                        "name": row["category__name"],
                        "values": {},
                    }
                data_rows[kind_key][category_id_key]["values"][period_key] = abs(
                    row["total"] or Decimal("0.00")
                )
            cogs_rows = build_rows(data_rows["cogs"], columns)
            payroll_rows = build_rows(data_rows["payroll"], columns)
            expense_rows = build_rows(data_rows["expense"], columns)
        else:
            dimension_field = "category__name" if display_by == "product" else "vendor__name"
            grouped = (
                txn_qs.values("category_id", "category__name", "category__kind", dimension_field)
                .annotate(total=Sum("amount"))
            )
            dim_values = []
            data_rows = {"cogs": {}, "payroll": {}, "expense": {}}
            for row in grouped:
                dim_value = row.get(dimension_field) or "Unassigned"
                dim_values.append(dim_value)
                kind_key = row["category__kind"]
                category_id_key = row["category_id"]
                if category_id_key not in data_rows[kind_key]:
                    data_rows[kind_key][category_id_key] = {
                        "name": row["category__name"],
                        "values": {},
                    }
                data_rows[kind_key][category_id_key]["values"][dim_value] = abs(
                    row["total"] or Decimal("0.00")
                )
            expense_data_rows = data_rows
            expense_dim_values = dim_values

    if display_by in {"customer", "vendor", "product"}:
        columns = _build_dimension_columns(income_dim_values + expense_dim_values)
        income_rows = build_rows(income_data_rows, columns) if income_data_rows else []
        cogs_rows = build_rows(expense_data_rows["cogs"], columns) if expense_data_rows else []
        payroll_rows = (
            build_rows(expense_data_rows["payroll"], columns) if expense_data_rows else []
        )
        expense_rows = (
            build_rows(expense_data_rows["expense"], columns) if expense_data_rows else []
        )

    is_single_period = (
        display_by in {"days", "weeks", "months", "quarters", "years"} and len(columns) == 1
    )

    # Always show Uncategorized Income / Expense rows in P&L
    uncat_income_cat = Category.objects.filter(
        name="Uncategorized Income", kind="income", is_protected=True
    ).first()
    uncat_expense_cat = Category.objects.filter(
        name="Uncategorized Expense", kind="expense", is_protected=True
    ).first()

    def _ensure_uncat_row(rows, category):
        if not category:
            return rows
        if any(r["category_id"] == category.id for r in rows):
            return rows
        zero_cells = [{"value": Decimal("0.00"), "column": col} for col in columns]
        rows.append({
            "name": category.name,
            "cells": zero_cells,
            "total": Decimal("0.00"),
            "category_id": category.id,
        })
        rows.sort(key=lambda r: r["name"])
        return rows

    if kind in {"all", "income"} and uncat_income_cat:
        income_rows = _ensure_uncat_row(income_rows, uncat_income_cat)
    if kind in {"all", "expense"} and uncat_expense_cat:
        expense_rows = _ensure_uncat_row(expense_rows, uncat_expense_cat)

    def group_rows_by_parent(rows):
        if not rows:
            return []
        category_ids = {row["category_id"] for row in rows if row.get("category_id")}
        categories = (
            Category.objects.filter(id__in=category_ids)
            .select_related("parent")
        )
        category_map = {cat.id: cat for cat in categories}
        groups = {}
        for row in rows:
            category_id_key = row.get("category_id")
            category = category_map.get(category_id_key)
            parent = category.parent if category and category.parent_id else category
            parent_id = parent.id if parent else category_id_key
            group = groups.setdefault(
                parent_id,
                {
                    "parent_id": parent_id,
                    "parent_name": parent.name if parent else row["name"],
                    "parent_category_id": parent.id if parent else category_id_key,
                    "cells": None,
                    "total": Decimal("0.00"),
                    "rows": [],
                },
            )
            group["rows"].append(row)
            if group["cells"] is None:
                group["cells"] = [
                    {"value": cell["value"], "column": cell["column"]}
                    for cell in row.get("cells", [])
                ]
            else:
                for idx, cell in enumerate(row.get("cells", [])):
                    group["cells"][idx]["value"] += cell["value"]
            group["total"] += row.get("total", Decimal("0.00"))

        grouped = list(groups.values())
        grouped.sort(key=lambda g: g["parent_name"])
        for group in grouped:
            group["rows"].sort(key=lambda r: r["name"])
            group["has_children"] = any(
                row.get("category_id") != group["parent_category_id"] for row in group["rows"]
            ) or len(group["rows"]) > 1
        return grouped

    def build_column_totals(rows, column_count):
        totals = [Decimal("0.00") for _ in range(column_count)]
        for row in rows:
            for idx, cell in enumerate(row.get("cells", [])):
                totals[idx] += cell["value"]
        return totals

    if columns:
        income_column_totals = build_column_totals(income_rows, len(columns))
        cogs_column_totals = build_column_totals(cogs_rows, len(columns))
        payroll_column_totals = build_column_totals(payroll_rows, len(columns))
        expense_column_totals = build_column_totals(expense_rows + payroll_rows, len(columns))
        gross_profit_column_totals = [
            income_column_totals[idx] - cogs_column_totals[idx]
            for idx in range(len(columns))
        ]
        net_operating_income_column_totals = [
            gross_profit_column_totals[idx] - expense_column_totals[idx]
            for idx in range(len(columns))
        ]
        net_income_column_totals = list(net_operating_income_column_totals)

    cogs_total = sum((row["total"] for row in cogs_rows), Decimal("0.00"))
    payroll_total = sum((row["total"] for row in payroll_rows), Decimal("0.00"))
    expense_total = sum((row["total"] for row in expense_rows), Decimal("0.00")) + payroll_total

    income_total_display = income_total
    cogs_total_display = abs(cogs_total)
    payroll_total_display = abs(payroll_total)
    expense_total_display = abs(expense_total)
    gross_profit = income_total - cogs_total
    gross_profit_display = abs(gross_profit)
    gross_profit_is_negative = gross_profit < 0
    net_operating_income = gross_profit - expense_total
    net_operating_income_display = abs(net_operating_income)
    net_operating_income_is_negative = net_operating_income < 0
    net_income = net_operating_income
    net_income_display = abs(net_income)
    net_income_is_negative = net_income < 0
    income_groups = group_rows_by_parent(income_rows)
    cogs_groups = group_rows_by_parent(cogs_rows)
    payroll_groups = group_rows_by_parent(payroll_rows)
    expense_groups = group_rows_by_parent(expense_rows)

    accounts = selectable_accounts()
    vendors = Vendor.objects.filter(is_active=True).order_by("name")
    categories = Category.objects.filter(is_active=True, kind__in=pnl_kinds).order_by(
        "kind", "name"
    )

    filters = {
        "date_range": date_range,
        "date_from": date_from,
        "date_to": date_to,
        "account_id": account_id,
        "vendor_id": vendor_id,
        "category_id": category_id,
        "kind": kind,
        "display_by": display_by,
    }

    return {
        "filters": filters,
        "query_string": request.GET.urlencode(),
        "report_ranges": REPORT_RANGE_OPTIONS,
        "display_by_options": DISPLAY_BY_OPTIONS,
        "accounts": accounts,
        "vendors": vendors,
        "categories": categories,
        "income_rows": income_rows,
        "cogs_rows": cogs_rows,
        "expense_rows": expense_rows,
        "payroll_rows": payroll_rows,
        "income_groups": income_groups,
        "cogs_groups": cogs_groups,
        "payroll_groups": payroll_groups,
        "expense_groups": expense_groups,
        "income_total": income_total,
        "cogs_total": cogs_total,
        "expense_total": expense_total,
        "payroll_total": payroll_total,
        "income_total_display": income_total_display,
        "cogs_total_display": cogs_total_display,
        "payroll_total_display": payroll_total_display,
        "expense_total_display": expense_total_display,
        "income_column_totals": income_column_totals,
        "cogs_column_totals": cogs_column_totals,
        "payroll_column_totals": payroll_column_totals,
        "expense_column_totals": expense_column_totals,
        "gross_profit_column_totals": gross_profit_column_totals,
        "net_operating_income_column_totals": net_operating_income_column_totals,
        "net_income_column_totals": net_income_column_totals,
        "gross_profit": gross_profit,
        "gross_profit_display": gross_profit_display,
        "gross_profit_is_negative": gross_profit_is_negative,
        "net_operating_income": net_operating_income,
        "net_operating_income_display": net_operating_income_display,
        "net_operating_income_is_negative": net_operating_income_is_negative,
        "net_income": net_income,
        "net_income_display": net_income_display,
        "net_income_is_negative": net_income_is_negative,
        "columns": columns,
        "display_by": display_by,
        "is_single_period": is_single_period,
    }


def _balance_sheet_context(request):
    date_range = (request.GET.get("date_range") or "this_year").strip()
    date_from = (request.GET.get("date_from") or "").strip()
    date_to = (request.GET.get("date_to") or "").strip()
    account_id = (request.GET.get("account_id") or "").strip()
    category_id = (request.GET.get("category_id") or "").strip()
    kind = (request.GET.get("kind") or "all").strip()

    date_range, _start_date, end_date = _resolve_report_range(date_range, date_from, date_to)
    if not end_date:
        _start_date, end_date = _default_date_bounds(date_range)
    as_of_date = end_date or date.today()

    account_id = account_id if account_id.isdigit() else ""
    category_id = category_id if category_id.isdigit() else ""

    accounts = list(selectable_accounts())
    categories = list(
        Category.objects.filter(is_active=True, kind__in=["liability", "equity"]).order_by("name")
    )

    account_id_int = int(account_id) if account_id.isdigit() else None
    balances = (
        Transaction.objects.filter(date__lte=as_of_date)
        .values("account_id")
        .annotate(total=Sum("amount"))
    )
    balance_map = {row["account_id"]: row["total"] or Decimal("0.00") for row in balances}
    for account in all_accounts:
        account.balance = balance_map.get(account.id, Decimal("0.00"))

    children_by_parent = {}
    for account in all_accounts:
        if account.parent_id:
            children_by_parent.setdefault(account.parent_id, []).append(account)

    assets_rows = []
    if account_id_int:
        selected = next((a for a in all_accounts if a.id == account_id_int), None)
        if selected:
            assets_rows.append({"row_type": "single", "name": selected.name, "amount": selected.balance})
    else:
        parents = [a for a in all_accounts if a.parent_id is None]
        for parent in parents:
            children = sorted(children_by_parent.get(parent.id, []), key=lambda c: c.name.lower())
            if children:
                parent_total = sum((child.balance for child in children), Decimal("0.00"))
                assets_rows.append({"row_type": "parent", "name": parent.name, "amount": parent_total, "parent_id": parent.id})
                for child in children:
                    assets_rows.append({"row_type": "child", "name": child.name, "amount": child.balance, "parent_id": parent.id})
            else:
                assets_rows.append({"row_type": "single", "name": parent.name, "amount": parent.balance})

    leaf_accounts = [a for a in all_accounts if not children_by_parent.get(a.id)]
    assets_total = sum((a.balance for a in leaf_accounts), Decimal("0.00"))

    def _category_totals(kind_value):
        qs = Transaction.objects.select_related("category").filter(
            category__kind=kind_value, date__lte=as_of_date
        )
        if account_id:
            qs = qs.filter(account_id=int(account_id))
        if category_id:
            qs = qs.filter(category_id=int(category_id))
        grouped = qs.values("category_id", "category__name").annotate(total=Sum("amount"))
        rows = []
        total = Decimal("0.00")
        for row in grouped:
            value = row["total"] or Decimal("0.00")
            rows.append({"name": row["category__name"], "amount": abs(value)})
            total += abs(value)
        rows.sort(key=lambda r: r["name"])
        return rows, total

    liability_rows, liability_total = _category_totals("liability")
    equity_rows, equity_total = _category_totals("equity")

    filters = {
        "date_range": date_range,
        "date_from": date_from,
        "date_to": date_to,
        "account_id": account_id,
        "category_id": category_id,
        "kind": kind if kind in {"all", "assets", "liability", "equity"} else "all",
    }

    return {
        "filters": filters,
        "report_ranges": REPORT_RANGE_OPTIONS,
        "as_of_date": as_of_date,
        "accounts": accounts,
        "categories": categories,
        "assets_rows": assets_rows,
        "assets_total": assets_total,
        "liability_rows": liability_rows,
        "liability_total": liability_total,
        "equity_rows": equity_rows,
        "equity_total": equity_total,
        "total_liabilities_equity": liability_total + equity_total,
    }


def _cashflow_context(request):
    date_range = (request.GET.get("date_range") or "this_year").strip()
    date_from = (request.GET.get("date_from") or "").strip()
    date_to = (request.GET.get("date_to") or "").strip()
    account_id = (request.GET.get("account_id") or "").strip()
    vendor_id = (request.GET.get("vendor_id") or "").strip()
    category_id = (request.GET.get("category_id") or "").strip()
    kind = (request.GET.get("kind") or "all").strip()
    view_mode = (request.GET.get("view") or "detailed").strip()

    date_range, start_date, end_date = _resolve_report_range(date_range, date_from, date_to)
    if not start_date or not end_date:
        start_date, end_date = _default_date_bounds(date_range)

    account_id = account_id if account_id.isdigit() else ""
    vendor_id = vendor_id if vendor_id.isdigit() else ""
    category_id = category_id if category_id.isdigit() else ""

    accounts = list(selectable_accounts())
    vendors = list(Vendor.objects.filter(is_active=True).order_by("name"))
    categories = list(Category.objects.filter(is_active=True).order_by("name"))

    base_qs = (
        Transaction.objects.select_related("category", "account", "vendor")
        .filter(date__gte=start_date, date__lte=end_date)
        .exclude(kind__in=["transfer", "opening"])
    )
    if account_id:
        base_qs = base_qs.filter(account_id=int(account_id))
    if vendor_id:
        base_qs = base_qs.filter(vendor_id=int(vendor_id))
    if category_id:
        base_qs = base_qs.filter(category_id=int(category_id))

    if kind != "all":
        base_qs = base_qs.filter(kind=kind)

    def _group_by_kind(kind_values):
        grouped = (
            base_qs.filter(kind__in=kind_values)
            .values("category_id", "category__name")
            .annotate(total=Sum("amount"))
        )
        rows = []
        total = Decimal("0.00")
        for row in grouped:
            amount = row["total"] or Decimal("0.00")
            rows.append(
                {
                    "name": row["category__name"] or "Uncategorized",
                    "amount": amount,
                    "category_id": row["category_id"],
                }
            )
            total += amount
        rows.sort(key=lambda r: r["name"])
        return rows, total

    operating_rows, operating_total = _group_by_kind(["income", "expense", "payroll", "cogs"])
    investing_rows, investing_total = _group_by_kind(["withdraw"])
    financing_rows, financing_total = _group_by_kind(["equity", "liability"])

    unmatched_invoice_total = Decimal("0.00")
    unmatched_bill_total = Decimal("0.00")

    invoice_qs = Invoice.objects.exclude(status="void")
    if account_id:
        invoice_qs = invoice_qs.filter(account_id=int(account_id))
    if vendor_id:
        invoice_qs = invoice_qs.filter(customer_id=int(vendor_id))
    if start_date:
        invoice_qs = invoice_qs.filter(date__gte=start_date)
    if end_date:
        invoice_qs = invoice_qs.filter(date__lte=end_date)
    for invoice in invoice_qs:
        remaining = invoice.remaining_balance
        if remaining > Decimal("0.00"):
            unmatched_invoice_total += remaining

    bill_qs = Bill.objects.exclude(status="void")
    if account_id:
        bill_qs = bill_qs.filter(account_id=int(account_id))
    if vendor_id:
        bill_qs = bill_qs.filter(vendor_id=int(vendor_id))
    if start_date:
        bill_qs = bill_qs.filter(date__gte=start_date)
    if end_date:
        bill_qs = bill_qs.filter(date__lte=end_date)
    for bill in bill_qs:
        remaining = bill.remaining_balance
        if remaining > Decimal("0.00"):
            unmatched_bill_total += remaining

    if unmatched_invoice_total != Decimal("0.00"):
        operating_rows.append(
            {"name": "Unmatched invoices", "amount": unmatched_invoice_total, "category_id": None}
        )
        operating_total += unmatched_invoice_total
    if unmatched_bill_total != Decimal("0.00"):
        operating_rows.append(
            {"name": "Unmatched bills", "amount": -unmatched_bill_total, "category_id": None}
        )
        operating_total -= unmatched_bill_total

    operating_rows.sort(key=lambda r: r["name"])

    def group_rows_by_parent(rows):
        if not rows:
            return []
        category_ids = {row["category_id"] for row in rows if row.get("category_id")}
        categories = Category.objects.filter(id__in=category_ids).select_related("parent")
        category_map = {cat.id: cat for cat in categories}
        groups = {}
        for row in rows:
            category_id_key = row.get("category_id")
            category = category_map.get(category_id_key)
            parent = category.parent if category and category.parent_id else category
            parent_id = parent.id if parent else category_id_key or row["name"]
            group = groups.setdefault(
                parent_id,
                {
                    "parent_id": parent_id,
                    "parent_name": parent.name if parent else row["name"],
                    "parent_category_id": parent.id if parent else category_id_key,
                    "rows": [],
                    "total": Decimal("0.00"),
                },
            )
            group["rows"].append(row)
            group["total"] += row.get("amount", Decimal("0.00"))

        grouped = list(groups.values())
        grouped.sort(key=lambda g: g["parent_name"])
        for group in grouped:
            group["rows"].sort(key=lambda r: r["name"])
            group["has_children"] = any(
                row.get("category_id") != group["parent_category_id"] for row in group["rows"]
            ) or len(group["rows"]) > 1
        return grouped

    operating_groups = group_rows_by_parent(operating_rows) if view_mode != "summary" else []
    investing_groups = group_rows_by_parent(investing_rows) if view_mode != "summary" else []
    financing_groups = group_rows_by_parent(financing_rows) if view_mode != "summary" else []

    filters = {
        "date_range": date_range,
        "date_from": date_from,
        "date_to": date_to,
        "account_id": account_id,
        "vendor_id": vendor_id,
        "category_id": category_id,
        "kind": kind if kind else "all",
        "view": view_mode,
    }

    query_params = request.GET.copy()
    query_params.pop("view", None)

    return {
        "filters": filters,
        "report_ranges": REPORT_RANGE_OPTIONS,
        "accounts": accounts,
        "vendors": vendors,
        "categories": categories,
        "query_string": query_params.urlencode(),
        "operating_rows": operating_rows,
        "operating_total": operating_total,
        "operating_groups": operating_groups,
        "investing_rows": investing_rows,
        "investing_total": investing_total,
        "investing_groups": investing_groups,
        "financing_rows": financing_rows,
        "financing_total": financing_total,
        "financing_groups": financing_groups,
        "net_change": operating_total + investing_total + financing_total,
        "view_mode": view_mode,
    }


def profit_loss_report(request):
    context = _profit_loss_context(request)
    return render(request, "fincore/reports/profit_loss.html", context)


def balance_sheet_report(request):
    context = _balance_sheet_context(request)
    return render(request, "fincore/reports/balance_sheet.html", context)


def balance_sheet_content(request):
    context = _balance_sheet_context(request)
    return render(request, "fincore/reports/balance_sheet_content.html", context)


def cashflow_report(request):
    context = _cashflow_context(request)
    return render(request, "fincore/reports/cashflow.html", context)


def cashflow_content(request):
    context = _cashflow_context(request)
    return render(request, "fincore/reports/cashflow_content.html", context)


def _build_simple_xlsx(rows, sheet_name="Profit & Loss"):
    import io
    import zipfile
    from xml.sax.saxutils import escape

    def col_letter(idx):
        letter = ""
        while idx > 0:
            idx, rem = divmod(idx - 1, 26)
            letter = chr(65 + rem) + letter
        return letter

    def cell_xml(col_idx, row_idx, value):
        cell_ref = f"{col_letter(col_idx)}{row_idx}"
        if value is None:
            return f'<c r="{cell_ref}"/>'
        if isinstance(value, (int, float)):
            return f'<c r="{cell_ref}"><v>{value}</v></c>'
        text = escape(str(value))
        return (
            f'<c r="{cell_ref}" t="inlineStr">'
            f"<is><t>{text}</t></is></c>"
        )

    sheet_rows = []
    for row_idx, row in enumerate(rows, start=1):
        cells = "".join(cell_xml(col_idx, row_idx, value) for col_idx, value in enumerate(row, start=1))
        sheet_rows.append(f'<row r="{row_idx}">{cells}</row>')

    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheetData>"
        + "".join(sheet_rows)
        + "</sheetData></worksheet>"
    )

    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets>'
        f'<sheet name="{escape(sheet_name)}" sheetId="1" r:id="rId1"/>'
        "</sheets></workbook>"
    )

    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )

    root_rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        "</Relationships>"
    )

    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", root_rels)
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    buffer.seek(0)
    return buffer.read()


def profit_loss_export_xlsx(request):
    context = _profit_loss_context(request)
    columns = context["columns"]
    is_single_period = context["is_single_period"]

    def normalize(value):
        if value is None:
            return 0
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0

    def row_values_from_cells(cells):
        if is_single_period:
            return [normalize(cells[0]["value"] if cells else 0)]
        return [normalize(cell["value"]) for cell in cells]

    def add_group_rows(label_prefix, groups):
        for group in groups:
            rows.append([f"{label_prefix}{group['parent_name']}"] + row_values_from_cells(group["cells"]) + ([] if is_single_period else [normalize(group["total"])]))
            for row in group["rows"]:
                if row["category_id"] == group["parent_category_id"]:
                    continue
                rows.append([f"  - {row['name']}"] + row_values_from_cells(row["cells"]) + ([] if is_single_period else [normalize(row["total"])]))

    income_col_totals = [normalize(v) for v in context["income_column_totals"]]
    cogs_col_totals = [normalize(v) for v in context["cogs_column_totals"]]
    payroll_col_totals = [normalize(v) for v in context["payroll_column_totals"]]
    expense_col_totals = [normalize(v) for v in context["expense_column_totals"]]
    gross_profit_col_totals = [normalize(v) for v in context["gross_profit_column_totals"]]
    net_operating_income_col_totals = [normalize(v) for v in context["net_operating_income_column_totals"]]
    net_income_col_totals = [normalize(v) for v in context["net_income_column_totals"]]

    header = ["Category"]
    if is_single_period:
        header.append("Amount")
    else:
        header.extend([col["label"] for col in columns])
        header.append("Total")

    rows = [header]

    if context["income_groups"]:
        rows.append(["Income"] + ([""] if is_single_period else [""] * (len(columns) + 1)))
        add_group_rows("", context["income_groups"])
        rows.append(["Total Income"] + (income_col_totals if not is_single_period else [normalize(context["income_total_display"])])
                    + ([] if is_single_period else [normalize(context["income_total_display"])]))

    if context["cogs_groups"]:
        rows.append(["COGS (Cost of Goods Sold)"] + ([""] if is_single_period else [""] * (len(columns) + 1)))
        add_group_rows("", context["cogs_groups"])
        rows.append(["Total COGS"] + (cogs_col_totals if not is_single_period else [normalize(context["cogs_total_display"])])
                    + ([] if is_single_period else [normalize(context["cogs_total_display"])]))

    rows.append(["Gross Profit"] + (gross_profit_col_totals if not is_single_period else [normalize(context["gross_profit_display"])])
                + ([] if is_single_period else [normalize(context["gross_profit_display"])]))

    if context["payroll_groups"]:
        rows.append(["Payroll"] + ([""] if is_single_period else [""] * (len(columns) + 1)))
        add_group_rows("", context["payroll_groups"])

    if context["expense_groups"]:
        rows.append(["Expenses"] + ([""] if is_single_period else [""] * (len(columns) + 1)))
        add_group_rows("", context["expense_groups"])
        rows.append(["Total Expenses"] + (expense_col_totals if not is_single_period else [normalize(context["expense_total_display"])])
                    + ([] if is_single_period else [normalize(context["expense_total_display"])]))

    rows.append(["Net Operating Income"] + (net_operating_income_col_totals if not is_single_period else [normalize(context["net_operating_income_display"])])
                + ([] if is_single_period else [normalize(context["net_operating_income_display"])]))
    rows.append(["Net Income"] + (net_income_col_totals if not is_single_period else [normalize(context["net_income_display"])])
                + ([] if is_single_period else [normalize(context["net_income_display"])]))

    content = _build_simple_xlsx(rows)
    filename = "profit-loss.xlsx"
    response = HttpResponse(
        content,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def profit_loss_content(request):
    """
    HTMX endpoint that returns just the P&L table content (for filter updates).
    Reuses the same logic as profit_loss_report but renders a partial template.
    """
    if not getattr(request, "htmx", False):
        query = request.META.get("QUERY_STRING", "")
        target = reverse("fincore:profit_loss_report")
        if query:
            target = f"{target}?{query}"
        return redirect(target)
    context = _profit_loss_context(request)
    return render(request, "fincore/reports/profit_loss_content.html", context)


def transaction_list(request):
    """
    Transaction list page server-rendered shell that loads our HTMX/Alpine UI.
    Data is mocked in the template for now; replace with real query + HTMX soon.
    """
    accounts = list(
        selectable_accounts()
        .order_by("name")
        .values("id", "name", "account_type")
    )
    categories = list(
        Category.objects.filter(is_active=True)
        .exclude(kind="transfer")
        .order_by("kind", "name")
        .values("id", "name", "kind")
    )
    vendors = list(
        Vendor.objects.filter(is_active=True)
        .order_by("name")
        .values("id", "name", "kind")
    )
    try:
        prefill_account_id = int(request.GET.get("import_account") or 0)
    except (TypeError, ValueError):
        prefill_account_id = 0
    account_ids = {acct["id"] for acct in accounts}
    if prefill_account_id not in account_ids:
        prefill_account_id = 0
    default_account_id = prefill_account_id or (accounts[0]["id"] if accounts else None)
    return render(
        request,
        "fincore/transactions/index.html",
        {
            "accounts": accounts,
            "categories": categories,
            "vendors": vendors,
            "prefill_account_id": prefill_account_id or None,
            "default_account_id": default_account_id,
            "table_query": request.GET.urlencode(),
        },
    )


def transaction_table(request):
    """HTMX partial for paginated transactions with simple search."""
    if not getattr(request, "htmx", False):
        query = request.META.get("QUERY_STRING", "")
        target = reverse("fincore:transaction_list")
        if query:
            target = f"{target}?{query}"
        return redirect(target)

    accounts = list(
        selectable_accounts()
        .order_by("name")
        .values("id", "name", "account_type")
    )
    account_ids = {acct["id"] for acct in accounts}
    try:
        selected_account_id = int(request.GET.get("account_id") or 0)
    except (TypeError, ValueError):
        selected_account_id = 0
    if selected_account_id not in account_ids:
        selected_account_id = accounts[0]["id"] if accounts else None

    qs = Transaction.objects.select_related(
        "account", "category", "transfer_group", "vendor"
    ).prefetch_related("invoice_payments__invoice")
    base_qs = Transaction.objects.all()
    search = request.GET.get("q", "").strip()
    date_range = request.GET.get("date_range", "all")
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    selected_payees = [value for value in request.GET.getlist("payee") if value]
    selected_descriptions = [value for value in request.GET.getlist("description") if value]
    selected_kinds = [value for value in request.GET.getlist("kind") if value]
    selected_category_ids = []
    for value in request.GET.getlist("category"):
        try:
            selected_category_ids.append(int(value))
        except (TypeError, ValueError):
            continue
    amount_type = request.GET.get("amount_type", "all").strip()
    amount_min = request.GET.get("amount_min", "").strip()
    amount_max = request.GET.get("amount_max", "").strip()
    sort_field = request.GET.get("sort", "").strip()
    sort_dir = request.GET.get("dir", "asc").strip()

    def parse_date(raw_value):
        raw_value = (raw_value or "").strip()
        if not raw_value:
            return None
        try:
            return datetime.strptime(raw_value, "%Y-%m-%d").date()
        except ValueError:
            return None

    def parse_decimal(raw_value):
        raw_value = (raw_value or "").strip()
        if raw_value == "":
            return None
        try:
            return Decimal(raw_value)
        except (InvalidOperation, ValueError):
            return None

    def month_bounds(year_value, month_value):
        last_day = calendar.monthrange(year_value, month_value)[1]
        return date(year_value, month_value, 1), date(year_value, month_value, last_day)

    def quarter_bounds(year_value, quarter_key):
        mapping = {"q1": (1, 3), "q2": (4, 6), "q3": (7, 9), "q4": (10, 12)}
        start_month, end_month = mapping[quarter_key]
        _, end_day = calendar.monthrange(year_value, end_month)
        return date(year_value, start_month, 1), date(year_value, end_month, end_day)

    if selected_account_id:
        qs = qs.filter(account_id=selected_account_id)
    else:
        qs = qs.none()

    if date_range and date_range != "all":
        today = date.today()
        start_date = None
        end_date = None
        if date_range == "this_month":
            start_date, end_date = month_bounds(today.year, today.month)
        elif date_range == "last_month":
            last_month = today.month - 1 or 12
            year_value = today.year - 1 if today.month == 1 else today.year
            start_date, end_date = month_bounds(year_value, last_month)
        elif date_range in {"q1", "q2", "q3", "q4"}:
            start_date, end_date = quarter_bounds(today.year, date_range)
        elif date_range == "this_year":
            start_date = date(today.year, 1, 1)
            end_date = date(today.year, 12, 31)
        elif date_range == "last_year":
            start_date = date(today.year - 1, 1, 1)
            end_date = date(today.year - 1, 12, 31)
        elif date_range == "custom":
            start_date = parse_date(date_from)
            end_date = parse_date(date_to)

        if start_date:
            qs = qs.filter(date__gte=start_date)
        if end_date:
            qs = qs.filter(date__lte=end_date)

    if selected_payees:
        qs = qs.filter(payee__in=selected_payees)

    if selected_descriptions:
        qs = qs.filter(description__in=selected_descriptions)

    if selected_kinds:
        qs = qs.filter(kind__in=selected_kinds)

    if selected_category_ids:
        qs = qs.filter(category_id__in=selected_category_ids)

    amount_min_val = parse_decimal(amount_min)
    amount_max_val = parse_decimal(amount_max)
    amount_type = amount_type if amount_type in {"all", "expense", "deposit"} else "all"

    def apply_amount_filters(queryset):
        if amount_type == "expense":
            queryset = queryset.filter(amount__lt=0)
            if amount_min_val is not None:
                queryset = queryset.filter(amount__lte=-amount_min_val)
            if amount_max_val is not None:
                queryset = queryset.filter(amount__gte=-amount_max_val)
        elif amount_type == "deposit":
            queryset = queryset.filter(amount__gt=0)
            if amount_min_val is not None:
                queryset = queryset.filter(amount__gte=amount_min_val)
            if amount_max_val is not None:
                queryset = queryset.filter(amount__lte=amount_max_val)
        return queryset

    if search:
        search_terms = [term for term in search.split() if term]
        if search_terms:
            for term in search_terms:
                qs = qs.filter(
                    Q(description__icontains=term)
                    | Q(payee__icontains=term)
                    | Q(account__name__icontains=term)
                )

    sort_map = {
        "date": "date",
        "payee": "payee",
        "description": "description",
        "kind": "kind",
        "amount": "amount",
    }
    if sort_field in sort_map:
        ordering = sort_map[sort_field]
        if sort_dir == "desc":
            ordering = f"-{ordering}"
        qs = qs.order_by(ordering, "-id")
    else:
        qs = qs.order_by("-date", "-id")
    try:
        page_size = int(request.GET.get("page_size", 25))
    except (TypeError, ValueError):
        page_size = 25
    qs = apply_amount_filters(qs)
    paginator = Paginator(qs, page_size)
    page_number = request.GET.get("page") or 1
    page_obj = paginator.get_page(page_number)
    
    # Calculate available options from filtered queryset (qs), not all transactions
    # Exclude currently applied filters from the options to show what's available
    options_qs = Transaction.objects.all()
    if selected_account_id:
        options_qs = options_qs.filter(account_id=selected_account_id)
    else:
        options_qs = options_qs.none()
    
    # Apply all filters EXCEPT the one we're calculating options for
    if date_range and date_range != "all":
        today = date.today()
        start_date = None
        end_date = None
        if date_range == "this_month":
            start_date, end_date = month_bounds(today.year, today.month)
        elif date_range == "last_month":
            last_month = today.month - 1 or 12
            year_value = today.year - 1 if today.month == 1 else today.year
            start_date, end_date = month_bounds(year_value, last_month)
        elif date_range in {"q1", "q2", "q3", "q4"}:
            start_date, end_date = quarter_bounds(today.year, date_range)
        elif date_range == "this_year":
            start_date = date(today.year, 1, 1)
            end_date = date(today.year, 12, 31)
        elif date_range == "last_year":
            start_date = date(today.year - 1, 1, 1)
            end_date = date(today.year - 1, 12, 31)
        elif date_range == "custom":
            start_date = parse_date(date_from)
            end_date = parse_date(date_to)
        if start_date:
            options_qs = options_qs.filter(date__gte=start_date)
        if end_date:
            options_qs = options_qs.filter(date__lte=end_date)
    
    if search:
        search_terms = [term for term in search.split() if term]
        if search_terms:
            for term in search_terms:
                options_qs = options_qs.filter(
                    Q(description__icontains=term)
                    | Q(payee__icontains=term)
                    | Q(account__name__icontains=term)
                )
    options_qs = apply_amount_filters(options_qs)
    
    # Payee options - exclude payee filter to show available payees
    payee_qs = options_qs
    if selected_descriptions:
        payee_qs = payee_qs.filter(description__in=selected_descriptions)
    if selected_kinds:
        payee_qs = payee_qs.filter(kind__in=selected_kinds)
    if selected_category_ids:
        payee_qs = payee_qs.filter(category_id__in=selected_category_ids)
    payee_options = list(
        payee_qs.exclude(payee="").values_list("payee", flat=True).distinct().order_by("payee")
    )
    
    # Description options - exclude description filter to show available descriptions
    desc_qs = options_qs
    if selected_payees:
        desc_qs = desc_qs.filter(payee__in=selected_payees)
    if selected_kinds:
        desc_qs = desc_qs.filter(kind__in=selected_kinds)
    if selected_category_ids:
        desc_qs = desc_qs.filter(category_id__in=selected_category_ids)
    description_options = list(
        desc_qs.exclude(description="").values_list("description", flat=True).distinct().order_by("description")
    )
    
    # Kind options - exclude kind filter to show available kinds
    kind_qs = options_qs
    if selected_payees:
        kind_qs = kind_qs.filter(payee__in=selected_payees)
    if selected_descriptions:
        kind_qs = kind_qs.filter(description__in=selected_descriptions)
    if selected_category_ids:
        kind_qs = kind_qs.filter(category_id__in=selected_category_ids)
    available_kinds = list(kind_qs.values_list("kind", flat=True).distinct())
    kind_options = [choice[0] for choice in Transaction.KIND_CHOICES if choice[0] in available_kinds]

    category_qs = options_qs.exclude(category_id__isnull=True).exclude(category__kind="transfer")
    if selected_payees:
        category_qs = category_qs.filter(payee__in=selected_payees)
    if selected_descriptions:
        category_qs = category_qs.filter(description__in=selected_descriptions)
    if selected_kinds:
        category_qs = category_qs.filter(kind__in=selected_kinds)
    category_options = list(
        category_qs.values("category_id", "category__name")
        .distinct()
        .order_by("category__name")
    )

    for value in selected_payees:
        if value not in payee_options:
            payee_options.append(value)
    for value in selected_descriptions:
        if value not in description_options:
            description_options.append(value)
    for value in selected_kinds:
        if value not in kind_options:
            kind_options.append(value)
    if selected_category_ids:
        selected_categories = list(
            Category.objects.filter(id__in=selected_category_ids)
            .exclude(kind="transfer")
            .values("id", "name")
        )
        existing_ids = {item["category_id"] for item in category_options}
        for category in selected_categories:
            if category["id"] not in existing_ids:
                category_options.append(
                    {"category_id": category["id"], "category__name": category["name"]}
                )

    date_labels = {
        "this_month": "This month",
        "last_month": "Last month",
        "q1": "1st quarter",
        "q2": "2nd quarter",
        "q3": "3rd quarter",
        "q4": "4th quarter",
        "this_year": "This year",
        "last_year": "Last year",
        "custom": "Custom",
    }
    summary_parts = []
    if date_range and date_range != "all":
        if date_range == "custom":
            summary_parts.append(f"Date: {date_from or ''}→{date_to or ''}".strip())
        else:
            summary_parts.append(f"Date: {date_labels.get(date_range, date_range)}")
    if selected_payees:
        summary_parts.append(f"Payee: {len(selected_payees)}")
    if selected_descriptions:
        summary_parts.append(f"Desc: {len(selected_descriptions)}")
    if selected_kinds:
        summary_parts.append(f"Kind: {len(selected_kinds)}")
    if selected_category_ids:
        summary_parts.append(f"Category: {len(selected_category_ids)}")
    if amount_type != "all" or amount_min_val is not None or amount_max_val is not None:
        label = "Amount"
        if amount_type == "expense":
            label = "Expense"
        elif amount_type == "deposit":
            label = "Deposit"
        if amount_min_val is not None or amount_max_val is not None:
            summary_parts.append(f"{label}: {amount_min or ''}-{amount_max or ''}")
        else:
            summary_parts.append(label)
    filter_summary = ", ".join([part for part in summary_parts if part]) or "No filters"

    query_params = request.GET.copy()
    query_params.pop("page", None)

    context = {
        "page_obj": page_obj,
        "paginator": paginator,
        "page_size": page_size,
        "search": search,
        "page_sizes": [25, 50, 100],
        "accounts": accounts,
        "selected_account_id": selected_account_id,
        "filter_payload": {
            "account_id": selected_account_id,
            "date_range": date_range or "all",
            "date_from": date_from,
            "date_to": date_to,
            "payee": selected_payees,
            "description": selected_descriptions,
            "kind": selected_kinds,
            "category": selected_category_ids,
            "amount_type": amount_type,
            "amount_min": amount_min,
            "amount_max": amount_max,
            "sort": sort_field,
            "dir": sort_dir,
            "page": page_obj.number,
            "page_size": page_size,
            "search": search,
        },
        "payee_options": payee_options,
        "description_options": description_options,
        "kind_options": kind_options,
        "category_options": category_options,
        "filter_summary": filter_summary,
        "filter_query": query_params.urlencode(),
    }
    return render(request, "fincore/transactions/table_partial.html", context)


def transaction_bulk_action(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    action = (request.POST.get("action") or "").strip()
    raw_ids = (request.POST.get("transaction_ids") or "").strip()
    if not raw_ids:
        return render(
            request,
            "fincore/accounts/form_errors.html",
            {"form_errors": ["Select at least one transaction."]},
            status=200,
        )
    try:
        transaction_ids = [int(val) for val in raw_ids.split(",") if val.strip()]
    except ValueError:
        return HttpResponseBadRequest("Invalid transaction selection")

    if action not in {"category", "payee", "delete"}:
        return render(
            request,
            "fincore/accounts/form_errors.html",
            {"form_errors": ["Select a supported bulk action."]},
            status=200,
        )

    if action == "delete":
        # Only allow deleting manually created transactions
        transactions = Transaction.objects.filter(id__in=transaction_ids)
        blocked = transactions.filter(
            Q(is_imported=True) | Q(is_locked=True) | Q(transfer_group__isnull=False)
        )
        if blocked.exists():
            return render(
                request,
                "fincore/accounts/form_errors.html",
                {"form_errors": ["Cannot delete imported, locked, or transfer transactions."]},
                status=200,
            )
        transactions.delete()
    elif action == "category":
        try:
            category_id = int(request.POST.get("category_id") or 0)
        except (TypeError, ValueError):
            return HttpResponseBadRequest("Invalid category")

        category = Category.objects.filter(is_active=True, pk=category_id).first()
        if not category or category.kind == "transfer":
            return render(
                request,
                "fincore/accounts/form_errors.html",
                {"form_errors": ["Select a valid active category."]},
                status=200,
            )

        Transaction.objects.filter(id__in=transaction_ids).update(
            category=category, kind=category.kind
        )
    elif action == "payee":
        try:
            vendor_id = int(request.POST.get("vendor_id") or 0)
        except (TypeError, ValueError):
            return HttpResponseBadRequest("Invalid vendor")

        vendor = Vendor.objects.filter(is_active=True, pk=vendor_id).first()
        if not vendor:
            return render(
                request,
                "fincore/accounts/form_errors.html",
                {"form_errors": ["Select a valid active vendor."]},
                status=200,
            )

        Transaction.objects.filter(id__in=transaction_ids).update(vendor=vendor)

    resp = HttpResponse(status=204)
    resp["HX-Trigger"] = '{"transactions:refresh": true, "transactions:bulkClose": true}'
    return resp


def transaction_transfer_matches(request):
    try:
        txn_id = int(request.GET.get("transaction_id") or 0)
    except (TypeError, ValueError):
        return HttpResponseBadRequest("Invalid transaction")

    txn = get_object_or_404(Transaction, pk=txn_id)
    if txn.transfer_group_id or txn.is_locked:
        return render(
            request,
            "fincore/transactions/transfer_match_list.html",
            {"transaction": txn, "matches": [], "errors": ["Transaction cannot be matched."]},
        )

    start_date = txn.date - timedelta(days=30)
    end_date = txn.date + timedelta(days=30)

    matches = (
        Transaction.objects.select_related("account")
        .filter(
            transfer_group__isnull=True,
            is_locked=False,
            date__range=(start_date, end_date),
            amount=-txn.amount,
        )
        .exclude(account_id=txn.account_id)
        .exclude(pk=txn.pk)
        .order_by("date", "id")
    )

    debug_candidates = []
    if not matches:
        candidates = (
            Transaction.objects.select_related("account")
            .filter(date__range=(start_date, end_date))
            .exclude(account_id=txn.account_id)
            .exclude(pk=txn.pk)
            .annotate(abs_amount=Abs("amount"))
            .filter(abs_amount=abs(txn.amount))
            .order_by("date", "id")
        )
        for candidate in candidates[:10]:
            reasons = []
            if candidate.transfer_group_id:
                reasons.append("already paired")
            if candidate.is_locked:
                reasons.append("locked")
            if candidate.amount != -txn.amount:
                reasons.append("amount sign mismatch")
            debug_candidates.append(
                {
                    "transaction": candidate,
                    "reasons": reasons or ["unknown"],
                }
            )

    return render(
        request,
        "fincore/transactions/transfer_match_list.html",
        {
            "transaction": txn,
            "matches": matches,
            "errors": [],
            "debug_candidates": debug_candidates,
        },
    )


def transaction_transfer_pair(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    try:
        txn_id = int(request.POST.get("transaction_id") or 0)
        match_id = int(request.POST.get("match_id") or 0)
    except (TypeError, ValueError):
        return HttpResponseBadRequest("Invalid transaction")

    if txn_id == match_id:
        return HttpResponseBadRequest("Invalid match")

    with db_transaction.atomic():
        txn = get_object_or_404(Transaction.objects.select_for_update(), pk=txn_id)
        match = get_object_or_404(Transaction.objects.select_for_update(), pk=match_id)

        errors = []
        if txn.transfer_group_id or match.transfer_group_id:
            errors.append("One of the transactions is already paired.")
        if txn.is_locked or match.is_locked:
            errors.append("One of the transactions is locked.")
        if txn.account_id == match.account_id:
            errors.append("Transfers must be between different accounts.")
        if txn.amount + match.amount != 0:
            errors.append("Transfer amounts must sum to zero.")
        if abs(txn.amount) != abs(match.amount):
            errors.append("Transfer amounts must be equal and opposite.")
        if abs((txn.date - match.date).days) > 30:
            errors.append("Transfer dates must be within 30 days.")
        if errors:
            return render(
                request,
                "fincore/accounts/form_errors.html",
                {"form_errors": errors},
                status=200,
            )

        group = TransferGroup.objects.create(reference=str(uuid4()))
        for item in (txn, match):
            item.kind = "transfer"
            item.category = None
            item.transfer_group = group
            item.is_locked = True
            item.save(update_fields=["kind", "category", "transfer_group", "is_locked"])

    resp = HttpResponse(status=204)
    resp["HX-Trigger"] = '{"transactions:refresh": true, "transactions:transferClose": true, "transactions:editClose": true}'
    return resp


def transfer_list(request):
    transfer_category = Category.objects.filter(kind="transfer").order_by("id").first()
    if transfer_category:
        return redirect(reverse("fincore:category_report", args=[transfer_category.id]))
    return _render_transfer_list(request)


def transfer_unpair(request, group_id):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    group = get_object_or_404(TransferGroup.objects.prefetch_related("transactions"), pk=group_id)
    txns = list(group.transactions.all())
    if not txns:
        return redirect(reverse("fincore:transfer_list"))

    with db_transaction.atomic():
        Transaction.objects.filter(transfer_group=group).update(
            transfer_group=None,
            category=None,
            is_locked=False,
        )
        for txn in txns:
            new_kind = "income" if txn.amount > 0 else "expense"
            Transaction.objects.filter(pk=txn.pk).update(kind=new_kind)
        group.delete()

    return redirect(reverse("fincore:transfer_list"))


def transaction_delete(request, pk):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    txn = get_object_or_404(Transaction, pk=pk)
    errors = []
    if txn.is_imported:
        errors.append("Imported transactions cannot be deleted.")
    if txn.transfer_group_id:
        errors.append("Transfers must be corrected via reversal.")
    if txn.is_locked:
        errors.append("Locked transactions cannot be deleted.")
    if errors:
        return render(
            request,
            "fincore/accounts/form_errors.html",
            {"form_errors": errors},
            status=200,
        )

    txn.delete()
    resp = HttpResponse(status=204)
    resp["HX-Trigger"] = '{"transactions:editClose": true}'
    return resp


def transaction_create(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    errors = []
    raw_date = (request.POST.get("date") or "").strip()
    raw_amount = (request.POST.get("amount") or "").strip()
    account_id = (request.POST.get("account_id") or "").strip()
    category_id = (request.POST.get("category_id") or "").strip()
    vendor_id = (request.POST.get("vendor_id") or "").strip()
    description = (request.POST.get("description") or "").strip()

    if not raw_date:
        errors.append("Date is required.")
    if not raw_amount:
        errors.append("Amount is required.")
    if not account_id.isdigit():
        errors.append("Account is required.")
    if not category_id.isdigit():
        errors.append("Category is required.")

    account = None
    category = None
    vendor = None
    parsed_date = None
    amount = None

    if account_id.isdigit():
        try:
            account = Account.objects.get(pk=int(account_id), is_active=True)
        except Account.DoesNotExist:
            errors.append("Invalid account selected.")

    if category_id.isdigit():
        try:
            category = Category.objects.get(pk=int(category_id))
        except Category.DoesNotExist:
            errors.append("Invalid category selected.")

    if vendor_id:
        try:
            vendor = Vendor.objects.get(pk=int(vendor_id), is_active=True)
        except (Vendor.DoesNotExist, ValueError, TypeError):
            errors.append("Invalid vendor selected.")

    if raw_date:
        try:
            parsed_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except ValueError:
            errors.append("Invalid date.")

    if raw_amount:
        try:
            amount = Decimal(str(raw_amount))
        except (InvalidOperation, ValueError, TypeError):
            errors.append("Invalid amount.")

    if errors:
        return render(
            request,
            "fincore/accounts/form_errors.html",
            {"form_errors": errors},
            status=200,
        )

    txn = Transaction(
        date=parsed_date,
        account=account,
        amount=amount,
        description=description,
        vendor=vendor,
        category=category,
        kind=category.kind,
        source="manual",
        is_imported=False,
    )
    txn.save()

    if getattr(request, "htmx", False):
        resp = HttpResponse(status=204)
        resp["HX-Trigger"] = '{"transactions:refresh": true, "transactions:newClose": true}'
        return resp
    return redirect("fincore:transaction_list")


def transaction_update(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    try:
        txn_id = int(request.POST.get("transaction_id") or 0)
    except (TypeError, ValueError):
        return HttpResponseBadRequest("Invalid transaction")

    txn = get_object_or_404(Transaction, pk=txn_id)

    vendor_id = (request.POST.get("vendor_id") or "").strip()
    category_id = request.POST.get("category_id") or None
    category = None
    vendor = None
    if vendor_id:
        try:
            vendor = Vendor.objects.get(pk=int(vendor_id), is_active=True)
        except (Vendor.DoesNotExist, ValueError, TypeError):
            return render(
                request,
                "fincore/accounts/form_errors.html",
                {"form_errors": ["Invalid vendor selected."]},
                status=200,
            )
    if category_id:
        try:
            category = Category.objects.get(pk=int(category_id))
        except (Category.DoesNotExist, ValueError, TypeError):
            return render(
                request,
                "fincore/accounts/form_errors.html",
                {"form_errors": ["Invalid category selected."]},
                status=200,
            )

    if txn.transfer_group_id:
        return render(
            request,
            "fincore/accounts/form_errors.html",
            {"form_errors": ["Transfers must be corrected via reversal."]},
            status=200,
        )
    if txn.is_locked:
        return render(
            request,
            "fincore/accounts/form_errors.html",
            {"form_errors": ["Locked transactions cannot be edited."]},
            status=200,
        )

    if txn.is_imported:
        txn.vendor = vendor
        txn.category = category
        txn.kind = category.kind if category else txn.kind
        txn.save()
    else:
        raw_date = request.POST.get("date")
        raw_amount = request.POST.get("amount")
        description = (request.POST.get("description") or "").strip()

        if not raw_date:
            return render(
                request,
                "fincore/accounts/form_errors.html",
                {"form_errors": ["Date is required."]},
                status=200,
            )
        try:
            parsed_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except ValueError:
            return render(
                request,
                "fincore/accounts/form_errors.html",
                {"form_errors": ["Invalid date."]},
                status=200,
            )
        try:
            amount = Decimal(str(raw_amount))
        except (InvalidOperation, ValueError, TypeError):
            return render(
                request,
                "fincore/accounts/form_errors.html",
                {"form_errors": ["Invalid amount."]},
                status=200,
            )

        txn.date = parsed_date
        txn.amount = amount
        txn.description = description
        txn.vendor = vendor
        txn.category = category
        txn.kind = category.kind if category else txn.kind
        txn.save()

    resp = HttpResponse(status=204)
    resp["HX-Trigger"] = '{"transactions:refresh": true, "transactions:editClose": true}'
    return resp
