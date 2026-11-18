# ADR-0033: Revaluation events for sudden changes in value

- **Status:** Accepted
- **Date:** 2026-11-05

## Context
Gradual market moves are negative or positive segments of an asset's value rate
(ADR-0019). A sudden shock (e.g. −20% in one month) cannot be expressed readably as an
annual rate converted to monthly.

## Decision
- A **Revaluation** event adjusts an asset's value once, on a date, either by a
  **percentage** (e.g. −20%) or to a **set value**.
- It is applied in the events step (ADR-0018 step 4), before growth. The period's growth
  is then computed on the opening value as usual, so the revalued value takes effect from
  the next period's growth.
- Like all events it is time-shiftable and taggable (e.g. tagged `market`), so the shift
  tool can move a crash relative to a planned sale.

## Consequences
- A revaluation changes value only. Acquisition price and cost basis are unchanged, so
  variable costs (ADR-0022) and capital gains (ADR-0017) are unaffected by the shock
  itself.
- Market-wide shocks across several properties need one revaluation per asset, all with
  the same tag. A market-level shock object may come later, together with CompositeRate.

## Amendment (2026-11-08): a set value is the month's closing value
- A revaluation **to a set value** (e.g. an appraisal) makes that value the asset's
  **closing value for the month**: no growth is added in that month. Growth resumes from
  the set value the following month.
- A revaluation **by a percentage** is unchanged: applied before the month's growth, which
  is computed on the opening value.
- Shown to users as a **"market adjustment"**. Reason: a set value that ends the month
  slightly above the stated figure looks wrong next to an appraisal.

## Amendment (2026-11-09): market adjustment on accounts (C-P16)
- A Revaluation may target an **Account** (TAXABLE, TAX_FREE, TAX_DEFERRED), not only an
  Asset. For accounts only the **percentage** form is allowed (e.g. −30% in 2030-03);
  the change applies to the balance in the events step, like an asset percentage.
- It is a market move, not a cash movement: the ledger books it as a revaluation against
  outside. No tax, no credit, no deduction.
- A TAXABLE account's **cost basis is unchanged** (ADR-0054): a drop reduces the
  unrealised gain (or creates an unrealised loss), a rise increases it.
- Not allowed on a PensionEntitlement (its value is computed, ADR-0052).
- Purpose: sequence-of-returns stress tests (a crash near retirement), tagged `market`
  and time-shiftable like other events.
