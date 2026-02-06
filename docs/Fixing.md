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
## Profit & Loss: Page Height Not Filling

Symptoms
- P&L page had whitespace below the table instead of filling the full viewport.

Fix
- Changed P&L container from `min-h-[70vh]` to `flex-1 min-h-0` to properly fill available space.
- Applied flexbox layout to parent container for proper height distribution.

Location
- `backend/fincore/templates/fincore/reports/profit_loss_content.html`

## Profit & Loss: Net Income Row Not Sticky at Bottom

Symptoms
- Net Income total row floated with the last data row instead of staying at the bottom of the viewport.
- With few rows, Net Income appeared near the top.
- With many rows, scrolling made Net Income invisible.

Solution
- Separated Net Income into its own footer `<div>` outside the main scrollable table.
- Main table has `flex-1 overflow-auto min-h-0` for scrollable body.
- Net Income footer has `flex-shrink-0` to stay fixed at bottom.
- Outer container uses `flex flex-col` for proper layout.

Location
- `backend/fincore/templates/fincore/reports/profit_loss_content.html`

## Profit & Loss: Income Not Showing Imported Transactions

Symptoms
- P&L income section showed $0.00 for "Uncategorized Income" despite category report showing 7 income transactions.
- Imported income transactions were invisible in P&L totals.

Root cause
- P&L income section ONLY queried `InvoiceItem` objects (invoice-based income).
- Imported income transactions are `Transaction` records with `kind="income"`, which were never queried.
- Expense section correctly queried `Transaction` objects, so expenses displayed properly.

Fix
- Added second query for `Transaction.objects.filter(kind="income", category__isnull=False).exclude(invoice_payments__isnull=False)` in income section.
- Merged Transaction-based income data with InvoiceItem-based income data into same `data_rows` dict.
- Applied same filters (account, vendor, category, date range) and period grouping to both queries.
- Prevented double-counting by excluding transactions that have invoice payments (already captured via InvoiceItems).

Location
- `backend/fincore/views/transaction_views.py` lines 489-598 (`_profit_loss_context` function)

## CSV Import: Universal Amount Normalization (3 Strategies)

Symptoms
- CSV import only supported signed amounts (positive=income, negative=expense).
- Could not import CSVs with separate Credit/Debit columns or indicator columns.

Solution
- Implemented 3 amount strategies:
  1. **Signed** (default): Single amount column with +/- sign
  2. **Indicator**: Amount column + Credit/Debit indicator column (user configures which value means credit)
  3. **Split Columns**: Separate debit and credit amount columns
- Server-side validation ensures correct mapping per strategy.
- Client-side JavaScript computes `signed_amount` for preview.
- All strategies normalize to signed amount before Transaction creation.

Changes
- Added `amount_strategy`, `indicator_credit_value`, `indicator_debit_value` fields to `ImportBatch` model.
- Completely rewrote `import_stage`, `import_review`, `import_commit` views with helper functions.
- Updated import wizard UI with strategy selection, conditional indicator config panel, dynamic preview calculations.

Locations
- `backend/fincore/models/import_batch.py`
- `backend/fincore/views/import_views.py`
- `backend/fincore/templates/fincore/transactions/index.html`
- `backend/fincore/migrations/0015_importbatch_amount_strategy.py`

## CSV Import: Map UI Improvements

Issues Fixed
1. **CSV column list not scrollable**: With many columns, mapping table overflowed.
2. **Mapped columns not visually distinct**: Hard to see which columns were mapped.
3. **Next button grayed out**: Using `x-for` inside `<select>` caused Alpine.js state sync loss.

Solutions
1. Added `max-h-[320px] overflow-auto` to mapping table container.
2. Added `border-2 border-indigo-500` highlight to select elements when mapped.
3. Replaced dynamic `x-for` options with static `<option>` elements using `:disabled` and `x-show` for conditional display.

Location
- `backend/fincore/templates/fincore/transactions/index.html`

## Alpine.js: Modal Flash on Page Load (x-cloak)

Symptoms
- Import modal briefly appeared on page load before Alpine.js hid it.
- Caused visual flash/flicker.

Root cause
- Missing `[x-cloak]` CSS rule to hide elements before Alpine.js initializes.

Fix
- Added `<style>[x-cloak] { display: none !important; }</style>` to `<head>` in base template.

Location
- `backend/fincore/templates/fincore/base.html`

## Uncategorized Categories: Auto-Assignment on Import

Problem
- Imported transactions had `category=None`, causing query errors in P&L reports.
- No standardized "uncategorized" categories for user review workflow.

Solution
- Created two protected categories: "Uncategorized Income" and "Uncategorized Expense".
- Import commit now assigns appropriate uncategorized category based on amount sign.
- P&L always shows uncategorized rows even when $0.00 (with `_ensure_uncat_row()` helper).
- Users can reassign categories after import; uncategorized categories cannot be deleted/renamed.

Changes
- Added `is_protected` field to `Category` model (already existed, now used).
- Created migration with `RunPython` to create protected categories.
- Updated `import_commit` to assign uncategorized categories.
- Updated P&L context builder to always show uncategorized rows.

Locations
- `backend/fincore/migrations/0016_uncategorized_categories.py`
- `backend/fincore/views/import_views.py` (import_commit)
- `backend/fincore/views/transaction_views.py` (_profit_loss_context, _ensure_uncat_row)

## Invoice: Tax System Redesign

Problem
- Invoice had `tax_total` as a stored value, making tax calculations opaque.
- No way to apply a standard tax rate across invoices.
- No protection against changing tax after invoice was paid.

Solution
- Replaced manual `tax_total` entry with **calculated tax from `tax_rate`**.
- Added fields:
  - `tax_rate` (DecimalField): Percentage rate (e.g., 7.75 for 7.75%)
  - `tax_exclude` (BooleanField): Skip tax for entire invoice if true
  - `is_locked` (BooleanField): Future use for reconciliation locking
- Tax computed as: `amount × (tax_rate / 100)` per line item.
- Line items can individually exclude tax via checkbox.
- **Tax rate locking**: When invoice status is `paid` or `partially_paid`, the `tax_rate` and `tax_exclude` fields become read-only.
- Migration backfills `tax_rate` by calculating from existing `tax_total / subtotal × 100`.

Changes
- Added `tax_rate`, `tax_exclude`, `is_locked` fields to Invoice model.
- Updated create/edit views to compute tax from rate and prevent changes when paid.
- Updated templates to show tax rate input, exclude checkbox, and disable when locked.
- Updated detail template to display tax rate and exclude status.

Locations
- `backend/fincore/models/invoice.py`
- `backend/fincore/views/sales_views.py` (sales_invoice_create, sales_invoice_edit)
- `backend/fincore/templates/fincore/sales/transactions/new.html`
- `backend/fincore/templates/fincore/sales/transactions/edit.html`
- `backend/fincore/templates/fincore/sales/transactions/detail.html`
- `backend/fincore/migrations/0017_invoice_tax_rate_lock.py`

## Invoice Matching: Partial Payment Support & Multi-Match

Problem
- Invoices could only match with one transaction
- No way to split partial payments across multiple transactions
- Match modal had template syntax error (backtick + Django template tags)

Root Cause
- Original match template used Alpine.js dynamic binding: `:name="\`match_${{{ txn.id }}}\`"` 
- Triple braces `${{{` caused TemplateSyntaxError because Django template engine confused it
- Single transaction + amount paradigm didn't support partial payments

Solution
- Completely rewrote match backend:
  - `_build_invoice_match_context()` now returns two lists:
    - **best_matches**: Transactions that can cover full remaining balance (desc by amount)
    - **other_transactions**: All others within ±30 days, same account
  - Multiple transaction selection via checkboxes
  - Amount input allows partial matching
  - Batch validation and atomic commit
- Fixed template:
  - Removed dynamic Alpine binding
  - Use static name: `name="match_{{ txn.id }}"`
  - One form submit with all selected `match_{txn_id}` values
- Auto-enrich matched transactions:
  - `transaction.category` ← `invoice.items[0].category`
  - `transaction.kind` ← `invoice.items[0].category.kind`
  - `transaction.vendor` ← `invoice.customer`

Changes
- Complete rewrite of `_build_invoice_match_context()` and `sales_invoice_match_apply()`
- New `match_list.html` template with Alpine state machine
- Transaction model: Added `@property` decorators to `invoice_display_label` and `invoice_display_link`

Locations
- `backend/fincore/views/sales_views.py` (lines 483-610)
- `backend/fincore/templates/fincore/sales/transactions/match_list.html`
- `backend/fincore/models/transaction.py`

## Transaction Display: Invoice Info in Category Column

Problem
- Transaction table showed category OR invoice link, not both
- Users couldn't see at a glance which invoice paid a transaction
- Had to open edit modal to find invoice reference

Solution
- Category column now displays:
  1. Category name (always)
  2. Invoice info as small text below (if matched)
  
Format:
```
[Category Name]
Invoice: INV20260206-XXXXX
```

Changes
- Modified category cell in transaction table template
- Invoice link clickable, navigates to invoice detail

Locations
- `backend/fincore/templates/fincore/transactions/table_table.html` (lines ~304-315)

## Checkbox Persistence Bug: tax_exclude Field

Problem
- Invoice "Exclude tax" checkbox didn't persist correctly
- Database showed `tax_exclude=True` but checkbox appeared unchecked on reload
- Saving didn't update the database value correctly

Root Cause Analysis
```html
<!-- BROKEN PATTERN: -->
<input type="hidden" name="tax_exclude" value="0">
<input type="checkbox" name="tax_exclude" value="1">

<!-- Backend read: -->
tax_exclude = request.POST.get("tax_exclude") == "1"  # ❌ Got "0" from hidden input
```

When both inputs with same name are present:
- `request.POST.get()` returns unpredictable result (might be "0" or "1")
- If hidden input submitted last, got "0" even when checkbox checked
- Unchecked checkboxes don't send anything (HTML standard behavior)

Solution
1. **Remove the hidden input hack entirely**
2. **Use standard checkbox with proper server-side logic**

```html
<!-- FIXED: Plain checkbox, no hidden input -->
<input
  type="checkbox"
  name="tax_exclude"
  value="1"
  {% if tax_exclude %}checked{% endif %}
/>
```

```python
# Backend: Check for key presence, not value
tax_exclude = "tax_exclude" in request.POST
# If checkbox checked: request.POST contains "tax_exclude=1" → key exists → True
# If unchecked: request.POST doesn't contain key → False
```

Why This Works
- **Checked**: Form sends `tax_exclude=1` → `"tax_exclude" in request.POST` → True
- **Unchecked**: Form sends nothing → key absent → False
- **Read**: `{% if tax_exclude %}checked{% endif %}` renders checked state from DB
- **Idempotent**: Save → Close → Reopen → checkbox reflects DB state correctly

Benefits
- Deterministic CRUD: Save-Read-Edit-Save cycle works reliably
- No JavaScript state sync required
- Works across page reloads and browser sessions
- Simple to debug: plain HTML form, no hidden inputs

Changes
- Removed hidden input from both create and edit invoice templates
- Changed POST read from `== "1"` to `in request.POST` in both views
- Added static `checked` attribute for server-side rendering

Locations
- `backend/fincore/templates/fincore/sales/transactions/edit.html` (lines ~63-75)
- `backend/fincore/templates/fincore/sales/transactions/new.html` (lines ~63-75)
- `backend/fincore/views/sales_views.py` (edit: line 330, create: line 145)

## Auto-Assignment: Transaction Category & Vendor from Invoice

Problem
- When matching a transaction to an invoice, the transaction's category remained unchanged
- Transaction wasn't properly linked to the invoice customer
- No visual connection between invoice and matched transaction

Solution
- When applying invoice matches, automatically set:
  - `transaction.category` from invoice's first line item category
  - `transaction.kind` from that category's kind
  - `transaction.vendor` from invoice.customer
- Ensures matched transactions are contextually enriched with invoice data

Changes
- Modified `sales_invoice_match_apply()` to update transaction fields during match apply
- Batches updates efficiently: only calls `save()` if fields changed
- Auto-enrichment preserves existing category if already matches

Locations
- `backend/fincore/views/sales_views.py` (lines ~593-603)
```