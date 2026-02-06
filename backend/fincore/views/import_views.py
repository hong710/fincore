import calendar
import csv
import io
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction as db_transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from fincore.models import Account, ImportBatch, ImportRow, Transaction


ALLOWED_MAP_VALUES = {"ignore", "date", "description", "amount", "indicator", "debit", "credit"}
VALID_STRATEGIES = {"signed", "indicator", "split_columns"}


def _parse_numeric(raw):
    """Parse a raw string into a Decimal, handling common formats."""
    raw = (raw or "").strip().replace(",", "").replace("$", "")
    if raw.startswith("(") and raw.endswith(")"):
        raw = f"-{raw[1:-1]}"
    return Decimal(raw)


def _validate_mapping(mapping, amount_strategy):
    """Validate column mapping based on amount strategy. Returns list of error strings."""
    errors = []
    values = [v for v in mapping.values() if v != "ignore"]

    if values.count("date") != 1:
        errors.append("Mapping must include exactly one Date column.")
    if values.count("description") > 1:
        errors.append("At most one Description column allowed.")

    if amount_strategy == "signed":
        if values.count("amount") != 1:
            errors.append("Mapping must include exactly one Amount column.")
        for forbidden in ("indicator", "debit", "credit"):
            if forbidden in values:
                errors.append(f"'{forbidden}' is not valid for Signed Amount strategy.")

    elif amount_strategy == "indicator":
        if values.count("amount") != 1:
            errors.append("Mapping must include exactly one Amount column.")
        if values.count("indicator") != 1:
            errors.append("Mapping must include exactly one Indicator column.")
        for forbidden in ("debit", "credit"):
            if forbidden in values:
                errors.append(f"'{forbidden}' is not valid for Amount + Indicator strategy.")

    elif amount_strategy == "split_columns":
        if values.count("debit") != 1:
            errors.append("Mapping must include exactly one Debit column.")
        if values.count("credit") != 1:
            errors.append("Mapping must include exactly one Credit column.")
        for forbidden in ("amount", "indicator"):
            if forbidden in values:
                errors.append(f"'{forbidden}' is not valid for Debit/Credit strategy.")

    return errors


def _normalize_row_amount(mapped, amount_strategy, indicator_credit, indicator_debit):
    """Normalize amount to signed Decimal. Returns (value_or_none, error_list)."""
    if amount_strategy == "signed":
        raw = str(mapped.get("amount", "") or "").strip()
        if not raw:
            return None, ["Missing amount value."]
        try:
            return _parse_numeric(raw), []
        except (InvalidOperation, ValueError):
            return None, ["Invalid amount value."]

    elif amount_strategy == "indicator":
        raw_amount = str(mapped.get("amount", "") or "").strip()
        raw_indicator = str(mapped.get("indicator", "") or "").strip()
        errs = []
        if not raw_amount:
            errs.append("Missing amount value.")
        if not raw_indicator:
            errs.append("Missing indicator value.")
        if errs:
            return None, errs
        try:
            unsigned = _parse_numeric(raw_amount)
        except (InvalidOperation, ValueError):
            return None, ["Invalid amount value."]
        ind_lower = raw_indicator.lower()
        credit_lower = (indicator_credit or "").strip().lower()
        debit_lower = (indicator_debit or "").strip().lower()
        if credit_lower and ind_lower == credit_lower:
            return abs(unsigned), []
        elif debit_lower and ind_lower == debit_lower:
            return -abs(unsigned), []
        else:
            return None, [f"Unknown indicator '{raw_indicator}'."]

    elif amount_strategy == "split_columns":
        raw_debit = str(mapped.get("debit", "") or "").strip()
        raw_credit = str(mapped.get("credit", "") or "").strip()
        has_debit = bool(raw_debit)
        has_credit = bool(raw_credit)
        if has_debit and has_credit:
            return None, ["Both debit and credit populated."]
        if not has_debit and not has_credit:
            return None, ["Both debit and credit empty."]
        try:
            if has_debit:
                return -abs(_parse_numeric(raw_debit)), []
            else:
                return abs(_parse_numeric(raw_credit)), []
        except (InvalidOperation, ValueError):
            return None, ["Invalid amount value."]

    return None, ["Unknown amount strategy."]


def import_stage(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    upload = request.FILES.get("csv_file")
    account_id = request.POST.get("account_id")
    mapping_raw = request.POST.get("mapping", "{}")
    amount_strategy = request.POST.get("amount_strategy", "signed")
    indicator_credit = request.POST.get("indicator_credit_value", "").strip()
    indicator_debit = request.POST.get("indicator_debit_value", "").strip()

    errors = []
    if not upload:
        errors.append("CSV file is required.")

    try:
        account_id = int(account_id or 0)
    except (TypeError, ValueError):
        account_id = 0

    account = None
    if not account_id:
        errors.append("Account selection is required.")
    else:
        try:
            account = Account.objects.get(pk=account_id, is_active=True)
        except Account.DoesNotExist:
            errors.append("Selected account is not available.")

    if amount_strategy not in VALID_STRATEGIES:
        errors.append("Invalid amount strategy.")
        amount_strategy = "signed"

    if amount_strategy == "indicator":
        if not indicator_credit:
            errors.append("Credit indicator value is required.")
        if not indicator_debit:
            errors.append("Debit indicator value is required.")

    try:
        mapping = json.loads(mapping_raw) if mapping_raw else {}
    except json.JSONDecodeError:
        mapping = {}
        errors.append("Invalid column mapping payload.")

    if mapping:
        for value in mapping.values():
            if value not in ALLOWED_MAP_VALUES:
                errors.append("Invalid mapping option detected.")
                break
        mapping_errors = _validate_mapping(mapping, amount_strategy)
        errors.extend(mapping_errors)
    else:
        errors.append("Column mapping is required.")

    if errors:
        return render(
            request,
            "fincore/transactions/import_errors.html",
            {"form_errors": errors},
            status=200,
        )

    batch = ImportBatch.objects.create(
        filename=upload.name,
        account=account,
        status="pending",
        amount_strategy=amount_strategy,
        indicator_credit_value=indicator_credit,
        indicator_debit_value=indicator_debit,
    )

    file_text = upload.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(file_text))
    row_errors = 0
    total_rows = 0

    for row in reader:
        total_rows += 1
        normalized_row = {}
        for key, value in row.items():
            if key is None:
                continue
            key_clean = str(key).strip().lower()
            if isinstance(value, list):
                value_clean = " ".join(str(item).strip() for item in value if item is not None)
            else:
                value_clean = (value or "").strip()
            normalized_row[key_clean] = value_clean
        mapped = {}
        row_error_list = []
        for column, target in mapping.items():
            if target == "ignore":
                continue
            normalized_column = str(column).strip().lower()
            mapped[target] = normalized_row.get(normalized_column, "")

        # Date is always required
        if not mapped.get("date"):
            row_error_list.append("Missing date value.")

        # Normalize amount to signed_amount
        signed_amount, amount_errors = _normalize_row_amount(
            mapped, amount_strategy, indicator_credit, indicator_debit
        )
        row_error_list.extend(amount_errors)

        if signed_amount is not None:
            mapped["signed_amount"] = str(signed_amount)

        if row_error_list:
            row_errors += 1

        ImportRow.objects.create(
            batch=batch,
            raw_row=row,
            mapped=mapped,
            errors=row_error_list,
        )

    if row_errors:
        batch.status = "failed"
        batch.error_message = f"{row_errors} row(s) have validation errors."
        batch.save(update_fields=["status", "error_message"])
        return render(
            request,
            "fincore/transactions/import_errors.html",
            {"form_errors": [batch.error_message]},
            status=200,
        )

    batch.status = "validated"
    batch.save(update_fields=["status"])

    response = render(
        request,
        "fincore/transactions/import_success.html",
        {
            "batch": batch,
            "total_rows": total_rows,
        },
        status=200,
    )
    response["HX-Trigger"] = json.dumps({"import:staged": {"batch_id": batch.id}})
    return response


def import_review(request, batch_id):
    batch = get_object_or_404(ImportBatch, pk=batch_id)
    rows = list(batch.rows.all())
    has_errors = any(row.errors for row in rows)
    show_errors = request.GET.get("errors") in {"1", "true", "yes"}

    if show_errors:
        rows = [row for row in rows if row.errors]

    try:
        page_size = int(request.GET.get("page_size", 25))
    except (TypeError, ValueError):
        page_size = 25

    paginator = Paginator(rows, page_size)
    page_number = request.GET.get("page") or 1
    page_obj = paginator.get_page(page_number)

    for row in page_obj.object_list:
        mapped = row.mapped or {}
        # Use signed_amount if available (new batches), fall back to amount (old batches)
        raw_signed = str(mapped.get("signed_amount", "") or "").strip()
        if not raw_signed:
            raw_signed = str(mapped.get("amount", "") or "").strip()
        amount_display = raw_signed or "-"
        amount_class = "text-slate-500"
        if raw_signed:
            cleaned = raw_signed.replace(",", "").replace("$", "").strip()
            if cleaned.startswith("(") and cleaned.endswith(")"):
                cleaned = f"-{cleaned[1:-1]}"
            try:
                amount_value = Decimal(cleaned)
            except (InvalidOperation, ValueError):
                amount_value = None
            if amount_value is not None:
                if amount_value > 0:
                    amount_display = f"+{amount_value:.2f}"
                    amount_class = "text-emerald-600"
                elif amount_value < 0:
                    amount_display = f"-{abs(amount_value):.2f}"
                    amount_class = "text-rose-600"
                else:
                    amount_display = "0.00"
        row.amount_display = amount_display
        row.amount_class = amount_class

    query_params = request.GET.copy()
    query_params.pop("page", None)
    query_params.pop("page_size", None)
    return render(
        request,
        "fincore/imports/review.html",
        {
            "batch": batch,
            "page_obj": page_obj,
            "paginator": paginator,
            "page_size": page_size,
            "has_errors": has_errors,
            "show_errors": show_errors,
            "filter_query": query_params.urlencode(),
        },
    )


def account_imports(request, account_id):
    account = get_object_or_404(Account, pk=account_id)
    batches = ImportBatch.objects.filter(account=account)
    date_range = request.GET.get("date_range", "all")
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    status = request.GET.get("status", "").strip()

    def parse_date(raw_value):
        raw_value = (raw_value or "").strip()
        if not raw_value:
            return None
        try:
            return datetime.strptime(raw_value, "%Y-%m-%d").date()
        except ValueError:
            return None

    def month_bounds(year_value, month_value):
        last_day = calendar.monthrange(year_value, month_value)[1]
        return date(year_value, month_value, 1), date(year_value, month_value, last_day)

    def quarter_bounds(year_value, quarter_key):
        mapping = {"q1": (1, 3), "q2": (4, 6), "q3": (7, 9), "q4": (10, 12)}
        start_month, end_month = mapping[quarter_key]
        _, end_day = calendar.monthrange(year_value, end_month)
        return date(year_value, start_month, 1), date(year_value, end_month, end_day)

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
            batches = batches.filter(uploaded_at__date__gte=start_date)
        if end_date:
            batches = batches.filter(uploaded_at__date__lte=end_date)

    status_keys = {choice[0] for choice in ImportBatch.STATUS_CHOICES}
    if status in status_keys:
        batches = batches.filter(status=status)

    batches = batches.order_by("-uploaded_at", "-id")
    return render(
        request,
        "fincore/imports/account_list.html",
        {
            "account": account,
            "batches": batches,
            "status_options": [choice[0] for choice in ImportBatch.STATUS_CHOICES],
            "filter_payload": {
                "date_range": date_range or "all",
                "date_from": date_from,
                "date_to": date_to,
                "status": status,
            },
        },
    )


def import_commit(request, batch_id):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    batch = get_object_or_404(ImportBatch, pk=batch_id)
    if batch.status == "imported":
        messages.info(request, "This import batch is already committed.")
        return redirect(reverse("fincore:import_review", args=[batch.id]))
    if batch.status != "validated":
        messages.error(request, "This import batch is not ready to commit.")
        return redirect(reverse("fincore:import_review", args=[batch.id]))
    if not batch.account:
        messages.error(request, "No account is assigned to this import batch.")
        return redirect(reverse("fincore:import_review", args=[batch.id]))

    rows = list(batch.rows.all())
    if not rows:
        messages.error(request, "No rows found for this import batch.")
        return redirect(reverse("fincore:import_review", args=[batch.id]))

    def parse_date_value(raw_value):
        raw_value = (raw_value or "").strip()
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
            try:
                return datetime.strptime(raw_value, fmt).date()
            except ValueError:
                continue
        return None

    row_errors = 0
    validated = []
    for row in rows:
        mapped = row.mapped or {}
        errors = []
        raw_date = mapped.get("date", "")
        raw_description = mapped.get("description", "")

        parsed_date = parse_date_value(str(raw_date))
        if not parsed_date:
            errors.append("Invalid date value.")

        # Use signed_amount (new batches) or fall back to amount (old batches)
        raw_signed = str(mapped.get("signed_amount", "") or "").strip()
        if raw_signed:
            try:
                parsed_amount = Decimal(raw_signed)
            except (InvalidOperation, ValueError):
                errors.append("Invalid signed amount value.")
                parsed_amount = None
        else:
            raw_amount = str(mapped.get("amount", "") or "").strip()
            try:
                parsed_amount = _parse_numeric(raw_amount)
            except (InvalidOperation, ValueError):
                errors.append("Invalid amount value.")
                parsed_amount = None

        description = str(raw_description).strip()

        if errors:
            row_errors += 1
            row.errors = errors
            row.save(update_fields=["errors"])
            continue

        kind = "expense" if parsed_amount < 0 else "income"
        validated.append(
            {
                "date": parsed_date,
                "amount": parsed_amount,
                "description": description,
                "kind": kind,
            }
        )

    if row_errors:
        batch.status = "failed"
        batch.error_message = f"{row_errors} row(s) failed commit validation."
        batch.save(update_fields=["status", "error_message"])
        messages.error(request, batch.error_message)
        return redirect(reverse("fincore:import_review", args=[batch.id]))

    from fincore.models import Transaction

    with db_transaction.atomic():
        Transaction.objects.bulk_create(
            [
                Transaction(
                    date=item["date"],
                    account=batch.account,
                    amount=item["amount"],
                    kind=item["kind"],
                    payee="",
                    category=None,
                    transfer_group=None,
                    is_imported=True,
                    import_batch=batch,
                    description=item["description"],
                    source="csv",
                )
                for item in validated
            ],
            batch_size=500,
        )
        batch.status = "imported"
        batch.error_message = ""
        batch.save(update_fields=["status", "error_message"])

    messages.success(request, f"Imported {len(validated)} rows successfully.")
    return redirect(reverse("fincore:import_review", args=[batch.id]))


def import_rollback(request, batch_id):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    batch = get_object_or_404(ImportBatch, pk=batch_id)
    if batch.status != "imported":
        messages.error(request, "Only imported batches can be rolled back.")
        return redirect(reverse("fincore:import_review", args=[batch.id]))

    account_id = batch.account_id
    with db_transaction.atomic():
        Transaction.objects.filter(import_batch=batch).delete()
        ImportRow.objects.filter(batch=batch).delete()
        batch.delete()

    messages.success(request, "Import batch rolled back and removed.")
    if account_id:
        return redirect(reverse("fincore:account_imports", args=[account_id]))
    return redirect(reverse("fincore:transaction_list"))


def import_delete(request, batch_id):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    batch = get_object_or_404(ImportBatch, pk=batch_id)
    account_id = batch.account_id

    if batch.status == "imported":
        confirm_text = (request.POST.get("confirm_text") or "").strip().upper()
        confirm_checked = request.POST.get("confirm_checked") == "on"
        if confirm_text != "DELETE" or not confirm_checked:
            messages.error(request, "Confirmation required to delete an imported batch.")
            return redirect(reverse("fincore:import_review", args=[batch.id]))
        with db_transaction.atomic():
            Transaction.objects.filter(import_batch=batch).delete()
            ImportRow.objects.filter(batch=batch).delete()
            batch.delete()
        messages.success(request, "Imported batch deleted with transactions removed.")
    else:
        with db_transaction.atomic():
            ImportRow.objects.filter(batch=batch).delete()
            batch.delete()
        messages.success(request, "Import batch deleted.")

    if account_id:
        return redirect(reverse("fincore:account_imports", args=[account_id]))
    return redirect(reverse("fincore:transaction_list"))
