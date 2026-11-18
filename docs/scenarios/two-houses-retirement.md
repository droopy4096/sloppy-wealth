# Walkthrough scenario: two houses to retirement fund

Used to test the domain model and pipeline end to end. The numbers are illustrative;
⚠ marks assumptions to confirm.

## Facts (from the user)
- Owns two houses today, each with a mortgage and an appreciation rate.
- Sells both in 10 years. The proceeds go to the bank account, which becomes the
  retirement fund (finite).
- Retires at 60, plans until 80. Question: does the fund cover the expected pension draw?

## The scenario in model terms

| Element | Type | Details |
|---|---|---|
| Economic unit | `EconomicUnit` | reference birth date ⚠ 1975-03 |
| Horizon | `Horizon` | 2026-11 to 2055-03 (age 80) |
| Inflation | `RateSeries` | ⚠ 2.5% |
| Effective tax rate | `RateSeries` | ⚠ 30% |
| Bank | `Account` (TAXABLE) | opening ⚠ $15k, return ⚠ 2% |
| H1 | `RealEstate`, principalResidence = **true** | value / cost basis ⚠, appreciation ⚠ 3% |
| H2 | `RealEstate`, principalResidence = false | value / cost basis ⚠, appreciation ⚠ 3% |
| M1, M2 | `Mortgage` securedBy H1, H2 | rate, amortisation, term, penalty rule ⚠ |
| Mortgage payments | derived by the engine, paymentFrom = bank (ADR-0029) | |
| H1, H2 costs | `FixedCost` (property tax, insurance), `VariableCost` (maintenance % of value) | |
| Salary (net, take-home) | `CashFlow` → bank | until 2037-03, CustomRate or generator for raises ⚠ |
| Living expenses | `CashFlow` bank → (outside) | InflationIndexed, whole horizon ⚠ |
| H2 rental income | `CashFlow` → bank, taxable = true | possible; included as an option |
| Sale of H1, H2 | 2 × `SaleEvent` at 2034-05 | proceeds → bank |
| Retirement | salary ends 2037-03 | |
| Pension draw | `CashFlow` bank → (outside) | $2.5k/month, InflationIndexed, 2037-03 to 2055-03 |
| Goal G1 | `LocalGoal` MAINTAIN on bank: SHORTFALL = 0 | "the fund lasts until 80" |
| Goal G2 | `LocalGoal` REACH on M1: BALANCE = 0 | "mortgage paid off" (optional) |

## What the walkthrough shows
- `SaleEvent` needs `proceedsTo : Account` (and `PurchaseEvent` needs `paidFrom`).
  Added to the class diagram, v0.3.
- A sale triggers a **settlement**: pay off the secured mortgage (+ early closure penalty),
  capital gains tax (H2 only), remainder to the bank, and the property's costs and
  mortgage payments stop.
- The order of steps within a month (Q-08) is decided in ADR-0018.
- Income is entered net by default; taxable income (e.g. rent) is flagged (ADR-0020).
