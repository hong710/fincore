from datetime import timedelta
from decimal import Decimal, InvalidOperation
from random import choices
from string import ascii_uppercase, digits

from django.db import transaction as db_transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import now
from django.utils.dateparse import parse_date

from django.core.paginator import Paginator

from fincore.models import Account, Bill, BillItem, BillPayment, Category, Transaction, Vendor
from .transaction_views import REPORT_RANGE_OPTIONS, _resolve_report_range


def _generate_bill_number():
    suffix = "".join(choices(ascii_uppercase + digits, k=6))
    return f"BILL{now().strftime('%Y%m%d')}-{suffix}"


def bills_list(request):
    qs = Bill.objects.select_related("vendor", "account").all()

    search = (request.GET.get("q") or "").strip()
    date_range = (request.GET.get("date_range") or "this_year").strip()
    date_from = (request.GET.get("date_from") or "").strip()
    date_to = (request.GET.get("date_to") or "").strip()
    account_id = (request.GET.get("account_id") or "").strip()
    vendor_id = (request.GET.get("vendor_id") or "").strip()
    status = (request.GET.get("status") or "").strip()
    min_total = (request.GET.get("min_total") or "").strip()
    max_total = (request.GET.get("max_total") or "").strip()

    date_range, start_date, end_date = _resolve_report_range(
        date_range, date_from, date_to
    )

    if search:
        qs = qs.filter(number__icontains=search)
    accounts = list(Account.objects.filter(is_active=True).order_by("name"))
    vendors = list(Vendor.objects.filter(is_active=True, kind="payee").order_by("name"))
    account_ids = {acct.id for acct in accounts}
    vendor_ids = {vend.id for vend in vendors}

    try:
        account_id_int = int(account_id) if account_id.isdigit() else None
    except (TypeError, ValueError):
        account_id_int = None
    if account_id_int not in account_ids:
        account_id_int = None

    try:
        vendor_id_int = int(vendor_id) if vendor_id.isdigit() else None
    except (TypeError, ValueError):
        vendor_id_int = None
    if vendor_id_int not in vendor_ids:
        vendor_id_int = None

    if account_id_int:
        qs = qs.filter(account_id=account_id_int)
    if vendor_id_int:
        qs = qs.filter(vendor_id=vendor_id_int)
    if status:
        qs = qs.filter(status=status)

    try:
        if min_total:
            qs = qs.filter(total__gte=Decimal(min_total))
        if max_total:
            qs = qs.filter(total__lte=Decimal(max_total))
    except InvalidOperation:
        pass

    qs = qs.order_by("-date", "-id")

    page_size = 25
    try:
        page_number = int(request.GET.get("page") or 1)
    except (TypeError, ValueError):
        page_number = 1
    paginator = Paginator(qs, page_size)
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "fincore/bills/transactions/index.html",
        {
            "page_obj": page_obj,
            "search": search,
            "date_range": date_range,
            "date_from": date_from,
            "date_to": date_to,
            "account_id": account_id_int,
            "vendor_id": vendor_id_int,
            "status": status,
            "min_total": min_total,
            "max_total": max_total,
            "report_ranges": REPORT_RANGE_OPTIONS,
            "accounts": accounts,
            "vendors": vendors,
            "status_options": ["draft", "received", "partially_paid", "paid", "void"],
        },
    )


def bill_create(request):
    accounts = Account.objects.filter(is_active=True).order_by("name")
    vendors = Vendor.objects.filter(is_active=True, kind="payee").order_by("name")
    categories = Category.objects.filter(is_active=True, kind__in=["expense", "cogs"]).order_by("name")
    category_ids = {str(cat.id) for cat in categories}
    item_rows = [{"category_id": "", "description": "", "amount": "", "total": ""}]
    errors = []
    item_count = 1

    if request.method == "POST":
        vendor_id = (request.POST.get("vendor_id") or "").strip()
        account_id = (request.POST.get("account_id") or "").strip()
        bill_date_raw = (request.POST.get("date") or "").strip()
        notes = (request.POST.get("notes") or "").strip()
        item_count_raw = (request.POST.get("item_count") or "1").strip()

        if not vendor_id.isdigit():
            errors.append("Vendor is required.")
        if not account_id.isdigit():
            errors.append("Account is required.")
        bill_date = parse_date(bill_date_raw) if bill_date_raw else None
        if not bill_date:
            errors.append("Bill date is required.")

        try:
            item_count = int(item_count_raw)
        except (TypeError, ValueError):
            item_count = 1
        item_count = max(1, min(item_count, 50))
        item_rows = [
            {"category_id": "", "description": "", "amount": "", "total": ""}
            for _ in range(item_count)
        ]

        items = []
        subtotal = Decimal("0.00")
        for idx in range(1, item_count + 1):
            category_field = (request.POST.get(f"item_category_{idx}") or "").strip()
            description = (request.POST.get(f"item_description_{idx}") or "").strip()
            amount_raw = (request.POST.get(f"item_amount_{idx}") or "").strip()
            item_rows[idx - 1] = {
                "category_id": category_field,
                "description": description,
                "amount": amount_raw,
                "total": "",
            }

            if not any([category_field, description, amount_raw]):
                continue
            if not amount_raw:
                errors.append("Line item amount is required.")
                continue
            if not category_field.isdigit() or category_field not in category_ids:
                errors.append("Line item category is required.")
                continue

            try:
                amount = Decimal(amount_raw)
            except InvalidOperation:
                errors.append("Line item amount is invalid.")
                continue

            total = amount.quantize(Decimal("0.01"))
            item_rows[idx - 1]["total"] = str(total)
            subtotal += amount
            items.append(
                {
                    "category_id": int(category_field),
                    "description": description,
                    "amount": amount,
                    "total": total,
                }
            )

        if not items:
            errors.append("At least one line item is required.")

        if not errors:
            vendor = get_object_or_404(Vendor, pk=int(vendor_id), kind="payee")
            account = get_object_or_404(Account, pk=int(account_id))
            with db_transaction.atomic():
                bill_number = _generate_bill_number()
                while Bill.objects.filter(number=bill_number).exists():
                    bill_number = _generate_bill_number()
                bill = Bill.objects.create(
                    number=bill_number,
                    vendor=vendor,
                    account=account,
                    date=bill_date,
                    subtotal=subtotal,
                    total=subtotal,
                    notes=notes,
                    status="draft",
                )
                for item in items:
                    BillItem.objects.create(
                        bill=bill,
                        category_id=item["category_id"],
                        description=item["description"],
                        amount=item["amount"],
                        total=item["total"],
                    )
            return redirect("fincore:bills_list")

    return render(
        request,
        "fincore/bills/transactions/new.html",
        {
            "accounts": accounts,
            "vendors": vendors,
            "categories": categories,
            "item_rows": item_rows,
            "form_errors": errors,
            "item_count": item_count,
        },
    )


def bill_edit(request, bill_id):
    bill = get_object_or_404(Bill.objects.select_related("vendor", "account"), pk=bill_id)
    accounts = Account.objects.filter(is_active=True).order_by("name")
    vendors = Vendor.objects.filter(is_active=True, kind="payee").order_by("name")
    categories = Category.objects.filter(is_active=True, kind__in=["expense", "cogs"]).order_by("name")
    category_ids = {str(cat.id) for cat in categories}
    errors = []

    item_rows = [
        {
            "category_id": str(item.category_id),
            "description": item.description,
            "amount": str(item.amount),
            "total": str(item.total),
        }
        for item in bill.items.all()
    ]
    if not item_rows:
        item_rows = [
            {"category_id": "", "description": "", "amount": "", "total": ""}
        ]
    item_count = len(item_rows)

    if request.method == "POST":
        vendor_id = (request.POST.get("vendor_id") or "").strip()
        account_id = (request.POST.get("account_id") or "").strip()
        bill_date_raw = (request.POST.get("date") or "").strip()
        notes = (request.POST.get("notes") or "").strip()
        item_count_raw = (request.POST.get("item_count") or str(item_count)).strip()

        if not vendor_id.isdigit():
            errors.append("Vendor is required.")
        if not account_id.isdigit():
            errors.append("Account is required.")
        bill_date = parse_date(bill_date_raw) if bill_date_raw else None
        if not bill_date:
            errors.append("Bill date is required.")

        try:
            item_count = int(item_count_raw)
        except (TypeError, ValueError):
            item_count = 1
        item_count = max(1, min(item_count, 50))
        item_rows = [
            {"category_id": "", "description": "", "amount": "", "total": ""}
            for _ in range(item_count)
        ]

        items = []
        subtotal = Decimal("0.00")
        for idx in range(1, item_count + 1):
            category_field = (request.POST.get(f"item_category_{idx}") or "").strip()
            description = (request.POST.get(f"item_description_{idx}") or "").strip()
            amount_raw = (request.POST.get(f"item_amount_{idx}") or "").strip()
            item_rows[idx - 1] = {
                "category_id": category_field,
                "description": description,
                "amount": amount_raw,
                "total": "",
            }

            if not any([category_field, description, amount_raw]):
                continue
            if not amount_raw:
                errors.append("Line item amount is required.")
                continue
            if not category_field.isdigit() or category_field not in category_ids:
                errors.append("Line item category is required.")
                continue

            try:
                amount = Decimal(amount_raw)
            except InvalidOperation:
                errors.append("Line item amount is invalid.")
                continue

            total = amount.quantize(Decimal("0.01"))
            item_rows[idx - 1]["total"] = str(total)
            subtotal += amount
            items.append(
                {
                    "category_id": int(category_field),
                    "description": description,
                    "amount": amount,
                    "total": total,
                }
            )

        if not items:
            errors.append("At least one line item is required.")

        if not errors:
            vendor = get_object_or_404(Vendor, pk=int(vendor_id), kind="payee")
            account = get_object_or_404(Account, pk=int(account_id))
            with db_transaction.atomic():
                bill.vendor = vendor
                bill.account = account
                bill.date = bill_date
                bill.subtotal = subtotal
                bill.total = subtotal
                bill.notes = notes
                bill.save()
                bill.items.all().delete()
                for item in items:
                    BillItem.objects.create(
                        bill=bill,
                        category_id=item["category_id"],
                        description=item["description"],
                        amount=item["amount"],
                        total=item["total"],
                    )
            return redirect("fincore:bills_list")

    return render(
        request,
        "fincore/bills/transactions/edit.html",
        {
            "bill": bill,
            "accounts": accounts,
            "vendors": vendors,
            "categories": categories,
            "item_rows": item_rows,
            "form_errors": errors,
            "item_count": item_count,
        },
    )


def _build_bill_match_context(bill):
    match_start = bill.date - timedelta(days=30)
    match_end = bill.date + timedelta(days=30)
    remaining = bill.remaining_balance

    base_qs = (
        Transaction.objects.select_related("account", "vendor")
        .filter(date__gte=match_start, date__lte=match_end)
        .filter(account=bill.account)
        .filter(amount__lt=0)
        .exclude(bill_payments__isnull=False)
    )

    best_matches = []
    if remaining > 0:
        best_matches = list(
            base_qs.filter(amount__lte=-remaining).order_by("-date", "-id")[:10]
        )

    best_match_ids = {txn.id for txn in best_matches}
    other_transactions = list(
        base_qs.exclude(id__in=best_match_ids).order_by("-date", "-id")[:50]
    )

    for txn in best_matches:
        txn.abs_amount = abs(txn.amount)
    for txn in other_transactions:
        txn.abs_amount = abs(txn.amount)

    return {
        "bill": bill,
        "remaining_balance": remaining,
        "best_matches": best_matches,
        "other_transactions": other_transactions,
    }


def bill_matches(request):
    bill_id = request.GET.get("bill_id")
    if not bill_id or not str(bill_id).isdigit():
        return HttpResponseBadRequest("Invalid bill")
    bill = get_object_or_404(Bill, pk=int(bill_id))
    return render(
        request,
        "fincore/bills/transactions/match_list.html",
        _build_bill_match_context(bill),
    )


def bill_match_apply(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    bill_id = (request.POST.get("bill_id") or "").strip()
    if not bill_id.isdigit():
        return HttpResponseBadRequest("Invalid bill")

    bill = get_object_or_404(Bill, pk=int(bill_id))

    selections = []
    for key, value in request.POST.items():
        if not key.startswith("match_txn_"):
            continue
        txn_id = key.split("match_txn_")[-1]
        if not txn_id.isdigit():
            continue
        selections.append((int(txn_id), value))

    errors = []
    if not selections:
        errors.append("Select at least one transaction to match.")

    total_matched = Decimal("0.00")
    matches = []
    for txn_id, amount_raw in selections:
        try:
            amount = Decimal(amount_raw or "0")
        except InvalidOperation:
            errors.append("Invalid matched amount.")
            continue
        if amount <= 0:
            errors.append("Matched amount must be greater than zero.")
            continue
        matches.append((txn_id, amount))
        total_matched += amount

    remaining = bill.remaining_balance
    if total_matched > remaining:
        errors.append(
            f"Total matched {total_matched} exceeds bill remaining {remaining}."
        )

    if errors:
        return render(
            request,
            "fincore/bills/transactions/match_list.html",
            {**_build_bill_match_context(bill), "form_errors": errors},
        )

    first_item = bill.items.select_related("category").first()
    bill_category = first_item.category if first_item else None

    with db_transaction.atomic():
        for txn_id, amount in matches:
            txn = get_object_or_404(Transaction, pk=txn_id)
            if txn.account_id != bill.account_id:
                return HttpResponseBadRequest("Account mismatch")
            if txn.amount >= 0:
                return HttpResponseBadRequest("Transaction must be an expense.")
            if BillPayment.objects.filter(transaction=txn).exists():
                return HttpResponseBadRequest("Transaction already matched.")
            if amount > abs(txn.amount):
                return HttpResponseBadRequest("Matched amount exceeds transaction.")

            BillPayment.objects.create(bill=bill, transaction=txn, amount=amount)

            if bill_category and txn.category_id != bill_category.id:
                txn.category = bill_category
                txn.kind = bill_category.kind
            if bill.vendor_id and txn.vendor_id != bill.vendor_id:
                txn.vendor = bill.vendor
            txn.save()

        bill.update_status_from_payments()
        bill.save()

    return render(
        request,
        "fincore/bills/transactions/match_list.html",
        _build_bill_match_context(bill),
    )


def bill_payment_delete(request, payment_id):
    payment = get_object_or_404(BillPayment.objects.select_related("bill"), pk=payment_id)
    bill = payment.bill
    payment.delete()
    bill.update_status_from_payments()
    bill.save()
    return redirect("fincore:bill_detail", bill_id=bill.id)


def bill_detail(request, bill_id):
    bill = get_object_or_404(
        Bill.objects.select_related("vendor", "account").prefetch_related("items"),
        pk=bill_id,
    )
    payments = bill.payments.select_related("transaction", "transaction__account")
    return render(
        request,
        "fincore/bills/transactions/detail.html",
        {"bill": bill, "payments": payments},
    )
