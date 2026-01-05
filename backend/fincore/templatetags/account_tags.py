from django import template

register = template.Library()


@register.inclusion_tag("fincore/accounts/action_menu.html")
def account_actions(account):
    """
    Renders the action dropdown for an account.
    """
    return {"account": account}
