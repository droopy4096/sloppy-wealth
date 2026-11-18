# ADR-0074: Vehicle cost of ownership per month

- **Status:** Proposed (owner's decision 2026-11-18, Q-50)
- **Date:** 2026-11-18
- **Relates to:** ADR-0073 (property break-even: the same approach), ADR-0067
  (associated expenses and costs)

## Context
After the property break-even (ADR-0073), the owner wants a similar calculator for
vehicles: each month, everything paid for the vehicle so far, less its value, spread
over the months owned: the total cost of ownership per month.

## Decision (Q-50, owner 2026-11-18: "same as properties")
1. **From the run**, like ADR-0073: per month owned, from the ledger and holdings.
2. **Paid so far** = the purchase price plus every associated expense and cost of the
   vehicle (fuel, insurance, maintenance, repairs) paid up to that month.
3. **Value** = its market value at the month's end less its selling costs (associated
   costs at its end, ADR-0067), if any.
4. **Cost per month** = (paid so far − value) / months owned.
5. **Bought before the horizon**: its value at the horizon start counts as already
   paid, and months count from the horizon start. A real sale ends the table.
6. **Page** like the break-even one: a summary (cost per month at the base month and at
   the end) and a monthly table with short titles and tooltips (Month, Owned (mo),
   Value, Sale costs, Paid so far, Cost/mo), opened by the chart icon on each vehicle's
   card and row. One figure (no owner/all split).

## Alternatives considered
- Also a depreciation-only figure ((purchase − value) / months) beside the total.
- The value without selling costs (strictly the formula as first stated).

## Consequences
- New view `state_machine/vehicle_cost.py`, `POST /api/view/vehicle-cost`, page
  `/run/vehicle-cost`. No new fields; results unchanged.
