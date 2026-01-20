from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from fincore.models import Transaction, Vendor


def vendor_list(request):
    return render(request, "fincore/vendors/index.html")


def vendor_create(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    name = (request.POST.get("name") or "").strip()
    kind = (request.POST.get("kind") or "").strip()
    description = (request.POST.get("description") or "").strip()
    is_active = request.POST.get("is_active") == "on"

    errors = []
    if not name:
        errors.append("Vendor name is required.")
    if kind not in dict(Vendor.KIND_CHOICES):
        errors.append("Vendor kind is required.")
    if Vendor.objects.filter(name=name, kind=kind).exists():
        errors.append("Vendor name must be unique within a kind.")
    if errors:
        return render(
            request,
            "fincore/accounts/form_errors.html",
            {"form_errors": errors},
            status=200,
        )

    Vendor.objects.create(
        name=name,
        kind=kind,
        description=description,
        is_active=is_active,
    )

    resp = HttpResponse(status=204)
    resp["HX-Trigger"] = '{"vendors:refresh": true, "vendors:createClose": true}'
    return resp


def vendor_table(request):
    if not getattr(request, "htmx", False):
        query = request.META.get("QUERY_STRING", "")
        target = reverse("fincore:vendor_list")
        if query:
            target = f"{target}?{query}"
        return redirect(target)

    search = request.GET.get("q", "").strip()
    selected_kinds = [value for value in request.GET.getlist("kind") if value]
    selected_active = [value for value in request.GET.getlist("active") if value]
    active_scope = request.GET.get("active_scope", "active").strip()
    try:
        page_size = int(request.GET.get("page_size", 25))
    except (TypeError, ValueError):
        page_size = 25

    qs = Vendor.objects.all()
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(description__icontains=search))
    if selected_kinds:
        qs = qs.filter(kind__in=selected_kinds)
    if selected_active:
        active_map = {"active": True, "inactive": False}
        active_values = [active_map[val] for val in selected_active if val in active_map]
        if active_values:
            qs = qs.filter(is_active__in=active_values)
    elif active_scope == "active":
        qs = qs.filter(is_active=True)
    qs = qs.order_by("kind", "name")

    options_base = Vendor.objects.all()
    if search:
        options_base = options_base.filter(Q(name__icontains=search) | Q(description__icontains=search))

    kind_options_qs = options_base
    if selected_active:
        active_map = {"active": True, "inactive": False}
        active_values = [active_map[val] for val in selected_active if val in active_map]
        if active_values:
            kind_options_qs = kind_options_qs.filter(is_active__in=active_values)
    elif active_scope == "active":
        kind_options_qs = kind_options_qs.filter(is_active=True)
    available_kinds = list(kind_options_qs.values_list("kind", flat=True).distinct())
    kind_options = [choice[0] for choice in Vendor.KIND_CHOICES if choice[0] in available_kinds]
    for value in selected_kinds:
        if value not in kind_options:
            kind_options.append(value)

    active_options_qs = options_base
    if selected_kinds:
        active_options_qs = active_options_qs.filter(kind__in=selected_kinds)
    available_active = list(active_options_qs.values_list("is_active", flat=True).distinct())
    active_options = []
    if True in available_active:
        active_options.append("active")
    if False in available_active:
        active_options.append("inactive")
    for value in selected_active:
        if value not in active_options:
            active_options.append(value)

    paginator = Paginator(qs, page_size)
    page_number = request.GET.get("page") or 1
    page_obj = paginator.get_page(page_number)

    context = {
        "page_obj": page_obj,
        "paginator": paginator,
        "page_size": page_size,
        "page_sizes": [25, 50, 100],
        "search": search,
        "filter_payload": {
            "kind": selected_kinds,
            "active": selected_active,
            "active_scope": active_scope,
            "page": page_obj.number,
            "page_size": page_size,
            "search": search,
        },
        "kind_options": kind_options,
        "active_options": active_options,
        "inactive_count": Vendor.objects.filter(is_active=False).count(),
    }
    return render(request, "fincore/vendors/table_partial.html", context)


def vendor_update(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    try:
        vendor_id = int(request.POST.get("vendor_id") or 0)
    except (TypeError, ValueError):
        return HttpResponseBadRequest("Invalid vendor")

    vendor = get_object_or_404(Vendor, pk=vendor_id)

    name = (request.POST.get("name") or "").strip()
    kind = (request.POST.get("kind") or "").strip()
    description = (request.POST.get("description") or "").strip()
    is_active = request.POST.get("is_active") == "on"

    errors = []
    if not name:
        errors.append("Vendor name is required.")
    if kind not in dict(Vendor.KIND_CHOICES):
        errors.append("Vendor kind is required.")
    if Vendor.objects.filter(name=name, kind=kind).exclude(pk=vendor.pk).exists():
        errors.append("Vendor name must be unique within a kind.")
    if errors:
        return render(
            request,
            "fincore/accounts/form_errors.html",
            {"form_errors": errors},
            status=200,
        )

    vendor.name = name
    vendor.kind = kind
    vendor.description = description
    vendor.is_active = is_active
    vendor.save()

    resp = HttpResponse(status=204)
    resp["HX-Trigger"] = '{"vendors:refresh": true, "vendors:editClose": true}'
    return resp


def vendor_delete(request, pk):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    vendor = get_object_or_404(Vendor, pk=pk)
    in_use = Transaction.objects.filter(vendor=vendor).exists()
    if in_use:
        if vendor.is_active:
            vendor.is_active = False
            vendor.save(update_fields=["is_active"])
        action = "deactivated"
    else:
        vendor.delete()
        action = "deleted"

    resp = HttpResponse(status=204)
    resp["HX-Trigger"] = '{"vendors:refresh": true, "vendors:editClose": true}'
    resp["X-Vendor-Action"] = action
    return resp
