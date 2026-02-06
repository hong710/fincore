# Database Overview (Fincore, Single-Entry Model)

## Entities
- **Account**: Where money lives. Balance is always derived.
  - has `is_active` (boolean). Inactive accounts are archived, never deleted once transactions exist.
- **Category**: Defines transaction kind. Has `kind` (`income` | `expense` | `transfer` | `opening` | `withdraw` | `equity` | `liability` | `cogs`), `is_active`, and `is_protected`. Imported transactions are assigned to uncategorized categories until reviewed.
  - **Protected categories**: Cannot be renamed, re-typed, deactivated, or deleted. Used for "Uncategorized Income" and "Uncategorized Expense".
- **Vendor**: Counterparty directory. Has `kind` (`payer` | `payee`), `description`, `is_active`.
- **Invoice**: Sales document for matching incoming transactions later. Has `number`, `customer` (Vendor, payer), `account`, `date`, `due_date`, `status`, `subtotal`, `tax_rate`, `tax_exclude`, `tax_total`, `total`, `is_locked`.
  - **Tax calculation**: Tax is computed as `amount × (tax_rate / 100)` per line item.
  - **Tax locking**: `tax_rate` and `tax_exclude` cannot be changed when status is `paid` or `partially_paid`.
- **InvoiceItem**: Line items for an invoice. Has `category`, `amount`, `tax`, `total`, `tax_exempt`, optional `description`.
- **InvoicePayment**: Link between an invoice and a cash transaction. Supports partial payments; stores matched amount and timestamp.
- **Transaction**: Core single-entry record (date, account, amount, kind, vendor?, payee?, category?, transfer_group?, import_batch?, is_imported, is_locked, description, source, created_at).
  - income  → amount > 0, category required
  - expense → amount < 0, category required
  - transfer → category required, transfer_group required
  - opening → category required; excluded from P&L; payee optional
  - withdraw → category required; excluded from P&L
  - vendor links to Vendor; direction is determined by kind/amount, not vendor
  - payee is free text (legacy/optional); direction is determined by kind/amount, not payee
  - is_imported true only for CSV-created rows; every imported row links to an import_batch
  - kind is derived from category when category is present; imported rows are assigned uncategorized categories
  - protected categories cannot be renamed, re-typed, deactivated, or deleted (description may be updated)
  - is_locked prevents editing/deletion (used for reconciliation)
- **TransferGroup**: Pairs transfer transactions; sum per group must be zero.
- **ImportBatch**: One CSV upload; status `pending|validated|imported|failed`. Has `amount_strategy` (`signed|indicator|split_columns`), `indicator_credit_value`, `indicator_debit_value`.
  - **Amount strategies**: 
    - `signed`: Single signed amount column (default)
    - `indicator`: Amount + Credit/Debit indicator column
    - `split_columns`: Separate debit and credit columns
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
Invoice (1) ──────< InvoicePayment >── (1) Transaction
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
  - date, due_date?, status (`draft|sent|partially_paid|paid|void`)
  - subtotal, tax_rate (percentage), tax_exclude (boolean), tax_total, total (computed from items on save)
  - is_locked (boolean, for reconciliation), notes?, created_at
  - **Tax rules**: 
    - Tax per line = `amount × (tax_rate / 100)` unless line is tax_exempt or invoice has tax_exclude=true
    - tax_rate and tax_exclude are read-only when status is `paid` or `partially_paid`
- **invoice_item**
  - id PK, invoice_id FK (CASCADE), category_id FK (PROTECT)
  - amount, tax, total, tax_exempt (boolean), description?, created_at
- **invoice_payment**
  - id PK, invoice_id FK (PROTECT), transaction_id FK (PROTECT)
  - amount, matched_at
  - unique_together: (invoice_id, transaction_id)
- **transfer_group**
  - id PK, reference (unique), created_at
- **transaction**
  - id PK, date, account_id FK, amount (signed), kind (`income|expense|transfer|opening|withdraw|equity|liability|cogs`),
    vendor_id FK NULL, payee (text, optional), category_id FK NULL, transfer_group_id FK NULL,
    is_imported (bool, default false), is_locked (bool, default false), import_batch_id FK NULL (PROTECT),
    description, source (`manual|csv`), created_at
  - business rules (enforced in validation/service layer):
    - income: amount > 0 AND category_id NOT NULL
    - expense: amount < 0 AND category_id NOT NULL
    - transfer: category_id NOT NULL AND transfer_group_id NOT NULL
    - opening: category_id NOT NULL; excluded from P&L; payee optional
    - withdraw: category_id NOT NULL; excluded from P&L
    - imported rows are assigned to "Uncategorized Income" or "Uncategorized Expense" categories until reviewed
    - each transfer_group sums to zero (paired +/–)
    - imported rows: if is_imported=true then import_batch_id is required and matches batch that created them; all rows in a batch share the same import_batch_id; imported transfers keep both sides in the same batch
    - is_locked prevents editing/deletion (used for reconciliation)

## Profit & Loss Rules
- Income is derived from **both** InvoiceItems (invoice-based revenue) **and** Transactions with `kind="income"` (imported/manual income).
- InvoiceItem income and Transaction income are merged by category and period.
- Expenses/COGS come from Transactions with kind `expense` or `cogs`.
- Always exclude transfers, opening, and withdraw transactions.
- Transactions that are matched to invoices (InvoicePayment exists) are excluded from income P&L to prevent double-counting.
- Uncategorized categories ("Uncategorized Income", "Uncategorized Expense") always appear in P&L even when $0.00.
- Documented behavior: "Profit & Loss shows invoice revenue plus transaction-based income (imports, manual entries) and cash expenses. Matched invoice payments never double-count revenue."

## Account Lifecycle
- Accounts with any transactions must never be hard-deleted. Archive by setting `is_active = false`.
- Inactive accounts remain visible in history/reports and affect balances/P&L; they are not selectable for new transactions/transfers/CSV imports.
- Transfers must keep referenced accounts; cascade deletes are forbidden.
- **import_batch**
  - id PK, filename, status (`pending|validated|imported|failed`), error_message?, uploaded_at
  - amount_strategy (`signed|indicator|split_columns`, default `signed`)
  - indicator_credit_value (text, nullable) - Value in indicator column that means "credit"
  - indicator_debit_value (text, nullable) - Value in indicator column that means "debit"
  - **Amount strategy rules**:
    - `signed`: User maps one Amount column with +/- values
    - `indicator`: User maps Amount column + Indicator column, configures which indicator value means credit
    - `split_columns`: User maps separate Debit and Credit columns
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
