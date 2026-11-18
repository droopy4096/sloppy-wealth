# ADR-0062: Adjustment of a cash flow's amount (CashFlowAdjustment)

- **Status:** Accepted
- **Date:** 2026-11-11
- **Relates to:** ADR-0012 (events, cash flows), ADR-0013 (indexing), ADR-0033 (revaluation
  of assets), ADR-0043 (renewals: last one in a month wins)

## Context
Indexed amounts grow smoothly, but real bills do not: property tax can stay flat for years
and then jump; a salary changes with a promotion. Today the only way is to end the item
and start another one, which breaks when dates move. The domain model already has
`CashFlowAdjustment` (a new amount on a date); the PoC has not built it. Asset values have
`marketAdjustment` (ADR-0033), but only for properties.

## Decision
1. **A new `adjustment` item** names a cash flow (income, expense, contribution, or a
   withdrawal with method amount), a date and a new amount (with `per`, default the
   flow's). From that month the flow's amount is the new amount.
2. **`marketAdjustment` also accepts vehicles** (ADR-0033 amendment): their value is set
   (percent or new value) and depreciation continues from it.

### Mechanics (defaults; not separate owner decisions)
- The new amount is in dollars of the adjustment date. Indexing continues with the flow's
  own indexing; its yearly steps count from the adjustment date.
- Several adjustments of one flow follow each other; in one month the last in item order
  wins (as renewals, ADR-0043).
- An adjustment outside the flow's window changes nothing until (unless) the flow runs.
- Each adjustment appears in the event log in its month.
- Not covered: pensions (their own indexing, ADR-0052), percent and annuity withdrawals
  (derived amounts), vehicle maintenance (an attribute of the vehicle; use an attached
  expense, ADR-0040 amendment, for a cost that needs resets).

## Alternatives considered
- One generic adjustment item for flows and asset values: mixes a flow's amount and an
  asset's value in one form; duplicates `marketAdjustment`.
- Splitting the flow into dated pieces (no change): manual, breaks when dates move.

## Consequences
- Bills that change in steps are entered as one flow plus adjustments.
- Older files are unchanged.

## Amendment (2026-11-11): new rate for percent withdrawals
- An adjustment of a withdrawal with method `percent` gives a new `annualRate` (fraction)
  instead of an amount. From the adjustment month the withdrawal takes that rate: its
  monthly amount is re-set then (opening balance × rate / 12, as at its start) and on
  each anniversary of the adjustment date.
- Several follow each other; in one month the last in item order wins. Annuity
  withdrawals stay out of scope (derived amounts).
