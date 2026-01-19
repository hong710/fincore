from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from fincore.models import Category, Transaction


def category_list(request):
    return render(request, "fincore/categories/index.html")


def category_create(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    name = (request.POST.get("name") or "").strip()
    kind = (request.POST.get("kind") or "").strip()
    description = (request.POST.get("description") or "").strip()
    is_active = request.POST.get("is_active") == "on"

    errors = []
    if not name:
        errors.append("Category name is required.")
    if kind not in dict(Category.KIND_CHOICES):
        errors.append("Category kind is required.")
    if Category.objects.filter(name=name, kind=kind).exists():
        errors.append("Category name must be unique within a kind.")
    if errors:
        return render(
            request,
            "fincore/accounts/form_errors.html",
            {"form_errors": errors},
            status=200,
        )

    Category.objects.create(
        name=name,
        kind=kind,
        description=description,
        is_active=is_active,
    )

    resp = HttpResponse(status=204)
    resp["HX-Trigger"] = '{"categories:refresh": true, "categories:createClose": true}'
    return resp


def category_table(request):
    if not getattr(request, "htmx", False):
        query = request.META.get("QUERY_STRING", "")
        target = reverse("fincore:category_list")
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

    qs = Category.objects.annotate(transaction_count=Count("transactions"))
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

    options_base = Category.objects.all()
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
    kind_options = [choice[0] for choice in Category.KIND_CHOICES if choice[0] in available_kinds]
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
        "inactive_count": Category.objects.filter(is_active=False).count(),
    }
    return render(request, "fincore/categories/table_partial.html", context)


def category_update(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    try:
        category_id = int(request.POST.get("category_id") or 0)
    except (TypeError, ValueError):
        return HttpResponseBadRequest("Invalid category")

    category = get_object_or_404(Category, pk=category_id)

    name = (request.POST.get("name") or "").strip()
    kind = (request.POST.get("kind") or "").strip()
    description = (request.POST.get("description") or "").strip()
    is_active = request.POST.get("is_active") == "on"

    errors = []
    if not name:
        errors.append("Category name is required.")
    if kind not in dict(Category.KIND_CHOICES):
        errors.append("Category kind is required.")
    if Category.objects.filter(name=name, kind=kind).exclude(pk=category.pk).exists():
        errors.append("Category name must be unique within a kind.")
    if errors:
        return render(
            request,
            "fincore/accounts/form_errors.html",
            {"form_errors": errors},
            status=200,
        )

    category.name = name
    category.kind = kind
    category.description = description
    category.is_active = is_active
    category.save()

    Transaction.objects.filter(category=category).update(kind=category.kind)

    resp = HttpResponse(status=204)
    resp["HX-Trigger"] = '{"categories:refresh": true, "categories:editClose": true}'
    return resp


def category_delete(request, pk):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    category = get_object_or_404(Category, pk=pk)
    in_use = Transaction.objects.filter(category=category).exists()
    if in_use:
        if category.is_active:
            category.is_active = False
            category.save(update_fields=["is_active"])
        action = "deactivated"
    else:
        category.delete()
        action = "deleted"

    resp = HttpResponse(status=204)
    resp["HX-Trigger"] = '{"categories:refresh": true, "categories:editClose": true}'
    resp["X-Category-Action"] = action
    return resp
