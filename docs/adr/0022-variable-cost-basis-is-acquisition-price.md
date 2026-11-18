# ADR-0022: A variable cost is a percentage of the asset's acquisition price

- **Status:** Accepted
- **Date:** 2026-11-04

## Context
Costs such as maintenance are "% of the asset". Basing them on the current *depreciated*
value makes vehicle maintenance fall as the car ages, the opposite of reality.

## Decision
- Variable cost (monthly) = rate(P) × **acquisition price** / 12, where the rate comes from
  the cost's rate generator (e.g. X% during the warranty, then X'%).
- The acquisition price is the purchase price of the asset, i.e. what it cost to acquire.
  It is a fixed input. It is **not** the cost basis, which grows as costs are paid
  (ADR-0014). Using the cost basis would compound costs on themselves.
- The cost's **indexing** (ADR-0013) still applies on top, e.g. an inflation-indexed
  maintenance cost.

## Consequences
- `Asset` gains `acquisitionPrice` (input). `costBasis` is the running metric: acquisition
  price + costs paid.
- For long horizons such as houses, a variable cost should normally be inflation-indexed,
  or the percentage of an old purchase price will understate future costs.
