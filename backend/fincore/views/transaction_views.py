from django.shortcuts import render


def transaction_list(request):
    """
    Transaction list page server-rendered shell that loads our HTMX/Alpine UI.
    Data is mocked in the template for now; replace with real query + HTMX soon.
    """
    return render(request, "fincore/transactions/index.html")
