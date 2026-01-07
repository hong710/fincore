import json

from django import template
from django.urls import reverse
from django.utils.html import format_html
from django.utils.html import escapejs

register = template.Library()

BASE_ITEM_CLASS = (
    "block w-full rounded-md px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50 whitespace-nowrap"
)
DANGER_ITEM_CLASS = (
    "block w-full rounded-md px-3 py-2 text-left text-sm text-rose-700 hover:bg-rose-50 whitespace-nowrap"
)


@register.inclusion_tag("fincore/components/action_menu.html")
def account_actions(account):
    """
    Renders the action dropdown for an account.
    """
    edit_payload = {
        "id": account.id,
        "name": account.name,
        "account_type": account.account_type,
        "institution": account.institution or "",
        "notes": account.description or "",
        "is_active": bool(account.is_active),
    }
    delete_payload = {"id": account.id, "name": account.name}
    items = [
        {
            "type": "button",
            "label": "Edit",
            "class": BASE_ITEM_CLASS,
            "attrs": format_html(
                "data-payload='{payload}' @click.stop=\"openId = null; window.dispatchEvent(new CustomEvent('open-edit', {{ detail: JSON.parse($el.dataset.payload) }}))\"",
                payload=json.dumps(edit_payload),
            ),
        },
        {
            "type": "link",
            "label": "Review imports",
            "href": reverse("fincore:account_imports", args=[account.id]),
            "class": BASE_ITEM_CLASS,
            "attrs": format_html('@click="openId = null"'),
        },
    ]
    if account.is_active:
        items.append(
            {
                "type": "link",
                "label": "Import CSV",
                "href": f"{reverse('fincore:transaction_list')}?import_account={account.id}",
                "class": BASE_ITEM_CLASS,
                "attrs": format_html('@click="openId = null"'),
            }
        )
    else:
        items.append({"disabled": True, "label": "Import CSV"})
    items.append(
        {
            "type": "button",
            "label": "Delete",
            "class": DANGER_ITEM_CLASS,
            "attrs": format_html(
                "data-payload='{payload}' @click.stop=\"openId = null; window.dispatchEvent(new CustomEvent('open-delete', {{ detail: JSON.parse($el.dataset.payload) }}))\"",
                payload=json.dumps(delete_payload),
            ),
        }
    )
    return {
        "label": "Actions",
        "items": items,
        "menu_id": f"account-{account.id}",
        "wrapper_class": "w-full justify-end",
        "button_class": "inline-flex items-center justify-center gap-1 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm hover:bg-slate-50 whitespace-nowrap",
        "menu_class": "absolute right-0 top-full z-50 mt-1 min-w-[180px] space-y-1 rounded-md border border-slate-200 bg-white p-2 shadow-lg",
    }


@register.inclusion_tag("fincore/components/action_menu.html")
def import_batch_actions(batch):
    """
    Renders the action dropdown for an import batch.
    """
    items = [
        {
            "type": "link",
            "label": "Review",
            "href": reverse("fincore:import_review", args=[batch.id]),
            "class": BASE_ITEM_CLASS,
            "attrs": format_html('@click="openId = null"'),
        }
    ]
    items.append(
        {
            "type": "link",
            "label": "Delete batch",
            "href": reverse("fincore:import_review", args=[batch.id]),
            "class": DANGER_ITEM_CLASS,
            "attrs": format_html('@click="openId = null"'),
        }
    )
    return {
        "label": "Actions",
        "items": items,
        "menu_id": f"batch-{batch.id}",
        "wrapper_class": "justify-end",
        "button_class": "inline-flex items-center justify-center gap-1 rounded-md border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-700 shadow-sm hover:bg-slate-50 whitespace-nowrap",
        "menu_class": "absolute right-0 top-full z-50 mt-1 min-w-[180px] space-y-1 rounded-md border border-slate-200 bg-white p-2 shadow-lg",
    }
