# Database Overview (Fincore, Single-Entry Model)

## Entities
- **Account**: Where money lives. Balance is always derived.
- **Category**: For income/expense only. Has `kind` (`income` | `expense`). Transfers never use categories.
- **Transaction**: Core single-entry record (date, account, amount, kind, payee?, category?, transfer_group?, description, source, created_at).
  - income  → amount > 0, category required
  - expense → amount < 0, category required
  - transfer → category NULL, transfer_group required
  - opening → system initialization; excluded from P&L; payee optional
  - payee is free text (other party); direction is determined by kind/amount, not payee
- **TransferGroup**: Pairs transfer transactions; sum per group must be zero.
- **ImportBatch**: One CSV upload; status `pending|validated|imported|failed`.
- **ImportRow**: Staged CSV rows with mapped fields + validation errors; never touch Transaction until batch commits.

## ERD (conceptual)
```
Account (1) ──< Transaction >── (1) Category
    |                     \
    |                      \ (optional)
    |                       >── (1) TransferGroup
    |
ImportBatch (1) ──< ImportRow
```
Details:
- Transaction.account → Account (FK, PROTECT)
- Transaction.category → Category (FK, PROTECT, nullable; only for income/expense)
- Transaction.transfer_group → TransferGroup (FK, PROTECT, nullable; required for transfers)
- ImportRow.batch → ImportBatch (FK, CASCADE)

## Tables & Key Fields
- **account**
  - id PK, name (unique), description?, created_at
- **category**
  - id PK, name, kind (`income|expense`), description?, created_at
  - unique_together: (name, kind)
- **transfer_group**
  - id PK, reference (unique), created_at
- **transaction**
  - id PK, date, account_id FK, amount (signed), kind (`income|expense|transfer|opening`),
    payee (text, optional), category_id FK NULL, transfer_group_id FK NULL, description,
    source (`manual|csv`), created_at
  - business rules (enforced in validation/service layer):
    - income: amount > 0 AND category_id NOT NULL
    - expense: amount < 0 AND category_id NOT NULL
    - transfer: category_id NULL AND transfer_group_id NOT NULL
    - opening: initialization; excluded from P&L; payee optional
    - each transfer_group sums to zero (paired +/–)
- **import_batch**
  - id PK, filename, status (`pending|validated|imported|failed`), error_message?, uploaded_at
- **import_row**
  - id PK, batch_id FK, raw_row (JSON), mapped (JSON), errors (JSON), created_at

## CSV Import Flow (two-phase)
1) Staging: create ImportBatch, store ImportRow raw/mapped/errors. Validate amounts, accounts, categories, transfer pairing. No Transaction writes.
2) Commit: if no errors, open DB tx, insert Transactions, re-validate transfer groups sum to zero, commit. Any error → rollback; no partial imports.

## SQLite Notes
- WAL mode recommended; serialize CSV imports (single writer acceptable).
- Max users: 5; keep transactions short; avoid NFS for DB file.

## Upgrade Path (double-entry)
- TransferGroup maps naturally to a future journal-entry header.
- Transaction can be expanded to debit/credit line items later; keep current single-entry rules intact until migration.
