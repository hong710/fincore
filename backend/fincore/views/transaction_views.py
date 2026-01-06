import calendar
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import reverse
from fincore.models import Account, Transaction


def transaction_list(request):
    """
    Transaction list page server-rendered shell that loads our HTMX/Alpine UI.
    Data is mocked in the template for now; replace with real query + HTMX soon.
    """
    accounts = list(
        Account.objects.filter(is_active=True)
        .order_by("name")
        .values("id", "name", "account_type")
    )
    try:
        prefill_account_id = int(request.GET.get("import_account") or 0)
    except (TypeError, ValueError):
        prefill_account_id = 0
    if not any(acct["id"] == prefill_account_id for acct in accounts):
        prefill_account_id = 0
    return render(
        request,
        "fincore/transactions/index.html",
        {"accounts": accounts, "prefill_account_id": prefill_account_id or None},
    )


def transaction_table(request):
    """HTMX partial for paginated transactions with simple search."""
    if not getattr(request, "htmx", False):
        query = request.META.get("QUERY_STRING", "")
        target = reverse("fincore:transaction_list")
        if query:
            target = f"{target}?{query}"
        return redirect(target)

    qs = Transaction.objects.select_related("account", "category", "transfer_group")
    base_qs = Transaction.objects.all()
    search = request.GET.get("q", "").strip()
    date_range = request.GET.get("date_range", "all")
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    selected_payees = [value for value in request.GET.getlist("payee") if value]
    selected_descriptions = [value for value in request.GET.getlist("description") if value]
    selected_kinds = [value for value in request.GET.getlist("kind") if value]
    spent_min = request.GET.get("spent_min", "").strip()
    spent_max = request.GET.get("spent_max", "").strip()
    received_min = request.GET.get("received_min", "").strip()
    received_max = request.GET.get("received_max", "").strip()
    sort_field = request.GET.get("sort", "").strip()
    sort_dir = request.GET.get("dir", "asc").strip()

    def parse_date(raw_value):
        raw_value = (raw_value or "").strip()
        if not raw_value:
            return None
        try:
            return datetime.strptime(raw_value, "%Y-%m-%d").date()
        except ValueError:
            return None

    def parse_decimal(raw_value):
        raw_value = (raw_value or "").strip()
        if raw_value == "":
            return None
        try:
            return Decimal(raw_value)
        except (InvalidOperation, ValueError):
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
            qs = qs.filter(date__gte=start_date)
        if end_date:
            qs = qs.filter(date__lte=end_date)

    if selected_payees:
        qs = qs.filter(payee__in=selected_payees)

    if selected_descriptions:
        qs = qs.filter(description__in=selected_descriptions)

    if selected_kinds:
        qs = qs.filter(kind__in=selected_kinds)

    spent_min_val = parse_decimal(spent_min)
    spent_max_val = parse_decimal(spent_max)
    if spent_min_val is not None or spent_max_val is not None:
        qs = qs.filter(amount__lt=0)
        if spent_min_val is not None:
            qs = qs.filter(amount__lte=-spent_min_val)
        if spent_max_val is not None:
            qs = qs.filter(amount__gte=-spent_max_val)

    received_min_val = parse_decimal(received_min)
    received_max_val = parse_decimal(received_max)
    if received_min_val is not None or received_max_val is not None:
        qs = qs.filter(amount__gt=0)
        if received_min_val is not None:
            qs = qs.filter(amount__gte=received_min_val)
        if received_max_val is not None:
            qs = qs.filter(amount__lte=received_max_val)

    if search:
        qs = qs.filter(
            Q(description__icontains=search)
            | Q(payee__icontains=search)
            | Q(account__name__icontains=search)
        )

    sort_map = {
        "date": "date",
        "payee": "payee",
        "description": "description",
        "kind": "kind",
        "spent": "amount",
        "received": "amount",
    }
    if sort_field in sort_map:
        ordering = sort_map[sort_field]
        if sort_dir == "desc":
            ordering = f"-{ordering}"
        qs = qs.order_by(ordering, "-id")
    else:
        qs = qs.order_by("-date", "-id")
    try:
        page_size = int(request.GET.get("page_size", 25))
    except (TypeError, ValueError):
        page_size = 25
    paginator = Paginator(qs, page_size)
    page_number = request.GET.get("page") or 1
    page_obj = paginator.get_page(page_number)
    
    # Calculate available options from filtered queryset (qs), not all transactions
    # Exclude currently applied filters from the options to show what's available
    options_qs = Transaction.objects.all()
    
    # Apply all filters EXCEPT the one we're calculating options for
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
            options_qs = options_qs.filter(date__gte=start_date)
        if end_date:
            options_qs = options_qs.filter(date__lte=end_date)
    
    if search:
        options_qs = options_qs.filter(
            Q(description__icontains=search)
            | Q(payee__icontains=search)
            | Q(account__name__icontains=search)
        )
    
    # Payee options - exclude payee filter to show available payees
    payee_qs = options_qs
    if selected_descriptions:
        payee_qs = payee_qs.filter(description__in=selected_descriptions)
    if selected_kinds:
        payee_qs = payee_qs.filter(kind__in=selected_kinds)
    if spent_min_val is not None or spent_max_val is not None:
        payee_qs = payee_qs.filter(amount__lt=0)
        if spent_min_val is not None:
            payee_qs = payee_qs.filter(amount__lte=-spent_min_val)
        if spent_max_val is not None:
            payee_qs = payee_qs.filter(amount__gte=-spent_max_val)
    if received_min_val is not None or received_max_val is not None:
        payee_qs = payee_qs.filter(amount__gt=0)
        if received_min_val is not None:
            payee_qs = payee_qs.filter(amount__gte=received_min_val)
        if received_max_val is not None:
            payee_qs = payee_qs.filter(amount__lte=received_max_val)
    
    payee_options = list(
        payee_qs.exclude(payee="").values_list("payee", flat=True).distinct().order_by("payee")
    )
    
    # Description options - exclude description filter to show available descriptions
    desc_qs = options_qs
    if selected_payees:
        desc_qs = desc_qs.filter(payee__in=selected_payees)
    if selected_kinds:
        desc_qs = desc_qs.filter(kind__in=selected_kinds)
    if spent_min_val is not None or spent_max_val is not None:
        desc_qs = desc_qs.filter(amount__lt=0)
        if spent_min_val is not None:
            desc_qs = desc_qs.filter(amount__lte=-spent_min_val)
        if spent_max_val is not None:
            desc_qs = desc_qs.filter(amount__gte=-spent_max_val)
    if received_min_val is not None or received_max_val is not None:
        desc_qs = desc_qs.filter(amount__gt=0)
        if received_min_val is not None:
            desc_qs = desc_qs.filter(amount__gte=received_min_val)
        if received_max_val is not None:
            desc_qs = desc_qs.filter(amount__lte=received_max_val)
    
    description_options = list(
        desc_qs.exclude(description="").values_list("description", flat=True).distinct().order_by("description")
    )
    
    # Kind options - exclude kind filter to show available kinds
    kind_qs = options_qs
    if selected_payees:
        kind_qs = kind_qs.filter(payee__in=selected_payees)
    if selected_descriptions:
        kind_qs = kind_qs.filter(description__in=selected_descriptions)
    if spent_min_val is not None or spent_max_val is not None:
        kind_qs = kind_qs.filter(amount__lt=0)
        if spent_min_val is not None:
            kind_qs = kind_qs.filter(amount__lte=-spent_min_val)
        if spent_max_val is not None:
            kind_qs = kind_qs.filter(amount__gte=-spent_max_val)
    if received_min_val is not None or received_max_val is not None:
        kind_qs = kind_qs.filter(amount__gt=0)
        if received_min_val is not None:
            kind_qs = kind_qs.filter(amount__gte=received_min_val)
        if received_max_val is not None:
            kind_qs = kind_qs.filter(amount__lte=received_max_val)
    
    available_kinds = list(kind_qs.values_list("kind", flat=True).distinct())
    kind_options = [choice[0] for choice in Transaction.KIND_CHOICES if choice[0] in available_kinds]

    for value in selected_payees:
        if value not in payee_options:
            payee_options.append(value)
    for value in selected_descriptions:
        if value not in description_options:
            description_options.append(value)
    for value in selected_kinds:
        if value not in kind_options:
            kind_options.append(value)

    date_labels = {
        "this_month": "This month",
        "last_month": "Last month",
        "q1": "1st quarter",
        "q2": "2nd quarter",
        "q3": "3rd quarter",
        "q4": "4th quarter",
        "this_year": "This year",
        "last_year": "Last year",
        "custom": "Custom",
    }
    summary_parts = []
    if date_range and date_range != "all":
        if date_range == "custom":
            summary_parts.append(f"Date: {date_from or ''}→{date_to or ''}".strip())
        else:
            summary_parts.append(f"Date: {date_labels.get(date_range, date_range)}")
    if selected_payees:
        summary_parts.append(f"Payee: {len(selected_payees)}")
    if selected_descriptions:
        summary_parts.append(f"Desc: {len(selected_descriptions)}")
    if selected_kinds:
        summary_parts.append(f"Kind: {len(selected_kinds)}")
    if spent_min_val is not None or spent_max_val is not None:
        summary_parts.append(f"Spent: {spent_min or ''}-{spent_max or ''}")
    if received_min_val is not None or received_max_val is not None:
        summary_parts.append(f"Recv: {received_min or ''}-{received_max or ''}")
    filter_summary = ", ".join([part for part in summary_parts if part]) or "No filters"

    query_params = request.GET.copy()
    query_params.pop("page", None)

    context = {
        "page_obj": page_obj,
        "paginator": paginator,
        "page_size": page_size,
        "search": search,
        "page_sizes": [25, 50, 100],
        "filter_payload": {
            "date_range": date_range or "all",
            "date_from": date_from,
            "date_to": date_to,
            "payee": selected_payees,
            "description": selected_descriptions,
            "kind": selected_kinds,
            "spent_min": spent_min,
            "spent_max": spent_max,
            "received_min": received_min,
            "received_max": received_max,
            "sort": sort_field,
            "dir": sort_dir,
            "page": page_obj.number,
            "page_size": page_size,
            "search": search,
        },
        "payee_options": payee_options,
        "description_options": description_options,
        "kind_options": kind_options,
        "filter_summary": filter_summary,
        "filter_query": query_params.urlencode(),
    }
    return render(request, "fincore/transactions/table_partial.html", context)
