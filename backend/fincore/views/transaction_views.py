from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render
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
    qs = Transaction.objects.select_related("account", "category", "transfer_group").order_by("-date", "-id")
    search = request.GET.get("q", "").strip()
    if search:
        qs = qs.filter(
            Q(description__icontains=search)
            | Q(payee__icontains=search)
            | Q(account__name__icontains=search)
        )
    try:
        page_size = int(request.GET.get("page_size", 25))
    except (TypeError, ValueError):
        page_size = 25
    paginator = Paginator(qs, page_size)
    page_number = request.GET.get("page") or 1
    page_obj = paginator.get_page(page_number)
    context = {
        "page_obj": page_obj,
        "paginator": paginator,
        "page_size": page_size,
        "search": search,
        "page_sizes": [25, 50, 100],
    }
    return render(request, "fincore/transactions/table_partial.html", context)
