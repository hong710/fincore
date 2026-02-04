# Database Overview (Fincore, Single-Entry Model)

## Entities
- **Account**: Where money lives. Balance is always derived.
  - has `is_active` (boolean). Inactive accounts are archived, never deleted once transactions exist.
- **Category**: Defines transaction kind. Has `kind` (`income` | `expense` | `transfer` | `opening` | `withdraw` | `equity` | `liability` | `cogs`), `is_active`, and `is_protected`. Imported transactions may remain uncategorized until reviewed.
- **Vendor**: Counterparty directory. Has `kind` (`payer` | `payee`), `description`, `is_active`.
- **Invoice**: Sales document for matching incoming transactions later. Has `number`, `customer` (Vendor, payer), `account`, `date`, `due_date`, `status`, `subtotal`, `tax_total`, `total`.
- **InvoiceItem**: Line items for an invoice. Has `category`, `amount`, `tax`, `total`, optional `description`.
- **Transaction**: Core single-entry record (date, account, amount, kind, vendor?, payee?, category?, transfer_group?, import_batch?, is_imported, description, source, created_at).
  - income  → amount > 0, category required
  - expense → amount < 0, category required
  - transfer → category required, transfer_group required
  - opening → category required; excluded from P&L; payee optional
  - withdraw → category required; excluded from P&L
  - vendor links to Vendor; direction is determined by kind/amount, not vendor
  - payee is free text (legacy/optional); direction is determined by kind/amount, not payee
  - is_imported true only for CSV-created rows; every imported row links to an import_batch
  - kind is derived from category when category is present; imported rows may be uncategorized until user assigns a category
  - protected categories cannot be renamed, re-typed, deactivated, or deleted (description may be updated)
- **TransferGroup**: Pairs transfer transactions; sum per group must be zero.
- **ImportBatch**: One CSV upload; status `pending|validated|imported|failed`.
- **ImportRow**: Staged CSV rows with mapped fields + validation errors; never touch Transaction until batch commits.

## ERD (conceptual)
```
Account (1) ──< Transaction >── (1) Category
    |                     \            /
    |                      \ (optional)/
    |                       >── (1) TransferGroup
    |                     /
ImportBatch (1) ─────────┘
    |
ImportBatch (1) ──< ImportRow
Vendor (1) ───────< Transaction (optional)
Vendor (1) ───────< Invoice (customer)
Account (1) ──────< Invoice
Invoice (1) ──────< InvoiceItem >── (1) Category
```
Details:
- Transaction.account → Account (FK, PROTECT)
- Transaction.category → Category (FK, PROTECT, nullable for imports only)
- Transaction.transfer_group → TransferGroup (FK, PROTECT, nullable; required for transfers)
- Transaction.vendor → Vendor (FK, PROTECT, nullable)
- ImportRow.batch → ImportBatch (FK, CASCADE)

## Tables & Key Fields
- **account**
  - id PK, name (unique), description?, is_active (bool, default true), created_at
- **category**
  - id PK, name, kind (`income|expense|transfer|opening|withdraw|equity|liability|cogs`), description?, is_active (bool, default true), is_protected (bool, default false), created_at
  - unique_together: (name, kind)
- **vendor**
  - id PK, name, kind (`payer|payee`), description?, is_active (bool, default true), created_at
  - unique_together: (name, kind)
- **invoice**
  - id PK, number (unique), customer_id FK (Vendor, payer), account_id FK (Account)
  - date, due_date?, status (`draft|sent|paid|void`)
  - subtotal, tax_total, total (derived from items on save), notes?, created_at
- **invoice_item**
  - id PK, invoice_id FK (CASCADE), category_id FK (PROTECT)
  - amount, tax, total, description?, created_at
- **transfer_group**
  - id PK, reference (unique), created_at
- **transaction**
  - id PK, date, account_id FK, amount (signed), kind (`income|expense|transfer|opening|withdraw|equity|liability|cogs`),
    vendor_id FK NULL, payee (text, optional), category_id FK NULL, transfer_group_id FK NULL,
    is_imported (bool, default false), import_batch_id FK NULL (PROTECT),
    description, source (`manual|csv`), created_at
  - business rules (enforced in validation/service layer):
    - income: amount > 0 AND category_id NOT NULL
    - expense: amount < 0 AND category_id NOT NULL
    - transfer: category_id NOT NULL AND transfer_group_id NOT NULL
    - opening: category_id NOT NULL; excluded from P&L; payee optional
    - withdraw: category_id NOT NULL; excluded from P&L
    - imported rows may keep category_id NULL until reviewed
    - each transfer_group sums to zero (paired +/–)
    - imported rows: if is_imported=true then import_batch_id is required and matches batch that created them; all rows in a batch share the same import_batch_id; imported transfers keep both sides in the same batch

## Profit & Loss Rules
- Default: include ALL income and expense transactions; ignore tags entirely.
- Always exclude transfers, opening, and withdraw transactions.
- Optional: user may exclude specific tags; any income/expense with an excluded tag is omitted. Transactions without tags remain included.
- Documented behavior: “Profit & Loss shows all income and expenses by default. Tags are optional filters that can be explicitly excluded by the user.”

## Account Lifecycle
- Accounts with any transactions must never be hard-deleted. Archive by setting `is_active = false`.
- Inactive accounts remain visible in history/reports and affect balances/P&L; they are not selectable for new transactions/transfers/CSV imports.
- Transfers must keep referenced accounts; cascade deletes are forbidden.
- **import_batch**
  - id PK, filename, status (`pending|validated|imported|failed`), error_message?, uploaded_at
- **import_row**
  - id PK, batch_id FK, raw_row (JSON), mapped (JSON), errors (JSON), created_at

## CSV Import Flow (two-phase)
1) Staging: create ImportBatch, store ImportRow raw/mapped/errors. Validate amounts, accounts, categories, transfer pairing. No Transaction writes.
2) Commit: if no errors, open DB tx, insert Transactions with `is_imported=true` and `import_batch_id` set, re-validate transfer groups sum to zero, commit. Any error → rollback; no partial imports.

### Persistence checkpoints (what is stored)
- Upload request parses the CSV in-memory only; the original file is not saved on disk.
- Staging writes: `ImportBatch` + `ImportRow` (raw row JSON, mapped fields, and per-row errors).
- Review UI reads from `ImportRow` and `ImportBatch` only.
- Commit writes `Transaction` rows in a single atomic transaction; no partial commit allowed.

### Imported Transactions & Rollback Safety
- All rows from a CSV import are tagged `is_imported=true` and share the same `import_batch_id`.
- Rollback happens only at the import_batch level: delete all transactions for that batch in one atomic operation; partial deletion is forbidden (especially for transfers).
- Imported transfers keep both sides in the same `import_batch_id` and must remain zero-sum.
- Documented rule: “Imported transactions can only be rolled back as a complete batch. This ensures accounting integrity and prevents partial data corruption.”

### CSV Import – Credit & Debit (Unified Flow)
- One flow for credit-card and debit/bank CSVs; user must pick the target account first (account.type guides validation).
- Required mapped fields: **Date**, **Description**, **Amount** (exactly one column each). All other columns must map to **Ignore**. Mapping Kind/Category/Transfer/Account from CSV is forbidden.
- Import logic:
  - Amount < 0 ⇒ kind = expense
  - Amount > 0 ⇒ kind = income
  - category = NULL (uncategorized until user review); payee = NULL
  - No transfers auto-created; ignore any balance columns.
- Safety:
  - Every imported row sets `is_imported=true` and shares the same `import_batch_id`.
  - Import is atomic; rollback only at the `import_batch` level (never per-row).
- UI (modal) steps to support the flow:
  1) Upload CSV
  2) Column mapping (only Date/Description/Amount; others → Ignore)
  3) Preview first 10 rows
  4) Select account (required)
  5) Confirm import
- Documented rule: “Credit and debit card CSV imports share the same flow. Only Date, Description, and Amount are required. All accounting meaning is assigned after import for accuracy.”

## SQLite Notes
- WAL mode recommended; serialize CSV imports (single writer acceptable).
- Max users: 5; keep transactions short; avoid NFS for DB file.

## Upgrade Path (double-entry)
- TransferGroup maps naturally to a future journal-entry header.
- Transaction can be expanded to debit/credit line items later; keep current single-entry rules intact until migration.
