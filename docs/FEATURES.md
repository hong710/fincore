# Recent Features & Enhancements

This document tracks major features and improvements added to Fincore.

## CSV Import: Universal Amount Normalization (3 Strategies)

**Added:** February 2026  
**Status:** ✅ Implemented

### Problem
CSV files from different banks use different formats for amounts:
- Some have signed amounts (+/- in one column)
- Some have absolute amounts with a separate Credit/Debit indicator column
- Some have separate Debit and Credit columns

The original import only supported signed amounts.

### Solution
Implemented 3 amount strategies with full UI and validation:

1. **Signed** (default)
   - Single amount column with +/- sign
   - Positive = income, Negative = expense
   
2. **Indicator**
   - Absolute amount column + indicator column (e.g., "Credit"/"Debit")
   - User configures which indicator value means credit vs debit
   - System converts to signed amount based on indicator
   
3. **Split Columns**
   - Separate Debit and Credit columns
   - Non-empty Debit = expense (negative)
   - Non-empty Credit = income (positive)

### Technical Implementation
- Added `amount_strategy`, `indicator_credit_value`, `indicator_debit_value` to `ImportBatch` model
- Server-side validation ensures correct column mapping per strategy
- Client-side JavaScript computes `signed_amount` for real-time preview
- All strategies normalize to signed amount before Transaction creation

### Files Modified
- `backend/fincore/models/import_batch.py`
- `backend/fincore/views/import_views.py` (complete rewrite of import flow)
- `backend/fincore/templates/fincore/transactions/index.html` (wizard UI)
- `backend/fincore/migrations/0015_importbatch_amount_strategy.py`

---

## Uncategorized Categories (Protected Categories)

**Added:** February 2026  
**Status:** ✅ Implemented

### Problem
- Imported transactions had `category=None`, causing query errors
- No standardized workflow for categorizing imports
- P&L reports crashed or showed incomplete data

### Solution
- Created two protected categories:
  - **"Uncategorized Income"** (kind=income, is_protected=true)
  - **"Uncategorized Expense"** (kind=expense, is_protected=true)
- Import commit auto-assigns appropriate uncategorized category based on amount sign
- Protected categories cannot be renamed, deleted, or deactivated
- P&L always shows uncategorized rows even when $0.00

### Benefits
- Eliminates NULL category errors
- Provides clear user workflow: import → review uncategorized → reassign
- Makes incomplete categorization visible in reports

### Files Modified
- `backend/fincore/migrations/0016_uncategorized_categories.py`
- `backend/fincore/views/import_views.py` (import_commit)
- `backend/fincore/views/transaction_views.py` (_ensure_uncat_row)

---

## Profit & Loss: Transaction-Based Income Support

**Added:** February 2026  
**Status:** ✅ Implemented

### Problem
P&L income section only queried `InvoiceItem` objects. Imported income transactions (which are `Transaction` records) were invisible, showing $0.00 totals despite transactions existing.

### Root Cause
Income query: `InvoiceItem.objects.filter(category__kind="income")`  
Missing: `Transaction.objects.filter(kind="income")`

Expense section correctly queried Transactions, so expenses worked fine.

### Solution
- Added second query for income Transactions: `Transaction.objects.filter(kind="income", category__isnull=False).exclude(invoice_payments__isnull=False)`
- Merged Transaction income with InvoiceItem income in same `data_rows` dict
- Applied identical filters (account, vendor, category, date range) to both queries
- Prevented double-counting via `.exclude(invoice_payments__isnull=False)`

### Impact
P&L now correctly shows:
- Invoice-based income (InvoiceItems)
- Imported income (CSV uploads assigned to "Uncategorized Income")
- Manual income transactions

### Files Modified
- `backend/fincore/views/transaction_views.py` (`_profit_loss_context` function, lines 489-598)

---

## Profit & Loss: Hierarchical View + Payroll Section

**Added:** February 2026  
**Status:** ✅ Implemented

### What Changed
- P&L now groups categories by parent and supports expand/collapse per parent.
- Parent categories display totals when collapsed.
- Payroll is a separate section (expense-kind), but included in total expenses.
- Single-period reports render as `Category | Amount` (no Total column).

---

## Reports: Balance Sheet + Cash Flow (UI)

**Added:** February 2026  
**Status:** ✅ Implemented (UI + server-rendered data)

### Balance Sheet
- New report at `/reports/balance-sheet/`.
- Filters auto-apply on change (report period, account, category, type).
- Sections: Assets, Liabilities, Equity with totals and final “Total Liabilities & Equity”.
- Snapshot uses report end date (as-of date).

### Cash Flow
- New report at `/reports/cashflow/`.
- Filters auto-apply on change (report period, account, vendor, category, type).
- Sections: Operating, Investing, Financing with section totals and “Net change in cash”.
- Includes unpaid invoice/bill balances to avoid duplicate cash when matched.
- “Detailed / Summary” toggle for a simplified inflow/outflow view.
- Cash Flow detailed view now supports parent/child category expand/collapse (same pattern as P&L).

### Files Modified
- `backend/fincore/views/transaction_views.py`
- `backend/fincore/templates/fincore/reports/profit_loss_content.html`

---

## Profit & Loss: Export + Print

**Added:** February 2026  
**Status:** ✅ Implemented

### What Changed
- Added **Export Excel** button (server-generated `.xlsx`).
- Added **Print** button with print-specific styles to render the full report in one page (no scroll clipping).
- Export includes all section rows with child categories.

### Files Modified
- `backend/fincore/views/transaction_views.py`
- `backend/fincore/templates/fincore/reports/profit_loss.html`
- `backend/fincore/templates/fincore/reports/profit_loss_content.html`
- `backend/fincore/urls.py`

### Print Behavior
- Print hides the full app shell (header/sidebar/footer).
- Only the P&L report content is rendered for print.

---

## Category Kind: Payroll

**Added:** February 2026  
**Status:** ✅ Implemented

### What Changed
- Added `payroll` to category kinds.
- Payroll shows in P&L as its own section.

### Files Modified
- `backend/fincore/models/category.py`
- `backend/fincore/migrations/0021_add_category_kind_payroll.py`
- `backend/fincore/templates/fincore/categories/index.html`

---

## Live Table Refresh + Category Dropdown Updates

**Added:** February 2026  
**Status:** ✅ Implemented

### What Changed
- Added **Refresh** buttons to list tables (Accounts, Sales Transactions, Bills).
- Buttons re-fetch table content via HTMX without full page reload.
- Transaction category dropdowns now re-load options on `categories:refresh` events.

### Files Modified
- `backend/fincore/templates/fincore/accounts/index.html`
- `backend/fincore/templates/fincore/sales/transactions/index.html`
- `backend/fincore/templates/fincore/bills/transactions/index.html`
- `backend/fincore/templates/fincore/transactions/index.html`
- `backend/fincore/views/category_views.py`
- `backend/fincore/templates/fincore/categories/options.html`
- `backend/fincore/urls.py`

---

## Invoice: Tax System Redesign

**Added:** February 2026  
**Status:** ✅ Implemented

### Problem
- Tax was a manual entry field (`tax_total`), making calculations opaque
- No standard tax rate across invoices
- No protection against changing tax after payment

### Solution
Replaced manual `tax_total` with **calculated tax from `tax_rate`**:

#### New Fields
- `tax_rate` (DecimalField): Percentage (e.g., 7.75 for 7.75%)
- `tax_exclude` (BooleanField): Skip tax for entire invoice
- `is_locked` (BooleanField): For future reconciliation locking

#### Tax Calculation
- Per line item: `amount × (tax_rate / 100)`
- Line items can individually opt out via "Exclude Tax" checkbox
- Invoice-level `tax_exclude` flag skips all line item tax

#### Tax Rate Locking
**CRITICAL**: When invoice status is `paid` or `partially_paid`, the `tax_rate` and `tax_exclude` fields become **read-only** (disabled in UI, blocked in backend).

This prevents tax manipulation after payment is recorded.

#### Migration
- Backfills `tax_rate` for existing invoices: `(tax_total / subtotal) × 100`
- Preserves existing tax totals

### Benefits
- Transparent tax calculations
- Consistent tax rates
- Prevents post-payment tax manipulation
- Supports mixed tax/non-tax line items

### Files Modified
- `backend/fincore/models/invoice.py`
- `backend/fincore/views/sales_views.py` (create/edit views)
- `backend/fincore/templates/fincore/sales/transactions/new.html`
- `backend/fincore/templates/fincore/sales/transactions/edit.html`
- `backend/fincore/templates/fincore/sales/transactions/detail.html`
- `backend/fincore/migrations/0017_invoice_tax_rate_lock.py`

---

## Bills & Receipts (Vendor Bills)

**Added:** February 2026  
**Status:** ✅ Implemented

### Purpose
Track vendor bills and match them to outgoing expense transactions (negative amounts), mirroring the Sales workflow but for expenses.

### Key Behaviors
- Bills are created manually with line items (Category, Description, Amount, Line Total).
- Matching links bills to expense transactions; no auto-matching.
- Matching supports partial payments and multiple transactions.
- Filters auto-apply on selection (no Apply button); server-selected values persist on reload.

### Files Modified
- `backend/fincore/models/bill.py`
- `backend/fincore/models/bill_item.py`
- `backend/fincore/models/bill_payment.py`
- `backend/fincore/views/bill_views.py`
- `backend/fincore/templates/fincore/bills/transactions/index.html`
- `backend/fincore/templates/fincore/bills/transactions/new.html`
- `backend/fincore/templates/fincore/bills/transactions/edit.html`
- `backend/fincore/templates/fincore/bills/transactions/detail.html`
- `backend/fincore/templates/fincore/bills/transactions/match_list.html`
- `backend/fincore/templates/fincore/base.html` (sidebar link)

---

## UI/UX Improvements

### P&L: Page Fill & Sticky Net Income Footer

**Problem:**
- P&L page didn't fill viewport (whitespace below table)
- Net Income row floated with data instead of anchoring at bottom

**Solution:**
- Container: `flex-1 min-h-0` (fills available space)
- Table body: `flex-1 overflow-auto min-h-0` (scrollable)
- Net Income: Separate footer `<div>` with `flex-shrink-0` (fixed at bottom)

**File:** `backend/fincore/templates/fincore/reports/profit_loss_content.html`

### CSV Import: Map UI Polish

**Improvements:**
1. Mapping table scrollable: `max-h-[320px] overflow-auto`
2. Mapped columns highlighted: `border-2 border-indigo-500`
3. Fixed "Next" button grayed out: Replaced `x-for` with static `<option>` elements

**File:** `backend/fincore/templates/fincore/transactions/index.html`

### Alpine.js: x-cloak Fix

**Problem:** Modals briefly flashed on page load before Alpine.js hid them

**Solution:** Added `[x-cloak] { display: none !important; }` to base template

**File:** `backend/fincore/templates/fincore/base.html`

---

## Migration Summary

All migrations applied successfully:

- **0015_importbatch_amount_strategy.py**: CSV import strategies
- **0016_uncategorized_categories.py**: Protected categories creation
- **0017_invoice_tax_rate_lock.py**: Invoice tax redesign with backfill

---

## Testing Notes

### Manual Testing Checklist

- [x] CSV import with signed amounts
- [x] CSV import with indicator column (Credit/Debit)
- [x] CSV import with split columns (separate Debit/Credit)
- [x] Import preview shows correct signed amounts
- [x] Imported transactions assigned to uncategorized categories
- [x] P&L shows imported income transactions
- [x] P&L shows uncategorized rows even when $0.00
- [x] Invoice tax calculated from rate
- [x] Invoice tax rate locked when paid/partially_paid
- [x] Invoice line items can exclude tax individually
- [x] P&L Net Income sticky at bottom
- [x] CSV map UI scrollable and highlights mapped columns

### Known Limitations

- Import rollback only at batch level (by design, for integrity)
- Protected categories cannot be deleted (by design)
- Tax rate backfill assumes single-rate invoices (acceptable for migration)

---

## Invoice Matching: Partial Payment Support

**Added:** February 2026  
**Status:** ✅ Implemented

### Problem
- Invoices could only match with a single transaction
- No way to record partial payments or split transactions across an invoice
- Match modal was unreliable (template syntax error)

### Solution
Complete redesign of invoice matching workflow:

#### Backend Changes
- `_build_invoice_match_context()`: Returns two lists
  - **Best Matches**: Transactions that can cover full remaining balance (sorted by amount DESC)
  - **All Other Transactions**: Everything else within ±30 days, same account
- Transactions can be pre-filtered by date range and account
- Multiple transaction selection with checkbox toggle
- Input fields allow partial matching (amount < transaction.amount)
- Batch validation before applying all matches atomically

#### Frontend Changes
- Match modal redesigned with two collapsible sections
- Checkbox selection with real-time total calculation
- "Clear All" button for quick reset
- Form submits all `match_{txn_id}` fields at once
- Alpine.js `matchManager` state machine for UI sync

#### Automatic Data Enrichment
When a transaction is matched to an invoice:
- `transaction.category` ← `invoice.items[0].category` (from first line item)
- `transaction.kind` ← `invoice.items[0].category.kind`
- `transaction.vendor` ← `invoice.customer`

This ensures matched transactions are properly categorized and linked to their source invoice.

### Benefits
- Single transaction can now pay multiple invoices (future)
- Multiple transactions can settle one invoice
- Partial payment tracking
- Auto-categorization from invoice context
- Deterministic match order (best matches first)

### Files Modified
- `backend/fincore/views/sales_views.py` (`_build_invoice_match_context`, `sales_invoice_match_apply`)
- `backend/fincore/templates/fincore/sales/transactions/match_list.html` (complete rewrite)
- `backend/fincore/models/invoice_payment.py` (unique constraint on invoice+transaction)

---

## Transaction Display: Invoice Info Integration

**Added:** February 2026  
**Status:** ✅ Implemented

### Problem
- Transaction category column showed only category OR invoice, not both
- No way to see both the categorization and which invoice paid the transaction
- Invoice match link required clicking into transaction detail

### Solution
- Category column now displays two lines:
  1. **Category name** (always shown)
  2. **Invoice info** (small link if transaction is matched)

Format:
```
[Category Name]
Invoice: INV20260206-XXXXX
```

Clickable invoice link navigates to invoice detail page.

### Benefits
- Faster visual scanning: see category + invoice context at a glance
- No need to open transaction edit modal to find invoice reference
- Clean integration with existing transaction list UI

### Files Modified
- `backend/fincore/templates/fincore/transactions/table_table.html` (category cell formatting)
- `backend/fincore/models/transaction.py` (`@property invoice_display_label`, `@property invoice_display_link`)

---

## Checkbox Persistence: tax_exclude Field

**Added:** February 2026  
**Status:** ✅ Implemented & Fixed

### Problem
Invoice "Exclude tax" checkbox was not persisting to database:
- Checkbox would save but not reload correctly
- Root cause: Hidden input hack combined with `request.POST.get()` returned wrong value
- Unchecked checkbox was never sent (standard HTML behavior)

### Root Cause Analysis
```python
# BROKEN:
<input type="hidden" name="tax_exclude" value="0">
<input type="checkbox" name="tax_exclude" value="1">

# Backend:
tax_exclude = request.POST.get("tax_exclude") == "1"  # ❌ Got "0" from hidden input
```

When both inputs present, `QueryDict.get()` returns unpredictable result.

### Solution
Removed hidden input hack. Use standard checkbox + proper server-side logic:

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
# Backend: Check for key presence instead of value
tax_exclude = "tax_exclude" in request.POST  # ✅ True if checked, False if unchecked
```

### Why This Works
- **Checked**: Form sends `tax_exclude=1` → key exists → True
- **Unchecked**: Form sends nothing → key absent → False
- **Read**: `{% if tax_exclude %}checked{% endif %}` renders initial state from DB
- **Server render**: Django template truth is source of truth

### Benefits
- Deterministic CRUD: Save → Read → Edit → Save cycle works correctly
- No JavaScript state sync needed
- Works across page reloads and browser sessions
- Simple to debug (plain HTML form submission)

### Files Modified
- `backend/fincore/templates/fincore/sales/transactions/edit.html` (checkbox fix)
- `backend/fincore/templates/fincore/sales/transactions/new.html` (checkbox fix)
- `backend/fincore/views/sales_views.py` (POST read: `"tax_exclude" in request.POST`)

---

## Documentation Updates

Updated documentation files:
- `docs/Fixing.md` - Added all recent fixes with root causes and solutions
- `docs/Database.md` - Updated entity descriptions, table schemas, P&L rules, import flow
- `docs/FEATURES.md` - This file, tracking major features

Refer to individual doc files for detailed technical specifications.
