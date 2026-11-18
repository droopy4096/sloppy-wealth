# Scenario: retirement readiness after selling one property

## Question
"How many years from today until I can sell one property and retire on $3,500/month?"
Deliberately simple: only the important points are modelled (ADR-0040).

## Given
| Fact | Value |
|---|---|
| Income | $150,000/yr (crude: net income + one "monthly expenses" figure, or just "free income") |
| Property A | value $600k, mortgage ~$300k |
| Property B | value $850k, mortgage ~$400k |
| Vehicles | 2 × value ~$12k, maintenance $1,500/yr each |
| RRSP | $80k today, contributions $600/month |
| Guaranteed pension | $1,500/month, starts at retirement |
| Target retirement income | $3,500/month |
| Horizon end | estimated death (a date, or years from today); no age needed |

## Simplified model (base scenario)
| Element | Type | Notes |
|---|---|---|
| Operating account | implicit "cash" (ADR-0040) | income lands here, and it pays everything |
| Free income, or salary + monthly expenses | `CashFlow`s, tagged `work` | end = retirement |
| Property A, B | `RealEstate`, value, appreciation (default 0) | A tagged `exit` |
| Mortgages A, B | `Mortgage`: balance, rate, amortisation; payments derived (ADR-0029) | |
| Vehicles | `Vehicle` ×2, $12k each; `FixedCost` $1.5k/yr each (ADR-0021: spread monthly) | replacement ignored |
| RRSP | `Account` TAX_DEFERRED, $80k | |
| RRSP contributions | `CashFlow` cash → RRSP, $600/month, tagged `work` | end = retirement |
| Sale of A | `SaleEvent`, proceedsTo = investments account, tagged `exit` | settlement per ADR-0034 |
| Pension | income `CashFlow` $1.5k/month, tagged `exit`, `retirement-income` | starts at retirement |
| Drawdowns | `DrawdownCashFlow` from the RRSP and from investments, tagged `exit`, `retirement-income` (ADR-0039) | start at retirement |
| Goal | MAINTAIN: TagSum(retirement-income, IN, PERIOD) ≥ $3,500, activeFrom = retirement | tagged `exit` so it moves too |

## Answering "how many years"
A variant sweep (ADR-0038): shift everything tagged `exit` and the end of everything tagged
`work` by +0, +1, …, +20 years. The engine runs the set in lockstep, and the earliest
variant whose goal holds is the answer.

## Ignored on purpose
Vehicle replacement (V1), RRSP contribution tax deduction (T1), renting, age.

## Inputs (from the user)
| Input | Value |
|---|---|
| Mortgage rate (A and B) | 4.5%, semi-annual compounding (ADR-0019) |
| Appreciation (A and B) | 4%/yr |
| Free income | $25,000/yr |
| Horizon | 30 years from today (estimated death) |
| ⚠ Remaining amortisation | not given; 25 years assumed below |

## Goal (decided)
The $3.5k must also cover B's mortgage, which continues in retirement. So the goal is on a
**derived tally**, disposable retirement income:

- `disposable` = TagSum(retirement-income, IN, PERIOD) − TagSum(mortgage-B, OUT, PERIOD)
- MAINTAIN: `disposable` ≥ $3,500, REAL, activeFrom = activeUntil = the retirement month
  (ADR-0014 amendment, ADR-0027, ADR-0037). With inflation at its default of 0, real =
  nominal.

## Free income (decided)
$25,000/yr is **after** mortgage payments. It is modelled with `netOf = [mortgage A,
mortgage B]` (ADR-0042), so the engine does not count the mortgages twice.
**ADR-0042 is deferred (2026-11-07):** until it is revisited, this scenario has to be
entered as gross income and expenses instead of a single free-income figure.
⚠ Is it also after vehicle costs and RRSP contributions?

## Sweep (decided)
`exit` shifted with BOTH, `work` shifted with END, +0 … +20 years (ADR-0041).

## Rough hand check (illustrative only; validates the model, not a result)
Assumptions: 25-year amortisation (confirmed); free income is after mortgages, vehicle
costs and RRSP contributions; neutral defaults for everything else (no tax, no selling
costs, 0 returns, 0 inflation); accumulated cash is drawn down too.

- Mortgage payments: monthly rate (1 + 0.045/2)^(1/6) − 1 ≈ 0.3715%; A ≈ $1,660.42/month,
  B ≈ $2,213.89/month.
- Needed: drawdown ≥ $3,500 − $1,500 pension + $2,213.89 B mortgage ≈ **$4,214/month**.

| Retire in year | A value | A balance | Proceeds | RRSP | Cash | Pots | Months left | Drawdown |
|---|---|---|---|---|---|---|---|---|
| 0 | 600k | 300k | 300k | 80k | 0 | 380k | 360 | ~$1,060 ❌ |
| 5 | 730k | 263k | 467k | 116k | 125k | 708k | 300 | ~$2,360 ❌ |
| 8 | 821k | 237k | 584k | 138k | 200k | 922k | 264 | ~$3,490 ❌ |
| 9 | 854k | 228k | 626k | 145k | 225k | 996k | 252 | ~$3,950 ❌ |
| 10 | 888k | 218k | 670k | 152k | 250k | 1,072k | 240 | ~$4,470 ✅ |

So, roughly **10 years** under these assumptions (4 years if B's mortgage did not have to be
covered).

Side observation: B's mortgage ends in year 25. From then on, disposable income rises by
about $2,200/month, so the fixed drawdown is front-loaded against a need that falls. A
drawdown recomputed when B's mortgage ends would allow an earlier retirement.

## ⚠ Open
- ADR-0042 (`netOf`) deferred: re-enter the free income as income and expenses, or revisit
  ADR-0042 when this scenario is run.
- Is the $25k also after vehicle costs and RRSP contributions? If not, they must be added
  to `netOf` too, or the cash saved shrinks.
