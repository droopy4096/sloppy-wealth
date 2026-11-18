# ADR-0013: Per-cash-flow indexing, with nominal and real reporting

- **Status:** Accepted
- **Date:** 2026-11-04

## Context
Inflation affects money in different ways: some amounts are fixed by contract, some rise
with prices, and some grow at their own rate. Long-horizon results are also hard to read
in nominal dollars.

## Decision
- Each cash flow declares its **indexing**: fixed nominal, inflation-indexed, or a custom
  rate series.
- Results can be reported in **nominal** dollars or in **real** dollars, i.e. deflated by
  the inflation series to the dollars of a reference date (by default the scenario start).

## Alternatives considered
- Indexing every cash flow to inflation: wrong for contractual amounts such as mortgage
  payments.
- Using inflation only for reporting: misses costs that rise with prices.

## Consequences
- Converting to real dollars happens during result assembly or in the view, never inside
  the monthly stepping stage. Movements stay nominal and rounded (ADR-0009).
- Goals need to say whether their target is nominal or real (e.g. "$3k/month in today's
  dollars"). To be decided in the domain model.

## Amendment (2026-11-07): an amount is in dollars of its own start date
- The amount of a cash flow is stated **in dollars of its start date**: a past contract in
  the dollars of the day it was signed, a current one in today's dollars, a future one in
  the dollars of the date it starts.
- Indexing grows the amount **from its start date** onward. Amounts are never re-based to
  the scenario start.
- Targets stated "in today's dollars" belong to goals, which carry a REAL basis
  (ADR-0014), not to cash flows.
- The PoC already behaves this way: an indexed amount steps up on each anniversary of the
  item's start date.

## Amendment (2026-11-07): the base date is named and settable
- The reference date of real values is called the **base date**, shown to users as "show
  real values in dollars of". It defaults to the scenario start and can be any date,
  typically today. Months before it are inflated to its dollars, months after deflated.
- Views label real columns with the base month (e.g. "Net worth (2026-11 $)"), and a
  comparison shows each scenario's base date with its inflation rate (ADR-0028 amendment).

## Amendment (2026-11-07): indexed amounts step up once a year, on the item's anniversary
- An indexed cash flow (inflation or custom rate) changes **once a year, on the
  anniversary of its own start date**: amount × (1 + rate)^(full years since start). This
  matches how salaries, rents and pensions change (a raise, a lease renewal, the annual
  pension adjustment).
- To step in a particular calendar month (e.g. a pension adjusted every January), start
  the item in that month.
- Each year's amount is **recomputed from the stated figure** and then rounded (ADR-0009),
  so rounding does not compound.
- Monthly compounding of indexation and a fixed calendar month for all items were
  considered and rejected: neither matches real contracts.

## Amendment (2026-11-07): the base date is part of the scenario
- `Scenario.baseDate [0..1]` (default: horizon start) is **input**, saved with the
  scenario. Goals with a REAL basis (ADR-0014) and real-value outputs both use it, so a
  target such as "$3,000/month in today's dollars" means the same on every run.
- Views may additionally show other base dates; that never changes goal results.

## Amendment (2026-11-09): base date is input only; display date is separate (C-P14)
- `Scenario.baseDate` defines **"today's dollars" for inputs**: pension amounts
  (ADR-0052), REAL goals (ADR-0014). Changing it restates those inputs; it is not a
  display setting. Authoring screens label it "amounts entered in dollars of" and warn
  that changing it changes the pension cash flows.
- Real-value **display** uses a separate **`displayDollarsOf`** (a view/result-request
  setting, not saved in the scenario; default: the scenario's baseDate). Changing it only
  rescales the real columns; it never changes cash flows or goal results.
- Real columns are labelled with the display month (e.g. "Net worth (2030-01 $)").

## Amendment (2026-11-09): an amount may be stated in base-date dollars
- An income or expense cash flow may set **`amountIn`**: `start` (default: dollars of its
  own start date, as above) or `base` (dollars of the scenario's base date, "today's
  dollars").
- With `base`, the amount at the item's start is the stated amount × (1 + inflation)^(t),
  t = years from the base date to the item's start (fractional; negative for a start
  before the base date). The item's own indexing then applies from its start as usual.
- Typical use: retirement living expenses known in today's money that start years from
  now; moving the start (e.g. a RetirementEvent sweep) moves the inflation with it.
- Same convention as pension amounts (ADR-0052), which are always in base-date dollars.
