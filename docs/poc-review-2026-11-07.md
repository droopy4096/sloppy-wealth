# PoC review: what the Python PoC changed in the planning (2026-11-07)

Scope: branch `poc/python-flask` (21 commits, 69734e3..049f16b), compared with the ADRs
and the domain model on `main` (v0.16).

## 1. Confirmed by the PoC (no change needed)
- Month order: income first, then events, then debits, then growth on opening balances
  (ADR-0018). No false shortfalls on payday.
- Financed purchase (ADR-0025), mortgage secured by a property (ADR-0024), sale settles
  the secured loans (ADR-0034), selling costs (ADR-0031).
- Derived loan payments; prepayments shorten the loan, the payment stays (ADR-0029).
- Shared horizon for comparisons (ADR-0028).
- Minimal input and crude modelling (ADR-0040): every PoC scenario ran with a handful of
  items.
- Letting cash go negative was a useful **diagnostic**: it exposed the 2021 funding gap in
  the baseline. This supports reporting shortfalls with an amount and period (ADR-0015).

## 2. Decisions already recorded from the PoC
| ADR | Change |
|---|---|
| 0013 (amended twice) | A cash-flow amount is in dollars of its own start date; real values use a named, settable **base date** |
| 0028 (amended) | Scenarios may use different inflation rates; comparisons display them |
| 0042 | Deferred |
| 0043 (new) | Mortgage renewal and lender switch; `MortgageTerm.amortizationMonths` |
| 0044 (new, amended) | Income-less mode; lump-sum `paidFrom` |

## 3. PoC behaviour not yet in the planning
| # | PoC behaviour | Planning impact | Proposal |
|---|---|---|---|
| P1 | Rates are fractions in JSON, percentages in the UI; implausible rates rejected | Not stated anywhere | New ADR: rate representation and plausibility validation (extends ADR-0040's validation) |
| P2 | The last scheduled payment clears the rounding remainder | ADR-0029 only caps overpayment | Amend ADR-0029 (ADR-0043 already states it for renewals) |
| P3 | First loan payment in the month after the advance | Unstated | Amend ADR-0029: default next month |
| P4 | Income entered **gross** with `taxable`; the form defaults to taxable; tax withheld as income arrives | ADR-0020 says net by default, taxed in step 7 | Keep JSON default false (neutral, ADR-0040) and let authoring default to taxable; tax step timing stays (same result monthly) |
| P5 | Amounts per month or **per year** stored in the JSON (`per`) | ADR-0021: no frequency attribute, authoring converts | Decide: amend ADR-0021 (engine accepts `per`), or keep it in authoring and store monthly |
| P6 | Indexed amounts step up **once a year on the anniversary** of the item start | ADR-0013 does not say | Amend ADR-0013: annual step on the anniversary (default) |
| P7 | Property **market value ≠ price** (house built for 366k, worth 550k) | Model has price (cost) and value but no event that sets value ≠ cost at purchase | Purchase sets cost basis = price; a `Revaluation` (ADR-0033) in the same period sets the value. Matters for capital gains on a non-principal residence (cost basis 366k, not 550k) |
| P8 | Construction modelled as a second property bought with the mortgage | No "capital improvement" concept | Watch item: an improvement event (adds to value and cost basis), or keep the PoC pattern |
| P9 | Scenario settings: `incomeMode`, `dollarsOf`, inflation, tax rate | Scenario class lacks incomeMode and baseDate | Domain model: Scenario +incomeMode, +baseDate |
| P10 | Output columns: cash, assets, debts, **assets net worth** (assets − debts), net worth, real columns | No output model yet | Output model (next diagram): per-period rows with nominal and real metrics, labelled with the base date; "assets net worth" = everything except the operating account, minus liabilities |
| P11 | An unlinked mortgage survives a property sale | Consistent with `securedBy [0..1]` | None |
| P12 | Early closure penalty not applied | Formula undefined (ADR-0043) | Open question |

## 4. Gaps: registered funds and defined-benefit pensions

### RRSP / TFSA (and non-registered investments)
In the model these are **Accounts** (ADR-0011) with a tax treatment (TFSA = tax-free,
RRSP = tax-deferred), a return rate, an optional withdrawal tax rate (ADR-0035),
contributions and withdrawals as cash flows, even drawdown (ADR-0039) and sweeps
(ADR-0030). Liquidation net worth already deducts the tax embedded in RRSP balances
(ADR-0031). Missing:

| # | Gap | Notes |
|---|---|---|
| R1 | **RRSP contribution deduction**: contributions reduce taxable income (a refund) | Not modelled anywhere. With one flat rate: deduction = contribution × rate. Options: same month (simplest), or as an annual refund |
| R2 | **Withdrawal as a rate** (e.g. 4% a year of the balance) | Only fixed amounts and even drawdown exist. Needs a percentage-of-balance withdrawal, recalculated yearly or monthly |
| R3 | **Contribution level** as an amount, possibly indexed, with an end date | Already a CashFlow operating → account. Needs a contribution form in the authoring tool only |
| R4 | **Where they show in the output** ("normally listed as assets") | In the model they are accounts, not assets. Output should group them as investments/registered funds within assets net worth |
| R5 | Employer matching (group RRSP), contribution room | Room is per person (Q-06, watch item); matching is a second cash flow from outside |
| R6 | **Interaction with income-less mode** (ADR-0044) | Are contributions "covered from outside" (they still land in the account) or skipped? Withdrawals are income: ignored or kept? |
| R7 | RRIF minimums | Q-13, watch item |

### Defined-benefit pension (guaranteed until death, inflation-indexed)
ADR-0036: an income cash flow from the pension start to the horizon end (death),
inflation-indexed, taxable, **no value in net worth**. The PoC can already express it as
an income item (indexing = inflation, taxable). Missing or to decide:

| # | Gap | Notes |
|---|---|---|
| D1 | A dedicated **pension type** in authoring (start date, amount, indexing; end = horizon) | Authoring only; the engine needs nothing new |
| D2 | **Value in net worth** (commuted value) | Q-14. Without it, "assets net worth" understates someone relying on a pension |
| D3 | **Income-less mode ignores it** (ADR-0044 ignores all income) | A retirement scenario in that mode would drop the pension. Needs a rule: e.g. income-less mode ignores employment income only |
| D4 | Member contributions while working, bridge benefit to 65, survivor benefit | Contributions are an expense or reduce free income; bridge = a second, ending income flow; survivor benefit out of scope (single economic unit, ADR-0002) |
| D5 | Partial indexing (e.g. CPI capped at 2%) | `CustomRate` covers a fixed partial rate; a cap would need a new rate generator (Q-11 CompositeRate) |

## 5. Suggested order
1. Decide P1–P6 (small amendments) and P7 (market value via Revaluation).
2. RRSP/TFSA: R1, R2, R4, R6.
3. Pension: D2, D3.
4. Output model class diagram (covers P10, R4).
5. Add accounts (RRSP/TFSA with contributions and withdrawals) and pensions to the PoC.
