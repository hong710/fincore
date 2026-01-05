from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def currency(value):
    """
    Format a numeric value as currency with thousands separators.
    """
    if value is None:
        return "$0.00"
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError):
        return "$0.00"
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    return f"{sign}${amount:,.2f}"
