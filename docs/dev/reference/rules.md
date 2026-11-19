# Rules and calculators

A rule is a calculator that emitters and events call. Rules subclass `base.Rule`, hold no
scenario state (state they need lives on the household), and use the formulas in
`state_machine/arith.py`. Rule modules live in `state_machine/rules/`; the
jurisdiction-specific rules (tax treatment of accounts, contribution limits) live in
`state_machine/jurisdictions/` ([jurisdictions.md](jurisdictions.md)).

| Rule | Module | Called by |
|---|---|---|
| [TaxRule](#taxrule) | `rules/tax.py` | `TaxStepEvent`, once a month |
| [IndexingRule](#indexingrule) | `rules/indexing.py` | income, expense, contribution, withdrawal (amount), associated items |
| [CapitalGainsRule](#capitalgainsrule) | `rules/capital_gains.py` | `Sale.apply` |
| [Account tax hooks](#account-tax-hooks) | `jurisdictions/__init__.py` `Jurisdiction` | account events |
| [Contribution limits](#contribution-limits) | `jurisdictions/__init__.py` `ContributionLimits` | account events, income |
| [Closure penalty](#closure-penalty) | `holdings/mortgage.py` `Mortgage.penalty_at` | sale, lump sum payoff, results |
| [Arithmetic](#arithmetic) | `arith.py` | everywhere |

## TaxRule

One flat rate on taxable income less deductions, per person, every month (ADR-0017,
ADR-0048, ADR-0061).

- Inputs: each person's `TaxAccumulator` (`household.tax_of(person)`), reset at the start
  of each month (`Household.begin_month`):
  - `taxable`: added by `add_taxable` (taxable income, pension payments, taxed returns,
    taxed withdrawals);
  - `deductions`: added by `add_deduction` (deductible contributions and transfers,
    pension contributions);
  - `extra_tax`: tax at an account's own `withdrawalTaxRate`, kept unrounded
    (`add_own_rate_tax`);
  - `pool`: unused deductions carried forward; never reset.
- Step (`TaxRule.person_step`):
  `available = deductions + pool`; `used = min(available, max(0, taxable))`;
  `pool = available − used`; `incomeTax = money(rate × (max(0, taxable) − used))`;
  `total = incomeTax + money(extra_tax)`. Tax is never negative; no cash credit.
- Rate: `person.current_tax_rate`: the person's `effectiveTaxRate` (else the scenario's),
  switching to the retirement rate once the person's `Retirement` event has run.
- Output: one [TAX](ledger.md#tax) movement per person (source: person id when there are
  several), and the month's detail in `household.tax_detail` (see
  [outputs.md](outputs.md#tax)).
- Wiring: `TaxEmitter` (`Order.TAX`, scenario level) emits a `TaxStepEvent` every month.
  It is registered by the scenario setup hook `setup_retirement_and_tax` in
  `events/retirement.py`.

## IndexingRule

A flow's yearly step-up (ADR-0013), with cash-flow adjustments (ADR-0062).

```python
IndexingRule(rate, anchor, divisor=1, steps=None)
IndexingRule.for_item(item, inflation, anchor, divisor=1, steps=None)  # rate from item
rule.amount(base, month) -> Decimal                                       # rounded to cents
```

- `rate`: from `arith.indexing_rate(item, inflation)`: `inflation` → the scenario's
  `annualInflation`, `custom` → `indexRate`, else 0.
- `anchor`: the month index the amount is stated for (the item's start, or the parent's
  start for associated items).
- `divisor`: `arith.PER[per]`: 1 (month), 3 (quarter), 12 (year).
- `steps`: `[(month, new base, divisor)]` from `flows/adjustment.steps_for`; the last
  step at or before `month` replaces base, divisor and anchor.
- `amount` = `arith.indexed(base, rate, month − anchor, divisor)` =
  `money(base × (1 + rate)^((month − anchor) // 12) / divisor)`.

Pensions do not use it: `Pension.payment` steps on the anniversary of the base date
(`dollarsOf`) with the same expression. Percent withdrawals and percentage associated
items use their own yearly re-set (`PercentStrategy`, `YearlyPercent`, `percent_of`).

## CapitalGainsRule

A deliberate no-op: no tax on gains from selling a property or vehicle (known gap C-M8,
ADR-0017).

- `CapitalGainsRule.on_sale(household, asset, proceeds, source)` returns `None`, records
  nothing, adds no taxable income.
- `RealAsset.capital_gains = NO_CAPITAL_GAINS` (the shared instance); `Sale.apply` calls
  it after the [SALE](ledger.md#sale) movement. A future capital-gains treatment plugs in
  here.

## Account tax hooks

Methods of `Jurisdiction`, called by account events with the rounded amount that
`household.move` returned. Default behaviour follows the account type's `Treatment`
flags; a jurisdiction overrides a hook for anything else.

| Hook | Called from | Default |
|---|---|---|
| `on_contribute(household, account, amount, source)` | `InvestmentAccount.accept_contribution` (own share), `Transfer.apply` | `deductible` and not `expensesCovered`: a deduction of `account.contributor`. Canada adds the RESP grant. |
| `on_return(household, account, ret)` | `AccountReturn.apply` | `returns_taxed`: taxable income of the owner, max(0, ret). |
| `on_withdraw(household, account, amount)` | `Withdrawal.apply` | `withdrawal_taxed`: own-rate tax if `withdrawalTaxRate`, else taxable income of the owner. |

Details: [jurisdictions.md](jurisdictions.md#hooks).

## Contribution limits

`household.jurisdiction.limits`, a `ContributionLimits` object
([jurisdictions.md](jurisdictions.md#contributionlimits)):

| Method | Called from |
|---|---|
| `cap(household, account, amount, match=False)` | `accept_contribution` (own share, then match with `match=True`), `Transfer.apply`, `AccountOpening.apply` (opening from cash) |
| `note_earned(household, amount, person)` | `Income.apply` when the income is earned |
| `note_withdrawal(household, account, amount)` | `Withdrawal.apply` |
| `remaining(household)` | `results.row`: the limit columns of each row |

Implementations: `NO_LIMITS` (base class, nothing capped), Canada `RoomLimits`
(`jurisdictions/ca/room.py`, with RESP lifetime limit from `ca/resp.py`), United States
`YearlyLimits` (`jurisdictions/us/limits.py`).

## Closure penalty

The early-closure penalty of a mortgage term (ADR-0073), `Mortgage.penalty_at(month)`
with the `ClosureTerm` of the term in effect (the mortgage's own, or the latest renewal's):

| penaltyMethod | Penalty |
|---|---|
| `flat` | `penaltyAmount` |
| `interestLeft` | `penaltyRate` × the schedule's interest over the months left in the term (`Mortgage.interest_left`, no prepayments) |
| `monthsInterest` | `penaltyMonths` × balance × monthly rate |

0 after the term ends, without a term, or when nothing is owed. Used by `Sale.apply`
(sale without `salePenalty`), `ClosurePenalty` (lump-sum payoff without `penalty`) and
`Mortgage.report_extra` (holdings field `closingPenalty` = penalty if closed after that
month).

## Arithmetic

`state_machine/arith.py` (copied verbatim from iteration 1; do not rearrange the
expressions, Decimal results depend on them):

| Function | Meaning |
|---|---|
| `money(x)` | Round half-even to cents. |
| `D(x)`, `dec(item, field, where)` | Decimal through `str`; `dec` raises a readable `ValueError`. |
| `power(base, exp)` | Fractional power via `ln`/`exp`. |
| `flow_amount(item)` | `(amount, per)`; `per` must be month, quarter or year. |
| `monthly_rate(annual)` | Mortgage rate: (1 + annual/2)^(1/6) − 1. |
| `annuity(balance, r, n)` | Level payment; `balance / n` at r = 0. |
| `mortgage_terms(item)` | `(r, payment, n)` of a mortgage item. |
| `keep_payment_months(balance, r, payment, limit)` | Months left when a renewal keeps the payment, or `None` (fall back). |
| `indexed(base, rate, months, divisor)` | See IndexingRule. |
| `indexing_rate(item, inflation)` | See IndexingRule. |

`flows/withdrawal.py` `annuity_factor(r, g, n)` is the present value of a growing annuity
used by the `annuity` withdrawal method.
