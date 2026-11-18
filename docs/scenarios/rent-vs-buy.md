# Scenario set: rent vs buy

Two competing scenarios with the **same horizon and the same income and living expenses**.
They differ only in housing. Buy-side objects are tagged `housing:buy`, rent-side objects
`housing:rent` (ADR-0023). ⚠ marks gaps.

## Common
| Element | Type | Details |
|---|---|---|
| Horizon | `Horizon` | same in both |
| Salary (net) | `CashFlow` → bank | same in both |
| Living expenses | `CashFlow` bank → (outside) | InflationIndexed, same in both |
| Bank | `Account` (TAXABLE) | operating account; income lands here |
| Investments | `Account` (TFSA or TAXABLE) | target of the sweep rule: bank buffer $X → investments (ADR-0030) |
| Inflation, effective tax rate | `RateGenerator` | shared, untagged |

## B: buy
| Element | Type | Details |
|---|---|---|
| Home | `RealEstate`, principalResidence = true | acquisitionPrice, appreciation generator |
| Purchase | `PurchaseEvent` | paidFrom = bank (down payment), financedBy = mortgage |
| Closing costs | `OneOffTransfer` bank → (outside) | land transfer tax, legal fees, inspection; entered as an amount |
| Mortgage | `Mortgage` securedBy home | principal = price − down payment (+ CMHC premium if under 20% down, entered); `TermScheduleRate` |
| Mortgage payments | derived by the engine, paymentFrom = bank (ADR-0029) | |
| Property tax, home insurance, condo fees | `FixedCost` | InflationIndexed |
| Maintenance | `VariableCost` | % of acquisition price, InflationIndexed |
| Selling costs | `sellingCostRate` ≈ 5% on the home (ADR-0031) | |

## R: rent
| Element | Type | Details |
|---|---|---|
| Rent | `CashFlow` bank → (outside) | CustomRate (e.g. rent increase guideline) |
| Tenant insurance | `FixedCost`-like cash flow | |
| Down payment + closing costs not spent | swept to investments (ADR-0030) | |
| Monthly difference (owner costs − rent) | swept to investments (ADR-0030) | |

## Comparison
- **Liquidation net worth** at the end of the horizon (real dollars) (ADR-0031).
- Total cost by tag (`housing:buy` vs `housing:rent`).
- Net worth over time: the crossover period (when buying overtakes renting) is a key output.

## Decisions taken from this scenario
R1 → ADR-0029, R2 → ADR-0030, R3 → ADR-0031, R4 → ADR-0028, R5 → ADR-0032, break-even →
ADR-0027 + ADR-0028.

Assumptions: closing costs and the CMHC premium are entered amounts, not calculated by tax
rules. TFSA contribution limits are not enforced (Q-06).

## Break-even goal (requested, being defined)
"Report when owning has paid off compared with renting": e.g. thanks to appreciation, after
about 2 years the owner is ahead of what rent would have cost. Principal residence, so no
tax on the gain (ADR-0017).

Candidate definition, per period P (all cumulative from the purchase):
- owner's net gain G(P) = (home value − mortgage balance) − cash paid out on `housing:buy`
  (down payment, closing costs, mortgage payments, costs)
  = appreciation − (interest + property tax + insurance + maintenance + closing costs)
- renter's cost R(P) = cumulative rent paid (+ tenant insurance) on `housing:rent`
- break-even condition (decided): **G(P) ≥ −R(P)**, i.e. owning has cost no more than
  renting. The literal "gain ≥ rent" was rejected because it counts the rent twice.
- Evaluation: tallies plus a goal evaluated every month by the stepping stage (ADR-0027,
  Proposed):
  - tally `ownerNetGain` (in the buy scenario) = Derived: (VALUE(home) − BALANCE(mortgage)) − TagSum(housing:buy, outflows)
  - tally `rentSpent` = TagSum(housing:rent, outflows), in the rent scenario
  - goal REACH: ownerNetGain + rentSpent ≥ 0, which reports the break-even period
- buy and rent run in lockstep as one scenario set (ADR-0028). The break-even goal is a **set-level goal**: `buy.ownerNetGain + rent.rentSpent ≥ 0`.
