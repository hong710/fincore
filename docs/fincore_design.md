# FINCORE Domain — Design Notes (Single-Entry Finance Tracker)

## Stack
- Django backend with `core` example app (models, permissions, HTMX views, server-side validation)
- HTMX for partial HTML requests; Alpine.js for UI-only validation/state; Preline UI for behaviors like modals
- Tailwind CSS compiled via Vite; assets served by Django (`STATIC_URL=/static/`, Vite outputs to `backend/static/app`)
- Storybook (HTML + Vite) for component previews
- Dockerfile + docker-compose (under `docker/`) for production-like runs (Gunicorn, Postgres)
- Icons: Heroicons (SVG-only, served via Django static files and rendered via core UI components)

## Scope & Principles
- Internal finance tracking (not tax/accounting compliant).
- Single-entry only; upgrade-ready for double-entry later.
- Django is the source of truth. No balances stored; always derived.
- HTMX + Alpine + Preline for UI; Heroicons for icons.
- SQLite (max 5 users). WAL, serialized CSV imports, short transactions.

## Core Data Model
1) Account
   - Where money lives. No stored balance column.
2) Category
   - kind: income | expense.
   - Transfers never reference categories.
3) Transaction (core table)
   - date, account (FK), amount (signed), kind (income | expense | transfer), category (nullable), transfer_group (nullable), description, source (manual | csv), created_at.
   - Rules:
     - income → amount > 0, category required.
     - expense → amount < 0, category required.
     - transfer → category null, transfer_group required.
4) TransferGroup
   - Groups paired transfer transactions; sum per group must be zero.
5) ImportBatch
   - Tracks CSV uploads and status: pending | validated | imported | failed.
6) ImportRow
   - Staged CSV rows with mapped fields and validation errors.

## Transfer Rules (must enforce)
- Transfers are paired with the same transfer_group.
- One negative (from), one positive (to); sum = 0 per group.
- Any violation → fail save/import, no partial writes.

## CSV Import Flow (two-phase)
1) Staging & Validation
   - Parse CSV, map columns.
   - Validate amounts, accounts, categories, transfer rules.
   - NOTHING written to Transaction.
2) Atomic Commit
   - If all valid: begin DB transaction, insert, re-validate transfer groups, commit.
   - If any error: rollback everything. Partial imports forbidden.

## Upgrade Path (future double-entry)
- TransferGroup can map to journal entry header.
- Transaction rows can expand to debit/credit lines later.
- Keep categories kinded; no debit/credit columns yet.

## Testing & Ops Notes
- SQLite WAL, single writer acceptable; serialize imports.
- Keep imports short; avoid NFS for DB.
- Add unit tests around transfer pairing and import validation.
