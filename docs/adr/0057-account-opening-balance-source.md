# ADR-0057: Source of an account's opening balance

- **Status:** Accepted
- **Date:** 2026-11-09
- **Relates to:** ADR-0025 (one-off transfer, outside), ADR-0044 (outside money),
  ADR-0053 (ledger), ADR-0054 (cost basis); CRITIQUE.md C-M4

## Context
An account opened inside the horizon brought its opening balance from nowhere: in the
user's file a large RRSP opened mid-horizon made net worth jump by its balance with no
source.
The entry meant "my balance today"; the money existed before but was not modelled.
Accounts opened before the horizon took the opening balance as the balance at horizon
start, while assets are grown from their purchase date; this was undocumented.

## Decision
- An Account with `openedOn` **inside the horizon** and a non-zero `openingValue` must
  state **`openingFrom`** (essential, no default):
  - **CASH**: a transfer from the operating account on the opening date (e.g. opening a
    TFSA with savings).
  - **OUTSIDE**: an existing balance not modelled before. The ledger books it as
    "opening balance from outside"; the result warns about the net-worth jump.
- For an account opened **before or at the horizon start**, `openingValue` is the
  **balance at the horizon start** (a statement balance). It is not grown from
  `openedOn`. This differs from assets, which are grown from purchase, because an
  account's past contributions are unknown.
- A TAXABLE account's opening cost basis defaults to its opening value in both cases
  (ADR-0054).

## Consequences
- No balance appears without a stated source.
- An OUTSIDE opening is the user's way of saying "known today, history not modelled";
  net worth before that date understates the household.
