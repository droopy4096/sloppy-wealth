# Scenario set: vehicle ownership (new vs lease vs used)

Three competing scenarios over the **same horizon**, compared against each other
(ADR-0006). Every vehicle-related object is tagged `vehicle` (ADR-0023). Prices are
entered including HST. Insurance and registration are optional `FixedCost`s.

## Common to all three
| Element | Type | Details |
|---|---|---|
| Horizon | `Horizon` | same start and end in all three, length T years |
| Bank | `Account` (TAXABLE) | pays for everything; has a return rate, so money spent on the car shows up as investment growth forgone |
| Inflation | `RateGenerator` (untagged, shared) | for real-dollar comparison |

## S1: buy new from a dealer
| Element | Type | Details |
|---|---|---|
| Vehicle | `Vehicle` | acquisitionPrice = P_new, `valueRate` = depreciation (negative) |
| Purchase | `PurchaseEvent` | paidFrom = bank, or financed (below) |
| Car loan (optional) | `Loan` securedBy vehicle | rate, amortisation; payments bank → loan |
| Maintenance | `VariableCost` | `SegmentedRate` (tagged `vehicle`): X% for N years (warranty), then X'% |

Shifting the purchase: shift tag `vehicle`. The vehicle, the purchase, the loan, the cost
and the warranty rate segments move together.

## S2: lease
| Element | Type | Details |
|---|---|---|
| Vehicle | `Vehicle`, owned = **false** | acquisitionPrice = MSRP, depreciation generator; projected but not in net worth |
| Down payment | `OneOffTransfer` bank → (outside) | at lease start |
| Lease payment | `CashFlow` bank → (outside) | monthly, FixedNominal, for the lease term |
| Maintenance | `FixedCost` | |
| Buyout at lease end (optional) | `PurchaseEvent` on the leased vehicle | price omitted, so its current projected value is used; vehicle becomes owned, maintenance switches to a `VariableCost` from then on |

## S3: buy used, M years old
| Element | Type | Details |
|---|---|---|
| Vehicle | `Vehicle` | acquisitionPrice = P_used, its own depreciation generator |
| Purchase | `PurchaseEvent` | paidFrom = bank (or Loan) |
| Maintenance | `VariableCost` | Y% of P_used |

## Comparison
- Primary: **net worth at the end of the horizon** (real dollars). An owned car is
  counted at its residual value; a lease leaves nothing.
- Secondary: **total cost by tag `vehicle`**, i.e. the sum of all tagged movements.

## Decisions taken from this scenario
G1 → ADR-0021, G2 → ADR-0022, G3/G4 → ADR-0023, G6 → ADR-0024, G5 → ADR-0025 (L1), ADR-0026 (L2).
