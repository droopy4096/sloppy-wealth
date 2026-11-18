# ADR-0046: Improvements (construction, renovation) are events on an existing asset

- **Status:** Accepted
- **Date:** 2026-11-07
- **Relates to:** ADR-0025 (financed purchase, market value), ADR-0017 (cost basis),
  ADR-0022 (variable costs), ADR-0034 (sale settles secured loans)

## Context
Building a house on a parcel already owned, or renovating, adds cost and value to an asset
that exists. Modelling it as a second asset (the PoC's separate "house" asset on a lot) splits one
property in two: two sales to keep in step, a secured loan attached to only one part, and
per-property settings (value rate, selling cost, principal residence) duplicated.

## Decision
- A new event, **`ImprovementEvent`**, on an existing `Asset`:
  - `date`, `cost : Money`, `paidFrom : Account`, `financedBy : Loan [0..1]` (as for a
    purchase, ADR-0025: the loan advance funds the cost);
  - `valueAdded : Money [0..1]`, defaulting to `cost`.
- Effects in its period (events step, ADR-0018):
  - cash (and/or the loan advance) pays the **cost**;
  - the asset's **cost basis** and **acquisition price** increase by the cost (capital
    gains, ADR-0017; variable costs, ADR-0022);
  - the asset's **value** increases by `valueAdded`, then keeps growing at its value rate.
- A loan financing the improvement is normally **secured by the same asset**, so a sale of
  the asset settles it (ADR-0034).

## Alternatives considered
- Keep one asset per construction or renovation: no model change, but the problems above.
- Purchase followed by a Revaluation: does not raise the cost basis, so capital gains would
  be wrong.

## Consequences
- The baseline scenario's lot and house become one property: the parcel purchase plus
  an improvement (its cost financed by a mortgage, a value added above the cost).
- A value added above the cost is an unrealised gain in net worth, as with a purchase
  market value (ADR-0025 amendment).
- Maintenance set as a % of acquisition price rises after an improvement, since a larger
  house costs more to maintain.
