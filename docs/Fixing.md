# AI Notes

## Accounts: Create modal not closing

Symptoms
- Clicking "Create Account" creates the account but modal stays open.

Root cause
- The create modal relied only on `accounts:createClose` (from `HX-Trigger`) to close.
- HTMX does not emit the `HX-Trigger` header on a `204` response, so the close event never fires.

Fix
- Close the modal on successful HTMX request as well.
- Add a direct handler on the create form:
  - `@htmx:after-request.camel="if ($event.detail.xhr.status === 204) createOpen = false"`

Location
- `backend/fincore/templates/fincore/accounts/index.html`

## Filter Table Component (Transactions)

Purpose
- Provides a reusable filter + table shell for Transactions with Alpine state, HTMX submit, and header/table partials.

How it works
- The container in `backend/fincore/templates/fincore/components/filter_table.html` owns the Alpine state.
- The filter header and table are split into partials:
  - `backend/fincore/templates/fincore/transactions/table_header.html`
  - `backend/fincore/templates/fincore/transactions/table_table.html`
- The shared shell is in `backend/fincore/templates/fincore/components/filter_table_shell.html`.
- Filters update hidden inputs and submit the HTMX form to `transactions/table/`.
- `submitFilters()` resets page to 1, syncs hidden inputs, and triggers HTMX submit.
- Column filter buttons (date/payee/description/kind/amount) use draft state:
  - Draft is edited in the popup.
  - Apply copies draft → active filters and submits.
  - Clear resets a filter and submits.
- Filter dropdown values are recursive/nested: options refresh based on the current filtered dataset.
- Search runs on Enter only (`@keydown.enter.prevent="submitFilters()"`).
- Reset filters clears search, sort, and all filter state.
- Bulk action uses `selectedIds` from the table and populates `#bulk-action-ids` before opening the modal.

Implementing elsewhere
1) Keep Alpine state in a top-level wrapper (like `filter_table.html`).
2) Use the shell component:
   - `{% include "fincore/components/filter_table_shell.html" with header_template="..." table_template="..." %}`
3) Header partial must include:
   - `<form>` with `hx-get` to the table endpoint and `x-ref="filterForm"`
   - Hidden inputs for any filters (page, sort, etc.)
4) Table partial can assume the Alpine state exists and can dispatch events or read `selectedIds`.
5) View must provide:
   - `page_obj`, `paginator`, `page_sizes`, `page_size`
   - `filter_payload` for Alpine init
   - Any option lists used by filters (e.g., payee/description/kind)

## Import Wizard Tables: Missing Hover State

Symptoms
- CSV import mapping/preview tables lacked row hover styling.

Fix
- Added `hover:bg-slate-50` to mapping and preview table rows in the import wizard.

Location
- `backend/fincore/templates/fincore/transactions/index.html`

## Profit & Loss: humanize Template Tag Error

Symptoms
- Profit & Loss report crashed with `TemplateSyntaxError: 'humanize' is not a registered tag library`.

Root cause
- `django.contrib.humanize` was not enabled in `INSTALLED_APPS`.

Fix
- Added `django.contrib.humanize` to `INSTALLED_APPS` in base settings so `{% load humanize %}` works.

Location
- `backend/config/settings/base.py`
