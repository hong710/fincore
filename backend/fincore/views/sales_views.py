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
    categories = (
        Category.objects.filter(is_active=True)
        .exclude(kind__in=["withdraw", "opening", "transfer", "equity", "liability"])
        .order_by("kind", "name")
    )
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
    tax_exclude = False
    item_count = 1

    if request.method == "POST":
        customer_id = (request.POST.get("customer_id") or "").strip()
        account_id = (request.POST.get("account_id") or "").strip()
        invoice_date_raw = (request.POST.get("date") or "").strip()
        due_date_raw = (request.POST.get("due_date") or "").strip()
        notes = (request.POST.get("notes") or "").strip()
        tax_rate_raw = (request.POST.get("tax_rate") or "").strip()
        tax_exclude = (request.POST.get("tax_exclude") or "").strip() == "1"
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

            if tax_exclude or tax_exempt:
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
                    tax_rate=tax_rate,
                    tax_exclude=tax_exclude,
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
                        tax_exempt=item["tax_exempt"],
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
            "tax_exclude": tax_exclude,
            "tax_rate_locked": False,
            "item_count": item_count,
        },
    )


def sales_invoice_edit(request, invoice_id):
    invoice = get_object_or_404(Invoice.objects.select_related("customer", "account"), pk=invoice_id)
    accounts = Account.objects.filter(is_active=True).order_by("name")
    customers = Vendor.objects.filter(is_active=True, kind="payer").order_by("name")
    categories = (
        Category.objects.filter(is_active=True)
        .exclude(kind__in=["withdraw", "opening", "transfer", "equity", "liability"])
        .order_by("kind", "name")
    )
    category_ids = {str(cat.id) for cat in categories}
    tax_rate_default = Decimal("7.75")
    tax_rate = invoice.tax_rate if invoice.tax_rate is not None else tax_rate_default
    tax_exclude = invoice.tax_exclude
    tax_rate_locked = invoice.status in {"paid", "partially_paid"}
    errors = []

    item_rows = [
        {
            "category_id": str(item.category_id),
            "description": item.description,
            "amount": str(item.amount),
            "tax": str(item.tax),
            "total": str(item.total),
            "tax_exempt": item.tax_exempt,
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
        tax_exclude = (request.POST.get("tax_exclude") or "").strip() == "1"
        item_count_raw = (request.POST.get("item_count") or str(item_count)).strip()

        if not customer_id.isdigit():
            errors.append("Customer is required.")
        if not account_id.isdigit():
            errors.append("Account is required.")
        invoice_date = parse_date(invoice_date_raw) if invoice_date_raw else None
        if not invoice_date:
            errors.append("Invoice date is required.")

        if tax_rate_locked:
            tax_rate = invoice.tax_rate
            tax_exclude = invoice.tax_exclude
        else:
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

            if tax_exclude or tax_exempt:
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
                    "tax_exempt": tax_exempt,
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
                if not tax_rate_locked:
                    invoice.tax_rate = tax_rate
                    invoice.tax_exclude = tax_exclude
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
                        tax_exempt=item["tax_exempt"],
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
            "tax_exclude": tax_exclude,
            "tax_rate_locked": tax_rate_locked,
            "item_count": item_count,
        },
    )


def _build_invoice_match_context(invoice):
    match_start = invoice.date - timedelta(days=30)
    match_end = invoice.date + timedelta(days=30)
    remaining = invoice.remaining_balance

    # Base queryset: positive income transactions in same account, not already matched, within date range
    base_qs = (
        Transaction.objects.select_related("account", "vendor")
        .filter(date__gte=match_start, date__lte=match_end)
        .filter(account=invoice.account)
        .filter(amount__gt=0)
        .exclude(invoice_payments__isnull=False)
    )

    # Best matches: transactions that can cover full remaining balance
    best_matches = []
    if remaining > 0:
        best_matches = list(
            base_qs.filter(amount__gte=remaining)
            .order_by("-date", "-id")[:10]
        )

    # All other available transactions (exclude best matches)
    best_match_ids = {txn.id for txn in best_matches}
    other_transactions = list(
        base_qs.exclude(id__in=best_match_ids)
        .order_by("-date", "-id")[:50]
    )

    return {
        "invoice": invoice,
        "remaining_balance": remaining,
        "best_matches": best_matches,
        "other_transactions": other_transactions,
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
    if not invoice_id.isdigit():
        return HttpResponseBadRequest("Invalid invoice")

    invoice = get_object_or_404(Invoice, pk=int(invoice_id))
    
    # Collect all selected transaction matches from the form
    matches = []
    for key in request.POST:
        if key.startswith("match_"):
            txn_id = key.replace("match_", "")
            amount_raw = request.POST.get(key, "").strip()
            if txn_id.isdigit() and amount_raw:
                try:
                    amount = Decimal(amount_raw)
                    if amount > 0:
                        matches.append({"transaction_id": int(txn_id), "amount": amount})
                except (InvalidOperation, ValueError):
                    pass
    
    if not matches:
        return HttpResponseBadRequest("No matches selected.")

    # Validate all matches before applying
    total_matched = Decimal("0.00")
    validated_matches = []
    
    for match in matches:
        txn = get_object_or_404(Transaction, pk=match["transaction_id"])
        amount = match["amount"]
        
        if txn.amount <= 0:
            return HttpResponseBadRequest(f"Transaction {txn.id} must be positive.")
        if txn.account_id != invoice.account_id:
            return HttpResponseBadRequest(f"Transaction {txn.id} account mismatch.")
        
        # Check transaction available balance
        already_matched = (
            InvoicePayment.objects.filter(transaction=txn)
            .aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )
        if amount + already_matched > txn.amount:
            return HttpResponseBadRequest(
                f"Transaction {txn.id}: amount {amount} exceeds available {txn.amount - already_matched}."
            )
        
        total_matched += amount
        validated_matches.append({"transaction": txn, "amount": amount})
    
    # Check invoice remaining balance
    remaining = invoice.remaining_balance
    if total_matched > remaining:
        return HttpResponseBadRequest(
            f"Total matched {total_matched} exceeds invoice remaining {remaining}."
        )

    # Get the primary category from the invoice (first item's category)
    first_item = invoice.items.select_related("category").first()
    invoice_category = first_item.category if first_item else None

    # Apply all matches atomically
    with db_transaction.atomic():
        for match in validated_matches:
            txn = match["transaction"]
            InvoicePayment.objects.create(
                invoice=invoice,
                transaction=txn,
                amount=match["amount"],
            )
            # Set transaction category and vendor from invoice
            update_fields = []
            if invoice_category and txn.category_id != invoice_category.id:
                txn.category = invoice_category
                txn.kind = invoice_category.kind
                update_fields += ["category", "kind"]
            if invoice.customer_id and txn.vendor_id != invoice.customer_id:
                txn.vendor = invoice.customer
                update_fields.append("vendor")
            if update_fields:
                txn.save(update_fields=update_fields)
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
    txn = payment.transaction
    with db_transaction.atomic():
        payment.delete()
        remaining_links = InvoicePayment.objects.filter(transaction=txn).exists()
        if not remaining_links:
            uncat_income = Category.objects.filter(
                name="Uncategorized Income", kind="income", is_protected=True
            ).first()
            uncat_expense = Category.objects.filter(
                name="Uncategorized Expense", kind="expense", is_protected=True
            ).first()
            fallback_category = uncat_expense if txn.amount < 0 else uncat_income
            update_fields = []
            if fallback_category and txn.category_id != fallback_category.id:
                txn.category = fallback_category
                txn.kind = fallback_category.kind
                update_fields += ["category", "kind"]
            if txn.vendor_id is not None:
                txn.vendor = None
                update_fields.append("vendor")
            if update_fields:
                txn.save(update_fields=update_fields)
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
