# ADR-0025: Generic one-off transfers, and purchases financed by a loan

- **Status:** Accepted
- **Date:** 2026-11-04

## Context
Lease down payments, one-off bills and gifts are single movements of money that are not
tied to a loan. A financed purchase is paid partly from an account and partly by a loan.

## Decision
- **OneOffTransfer** event: amount, `from : Account [0..1]`, `to : Holding [0..1]`, tags.
  Leaving out `from` means money comes in from outside (e.g. a gift). Leaving out `to`
  means money leaves the economic unit (e.g. a bill, a down payment).
- **PurchaseEvent** gains `financedBy : Loan [0..1]`. The loan's principal covers part of
  the price; the rest comes from `paidFrom`.

## Consequences
- OneOffTransfer debits follow the capping and shortfall rule (ADR-0015). They run in the
  events step (ADR-0018 step 4), after income.
- `LumpSumPrepayment` stays as the specialised event for prepaying a loan, because it is
  subject to prepayment options.

## Amendment (2026-11-07): a purchase may set a market value different from its price
- A `PurchaseEvent` has an optional **`marketValue`**. When given:
  - cash leaves `paidFrom` (and the financing loan) for the **price**;
  - the asset's **cost basis** and **acquisition price** are the price (capital gains,
    ADR-0017; variable costs, ADR-0022);
  - the asset's **value** starts at `marketValue` and is then projected by its value rate.
- The difference is an unrealised gain (or loss) that shows in net worth from the purchase
  period. On a later sale of an asset that is not a principal residence, it is part of the
  taxable gain.
- Typical use: a house built for less than it is worth (e.g. built for $300,000,
  market value $450,000). Equivalent to a purchase followed by a `Revaluation` (ADR-0033)
  in the same period, without needing two events or an ordering rule between them.

## Amendment (2026-11-09): closing costs are inside the mortgage amount (C-P12)
- **Assumption:** purchase closing costs (land transfer tax, legal fees, inspection) are
  rolled into the mortgage; the **mortgage principal the user enters already includes
  them**. There is no `closingCosts` field.
- Closing costs therefore do not raise the cost basis. A capital gain on a later
  non-principal-residence sale is overstated by them (a few percent of the price).
- If they were paid in cash instead, the user adds them to the down payment or as a
  one-off transfer in the purchase month.
