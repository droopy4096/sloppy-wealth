# ADR-0026: A holding can exist without being owned (lease, then buyout)

- **Status:** Accepted
- **Date:** 2026-11-04

## Context
For a lease, the buyout price at the end should follow from the vehicle's depreciation
(MSRP depreciated to the lease end), not from a hand-entered number.

## Decision
- `Holding` gains **`owned : bool`** (default true).
- A holding that is not owned is still projected (its value follows its value rate each
  month), but it:
  - is **excluded from net worth** and from global goals,
  - carries **no costs** and cannot be sold.
- A `PurchaseEvent` on an existing holding that is not owned **transfers ownership**. Its
  price defaults to the holding's **current projected value** in that period. From then on
  the holding is owned and counts normally.
- If the lease ends without a buyout, nothing more is needed: the vehicle that is not
  owned remains excluded.

## Alternatives considered
- A price derived by a formula on the buyout event: a one-off concept used by a single case.
- A hand-entered residual value: drifts when the depreciation assumption changes.

## Consequences
- `PurchaseEvent.price` becomes optional: required for a new holding, defaulting to current
  value for one that is not owned.
- Lease-related costs (payments, maintenance) are modelled as cash flows tagged with the
  lease, not as costs of the holding.

## Amendment (2026-11-04): reset on ownership transfer
- When a purchase transfers ownership of a holding that was not owned, the holding's
  **acquisition price and cost basis are reset to the buyout price**. From then on, variable
  costs (ADR-0022) and capital gains (ADR-0017) are based on what was actually paid, the
  same as buying a used vehicle.
