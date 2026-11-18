# ADR-0031: Selling costs, and a liquidation-adjusted net worth

- **Status:** Accepted
- **Date:** 2026-11-04

## Context
Net worth counts a home at its full value, but turning it into cash costs about 4–6%
(realtor, legal). Comparing an owner with a renter on unadjusted net worth favours buying.

## Decision
- `Asset` gains **`sellingCostRate`** (a percentage of the sale price).
- On a `SaleEvent`, selling costs = price × sellingCostRate. They are deducted from the
  proceeds and **reduce the capital gain** (ADR-0017).
- A **liquidation net worth** is available as a tally (`NetWorthTally.liquidationAdjusted`,
  ADR-0027). It is net worth minus what selling everything in that period would cost:
  selling costs and capital gains tax on owned assets, and tax at the effective rate on
  tax-deferred account balances.

## Consequences
- Comparisons and goals can use either net worth or liquidation net worth. Rent vs buy
  should use liquidation net worth.

## Amendment (2026-11-09): liquidation tax rate (C-P6)
- Scenario setting **`liquidationTaxRate`** (rate series; default: the effective tax
  rate; listed as an applied default). It is used for **every tax in liquidation net
  worth**: tax-deferred balances, unrealised gains on TAXABLE accounts (ADR-0054) and
  capital gains on owned assets.
- The pension value (ADR-0052 amendment 2026-11-09) keeps the effective rate: it is
  received over years, not cashed in at once.
- Reason: liquidating everything puts it all in one tax year; the flat rate understates
  that tax by six figures on large balances.
