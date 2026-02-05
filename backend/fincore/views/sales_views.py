from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from django.utils.dateparse import parse_date
from django.db.models import Sum
from django.core.paginator import Paginator
from django.db import transaction as db_transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render

from fincore.models import (
    Account,
    Category,
    Invoice,
    InvoiceItem,
    InvoicePayment,
    Transaction,
    Vendor,
)
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

    accounts = list(Account.objects.filter(is_active=True).order_by("name"))
    customers = list(Vendor.objects.filter(is_active=True, kind="payer").order_by("name"))
    account_ids = {acct.id for acct in accounts}
    customer_ids = {cust.id for cust in customers}
    
    # Normalize to int or None for clean template comparisons
    try:
        account_id_int = int(account_id) if account_id.isdigit() else None
    except (ValueError, TypeError):
        account_id_int = None
    if account_id_int not in account_ids:
        account_id_int = None
        
    try:
        customer_id_int = int(customer_id) if customer_id.isdigit() else None
    except (ValueError, TypeError):
        customer_id_int = None
    if customer_id_int not in customer_ids:
        customer_id_int = None

    qs = Invoice.objects.select_related("customer", "account").all()
    if search:
        qs = qs.filter(number__icontains=search)
    if account_id_int:
        qs = qs.filter(account_id=account_id_int)
    if customer_id_int:
        qs = qs.filter(customer_id=customer_id_int)
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
            "account_id": account_id_int,
            "customer_id": customer_id_int,
            "status": status,
            "min_total": min_total,
            "max_total": max_total,
            "search": search,
            "report_ranges": REPORT_RANGE_OPTIONS,
            "accounts": accounts,
            "customers": customers,
            "status_options": ["draft", "sent", "partially_paid", "paid", "void"],
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
            "total": "",
            "tax_exempt": False,
        }
    ]
    errors = []
    tax_rate_default = Decimal("7.75")
    tax_rate = tax_rate_default
    item_count = 1

    if request.method == "POST":
        customer_id = (request.POST.get("customer_id") or "").strip()
        account_id = (request.POST.get("account_id") or "").strip()
        invoice_date_raw = (request.POST.get("date") or "").strip()
        due_date_raw = (request.POST.get("due_date") or "").strip()
        notes = (request.POST.get("notes") or "").strip()
        tax_rate_raw = (request.POST.get("tax_rate") or "").strip()
        item_count_raw = (request.POST.get("item_count") or "1").strip()

        if not customer_id.isdigit():
            errors.append("Customer is required.")
        if not account_id.isdigit():
            errors.append("Account is required.")
        invoice_date = parse_date(invoice_date_raw) if invoice_date_raw else None
        due_date = parse_date(due_date_raw) if due_date_raw else None
        if not invoice_date:
            errors.append("Invoice date is required.")

        try:
            tax_rate = Decimal(tax_rate_raw)
        except (InvalidOperation, TypeError):
            errors.append("Tax rate is invalid.")
            tax_rate = tax_rate_default
        if tax_rate < 0:
            errors.append("Tax rate must be zero or positive.")
            tax_rate = tax_rate_default

        try:
            item_count = int(item_count_raw)
        except (TypeError, ValueError):
            item_count = 1
        item_count = max(1, min(item_count, 50))
        item_rows = [
            {
                "category_id": "",
                "description": "",
                "amount": "",
                "tax": "",
                "total": "",
                "tax_exempt": False,
            }
            for _ in range(item_count)
        ]

        items = []
        subtotal = Decimal("0.00")
        tax_total = Decimal("0.00")
        for idx in range(1, item_count + 1):
            category_field = (request.POST.get(f"item_category_{idx}") or "").strip()
            description = (request.POST.get(f"item_description_{idx}") or "").strip()
            amount_raw = (request.POST.get(f"item_amount_{idx}") or "").strip()
            tax_exempt = (request.POST.get(f"item_tax_exempt_{idx}") or "").strip() == "1"
            item_rows[idx - 1] = {
                "category_id": category_field,
                "description": description,
                "amount": amount_raw,
                "tax": "",
                "total": "",
                "tax_exempt": tax_exempt,
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

            if tax_exempt:
                tax_value = Decimal("0.00")
            else:
                tax_value = (amount * (tax_rate / Decimal("100"))).quantize(
                    Decimal("0.01")
                )
            total = (amount + tax_value).quantize(Decimal("0.01"))
            item_rows[idx - 1]["tax"] = str(tax_value)
            item_rows[idx - 1]["total"] = str(total)
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
            "tax_rate": tax_rate,
            "item_count": item_count,
        },
    )


def sales_invoice_edit(request, invoice_id):
    invoice = get_object_or_404(Invoice.objects.select_related("customer", "account"), pk=invoice_id)
    accounts = Account.objects.filter(is_active=True).order_by("name")
    customers = Vendor.objects.filter(is_active=True, kind="payer").order_by("name")
    categories = Category.objects.filter(is_active=True, kind="income").order_by("name")
    category_ids = {str(cat.id) for cat in categories}
    tax_rate_default = Decimal("7.75")
    tax_rate = tax_rate_default
    errors = []

    item_rows = [
        {
            "category_id": str(item.category_id),
            "description": item.description,
            "amount": str(item.amount),
            "tax": str(item.tax),
            "total": str(item.total),
            "tax_exempt": False,
        }
        for item in invoice.items.all()
    ]
    if not item_rows:
        item_rows = [
            {
                "category_id": "",
                "description": "",
                "amount": "",
                "tax": "",
                "total": "",
                "tax_exempt": False,
            }
        ]

    item_count = len(item_rows)

    if request.method == "POST":
        customer_id = (request.POST.get("customer_id") or "").strip()
        account_id = (request.POST.get("account_id") or "").strip()
        invoice_date_raw = (request.POST.get("date") or "").strip()
        notes = (request.POST.get("notes") or "").strip()
        tax_rate_raw = (request.POST.get("tax_rate") or "").strip()
        item_count_raw = (request.POST.get("item_count") or str(item_count)).strip()

        if not customer_id.isdigit():
            errors.append("Customer is required.")
        if not account_id.isdigit():
            errors.append("Account is required.")
        invoice_date = parse_date(invoice_date_raw) if invoice_date_raw else None
        if not invoice_date:
            errors.append("Invoice date is required.")

        try:
            tax_rate = Decimal(tax_rate_raw)
        except (InvalidOperation, TypeError):
            errors.append("Tax rate is invalid.")
            tax_rate = tax_rate_default
        if tax_rate < 0:
            errors.append("Tax rate must be zero or positive.")
            tax_rate = tax_rate_default

        try:
            item_count = int(item_count_raw)
        except (TypeError, ValueError):
            item_count = 1
        item_count = max(1, min(item_count, 50))
        item_rows = [
            {
                "category_id": "",
                "description": "",
                "amount": "",
                "tax": "",
                "total": "",
                "tax_exempt": False,
            }
            for _ in range(item_count)
        ]

        items = []
        subtotal = Decimal("0.00")
        tax_total = Decimal("0.00")
        for idx in range(1, item_count + 1):
            category_field = (request.POST.get(f"item_category_{idx}") or "").strip()
            description = (request.POST.get(f"item_description_{idx}") or "").strip()
            amount_raw = (request.POST.get(f"item_amount_{idx}") or "").strip()
            tax_exempt = (request.POST.get(f"item_tax_exempt_{idx}") or "").strip() == "1"
            item_rows[idx - 1] = {
                "category_id": category_field,
                "description": description,
                "amount": amount_raw,
                "tax": "",
                "total": "",
                "tax_exempt": tax_exempt,
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

            if tax_exempt:
                tax_value = Decimal("0.00")
            else:
                tax_value = (amount * (tax_rate / Decimal("100"))).quantize(
                    Decimal("0.01")
                )
            total = (amount + tax_value).quantize(Decimal("0.01"))
            item_rows[idx - 1]["tax"] = str(tax_value)
            item_rows[idx - 1]["total"] = str(total)
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
            with db_transaction.atomic():
                invoice.customer = customer
                invoice.account = account
                invoice.date = invoice_date
                invoice.subtotal = subtotal
                invoice.tax_total = tax_total
                invoice.total = subtotal + tax_total
                invoice.notes = notes
                invoice.save()
                invoice.items.all().delete()
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
        "fincore/sales/transactions/edit.html",
        {
            "invoice": invoice,
            "accounts": accounts,
            "customers": customers,
            "categories": categories,
            "item_rows": item_rows,
            "form_errors": errors,
            "tax_rate": tax_rate,
            "item_count": item_count,
        },
    )


def _build_invoice_match_context(invoice):
    match_start = invoice.date - timedelta(days=30)
    match_end = invoice.date + timedelta(days=30)
    remaining = invoice.remaining_balance

    qs = (
        Transaction.objects.select_related("account", "vendor")
        .filter(date__gte=match_start, date__lte=match_end)
        .filter(account=invoice.account)
        .filter(amount__gt=0)
        .exclude(invoice_payments__isnull=False)
        .order_by("-date", "-id")
    )
    if remaining > 0:
        qs = qs.filter(amount__gte=remaining)

    return {
        "invoice": invoice,
        "remaining_balance": remaining,
        "matches": qs,
    }


def sales_invoice_matches(request):
    invoice_id = request.GET.get("invoice_id")
    if not invoice_id or not str(invoice_id).isdigit():
        return HttpResponseBadRequest("Invalid invoice")

    invoice = get_object_or_404(Invoice, pk=int(invoice_id))
    return render(
        request,
        "fincore/sales/transactions/match_list.html",
        _build_invoice_match_context(invoice),
    )


def sales_invoice_match_apply(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")
    invoice_id = (request.POST.get("invoice_id") or "").strip()
    transaction_id = (request.POST.get("transaction_id") or "").strip()
    amount_raw = (request.POST.get("amount") or "").strip()

    if not invoice_id.isdigit() or not transaction_id.isdigit():
        return HttpResponseBadRequest("Invalid match")

    invoice = get_object_or_404(Invoice, pk=int(invoice_id))
    txn = get_object_or_404(Transaction, pk=int(transaction_id))

    if txn.amount <= 0:
        return HttpResponseBadRequest("Transaction must be positive to match.")
    if txn.account_id != invoice.account_id:
        return HttpResponseBadRequest("Transaction account must match invoice account.")

    try:
        amount = Decimal(amount_raw) if amount_raw else invoice.remaining_balance
    except InvalidOperation:
        return HttpResponseBadRequest("Invalid amount.")
    if amount <= 0:
        return HttpResponseBadRequest("Amount must be positive.")

    remaining = invoice.remaining_balance
    if amount > remaining:
        return HttpResponseBadRequest("Amount exceeds invoice remaining balance.")

    already_matched = (
        InvoicePayment.objects.filter(transaction=txn)
        .aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )
    if amount + already_matched > txn.amount:
        return HttpResponseBadRequest("Amount exceeds transaction available balance.")

    with db_transaction.atomic():
        InvoicePayment.objects.create(
            invoice=invoice,
            transaction=txn,
            amount=amount,
        )
        invoice.update_status_from_payments()
        invoice.save()

    return render(
        request,
        "fincore/sales/transactions/match_list.html",
        _build_invoice_match_context(invoice),
    )


def sales_invoice_payment_delete(request, payment_id):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")
    payment = get_object_or_404(InvoicePayment.objects.select_related("invoice"), pk=payment_id)
    invoice = payment.invoice
    with db_transaction.atomic():
        payment.delete()
        invoice.update_status_from_payments()
        invoice.save()
    return redirect("fincore:sales_invoice_detail", invoice_id=invoice.id)


def sales_invoice_detail(request, invoice_id):
    invoice = get_object_or_404(
        Invoice.objects.select_related("customer", "account").prefetch_related(
            "items__category", "payments__transaction__account"
        ),
        pk=invoice_id,
    )
    payments = invoice.payments.select_related("transaction", "transaction__account")
    return render(
        request,
        "fincore/sales/transactions/detail.html",
        {
            "invoice": invoice,
            "payments": payments,
        },
    )
