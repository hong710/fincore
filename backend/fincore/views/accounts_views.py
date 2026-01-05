import json

from django.db.models import DecimalField, Max, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import render
from fincore.models import Account


def account_list(request):
    """
    Accounts page shell. Data will be server-rendered/HTMX-driven later.
    """
    accounts = Account.objects.order_by("name")
    return render(request, "fincore/accounts/index.html", {"accounts": accounts})


def account_table(request):
    show_archived = request.GET.get("show_archived") == "1"
    qs = Account.objects.order_by("name")
    if not show_archived:
        qs = qs.filter(is_active=True)
    qs = qs.annotate(
        balance=Coalesce(
            Sum("transactions__amount"),
            0,
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
    ).annotate(last_activity=Max("transactions__date"))
    return render(
        request,
        "fincore/accounts/table_partial.html",
        {"accounts": qs, "show_archived": show_archived},
    )


def account_create(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    name = (request.POST.get("name") or "").strip()
    account_type = request.POST.get("account_type") or "checking"
    institution = (request.POST.get("institution") or "").strip()
    notes = (request.POST.get("notes") or "").strip()
    is_active = request.POST.get("is_active") == "on"

    errors = []
    if not name:
        errors.append("Account name is required.")
    if Account.objects.filter(name=name).exists():
        errors.append("Account name must be unique.")
    if errors:
        # Return 200 with inline errors to avoid console noise; client shows errors in the targeted div.
        return render(
            request,
            "fincore/accounts/form_errors.html",
            {"form_errors": errors},
            status=200,
        )

    Account.objects.create(
        name=name,
        account_type=account_type,
        institution=institution,
        description=notes,
        is_active=is_active,
    )
    # 204 with HX-Trigger to refresh the table; modal closes via client hook.
    response = HttpResponse(status=204)
    response["HX-Trigger"] = "accounts:refresh"
    return response


def account_archive(request, pk):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")
    try:
        account = Account.objects.get(pk=pk)
    except Account.DoesNotExist:
        return HttpResponseBadRequest("Account not found")
    account.is_active = False
    account.save(update_fields=["is_active"])
    resp = HttpResponse("", status=200)
    resp["HX-Trigger"] = json.dumps({"accounts:refresh": True, "accounts:editClose": True})
    return resp


def account_delete(request, pk):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")
    try:
        account = Account.objects.get(pk=pk)
    except Account.DoesNotExist:
        return HttpResponseBadRequest("Account not found")
    try:
        account.delete()
    except Exception as exc:
        return render(
            request,
            "fincore/accounts/form_errors.html",
            {"form_errors": [str(exc)]},
            status=200,
        )
    resp = HttpResponse(status=204)
    resp["HX-Trigger"] = "accounts:refresh"
    return resp


def account_update(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")
    try:
        account_id = int(request.POST.get("account_id") or 0)
    except (TypeError, ValueError):
        return HttpResponseBadRequest("Invalid account")
    try:
        account = Account.objects.get(pk=account_id)
    except Account.DoesNotExist:
        return HttpResponseBadRequest("Account not found")

    name = (request.POST.get("name") or "").strip()
    account_type = request.POST.get("account_type") or "checking"
    institution = (request.POST.get("institution") or "").strip()
    notes = (request.POST.get("notes") or "").strip()
    is_active = request.POST.get("is_active") == "on"

    errors = []
    if not name:
        errors.append("Account name is required.")
    if Account.objects.filter(name=name).exclude(pk=account.pk).exists():
        errors.append("Account name must be unique.")
    if errors:
        return render(
            request,
            "fincore/accounts/form_errors.html",
            {"form_errors": errors},
            status=200,
        )

    account.name = name
    account.account_type = account_type
    account.institution = institution
    account.description = notes
    account.is_active = is_active
    account.save()

    resp = HttpResponse(status=204)
    resp["HX-Trigger"] = json.dumps({"accounts:refresh": True, "accounts:editClose": True})
    return resp
