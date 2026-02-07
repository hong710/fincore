from django.db.models import Count

from fincore.models import Account


def selectable_accounts():
    """
    Return only leaf accounts (no children) for selection in forms/filters.
    Parent accounts are organizational only and should not be directly selectable.
    """
    return (
        Account.objects.filter(is_active=True)
        .annotate(child_count=Count("children"))
        .filter(child_count=0)
        .order_by("name")
    )
