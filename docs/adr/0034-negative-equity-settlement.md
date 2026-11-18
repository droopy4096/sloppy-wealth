# ADR-0034: Settling a sale when proceeds do not cover the secured loans

- **Status:** Accepted
- **Date:** 2026-11-05
- **Amends:** ADR-0018 step 4 (sale settlement), ADR-0024

## Context
After a price drop, an asset may sell for less than the balance of the loans secured by it
(negative equity). The settlement rule assumed the remainder after paying off the loans was
always positive.

## Decision
Sale settlement order:
1. Gross proceeds = sale price.
2. Deduct selling costs (ADR-0031).
3. Pay off every loan secured by the asset, plus early closure penalties.
4. Deduct capital gains tax, if any (ADR-0017).
5. If the remainder is **positive**, credit it to `proceedsTo`.
6. If it is **negative**, debit the deficit from `proceedsTo`. The debit is **capped at
   available funds**, and any unpaid part is recorded as a **shortfall** on the sale
   (ADR-0015).

The loans are always closed by the sale. An unpaid deficit is reported as a shortfall,
not carried as a residual debt.

## Consequences
- A MAINTAIN goal on the sale proceeds account's SHORTFALL catches unaffordable sales.
- Not modelled: carrying the deficit as a new unsecured loan, or lender actions.
- Capital losses still produce no tax credit (ADR-0017).
