# ADR-0063: Cash balance reconciliation item

- **Status:** Accepted
- **Date:** 2026-11-11
- **Relates to:** ADR-0011 (holdings, implicit cash), ADR-0033 (revaluation; C-P16 market
  adjustment of accounts), ADR-0062 (cash flow adjustment)

## Context
A plan that starts in the past (the owner's starts in 2019) drifts from the real bank
balance: actual spending, gifts and one-off costs are not all modelled. Today the cash
balance can only be corrected with a one-month income or expense whose amount must be
worked out by hand and goes stale when earlier items change.

## Decision
A **`cashBalance` item** (`balanceDate`, `balance`) states the actual cash balance at the
end of that month. The engine sets cash to it; the difference is a
`CASH_RECONCILIATION` movement from or to outside the model.

### Mechanics (defaults; not separate owner decisions)
- Applied after the month's tax step, before the month's results row, so the row shows the
  stated balance.
- Not income, not an expense, not taxable; it changes no other holding.
- Several items follow each other (e.g. one per statement); in one month the last in item
  order wins.
- The date must be within the horizon. Also applies in income-less mode.
- Visible in the ledger and the event log (the difference, and the balance before).
- Investment accounts are not covered (C-P16, decided, built separately).

## Alternatives considered
- `marketAdjustment` on cash: cash does not change value; the name and its percent option
  do not fit.
- One-month income or expense (no change): manual and goes stale.

## Consequences
- Plans can be anchored to real statements; the gap between plan and reality is shown.
