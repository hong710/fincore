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
    parent_options = Account.objects.filter(parent__isnull=True).order_by("name")
    return render(
        request,
        "fincore/accounts/index.html",
        {
            "accounts": accounts,
            "parent_options": parent_options,
            "account_types": Account.ACCOUNT_TYPES,
        },
    )


def account_table(request):
    status = (request.GET.get("status") or "active").strip()
    account_type = (request.GET.get("account_type") or "").strip()
    qs = Account.objects.select_related("parent").order_by("name")
    if status == "active":
        qs = qs.filter(is_active=True)
    elif status == "inactive":
        qs = qs.filter(is_active=False)
    if account_type:
        qs = qs.filter(account_type=account_type)
    qs = qs.annotate(
        balance=Coalesce(
            Sum("transactions__amount"),
            0,
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
    ).annotate(last_activity=Max("transactions__date"))
    accounts = list(qs)
    children_by_parent = {}
    for account in accounts:
        if account.parent_id:
            children_by_parent.setdefault(account.parent_id, []).append(account)

    rows = []
    for account in accounts:
        if account.parent_id:
            continue
        children = children_by_parent.get(account.id, [])
        if children:
            parent_balance = sum((child.balance for child in children), 0)
            parent_last_activity = None
            for child in children:
                if child.last_activity and (parent_last_activity is None or child.last_activity > parent_last_activity):
                    parent_last_activity = child.last_activity
            rows.append(
                {
                    "row_type": "parent",
                    "account": account,
                    "balance": parent_balance,
                    "last_activity": parent_last_activity,
                    "children": sorted(children, key=lambda c: c.name.lower()),
                }
            )
        else:
            rows.append(
                {
                    "row_type": "single",
                    "account": account,
                    "balance": account.balance,
                    "last_activity": account.last_activity,
                    "children": [],
                }
            )

    return render(
        request,
        "fincore/accounts/table_partial.html",
        {"account_rows": rows},
    )


def account_create(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    name = (request.POST.get("name") or "").strip()
    account_type = request.POST.get("account_type") or "checking"
    institution = (request.POST.get("institution") or "").strip()
    notes = (request.POST.get("notes") or "").strip()
    parent_id = (request.POST.get("parent_id") or "").strip()
    is_active = request.POST.get("is_active") == "on"

    parent = None
    if parent_id:
        try:
            parent = Account.objects.get(pk=int(parent_id))
        except (Account.DoesNotExist, ValueError, TypeError):
            parent = None

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
        parent=parent,
    )
    # 204 with HX-Trigger to refresh the table; modal closes via client hook.
    response = HttpResponse(status=204)
    response["HX-Trigger"] = json.dumps({"accounts:refresh": True, "accounts:createClose": True})
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
    parent_id = (request.POST.get("parent_id") or "").strip()
    is_active = request.POST.get("is_active") == "on"

    parent = None
    if parent_id:
        try:
            parent = Account.objects.get(pk=int(parent_id))
        except (Account.DoesNotExist, ValueError, TypeError):
            parent = None

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
    if parent and parent.pk == account.pk:
        parent = None
    account.parent = parent
    account.save()

    resp = HttpResponse(status=204)
    resp["HX-Trigger"] = json.dumps({"accounts:refresh": True, "accounts:editClose": True})
    return resp
