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
    account_ids = {acct["id"] for acct in accounts}
    if prefill_account_id not in account_ids:
        prefill_account_id = 0
    default_account_id = prefill_account_id or (accounts[0]["id"] if accounts else None)
    return render(
        request,
        "fincore/transactions/index.html",
        {
            "accounts": accounts,
            "prefill_account_id": prefill_account_id or None,
            "default_account_id": default_account_id,
        },
    )


def transaction_table(request):
    """HTMX partial for paginated transactions with simple search."""
    if not getattr(request, "htmx", False):
        query = request.META.get("QUERY_STRING", "")
        target = reverse("fincore:transaction_list")
        if query:
            target = f"{target}?{query}"
        return redirect(target)

    accounts = list(
        Account.objects.filter(is_active=True)
        .order_by("name")
        .values("id", "name", "account_type")
    )
    account_ids = {acct["id"] for acct in accounts}
    try:
        selected_account_id = int(request.GET.get("account_id") or 0)
    except (TypeError, ValueError):
        selected_account_id = 0
    if selected_account_id not in account_ids:
        selected_account_id = accounts[0]["id"] if accounts else None

    qs = Transaction.objects.select_related("account", "category", "transfer_group")
    base_qs = Transaction.objects.all()
    search = request.GET.get("q", "").strip()
    date_range = request.GET.get("date_range", "all")
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    selected_payees = [value for value in request.GET.getlist("payee") if value]
    selected_descriptions = [value for value in request.GET.getlist("description") if value]
    selected_kinds = [value for value in request.GET.getlist("kind") if value]
    amount_type = request.GET.get("amount_type", "all").strip()
    amount_min = request.GET.get("amount_min", "").strip()
    amount_max = request.GET.get("amount_max", "").strip()
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

    if selected_account_id:
        qs = qs.filter(account_id=selected_account_id)
    else:
        qs = qs.none()

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

    amount_min_val = parse_decimal(amount_min)
    amount_max_val = parse_decimal(amount_max)
    amount_type = amount_type if amount_type in {"all", "expense", "deposit"} else "all"

    def apply_amount_filters(queryset):
        if amount_type == "expense":
            queryset = queryset.filter(amount__lt=0)
            if amount_min_val is not None:
                queryset = queryset.filter(amount__lte=-amount_min_val)
            if amount_max_val is not None:
                queryset = queryset.filter(amount__gte=-amount_max_val)
        elif amount_type == "deposit":
            queryset = queryset.filter(amount__gt=0)
            if amount_min_val is not None:
                queryset = queryset.filter(amount__gte=amount_min_val)
            if amount_max_val is not None:
                queryset = queryset.filter(amount__lte=amount_max_val)
        return queryset

    if search:
        search_terms = [term for term in search.split() if term]
        if search_terms:
            for term in search_terms:
                qs = qs.filter(
                    Q(description__icontains=term)
                    | Q(payee__icontains=term)
                    | Q(account__name__icontains=term)
                )

    sort_map = {
        "date": "date",
        "payee": "payee",
        "description": "description",
        "kind": "kind",
        "amount": "amount",
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
    qs = apply_amount_filters(qs)
    paginator = Paginator(qs, page_size)
    page_number = request.GET.get("page") or 1
    page_obj = paginator.get_page(page_number)
    
    # Calculate available options from filtered queryset (qs), not all transactions
    # Exclude currently applied filters from the options to show what's available
    options_qs = Transaction.objects.all()
    if selected_account_id:
        options_qs = options_qs.filter(account_id=selected_account_id)
    else:
        options_qs = options_qs.none()
    
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
        search_terms = [term for term in search.split() if term]
        if search_terms:
            for term in search_terms:
                options_qs = options_qs.filter(
                    Q(description__icontains=term)
                    | Q(payee__icontains=term)
                    | Q(account__name__icontains=term)
                )
    options_qs = apply_amount_filters(options_qs)
    
    # Payee options - exclude payee filter to show available payees
    payee_qs = options_qs
    if selected_descriptions:
        payee_qs = payee_qs.filter(description__in=selected_descriptions)
    if selected_kinds:
        payee_qs = payee_qs.filter(kind__in=selected_kinds)
    payee_options = list(
        payee_qs.exclude(payee="").values_list("payee", flat=True).distinct().order_by("payee")
    )
    
    # Description options - exclude description filter to show available descriptions
    desc_qs = options_qs
    if selected_payees:
        desc_qs = desc_qs.filter(payee__in=selected_payees)
    if selected_kinds:
        desc_qs = desc_qs.filter(kind__in=selected_kinds)
    description_options = list(
        desc_qs.exclude(description="").values_list("description", flat=True).distinct().order_by("description")
    )
    
    # Kind options - exclude kind filter to show available kinds
    kind_qs = options_qs
    if selected_payees:
        kind_qs = kind_qs.filter(payee__in=selected_payees)
    if selected_descriptions:
        kind_qs = kind_qs.filter(description__in=selected_descriptions)
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
    if amount_type != "all" or amount_min_val is not None or amount_max_val is not None:
        label = "Amount"
        if amount_type == "expense":
            label = "Expense"
        elif amount_type == "deposit":
            label = "Deposit"
        if amount_min_val is not None or amount_max_val is not None:
            summary_parts.append(f"{label}: {amount_min or ''}-{amount_max or ''}")
        else:
            summary_parts.append(label)
    filter_summary = ", ".join([part for part in summary_parts if part]) or "No filters"

    query_params = request.GET.copy()
    query_params.pop("page", None)

    context = {
        "page_obj": page_obj,
        "paginator": paginator,
        "page_size": page_size,
        "search": search,
        "page_sizes": [25, 50, 100],
        "accounts": accounts,
        "selected_account_id": selected_account_id,
        "filter_payload": {
            "account_id": selected_account_id,
            "date_range": date_range or "all",
            "date_from": date_from,
            "date_to": date_to,
            "payee": selected_payees,
            "description": selected_descriptions,
            "kind": selected_kinds,
            "amount_type": amount_type,
            "amount_min": amount_min,
            "amount_max": amount_max,
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
