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
