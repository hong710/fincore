from django.shortcuts import render


def account_list(request):
    """
    Accounts page shell. Data will be server-rendered/HTMX-driven later.
    """
    return render(request, "fincore/accounts/index.html")
