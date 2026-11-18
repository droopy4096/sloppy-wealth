# ADR-0042: Free income can be declared net of payments the engine models

- **Status:** Deferred (2026-11-07)
- **Date:** 2026-11-05
- **Builds on:** ADR-0040 (crude input is first-class), ADR-0029 (derived loan payments)

## Context
Users naturally state "free income": what is left after paying everything, including
mortgages. The engine also derives and debits mortgage payments itself (ADR-0029), so
entering free income as-is counts the mortgages twice. Asking the user to add the payments
back by hand defeats the point of crude input, and breaks when payments change (renewals,
a sale).

## Decision (proposed)
- An income `CashFlow` can declare **`netOf`**: a list of loans, costs or cash flows that its
  amount has already been reduced by.
- Each period, the engine credits **the amount plus the current amounts of the `netOf`
  items that are active in that period**. The engine then debits those items normally, so
  the net effect equals the stated free income.
- When a `netOf` item ends (e.g. a loan is paid off or settled by a sale), the add-back
  ends too, so the free income rises by the payment no longer made, which is what happens
  in reality.

## Alternatives considered
- Authoring tooling grossing the figure up by hand: it would have to duplicate the
  payment logic and goes stale at renewals and sales.
- Not modelling mortgages when free income is used: loses balances, equity and the sale
  settlement.

## Consequences
- The add-back amounts are recorded as movements tagged with the income, so they stay
  visible and auditable.
- `netOf` items must belong to the same scenario; this is validated on input.

## Deferral (2026-11-07)
- Deferred, not rejected. ADR-0044 (income-less mode) covers the case with no free money,
  and the scenarios at hand have full income and expense data, so nothing needs `netOf` now.
- Revisit when a scenario states a partial "free income" alongside modelled loans.
