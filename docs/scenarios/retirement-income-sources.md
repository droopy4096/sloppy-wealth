# Scenario: retirement income sources (RRSP drawdown vs guaranteed pension)

Two shapes of retirement money:
- **RRSP**: a finite pot. Withdrawals are taxed and the pot can run out.
- **Pension** (defined-benefit-like, or CPP/OAS-like): a guaranteed monthly income from a
  start date until the recipient's death, indexed to inflation. No pot, and it cannot run
  out.

Death = the end of the scenario's horizon (the planned lifespan, e.g. age 80; ADR-0016).

## Mapping onto the model
| Element | Type | Details |
|---|---|---|
| RRSP | `Account`, taxTreatment = TAX_DEFERRED | balance, return rate; tagged `retirement` |
| RRSP withdrawals | `CashFlow` RRSP → bank | from the retirement date; capped at the balance → shortfall when it runs out (ADR-0015) |
| Tax on withdrawals | tax step (ADR-0018 step 7) | rate = RRSP withdrawalTaxRate or the scenario rate; paid from taxPaidFrom |
| Pension | `CashFlow` (outside) → bank | start = pension start, end = horizon end, `InflationIndexed` (or `CustomRate` for partial indexing), taxable = true; tagged `retirement-income`; not in net worth |
| Goal "≥ $3k monthly retirement income" | goal on a tally of monthly inflows tagged `retirement-income`, window PERIOD, activeFrom = retirement |
| Goal "RRSP lasts to 80" | MAINTAIN: SHORTFALL(RRSP withdrawals) = 0 |

## Decisions taken from this scenario
- P1 → ADR-0035: an optional withdrawalTaxRate per tax-deferred account, falling back to
  the scenario rate.
- P2 → ADR-0035: withdrawals are gross; the engine does not gross them up.
- P3 → ADR-0035: the scenario's taxPaidFrom account pays every tax.
- P4 → ADR-0036: RRIF not modelled (Q-13).
- P5 → ADR-0036: a pension is income only, with no net worth value (Q-14).
- P6 → ADR-0037: TagSum window PERIOD; goal active window.
  "≥ $3k monthly retirement income" = MAINTAIN, TagSum(retirement-income, IN, PERIOD) ≥ $3k
  (real), activeFrom = the retirement date.
- P7 → Q-15 (later).
