import csv
import io
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction as db_transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from fincore.models import Account, ImportBatch, ImportRow


REQUIRED_MAP_KEYS = {"date", "description", "amount"}
ALLOWED_MAP_VALUES = {"ignore", "date", "description", "amount"}


def import_stage(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    upload = request.FILES.get("csv_file")
    account_id = request.POST.get("account_id")
    mapping_raw = request.POST.get("mapping", "{}")

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
        values = list(mapping.values())
        if values.count("date") != 1 or values.count("description") != 1 or values.count("amount") != 1:
            errors.append("Mapping must include exactly one Date, Description, and Amount.")
    else:
        errors.append("Column mapping is required.")

    if errors:
        return render(
            request,
            "fincore/transactions/import_errors.html",
            {"form_errors": errors},
            status=200,
        )

    batch = ImportBatch.objects.create(filename=upload.name, account=account, status="pending")

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

        for required in REQUIRED_MAP_KEYS:
            if not mapped.get(required):
                row_error_list.append(f"Missing {required} value.")

        if mapped.get("amount"):
            try:
                raw_amount = mapped["amount"].replace(",", "").replace("$", "").strip()
                if raw_amount.startswith("(") and raw_amount.endswith(")"):
                    raw_amount = f"-{raw_amount[1:-1]}"
                Decimal(raw_amount)
            except (InvalidOperation, AttributeError):
                row_error_list.append("Invalid amount value.")

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
    return render(request, "fincore/imports/review.html", {"batch": batch})


def account_imports(request, account_id):
    account = get_object_or_404(Account, pk=account_id)
    batches = ImportBatch.objects.filter(account=account).order_by("-uploaded_at", "-id")
    return render(
        request,
        "fincore/imports/account_list.html",
        {"account": account, "batches": batches},
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

    def parse_amount_value(raw_value):
        raw_value = (raw_value or "").strip().replace(",", "").replace("$", "")
        if raw_value.startswith("(") and raw_value.endswith(")"):
            raw_value = f"-{raw_value[1:-1]}"
        return Decimal(raw_value)

    row_errors = 0
    validated = []
    for row in rows:
        mapped = row.mapped or {}
        errors = []
        raw_date = mapped.get("date", "")
        raw_amount = mapped.get("amount", "")
        raw_description = mapped.get("description", "")

        parsed_date = parse_date_value(str(raw_date))
        if not parsed_date:
            errors.append("Invalid date value.")

        try:
            parsed_amount = parse_amount_value(str(raw_amount))
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
