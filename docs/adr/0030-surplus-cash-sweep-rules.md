# ADR-0030: Sweep rules move surplus cash into investment accounts

- **Status:** Accepted
- **Date:** 2026-11-04
- **Amends:** ADR-0018 (adds a sweep step)

## Context
Income lands in an operating account, so without a sweep, unspent money earns only that
account's rate. In rent vs buy this understates renting, because the opportunity cost of
the down payment and of the monthly difference goes missing.

## Decision
- A scenario can define ordered **SweepRules**: `from : Account`, `buffer : Money`,
  `to : Account`. Each month, anything in `from` above `buffer` moves to `to`.
- Sweeps run **after tax and before close** (new step 7a in ADR-0018), so the period's tax
  has already been paid before anything is swept.
- Swept money earns returns in its target account from the next period, because growth is
  computed on opening balances (ADR-0018).
- Sweeps go **one way only**. Covering a shortfall by drawing from investment accounts (a
  withdrawal waterfall) remains out of scope (ADR-0015).

## Consequences
- In rent vs buy, both scenarios sweep the bank into the same investment account, so the
  renter's unspent money is invested on equal terms.
- Contribution limits (e.g. TFSA room) are not enforced (watch item Q-06).
