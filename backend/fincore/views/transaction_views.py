import calendar
from datetime import date, datetime, timedelta
from uuid import uuid4
from decimal import Decimal, InvalidOperation

from django.core.paginator import Paginator
from django.db import transaction as db_transaction
from django.db.models import Q
from django.db.models.functions import Abs
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from fincore.models import Account, Category, Transaction, TransferGroup, Vendor


def _render_transfer_list(request, category=None):
    groups = (
        TransferGroup.objects.prefetch_related(
            "transactions__account",
            "transactions__vendor",
            "transactions__category",
        )
        .order_by("-created_at")
    )
    page_size = 25
    try:
        page_size = int(request.GET.get("page_size") or page_size)
    except (TypeError, ValueError):
        page_size = 25
    paginator = Paginator(groups, page_size)
    try:
        page_number = int(request.GET.get("page") or 1)
    except (TypeError, ValueError):
        page_number = 1
    page_obj = paginator.get_page(page_number)
    rows = []
    for group in page_obj.object_list:
        txns = list(group.transactions.all())
        if not txns:
            continue
        txns.sort(key=lambda t: (t.amount, t.id))
        txn_out = next((t for t in txns if t.amount < 0), txns[0])
        txn_in = next((t for t in txns if t.amount > 0), txns[-1])
        rows.append(
            {
                "group": group,
                "txn_out": txn_out,
                "txn_in": txn_in,
                "count": len(txns),
            }
        )
    return render(
        request,
        "fincore/transactions/transfers.html",
        {
            "category": category,
            "page_obj": page_obj,
            "rows": rows,
        },
    )


def category_report(request, pk):
    category = get_object_or_404(Category, pk=pk)
    if category.kind == "transfer":
        return _render_transfer_list(request, category=category)

    date_range = (request.GET.get("date_range") or "this_year").strip()
    date_from = (request.GET.get("date_from") or "").strip()
    date_to = (request.GET.get("date_to") or "").strip()

    valid_ranges = {"this_year", "last_year", "this_month", "last_month", "this_quarter", "custom"}
    if date_range not in valid_ranges:
        date_range = "this_year"

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

    qs = (
        Transaction.objects.select_related("account", "vendor")
        .filter(category=category)
        .order_by("-date", "-id")
    )

    start_date = None
    end_date = None
    today = date.today()
    if date_range == "this_month":
        start_date, end_date = month_bounds(today.year, today.month)
    elif date_range == "last_month":
        last_month = today.month - 1 or 12
        year_value = today.year - 1 if today.month == 1 else today.year
        start_date, end_date = month_bounds(year_value, last_month)
    elif date_range == "last_year":
        start_date = date(today.year - 1, 1, 1)
        end_date = date(today.year - 1, 12, 31)
    elif date_range == "this_year":
        start_date = date(today.year, 1, 1)
        end_date = date(today.year, 12, 31)
    elif date_range == "this_quarter":
        quarter_key = f"q{((today.month - 1) // 3) + 1}"
        start_date, end_date = quarter_bounds(today.year, quarter_key)
    elif date_range == "custom":
        start_date = parse_date(date_from)
        end_date = parse_date(date_to)

    if start_date:
        qs = qs.filter(date__gte=start_date)
    if end_date:
        qs = qs.filter(date__lte=end_date)

    page_size = 25
    try:
        page_number = int(request.GET.get("page") or 1)
    except (TypeError, ValueError):
        page_number = 1
    paginator = Paginator(qs, page_size)
    page_obj = paginator.get_page(page_number)

    goto_date_range = date_range
    goto_date_from = date_from
    goto_date_to = date_to
    if date_range == "this_quarter":
        goto_date_range = f"q{((today.month - 1) // 3) + 1}"
        goto_date_from = ""
        goto_date_to = ""
    elif date_range in {"this_year", "this_month", "last_month"}:
        goto_date_from = ""
        goto_date_to = ""

    query_params = request.GET.copy()
    query_params.pop("page", None)

    return render(
        request,
        "fincore/categories/report.html",
        {
            "category": category,
            "page_obj": page_obj,
            "page_size": page_size,
            "date_range": date_range,
            "date_from": date_from,
            "date_to": date_to,
            "goto_date_range": goto_date_range,
            "goto_date_from": goto_date_from,
            "goto_date_to": goto_date_to,
            "filter_query": query_params.urlencode(),
            "report_ranges": [
                ("this_year", "This year"),
                ("last_year", "Last year"),
                ("this_month", "This month"),
                ("last_month", "Last month"),
                ("this_quarter", "This quarter"),
                ("custom", "Custom dates"),
            ],
        },
    )


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
    categories = list(
        Category.objects.filter(is_active=True)
        .exclude(kind="transfer")
        .order_by("kind", "name")
        .values("id", "name", "kind")
    )
    vendors = list(
        Vendor.objects.filter(is_active=True)
        .order_by("name")
        .values("id", "name", "kind")
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
            "categories": categories,
            "vendors": vendors,
            "prefill_account_id": prefill_account_id or None,
            "default_account_id": default_account_id,
            "table_query": request.GET.urlencode(),
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

    qs = Transaction.objects.select_related("account", "category", "transfer_group", "vendor")
    base_qs = Transaction.objects.all()
    search = request.GET.get("q", "").strip()
    date_range = request.GET.get("date_range", "all")
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    selected_payees = [value for value in request.GET.getlist("payee") if value]
    selected_descriptions = [value for value in request.GET.getlist("description") if value]
    selected_kinds = [value for value in request.GET.getlist("kind") if value]
    selected_category_ids = []
    for value in request.GET.getlist("category"):
        try:
            selected_category_ids.append(int(value))
        except (TypeError, ValueError):
            continue
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

    if selected_category_ids:
        qs = qs.filter(category_id__in=selected_category_ids)

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
    if selected_category_ids:
        payee_qs = payee_qs.filter(category_id__in=selected_category_ids)
    payee_options = list(
        payee_qs.exclude(payee="").values_list("payee", flat=True).distinct().order_by("payee")
    )
    
    # Description options - exclude description filter to show available descriptions
    desc_qs = options_qs
    if selected_payees:
        desc_qs = desc_qs.filter(payee__in=selected_payees)
    if selected_kinds:
        desc_qs = desc_qs.filter(kind__in=selected_kinds)
    if selected_category_ids:
        desc_qs = desc_qs.filter(category_id__in=selected_category_ids)
    description_options = list(
        desc_qs.exclude(description="").values_list("description", flat=True).distinct().order_by("description")
    )
    
    # Kind options - exclude kind filter to show available kinds
    kind_qs = options_qs
    if selected_payees:
        kind_qs = kind_qs.filter(payee__in=selected_payees)
    if selected_descriptions:
        kind_qs = kind_qs.filter(description__in=selected_descriptions)
    if selected_category_ids:
        kind_qs = kind_qs.filter(category_id__in=selected_category_ids)
    available_kinds = list(kind_qs.values_list("kind", flat=True).distinct())
    kind_options = [choice[0] for choice in Transaction.KIND_CHOICES if choice[0] in available_kinds]

    category_qs = options_qs.exclude(category_id__isnull=True).exclude(category__kind="transfer")
    if selected_payees:
        category_qs = category_qs.filter(payee__in=selected_payees)
    if selected_descriptions:
        category_qs = category_qs.filter(description__in=selected_descriptions)
    if selected_kinds:
        category_qs = category_qs.filter(kind__in=selected_kinds)
    category_options = list(
        category_qs.values("category_id", "category__name")
        .distinct()
        .order_by("category__name")
    )

    for value in selected_payees:
        if value not in payee_options:
            payee_options.append(value)
    for value in selected_descriptions:
        if value not in description_options:
            description_options.append(value)
    for value in selected_kinds:
        if value not in kind_options:
            kind_options.append(value)
    if selected_category_ids:
        selected_categories = list(
            Category.objects.filter(id__in=selected_category_ids)
            .exclude(kind="transfer")
            .values("id", "name")
        )
        existing_ids = {item["category_id"] for item in category_options}
        for category in selected_categories:
            if category["id"] not in existing_ids:
                category_options.append(
                    {"category_id": category["id"], "category__name": category["name"]}
                )

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
    if selected_category_ids:
        summary_parts.append(f"Category: {len(selected_category_ids)}")
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
            "category": selected_category_ids,
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
        "category_options": category_options,
        "filter_summary": filter_summary,
        "filter_query": query_params.urlencode(),
    }
    return render(request, "fincore/transactions/table_partial.html", context)


def transaction_bulk_action(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    action = (request.POST.get("action") or "").strip()
    raw_ids = (request.POST.get("transaction_ids") or "").strip()
    if not raw_ids:
        return render(
            request,
            "fincore/accounts/form_errors.html",
            {"form_errors": ["Select at least one transaction."]},
            status=200,
        )
    try:
        transaction_ids = [int(val) for val in raw_ids.split(",") if val.strip()]
    except ValueError:
        return HttpResponseBadRequest("Invalid transaction selection")

    if action not in {"category", "payee"}:
        return render(
            request,
            "fincore/accounts/form_errors.html",
            {"form_errors": ["Select a supported bulk action."]},
            status=200,
        )

    if action == "category":
        try:
            category_id = int(request.POST.get("category_id") or 0)
        except (TypeError, ValueError):
            return HttpResponseBadRequest("Invalid category")

        category = Category.objects.filter(is_active=True, pk=category_id).first()
        if not category or category.kind == "transfer":
            return render(
                request,
                "fincore/accounts/form_errors.html",
                {"form_errors": ["Select a valid active category."]},
                status=200,
            )

        Transaction.objects.filter(id__in=transaction_ids).update(
            category=category, kind=category.kind
        )
    elif action == "payee":
        try:
            vendor_id = int(request.POST.get("vendor_id") or 0)
        except (TypeError, ValueError):
            return HttpResponseBadRequest("Invalid vendor")

        vendor = Vendor.objects.filter(is_active=True, pk=vendor_id).first()
        if not vendor:
            return render(
                request,
                "fincore/accounts/form_errors.html",
                {"form_errors": ["Select a valid active vendor."]},
                status=200,
            )

        Transaction.objects.filter(id__in=transaction_ids).update(vendor=vendor)

    resp = HttpResponse(status=204)
    resp["HX-Trigger"] = '{"transactions:refresh": true, "transactions:bulkClose": true}'
    return resp


def transaction_transfer_matches(request):
    try:
        txn_id = int(request.GET.get("transaction_id") or 0)
    except (TypeError, ValueError):
        return HttpResponseBadRequest("Invalid transaction")

    txn = get_object_or_404(Transaction, pk=txn_id)
    if txn.transfer_group_id or txn.is_locked:
        return render(
            request,
            "fincore/transactions/transfer_match_list.html",
            {"transaction": txn, "matches": [], "errors": ["Transaction cannot be matched."]},
        )

    start_date = txn.date - timedelta(days=30)
    end_date = txn.date + timedelta(days=30)

    matches = (
        Transaction.objects.select_related("account")
        .filter(
            transfer_group__isnull=True,
            is_locked=False,
            date__range=(start_date, end_date),
            amount=-txn.amount,
        )
        .exclude(account_id=txn.account_id)
        .exclude(pk=txn.pk)
        .order_by("date", "id")
    )

    debug_candidates = []
    if not matches:
        candidates = (
            Transaction.objects.select_related("account")
            .filter(date__range=(start_date, end_date))
            .exclude(account_id=txn.account_id)
            .exclude(pk=txn.pk)
            .annotate(abs_amount=Abs("amount"))
            .filter(abs_amount=abs(txn.amount))
            .order_by("date", "id")
        )
        for candidate in candidates[:10]:
            reasons = []
            if candidate.transfer_group_id:
                reasons.append("already paired")
            if candidate.is_locked:
                reasons.append("locked")
            if candidate.amount != -txn.amount:
                reasons.append("amount sign mismatch")
            debug_candidates.append(
                {
                    "transaction": candidate,
                    "reasons": reasons or ["unknown"],
                }
            )

    return render(
        request,
        "fincore/transactions/transfer_match_list.html",
        {
            "transaction": txn,
            "matches": matches,
            "errors": [],
            "debug_candidates": debug_candidates,
        },
    )


def transaction_transfer_pair(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    try:
        txn_id = int(request.POST.get("transaction_id") or 0)
        match_id = int(request.POST.get("match_id") or 0)
    except (TypeError, ValueError):
        return HttpResponseBadRequest("Invalid transaction")

    if txn_id == match_id:
        return HttpResponseBadRequest("Invalid match")

    with db_transaction.atomic():
        txn = get_object_or_404(Transaction.objects.select_for_update(), pk=txn_id)
        match = get_object_or_404(Transaction.objects.select_for_update(), pk=match_id)

        errors = []
        if txn.transfer_group_id or match.transfer_group_id:
            errors.append("One of the transactions is already paired.")
        if txn.is_locked or match.is_locked:
            errors.append("One of the transactions is locked.")
        if txn.account_id == match.account_id:
            errors.append("Transfers must be between different accounts.")
        if txn.amount + match.amount != 0:
            errors.append("Transfer amounts must sum to zero.")
        if abs(txn.amount) != abs(match.amount):
            errors.append("Transfer amounts must be equal and opposite.")
        if abs((txn.date - match.date).days) > 30:
            errors.append("Transfer dates must be within 30 days.")
        if errors:
            return render(
                request,
                "fincore/accounts/form_errors.html",
                {"form_errors": errors},
                status=200,
            )

        group = TransferGroup.objects.create(reference=str(uuid4()))
        for item in (txn, match):
            item.kind = "transfer"
            item.category = None
            item.transfer_group = group
            item.is_locked = True
            item.save(update_fields=["kind", "category", "transfer_group", "is_locked"])

    resp = HttpResponse(status=204)
    resp["HX-Trigger"] = '{"transactions:refresh": true, "transactions:transferClose": true, "transactions:editClose": true}'
    return resp


def transfer_list(request):
    transfer_category = Category.objects.filter(kind="transfer").order_by("id").first()
    if transfer_category:
        return redirect(reverse("fincore:category_report", args=[transfer_category.id]))
    return _render_transfer_list(request)


def transfer_unpair(request, group_id):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    group = get_object_or_404(TransferGroup.objects.prefetch_related("transactions"), pk=group_id)
    txns = list(group.transactions.all())
    if not txns:
        return redirect(reverse("fincore:transfer_list"))

    with db_transaction.atomic():
        Transaction.objects.filter(transfer_group=group).update(
            transfer_group=None,
            category=None,
            is_locked=False,
        )
        for txn in txns:
            new_kind = "income" if txn.amount > 0 else "expense"
            Transaction.objects.filter(pk=txn.pk).update(kind=new_kind)
        group.delete()

    return redirect(reverse("fincore:transfer_list"))


def transaction_delete(request, pk):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    txn = get_object_or_404(Transaction, pk=pk)
    errors = []
    if txn.is_imported:
        errors.append("Imported transactions cannot be deleted.")
    if txn.transfer_group_id:
        errors.append("Transfers must be corrected via reversal.")
    if txn.is_locked:
        errors.append("Locked transactions cannot be deleted.")
    if errors:
        return render(
            request,
            "fincore/accounts/form_errors.html",
            {"form_errors": errors},
            status=200,
        )

    txn.delete()
    resp = HttpResponse(status=204)
    resp["HX-Trigger"] = '{"transactions:editClose": true}'
    return resp


def transaction_update(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    try:
        txn_id = int(request.POST.get("transaction_id") or 0)
    except (TypeError, ValueError):
        return HttpResponseBadRequest("Invalid transaction")

    txn = get_object_or_404(Transaction, pk=txn_id)

    vendor_id = (request.POST.get("vendor_id") or "").strip()
    category_id = request.POST.get("category_id") or None
    category = None
    vendor = None
    if vendor_id:
        try:
            vendor = Vendor.objects.get(pk=int(vendor_id), is_active=True)
        except (Vendor.DoesNotExist, ValueError, TypeError):
            return render(
                request,
                "fincore/accounts/form_errors.html",
                {"form_errors": ["Invalid vendor selected."]},
                status=200,
            )
    if category_id:
        try:
            category = Category.objects.get(pk=int(category_id))
        except (Category.DoesNotExist, ValueError, TypeError):
            return render(
                request,
                "fincore/accounts/form_errors.html",
                {"form_errors": ["Invalid category selected."]},
                status=200,
            )

    if txn.transfer_group_id:
        return render(
            request,
            "fincore/accounts/form_errors.html",
            {"form_errors": ["Transfers must be corrected via reversal."]},
            status=200,
        )
    if txn.is_locked:
        return render(
            request,
            "fincore/accounts/form_errors.html",
            {"form_errors": ["Locked transactions cannot be edited."]},
            status=200,
        )

    if txn.is_imported:
        txn.vendor = vendor
        txn.category = category
        txn.kind = category.kind if category else txn.kind
        txn.save()
    else:
        raw_date = request.POST.get("date")
        raw_amount = request.POST.get("amount")
        description = (request.POST.get("description") or "").strip()

        if not raw_date:
            return render(
                request,
                "fincore/accounts/form_errors.html",
                {"form_errors": ["Date is required."]},
                status=200,
            )
        try:
            parsed_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except ValueError:
            return render(
                request,
                "fincore/accounts/form_errors.html",
                {"form_errors": ["Invalid date."]},
                status=200,
            )
        try:
            amount = Decimal(str(raw_amount))
        except (InvalidOperation, ValueError, TypeError):
            return render(
                request,
                "fincore/accounts/form_errors.html",
                {"form_errors": ["Invalid amount."]},
                status=200,
            )

        txn.date = parsed_date
        txn.amount = amount
        txn.description = description
        txn.vendor = vendor
        txn.category = category
        txn.kind = category.kind if category else txn.kind
        txn.save()

    resp = HttpResponse(status=204)
    resp["HX-Trigger"] = '{"transactions:refresh": true, "transactions:editClose": true}'
    return resp
