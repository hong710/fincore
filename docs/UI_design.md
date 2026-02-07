# UI Design Foundations

This document captures the visual foundations we use across Storybook and Django templates. It mirrors the Storybook foundations entries (colors, typography) so engineers can keep the app consistent.

## Palette (Tailwind tokens)
- Background: `slate-50`
- Cards/Panels: `white`
- Primary: `indigo-600` (hover `indigo-700`)
- Success/Income: `emerald-600`
- Danger/Expense: `rose-600`
- Warning: `amber-500`
- Text Primary: `slate-900`
- Text Secondary: `slate-500`
- Borders: `slate-200`

## Typography
- Page title: `text-lg font-semibold`
- Section title: `text-sm font-medium text-slate-700`
- Body: `text-sm text-slate-800`
- Muted: `text-xs text-slate-500`
- Rule: “finance boring” — no creative fonts; stick to Tailwind defaults.

## Layout and Spacing
- Page padding: `p-4`
- Card padding: `p-4`
- Vertical section gap: `space-y-4`
- Table rows: `py-2`
- Table row hover: `hover:bg-slate-50` for all data tables
- Base layout: fixed header, collapsible left sidebar, scrollable main, persistent footer.
- Modals should open centered on screen (use `items-center` in the overlay wrapper).

## Storybook References
- Colors: `frontend/storybook/foundations/colors.html`
- Typography: `frontend/storybook/foundations/typography.html`
- Layout (app shell): `frontend/storybook/pages/base.html`
- Transactions page reference: `frontend/storybook/pages/transactions.html`

## Usage Notes
- Icons: Heroicons SVG only (served locally).
- Behaviors: Preline UI for dropdowns/modals; Alpine.js for UI state only.
- HTMX will handle partial updates; keep templates HTML-first and server-driven.

## Reports (Profit & Loss)
- Layout: title + filter bar (report period, account, vendor, category, type) that auto-submits on change (no `Apply` CTA).
- Table: summary by category with section headers (Income, COGS, Expenses) and totals; `Net Income` highlighted in `indigo-50`.
- Amounts: income in `emerald-600`, expenses/COGS in `rose-600`, net income color based on sign.
- Table rows use `hover:bg-slate-50` for data rows; section/total rows remain static.

## Reports (Balance Sheet)
- Layout: title + filter bar (report period, account, category, type) that auto-submits on change.
- Table: Assets, Liabilities, Equity sections with totals and a final “Total Liabilities & Equity”.
- Amount column is right-aligned; section headers are uppercase.

## Reports (Cash Flow)
- Layout: title + filter bar (report period, account, vendor, category, type) that auto-submits on change.
- Table: Operating, Investing, Financing sections with section totals and final “Net change in cash”.
- Supports a “Detailed / Summary” toggle (summary shows section totals only).
- Detailed view uses parent/child expandable category rows (same interaction as P&L).

## Sales Transactions (Invoices)
- Layout: title + filter bar (report period, account, customer, status, min/max total, search) that auto-submits on change (no `Apply` CTA).
- Table: QuickBooks-like summary with columns for invoice number, date, customer, total, status, due date, account, actions.
- Actions: `Match` opens a modal with suggested transactions; no link is saved yet.
- Create invoice page: header fields + line items table (category, description, amount, tax), totals calculated on save.

## Bills & Receipts
- Layout: title + filter bar (report period, account, vendor, status, min/max total, search) that auto-submits on change.
- Table: bills list with columns for bill number, date, vendor, total, status, account, actions.
- Actions: `Match` opens suggested expense transactions; matching is manual.
- Create/edit bill: header fields + line items table (category, description, amount), totals calculated on save.
