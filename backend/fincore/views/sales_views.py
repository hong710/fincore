from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from django.utils.dateparse import parse_date
from django.core.paginator import Paginator
from django.db import transaction as db_transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render

from fincore.models import Account, Category, Invoice, InvoiceItem, Transaction, Vendor
from .transaction_views import REPORT_RANGE_OPTIONS, _resolve_report_range


def _generate_invoice_number():
    return f"INV{date.today():%Y%m%d}-{uuid4().hex[:6].upper()}"


def sales_transactions_list(request):
    date_range = (request.GET.get("date_range") or "this_year").strip()
    date_from = (request.GET.get("date_from") or "").strip()
    date_to = (request.GET.get("date_to") or "").strip()
    account_id = (request.GET.get("account_id") or "").strip()
    customer_id = (request.GET.get("customer_id") or "").strip()
    status = (request.GET.get("status") or "").strip()
    min_total = (request.GET.get("min_total") or "").strip()
    max_total = (request.GET.get("max_total") or "").strip()
    search = (request.GET.get("q") or "").strip()

    date_range, start_date, end_date = _resolve_report_range(date_range, date_from, date_to)

    qs = Invoice.objects.select_related("customer", "account").all()
    if search:
        qs = qs.filter(number__icontains=search)
    if account_id.isdigit():
        qs = qs.filter(account_id=int(account_id))
    if customer_id.isdigit():
        qs = qs.filter(customer_id=int(customer_id))
    if status:
        qs = qs.filter(status=status)
    if start_date:
        qs = qs.filter(date__gte=start_date)
    if end_date:
        qs = qs.filter(date__lte=end_date)
    try:
        if min_total:
            qs = qs.filter(total__gte=Decimal(min_total))
    except InvalidOperation:
        min_total = ""
    try:
        if max_total:
            qs = qs.filter(total__lte=Decimal(max_total))
    except InvalidOperation:
        max_total = ""

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
        "fincore/sales/transactions/index.html",
        {
            "page_obj": page_obj,
            "date_range": date_range,
            "date_from": date_from,
            "date_to": date_to,
            "account_id": account_id,
            "customer_id": customer_id,
            "status": status,
            "min_total": min_total,
            "max_total": max_total,
            "search": search,
            "report_ranges": REPORT_RANGE_OPTIONS,
            "accounts": Account.objects.filter(is_active=True).order_by("name"),
            "customers": Vendor.objects.filter(is_active=True, kind="payer").order_by("name"),
            "status_options": ["draft", "sent", "paid", "void"],
        },
    )


def sales_invoice_create(request):
    accounts = Account.objects.filter(is_active=True).order_by("name")
    customers = Vendor.objects.filter(is_active=True, kind="payer").order_by("name")
    categories = Category.objects.filter(is_active=True, kind="income").order_by("name")
    category_ids = {str(cat.id) for cat in categories}
    item_rows = [
        {
            "category_id": "",
            "description": "",
            "amount": "",
            "tax": "",
        }
        for _ in range(5)
    ]
    errors = []

    if request.method == "POST":
        customer_id = (request.POST.get("customer_id") or "").strip()
        account_id = (request.POST.get("account_id") or "").strip()
        invoice_date_raw = (request.POST.get("date") or "").strip()
        due_date_raw = (request.POST.get("due_date") or "").strip()
        notes = (request.POST.get("notes") or "").strip()

        if not customer_id.isdigit():
            errors.append("Customer is required.")
        if not account_id.isdigit():
            errors.append("Account is required.")
        invoice_date = parse_date(invoice_date_raw) if invoice_date_raw else None
        due_date = parse_date(due_date_raw) if due_date_raw else None
        if not invoice_date:
            errors.append("Invoice date is required.")

        items = []
        subtotal = Decimal("0.00")
        tax_total = Decimal("0.00")
        for idx in range(1, 6):
            category_field = (request.POST.get(f"item_category_{idx}") or "").strip()
            description = (request.POST.get(f"item_description_{idx}") or "").strip()
            amount_raw = (request.POST.get(f"item_amount_{idx}") or "").strip()
            tax_raw = (request.POST.get(f"item_tax_{idx}") or "").strip()
            item_rows[idx - 1] = {
                "category_id": category_field,
                "description": description,
                "amount": amount_raw,
                "tax": tax_raw,
            }

            if not any([category_field, description, amount_raw, tax_raw]):
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

            tax_value = Decimal("0.00")
            if tax_raw:
                try:
                    tax_value = Decimal(tax_raw)
                except InvalidOperation:
                    errors.append("Line item tax is invalid.")
                    continue

            total = amount + tax_value
            subtotal += amount
            tax_total += tax_value
            items.append(
                {
                    "category_id": int(category_field),
                    "description": description,
                    "amount": amount,
                    "tax": tax_value,
                    "total": total,
                }
            )

        if not items:
            errors.append("At least one line item is required.")

        if not errors:
            customer = get_object_or_404(Vendor, pk=int(customer_id), kind="payer")
            account = get_object_or_404(Account, pk=int(account_id))
            invoice_number = _generate_invoice_number()
            while Invoice.objects.filter(number=invoice_number).exists():
                invoice_number = _generate_invoice_number()
            with db_transaction.atomic():
                invoice = Invoice.objects.create(
                    number=invoice_number,
                    customer=customer,
                    account=account,
                    date=invoice_date,
                    due_date=due_date,
                    status="draft",
                    subtotal=subtotal,
                    tax_total=tax_total,
                    total=subtotal + tax_total,
                    notes=notes,
                )
                for item in items:
                    InvoiceItem.objects.create(
                        invoice=invoice,
                        category_id=item["category_id"],
                        description=item["description"],
                        amount=item["amount"],
                        tax=item["tax"],
                        total=item["total"],
                    )
            return redirect("fincore:sales_transactions_list")

    return render(
        request,
        "fincore/sales/transactions/new.html",
        {
            "accounts": accounts,
            "customers": customers,
            "categories": categories,
            "item_rows": item_rows,
            "form_errors": errors,
        },
    )


def sales_invoice_matches(request):
    invoice_id = request.GET.get("invoice_id")
    if not invoice_id or not str(invoice_id).isdigit():
        return HttpResponseBadRequest("Invalid invoice")

    invoice = get_object_or_404(Invoice, pk=int(invoice_id))
    match_start = invoice.date - timedelta(days=30)
    match_end = invoice.date + timedelta(days=30)

    qs = (
        Transaction.objects.select_related("account", "vendor")
        .filter(date__gte=match_start, date__lte=match_end)
        .filter(amount=invoice.total)
        .order_by("-date", "-id")
    )
    return render(
        request,
        "fincore/sales/transactions/match_list.html",
        {
            "invoice": invoice,
            "matches": qs,
        },
    )
