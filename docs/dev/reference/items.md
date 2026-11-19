# Scenario items

A scenario is one JSON object: some settings and a list of `items`. Each item has a `type`.
This page lists every item type the engine registers (`compiler.registered_types()`),
with its fields, links, run behaviour and code. `webapp/SPEC.md` is the longer spec; where
it and the code differ, this page follows the code.

Conventions used in the tables:

| Format | Meaning |
|---|---|
| decimal | A decimal string, e.g. `"1500"` or `"1500.50"`. JSON numbers are also read (through `str`), but an optional field holding the number `0` counts as "not given". |
| fraction | A rate as a decimal string fraction: `"0.035"` is 3.5 %. The builder form shows percentages; `web/pages.py` converts them (ADR-0045). |
| date | `"YYYY-MM-DD"`. Only year and month are used (ADR-0007). |
| bool | JSON `true` / `false` (not strings). |
| id | The `id` of another item. |
| choice | One of the listed strings. |

"Required" means validation (`state_machine/validation.py`) refuses the item without it.
Many dates are required but may come from a [trigger](#trigger) instead of the item itself.
Order names (`INCOME`, `SERVICE_DEBT`, ...) are the steps of the month: see
[modules.md#month-order](modules.md#month-order). Ledger kinds link to [ledger.md](ledger.md).

Contents: [Scenario settings](#scenario-settings) · [Common item fields](#common-item-fields) ·
People & settings ([person](#person), [retirement](#retirement), [cashBalance](#cashbalance)) ·
Income & pensions ([income](#income), [pension](#pension), [associatedIncome](#associatedincome),
[associatedOneOff](#associatedoneoff)) ·
Accounts ([account](#account), [contribution](#contribution), [withdrawal](#withdrawal),
[transfer](#transfer)) ·
Properties & mortgages ([property](#property), [mortgage](#mortgage), [renewal](#renewal),
[extraPayment](#extrapayment), [lumpSum](#lumpsum), [improvement](#improvement),
[marketAdjustment](#marketadjustment), [sale](#sale)) ·
Vehicles ([vehicle](#vehicle)) ·
Expenses & associated items ([expense](#expense), [associatedExpense](#associatedexpense),
[associatedCost](#associatedcost)) ·
Triggers & adjustments ([trigger](#trigger), [adjustment](#adjustment)) ·
Jurisdiction-specific ([contributionRoom](#contributionroom), [contributionLimit](#contributionlimit))

---

## Scenario settings

| Field | Required | Format | Meaning, default |
|---|---|---|---|
| schemaVersion | for `/api/load` | `1` | File format version. `POST /api/load` refuses any other value; the engine itself ignores it. |
| name | no | string | Scenario name. Default in new scenarios: `"Untitled"`. |
| jurisdiction | no | choice `CA`, `US` | Tax jurisdiction ([jurisdictions.md](jurisdictions.md)). Missing: `CA` (`upgrade.py` inserts it). |
| horizon | yes | `{"start": date, "end": date}` | First and last month of the run, inclusive. `end` may not be before `start`. The API refuses horizons over 100 years. |
| openingCash | yes | decimal | Cash at the start. Cash has no return and may go negative. |
| items | yes | list | The items. The API refuses more than 1,000. |
| annualInflation | no | fraction in (-1, 1) | Default 0. Used by `indexing: inflation`, `amountIn: base`, pension values and the real columns. |
| dollarsOf | no | date | Base date of real values and pension amounts. Default: horizon start. |
| effectiveTaxRate | no | fraction in [0, 1) | Flat income tax rate. Default 0. |
| retirementTaxRate | no | fraction in [0, 1) | Rate from a person's retirement. Blank: no switch. |
| incomeMode | no | choice `modelled`, `expensesCovered` | Default `modelled`. `expensesCovered` (ADR-0044): income items are ignored; expenses, associated expenses, loan payments, extra payments and contributions are paid from outside (no cash change); one-off events still move cash. |
| retirementDate | no | date | Older form. Converted on load to a [retirement](#retirement) item. Having both is an error. |

```json
{"schemaVersion": 1, "name": "Example", "jurisdiction": "CA",
 "horizon": {"start": "2027-01-01", "end": "2050-12-01"},
 "openingCash": "20000", "annualInflation": "0.02", "dollarsOf": "2027-01-01",
 "effectiveTaxRate": "0.30", "retirementTaxRate": "0.20", "incomeMode": "modelled",
 "items": []}
```

## Common item fields

| Field | Required | Format | Meaning, default |
|---|---|---|---|
| type | yes | choice | The item type (sections below). Unknown types are refused; a type of another jurisdiction is refused with its name. |
| id | no (yes for `person`) | string | Unique in the scenario. Other items refer to it. Without one the compiler uses `item<index>`; `/api/load` and `/api/items/add` assign 8 hex characters. |
| name | no | string | Display name. `/api/items/add` fills in the type name. |
| enabled | no | bool | Default `true`. `false` leaves the item out of the run, together with every item that refers to it through `property`, `mortgage`, `account`, `flow`, `event`, `target`, `parent`, `owner`, `contributor` or `retirementOf`, and every item a start trigger on it would start (`enabled.py`, ADR-0064). |
| owner | no | id of a [person](#person) | Only on `income`, `account`, `pension`, `retirement`, and the jurisdiction's own `contributionRoom` / `contributionLimit`. Blank: the first person. Contributions and withdrawals take their account's owner. |
| retirementOf | no | id of a person | Whose retirement an item follows when its start is blank (pension, withdrawal) or in older at-retirement forms. Default: the owner, else the first person. |

Older forms are converted on input by `state_machine/upgrade.py` (`monthlyAmount` on
flows, withdrawal method `even`, `startsAtRetirement` / `endsAtRetirement` /
`atRetirement`, an expense's `attachedTo`, a vehicle's `annualMaintenance`, a property's
`saleDate`, a sale's `sellingCostRate`). The engine reads only the current forms below.

Each item type is compiled by one factory registered with `@item_type("<type>")`. The
factory returns emitters; emitters produce events each month; events record ledger
movements. See [modules.md](modules.md).

---

# People & settings

## person

A member of the household with own tax rates, retirement, accounts and limits (ADR-0061).

| Field | Required | Format | Meaning, default |
|---|---|---|---|
| id | yes | string | Unique among persons. `owner` fields refer to it. |
| birthDate | no | date | For age rules (US catch-up contributions). |
| effectiveTaxRate | no | fraction in [0, 1) | Blank: the scenario's. |
| retirementTaxRate | no | fraction in [0, 1) | Blank: the scenario's `retirementTaxRate`, else the person's working rate. |

- Links: none. Other items link to it through `owner`, `contributor`, `retirementOf`.
- Run: no emitters. `Household` builds one `Person` per person item (`household.build_persons`),
  each with its own tax accumulator and deduction pool. Each person pays a separate `TAX`
  movement. A scenario without person items has one implicit person, id `self`.
- Code: `state_machine/rules/person.py` (`compile_person`, returns nothing);
  `state_machine/persons.py` (owner rules); `state_machine/household.py` (`Person`).

```json
{"type": "person", "id": "alex", "name": "Alex", "birthDate": "1980-05-01",
 "effectiveTaxRate": "0.30", "retirementTaxRate": "0.20"}
```

## retirement

The month a person retires (ADR-0059). At most one per person.

| Field | Required | Format | Meaning, default |
|---|---|---|---|
| retirementDate | yes | date | Within the horizon (older files converted by `upgrade.py` may carry `"outsideHorizon": true` instead). |
| owner | no | id | Whose retirement. Blank: the first person. |

- Links: triggers use it as `event` to start or end other items.
- Run: in the retirement month (`OPEN` step) a `Retirement` state event marks the person
  retired, so their tax rate switches to the retirement rate. Pensions and withdrawals of
  that person without a `startDate` begin in that month. No ledger movement.
- Code: `state_machine/events/retirement.py`. `compile_retirement` returns nothing; the
  scenario setup hook `setup_retirement_and_tax` yields one `RetirementEmitter` per
  retiring person (and the `TaxEmitter`).

```json
{"type": "retirement", "id": "ret", "name": "Alex retires", "owner": "alex",
 "retirementDate": "2045-01-01"}
```

## cashBalance

Sets cash to an actual statement balance at the end of a month (ADR-0063).

| Field | Required | Format | Meaning, default |
|---|---|---|---|
| balanceDate | yes | date | Within the horizon. |
| balance | yes | decimal | Cash at the end of that month. |

- Links: none.
- Run: after the tax step (order `TAX + 50`), records the difference as
  [CASH_RECONCILIATION](ledger.md#cash_reconciliation) (from or to outside). Not income,
  not taxed. Several in one month: the last in item order wins.
- Code: `state_machine/events/cash_balance.py` (`compile_cash_balance`,
  `CashBalanceEmitter`, `CashReconciled`).

```json
{"type": "cashBalance", "id": "stmt", "name": "Bank statement",
 "balanceDate": "2028-06-01", "balance": "25000"}
```

---

# Income & pensions

## income

A recurring income (salary, rent received, ...).

| Field | Required | Format | Meaning, default |
|---|---|---|---|
| startDate | yes | date | Own, or set by a trigger. |
| endDate | no | date | Last month. Blank: horizon end. |
| amount | yes | decimal | Per `per`, in dollars of `startDate` (see `amountIn`). |
| per | no | choice `month`, `quarter`, `year` | Default `month`. A quarterly or yearly amount is paid as amount/3 or amount/12 each month. |
| amountIn | no | choice `start`, `base` | Default `start`. `base`: the amount is in dollars of the base date (`dollarsOf`) and is inflated to the start: amount × (1 + annualInflation)^((start − base)/12). |
| taxable | no | bool | Default `false` (amount already after tax). `true`: added to the owner's taxable income. |
| earnedIncome | no | bool | Default: same as `taxable`. Counts for limits that depend on earned income (CA RRSP room). |
| indexing | no | choice `none`, `inflation`, `custom` | Default `none`. |
| indexRate | with `custom` | fraction in (-1, 1) | Yearly rate for `custom`. |
| owner | no | id | Person. |

- Links: can be the `parent` of associated items, the `flow` of an adjustment, a trigger's
  event or target.
- Run: every month from start to end (`INCOME` step): [INCOME](ledger.md#income)
  outside → cash. The amount steps up once a year on the anniversary of the start:
  amount × (1 + rate)^(full years) / divisor, rounded to cents (ADR-0013). Adjustments
  replace the amount from their month. Nothing in `expensesCovered` mode.
- Code: `state_machine/flows/income_expense.py` (`compile_income`, `IncomeEmitter`,
  `Income`); amounts by `rules/indexing.py` `IndexingRule`.

```json
{"type": "income", "id": "salary", "name": "Salary", "owner": "alex",
 "startDate": "2027-01-01", "endDate": "2044-12-01", "amount": "90000", "per": "year",
 "taxable": true, "indexing": "inflation"}
```

## pension

A guaranteed (defined-benefit or government) pension (ADR-0052). Its value counts in
investments.

| Field | Required | Format | Meaning, default |
|---|---|---|---|
| amount | yes | decimal | Per `per`, in dollars of the base date (`dollarsOf`). |
| per | no | choice | Default `month`. |
| startDate | no | date | Blank: the owner's retirement month (a retirement item is then required). |
| endDate | no | date | Blank: horizon end. May not be before the effective start. |
| taxable | no | bool | Default `true`. |
| indexing, indexRate | no | as income | Yearly step on the anniversary of the base date. |
| owner | no | id | Person. |

- Links: can be the `account` of a contribution and the `parent` of associated income.
- Run: created before the first month (`INITIAL`) with its value. Each month from start
  to end (`PENSION_PAY`): [PENSION_PAYMENT](ledger.md#pension_payment) pension → cash,
  amount = base × (1 + rate)^(full years since base date) / divisor; paid also in
  `expensesCovered` mode; taxable income if `taxable`. Every month (`REVALUE_PENSIONS`):
  [REVALUATION](ledger.md#revaluation) to its value = the payments still to come in
  base-date dollars, undiscounted, expressed in the month's dollars.
- Code: `state_machine/holdings/pension.py` (`compile_pension`, `Pension`,
  `PensionCreation`, `PensionPayment`, `PensionRevaluation`).

```json
{"type": "pension", "id": "db", "name": "Work pension", "owner": "alex",
 "amount": "2000", "per": "month", "taxable": true, "indexing": "inflation"}
```

## associatedIncome

Income that lives with an income or a pension: a bonus, a 13th payment (ADR-0068).

| Field | Required | Format | Meaning, default |
|---|---|---|---|
| parent | yes | id of an `income` or `pension` | Runs from the parent's first to its last month. |
| amount | one of amount / annualRate | decimal | Indexed from the parent's start as an income. |
| annualRate | one of amount / annualRate | fraction in (0, 10] | Share of the parent's yearly amount, taken on the parent's start and each anniversary. |
| per | no | choice | Default `month`. With `paid: lump` it must be `quarter` or `year`. |
| paid | no | choice `monthly`, `lump` | Default `monthly`. `lump`: the sum of a period's monthly shares, paid in arrears on each quarterly or yearly anniversary of the parent's start; a partial last period is not paid. |
| indexing, indexRate | no | as income | For `amount`. |
| amountIn | no | as income | Accepted by the engine for `amount`; not on the form. |

- Taxable, earned income and owner are the parent's.
- Run: `INCOME` step: [INCOME](ledger.md#income), source = this item. Not paid in
  `expensesCovered` mode for an income parent; paid for a pension parent. A lump for the
  last full period is paid the month after the parent's last month, if within the horizon.
- Code: `state_machine/flows/associated_income.py` (`compile_associated_income`,
  `AssociatedIncomeEmitter`; event `Income`).

```json
{"type": "associatedIncome", "id": "bonus", "name": "Bonus", "parent": "salary",
 "annualRate": "0.10", "per": "year", "paid": "lump"}
```

## associatedOneOff

A one-off income tied to an income or pension: signing bonus, severance (ADR-0068).

| Field | Required | Format | Meaning, default |
|---|---|---|---|
| parent | yes | id of an `income` or `pension` | |
| at | no | choice `start`, `end`, `date` | Default `start`. `end` = the parent's last month, only if the parent has an `endDate`. |
| paymentDate | with `at: date` | date | Within the horizon. |
| amount | one of amount / rate | decimal ≥ 0 | |
| rate | one of amount / rate | fraction in (0, 10] | Share of the parent's yearly amount that month. |

- Run: once (`INCOME` step): [INCOME](ledger.md#income), taxed as the parent. Dropped if
  the month is outside the parent's window or the horizon, or the amount is 0. Covered
  mode as associatedIncome.
- Code: `state_machine/flows/associated_income.py` (`compile_associated_one_off`,
  `AssociatedOneOffEmitter`).

```json
{"type": "associatedOneOff", "id": "severance", "name": "Severance", "parent": "salary",
 "at": "end", "amount": "20000"}
```

---

# Accounts

## account

An investment account of one of the jurisdiction's account types (ADR-0011, ADR-0071).
How it is taxed comes from the type's treatment: see [jurisdictions.md](jurisdictions.md).

| Field | Required | Format | Meaning, default |
|---|---|---|---|
| accountType | yes | choice | A code of the scenario's jurisdiction (CA: `tfsa`, `rrsp`, `nonRegistered`, `resp`; US: `traditional401k`, `roth401k`, `traditionalIra`, `rothIra`, `hsa`, `brokerage`). |
| annualReturn | yes | fraction in (-1, 1) | Monthly rate = (1 + annualReturn)^(1/12) − 1. |
| openingBalance | no | decimal ≥ 0 | Default 0. Opened on or before the horizon start: the balance at the horizon start (ADR-0057). |
| openedDate | no | date | Default: horizon start. Not after the horizon end. |
| openingFrom | if opened inside the horizon with a balance | choice `cash`, `outside` | `cash`: moved from cash. `outside`: an existing balance not modelled before. |
| withdrawalTaxRate | no | fraction in [0, 1) | Own tax rate on withdrawals. Used only for types whose withdrawals are taxed (RRSP, traditional 401(k)/IRA). |
| contributor | no | id of a person | CA `rrsp` only (spousal RRSP): whose room and deduction; not the owner. |
| unusedGrantRoom, grantReceived, contributedSoFar | no | decimal ≥ 0 | CA `resp` only (ADR-0072): history before the horizon, default 0. |
| owner | no | id | Person. |

- Links: `account` of contributions, withdrawals and transfers; `parent` of associated
  expenses (basis `balance`) and costs.
- Run: opened on or before the horizon start: exists before the first month with
  `openingBalance`, no ledger line. Opened later: in that month (`ACQUIRE`)
  [OPENING_TRANSFER](ledger.md#opening_transfer) from cash (capped by limits) or
  [OPENING_BALANCE](ledger.md#opening_balance) from outside. Every month it existed at the
  start of (`GROW`): [RETURN](ledger.md#return) = opening balance × monthly rate, then the
  jurisdiction's `on_return`.
- Code: `state_machine/holdings/account.py` (`compile_account`, `AccountSpec`,
  `InvestmentAccount`, `AccountAtStartEmitter`, `AccountOpeningEmitter`,
  `AccountReturnEmitter`).

```json
{"type": "account", "id": "rrsp", "name": "RRSP", "owner": "alex", "accountType": "rrsp",
 "openingBalance": "50000", "annualReturn": "0.05"}
```

## contribution

Regular saving into an account or a pension plan.

| Field | Required | Format | Meaning, default |
|---|---|---|---|
| account | yes | id of an `account` or `pension` | |
| startDate | yes | date | Own or set by a trigger. |
| endDate | no | date | Blank: horizon end. |
| amount | yes | decimal | Per `per`. |
| per | no | choice | Default `month`. |
| employerMatch | no | fraction in [0, 1] | Share of each contribution added from outside. |
| indexing, indexRate | no | as income | |

- Run: every month in the window while the target exists (`CONTRIBUTE`).
  Into an account: [CONTRIBUTION](ledger.md#contribution) from cash (from outside in
  `expensesCovered` mode), capped by the jurisdiction's limits; then `on_contribute`
  (deduction of the contributor for deductible types, not in `expensesCovered` mode; CA
  RESP grant); then [EMPLOYER_MATCH](ledger.md#employer_match) = match × the share paid,
  capped (CA room; not capped in the US). Into a pension: [PENSION_CONTRIBUTION](ledger.md#pension_contribution)
  cash → outside, a deduction; nothing in `expensesCovered` mode; the match is ignored.
- Code: `state_machine/flows/contribution.py` (`compile_contribution`,
  `ContributionEmitter`, `Contribution`); `InvestmentAccount.accept_contribution`,
  `Pension.accept_contribution`.

```json
{"type": "contribution", "id": "rrsp-save", "name": "RRSP saving", "account": "rrsp",
 "startDate": "2027-01-01", "endDate": "2044-12-01", "amount": "500",
 "employerMatch": "0.5"}
```

## withdrawal

Regular draws from an account into cash.

| Field | Required | Format | Meaning, default |
|---|---|---|---|
| account | yes | id of an `account` | |
| method | yes | choice `amount`, `percent`, `annuity` | See below. |
| startDate | no | date | Blank: the owner's retirement month (a retirement item is then required). `percent` and `annuity` may not start before the account opens. |
| endDate | no | date | Blank: horizon end. |
| amount | with `amount` | decimal | Per `per`, indexed. |
| per | no | choice | Default `month`. |
| annualRate | with `percent` | fraction in (0, 1) | |
| indexing, indexRate | no | as income | Not allowed with `percent`. |

Methods (`flows/withdrawal.py`):
- `amount`: the indexed amount.
- `percent`: on the start and each anniversary, annualRate / 12 × the balance at the start
  of that month; paid monthly for a year (ADR-0049). An empty account at an anniversary
  pays 0 that year.
- `annuity`: spends the account down by min(endDate, horizon end); set from the balance in
  the first month with a balance and re-set each anniversary, at the account's own return;
  with indexing the payment grows yearly by the indexing rate; the final month takes the
  whole balance (ADR-0039 amendment).

- Run: `WITHDRAW` step: [WITHDRAWAL](ledger.md#withdrawal) account → cash, capped at the
  balance; nothing while the balance is 0. Then `on_withdraw` (taxable income of the
  owner, or tax at `withdrawalTaxRate`) and `note_withdrawal` (CA TFSA room).
- Code: `state_machine/flows/withdrawal.py` (`compile_withdrawal`, `WithdrawalEmitter`,
  `AmountStrategy`, `PercentStrategy`, `AnnuityStrategy`, `Withdrawal`).

```json
{"type": "withdrawal", "id": "draw", "name": "RRSP draw", "account": "rrsp",
 "method": "annuity", "indexing": "inflation"}
```

## transfer

A one-off move from cash into an account (ADR-0025).

| Field | Required | Format | Meaning, default |
|---|---|---|---|
| account | yes | id of an `account` | |
| amount | yes | decimal > 0 | |
| transferDate | yes | date | Own or set by a trigger. Within the horizon, not before the account opens. |

- Run: `TRANSFER` step (after the month's sales): [TRANSFER](ledger.md#transfer) cash →
  account, capped by limits, always from cash (also in `expensesCovered` mode). Then
  `on_contribute`: a deduction for deductible types (not in `expensesCovered` mode), the
  RESP grant.
- Code: `state_machine/events/transfer.py` (`compile_transfer`, `TransferEmitter`,
  `Transfer`).

```json
{"type": "transfer", "id": "top-up", "name": "Top-up", "account": "rrsp",
 "amount": "10000", "transferDate": "2030-03-01"}
```

---

# Properties & mortgages

## property

Real estate.

| Field | Required | Format | Meaning, default |
|---|---|---|---|
| purchaseDate | yes | date | Not after the horizon end. May be before the start. |
| price | yes | decimal | Cash paid. |
| marketValue | no | decimal ≥ 0 | Value at purchase, if different from the price. Blank: price. |
| annualAppreciation | yes | fraction in (-1, 1) | Monthly rate = (1 + a)^(1/12) − 1. |

- Links: `property` of mortgages, sales, improvements, market adjustments; `parent` of
  associated expenses and costs (basis `value` or `price`).
- Run: bought inside the horizon: in its month (`ACQUIRE`) [PURCHASE](ledger.md#purchase)
  cash → property, and [REVALUATION](ledger.md#revaluation) by marketValue − price if
  given. Bought before: carried in before the first month at (marketValue or price) ×
  (1 + monthly rate)^(months since purchase), no movement. Every month it existed at the
  start of (`GROW`): [APPRECIATION](ledger.md#appreciation) = opening value × monthly rate,
  except after its sale and in a month a market adjustment set a `newValue`.
- Code: `state_machine/holdings/real_estate.py` (`compile_property`, `RealEstate`,
  `AppreciationEmitter`); `state_machine/events/purchase.py` (`PurchaseEmitter`,
  `CarryInEmitter`, `Revaluation`).

```json
{"type": "property", "id": "house", "name": "House", "purchaseDate": "2027-06-01",
 "price": "600000", "annualAppreciation": "0.03"}
```

## mortgage

A loan, optionally secured by a property or financing a vehicle (ADR-0024, ADR-0029).

| Field | Required | Format | Meaning, default |
|---|---|---|---|
| property | no | id of a `property` or `vehicle` | Secured by / financed asset. Paid off when the asset is sold. |
| startDate | if no `property` | date | Blank: the asset's purchase month. Must be within the horizon, not before the purchase, before the asset's sale. |
| principal | yes | decimal | |
| annualRate | yes | fraction in [0, 1) | Monthly rate = (1 + annualRate/2)^(1/6) − 1 (semi-annual compounding, ADR-0019). |
| amortizationYears | yes | decimal | × 12 must be a whole number ≥ 1. |
| firstPaymentDate | no | date | After the start. Default: the month after the start. |
| termMonths | with penaltyMethod | whole number > 0 | Term from the start (ADR-0073). |
| penaltyMethod | with termMonths | choice `flat`, `interestLeft`, `monthsInterest` | Early-closure penalty formula during the term. |
| penaltyAmount | with `flat` | decimal ≥ 0 | |
| penaltyRate | with `interestLeft` | fraction in [0, 1] | Share of the schedule's interest left in the term. |
| penaltyMonths | with `monthsInterest` | decimal ≥ 0 | Months of interest on the balance. |

- Links: `mortgage` of renewals, extra payments, lump sums; `parent` of associated items
  (basis `principal` or `balance`).
- Run: start month (`ACQUIRE`): [LOAN_ADVANCE](ledger.md#loan_advance) loan → cash.
  From the next month (`SERVICE_DEBT`), while owed: before `firstPaymentDate`,
  [LOAN_INTEREST](ledger.md#loan_interest) on the principal accrues; in the first payment
  month [INTEREST_ADJUSTMENT](ledger.md#interest_adjustment) pays it; then each month
  LOAN_INTEREST on the balance and [LOAN_PAYMENT](ledger.md#loan_payment) of the fixed
  annuity payment P = L·r / (1 − (1+r)^−n); the last payment clears the rest. Payments come
  from outside in `expensesCovered` mode. A sale of the linked asset pays it off
  ([LOAN_PAYOFF](ledger.md#loan_payoff)) and charges the term's penalty unless the sale
  gives one. Holdings points carry `interest`, `paid`, `principalPaid`, and
  `closingPenalty` when a term is given.
- Code: `state_machine/events/loan.py` (`compile_mortgage`, `LoanAdvanceEmitter`,
  `LoanServiceEmitter`, events `LoanAdvance`, `AccrueInterest`, `InterestAdjustment`,
  `LoanInterest`, `ScheduledPayment`); `state_machine/holdings/mortgage.py` (`Mortgage`,
  `LoanTerms`, `ClosureTerm`).

```json
{"type": "mortgage", "id": "mtg", "name": "Mortgage", "property": "house",
 "principal": "480000", "annualRate": "0.045", "amortizationYears": "25",
 "termMonths": "60", "penaltyMethod": "monthsInterest", "penaltyMonths": "3"}
```

## renewal

A mortgage renewal or switch to another lender: a new rate from a month (ADR-0043).

| Field | Required | Format | Meaning, default |
|---|---|---|---|
| mortgage | yes | id of a `mortgage` | |
| startDate | yes | date | After the mortgage start; before the month its asset is sold; one renewal per mortgage per month. |
| annualRate | yes | fraction in [0, 1) | New rate. |
| keepPayment | no | bool | Default `false`: the payment is recomputed over the remaining amortization. `true`: the payment is kept and the remaining months derived; falls back to recomputing if it cannot repay in time. |
| amortizationYears | no | decimal | New amortization (not with `keepPayment`). |
| penalty | no | decimal ≥ 0 | Penalty for breaking the previous term, in dollars of that date. |
| termMonths, penaltyMethod, penaltyAmount, penaltyRate, penaltyMonths | no | as mortgage | The new term's closure penalty. |

- Run: modifier at the mortgage's slot (`SERVICE_DEBT`, before the service): `Renew`
  changes rate, payment and remaining months (no movement); then
  [PENALTY](ledger.md#penalty) if `penalty`. Lost if the loan is not serviced that month.
  Later interest and payments carry the renewal id as `source`.
- Code: `state_machine/events/loan.py` (`compile_renewal`, `RenewalEmitter`, `Renew`,
  `RenewalPenalty`); `Mortgage.renew`; `arith.keep_payment_months`.

```json
{"type": "renewal", "id": "renew1", "name": "Renewal", "mortgage": "mtg",
 "startDate": "2032-06-01", "annualRate": "0.05", "keepPayment": true}
```

## extraPayment

A monthly prepayment on a mortgage. It does not change the scheduled payment; the loan
ends earlier.

| Field | Required | Format | Meaning, default |
|---|---|---|---|
| mortgage | yes | id of a `mortgage` | |
| startDate | yes | date | |
| endDate | no | date | Blank: horizon end. |
| monthlyAmount | yes | decimal > 0 | Note the field name: not `amount`. |

- Run: modifier at the mortgage's slot (`SERVICE_DEBT`, after the service), only in months
  the scheduled payment was made: [PREPAYMENT](ledger.md#prepayment), capped at the
  balance, from cash (from outside in `expensesCovered` mode).
- Code: `state_machine/events/loan.py` (`compile_extra_payment`, `ExtraPaymentEmitter`,
  `ExtraPrepayment`).

```json
{"type": "extraPayment", "id": "extra", "name": "Extra", "mortgage": "mtg",
 "startDate": "2028-01-01", "endDate": "2030-12-01", "monthlyAmount": "300"}
```

## lumpSum

A one-off prepayment, or the payoff of a mortgage.

| Field | Required | Format | Meaning, default |
|---|---|---|---|
| mortgage | yes | id of a `mortgage` | |
| paymentDate | yes | date | Own or set by a trigger. After the mortgage start. |
| amount | one of amount / payOff | decimal > 0 | |
| payOff | one of amount / payOff | bool | `true`: the whole balance left after that month's payment. The form's `covers` (`amount` / `all`) maps to it. |
| paidFrom | no | choice `cash`, `outside` | Default `cash`. `outside`: e.g. a gift; reduces the loan, not cash. |
| penalty | no | decimal ≥ 0 | Blank with `payOff`: the term's formula. Blank with an amount: none. |

- Run: modifier at the mortgage's slot (`SERVICE_DEBT`, after the service), only if the
  scheduled payment was made that month: [PREPAYMENT](ledger.md#prepayment), then
  [PENALTY](ledger.md#penalty). A payoff without a penalty computes the formula penalty
  first (before the balance drops).
- Code: `state_machine/events/loan.py` (`compile_lump_sum`, `LumpSumEmitter`,
  `LumpSumPrepayment`, `LumpSumPenalty`, `ClosurePenalty`).

```json
{"type": "lumpSum", "id": "lump", "name": "Bonus prepayment", "mortgage": "mtg",
 "paymentDate": "2029-03-01", "amount": "10000", "paidFrom": "cash"}
```

## improvement

Construction or renovation of a property (ADR-0046).

| Field | Required | Format | Meaning, default |
|---|---|---|---|
| property | yes | id of a `property` | Not a vehicle. |
| improvementDate | yes | date | Within the horizon, on or after the purchase, before the sale. |
| cost | yes | decimal ≥ 0 | Paid from cash. |
| valueAdded | no | decimal ≥ 0 | Default: the cost. |

- Run: `IMPROVE` step, at its own item index: [IMPROVEMENT](ledger.md#improvement) cash →
  property, then [REVALUATION](ledger.md#revaluation) by valueAdded − cost. Growth on the
  new value starts the next month.
- Code: `state_machine/events/improvement.py` (`compile_improvement`,
  `ImprovementEmitter`, `Improvement`).

```json
{"type": "improvement", "id": "reno", "name": "Kitchen", "property": "house",
 "improvementDate": "2031-05-01", "cost": "40000", "valueAdded": "30000"}
```

## marketAdjustment

A one-off change in a property's or vehicle's value (ADR-0033).

| Field | Required | Format | Meaning, default |
|---|---|---|---|
| property | yes | id of a `property` or `vehicle` | |
| adjustmentDate | yes | date | Within the horizon, on or after the purchase, before the sale. |
| percent | one of percent / newValue | fraction in (-1, 1) | Applied to the value before the month's growth. |
| newValue | one of percent / newValue | decimal ≥ 0 | The month's closing value; no growth that month. |

- Run: `ADJUST` step, at its own item index: [MARKET_ADJUSTMENT](ledger.md#market_adjustment)
  outside → asset. Value only: cash and debts unchanged.
- Code: `state_machine/events/adjustment.py` (`compile_market_adjustment`,
  `MarketAdjustmentEmitter`, `MarketAdjustment`).

```json
{"type": "marketAdjustment", "id": "dip", "name": "Market dip", "property": "house",
 "adjustmentDate": "2029-01-01", "percent": "-0.10"}
```

## sale

The sale of a property or vehicle (ADR-0031, ADR-0034). One per asset.

| Field | Required | Format | Meaning, default |
|---|---|---|---|
| property | yes | id of a `property` or `vehicle` | |
| saleDate | yes | date | Own or set by a trigger. After the purchase, within the horizon. |
| salePrice | no | decimal ≥ 0 | Blank: the asset's value that month. |
| salePenalty | no | decimal ≥ 0 | Penalty for the loans it pays off. Blank: the sum of the secured loans' term formulas (0 without terms). |

Selling costs are an [associatedCost](#associatedcost) with `at: end` on the asset. An older
`sellingCostRate` on a sale is converted to one on load.

- Run: modifier at the asset's slot (`SELL`):
  [SALE_PRICE_DIFFERENCE](ledger.md#sale_price_difference) if `salePrice`, then
  [SALE](ledger.md#sale) asset → cash at its value; the capital-gains rule (a no-op); then
  [LOAN_PAYOFF](ledger.md#loan_payoff) for each loan secured by it, then
  [PENALTY](ledger.md#penalty). The asset stays with balance 0. Cash may go negative.
- Code: `state_machine/events/sale.py` (`compile_sale`, `SaleEmitter`, `Sale`,
  `LoanPayoff`, `SalePenalty`).

```json
{"type": "sale", "id": "house-sale", "name": "Sell house", "property": "house",
 "saleDate": "2046-06-01"}
```

---

# Vehicles

## vehicle

A depreciating asset. Running costs are associated expenses; a loan is a mortgage with
`property` = the vehicle id (ADR-0074 amendment).

| Field | Required | Format | Meaning, default |
|---|---|---|---|
| purchaseDate | yes | date | Not after the horizon end. May be before the start. |
| price | yes | decimal | |
| annualDepreciation | yes | fraction in (-1, 1) | Monthly rate = (1 − d)^(1/12) − 1. |

No `marketValue`. Older `annualMaintenance` / `maintenanceIncrease` are converted to an
associated expense on load.

- Run: as [property](#property) (purchase or carry-in, then growth), with negative
  [APPRECIATION](ledger.md#appreciation). Sold by a [sale](#sale) item.
- Code: `state_machine/holdings/vehicle.py` (`compile_vehicle`, `Vehicle`); shared code in
  `holdings/real_estate.py` (`RealAsset`, `compile_real_asset`).

```json
{"type": "vehicle", "id": "car", "name": "Car", "purchaseDate": "2025-03-01",
 "price": "35000", "annualDepreciation": "0.15"}
```

---

# Expenses & associated items

## expense

A recurring household expense.

| Field | Required | Format | Meaning, default |
|---|---|---|---|
| startDate | yes | date | Own or set by a trigger. |
| endDate | no | date | Blank: horizon end. |
| amount | yes | decimal | |
| per | no | choice | Default `month`. |
| amountIn | no | choice | As income. |
| indexing, indexRate | no | as income | |

- Run: `EXPENSE` step, every month in the window: [EXPENSE](ledger.md#expense) cash →
  outside. Indexed as income. Nothing in `expensesCovered` mode.
- Code: `state_machine/flows/income_expense.py` (`compile_expense`, `ExpenseEmitter`,
  `Expense`).

```json
{"type": "expense", "id": "living", "name": "Living", "startDate": "2027-01-01",
 "amount": "3000", "indexing": "inflation"}
```

## associatedExpense

A recurring cost paid while its parent exists: property tax, insurance, account fees
(ADR-0067).

| Field | Required | Format | Meaning, default |
|---|---|---|---|
| parent | yes | id | A `property`, `vehicle`, `account`, `mortgage`, `income`, `expense`, `contribution`, `withdrawal`, `pension`, `extraPayment` or another `associatedExpense`. |
| amount | one of amount / annualRate | decimal | Per `per`, indexed from the parent's start (also before the horizon). |
| per, indexing, indexRate | no | as expense | For `amount`. |
| amountIn | no | as income | Accepted for `amount`; not on the form. |
| annualRate | one of amount / annualRate | fraction in (0, 1) | basis × rate / 12, re-set on the first month and each anniversary of the parent's start; not indexed. |
| basis | with annualRate | choice | property / vehicle: `value` (value at the start of the month; at its sale, the sale price) or `price`; account: `balance`; mortgage: `principal` or `balance`; income: `amount` (its yearly amount). Other parents take no rate. |
| alsoWhenRenting | no | bool | Default `false`. `true`: a renter pays it too; left out of the break-even's ownership variant. No effect on the run. |

- Run: `EXPENSE` step, every month from the parent's start to its end, and for a holding
  parent only while it exists, is not sold, and (mortgage) is owed:
  [EXPENSE](ledger.md#expense) cash → outside, source = this item. Not paid in
  `expensesCovered` mode. Not deductible; not added to the asset's value.
- Code: `state_machine/flows/associated.py` (`compile_associated_expense`,
  `AssociatedExpenseEmitter`, `YearlyPercent`, `basis_reader`, `lifetime`; event `Expense`).

```json
{"type": "associatedExpense", "id": "ptax", "name": "Property tax", "parent": "house",
 "annualRate": "0.01", "basis": "value"}
```

## associatedCost

A one-off cost at its parent's start, end, or a date: closing costs, selling costs
(ADR-0067).

| Field | Required | Format | Meaning, default |
|---|---|---|---|
| parent | yes | id | As associatedExpense. |
| at | no | choice `start`, `end`, `date` | Default `start`. `end`: an asset's sale month; a mortgage's property's sale month; a recurring item's last month (only with an `endDate`); never for an account. |
| costDate | with `at: date` | date | Within the horizon. Dropped if the parent does not exist then. |
| amount | one of amount / rate | decimal ≥ 0 | |
| rate | one of amount / rate | fraction in (0, 1) | × the basis that month (at a sale: the sale price). |
| basis | with rate | choice | As associatedExpense. |

- Run: once, `EXPENSE` step (after the month's sales and purchases):
  [COST](ledger.md#cost) cash → outside. Paid also in `expensesCovered` mode. Dropped if
  the month is outside the horizon or the parent's life.
- Code: `state_machine/flows/associated.py` (`compile_associated_cost`,
  `AssociatedCostEmitter`, `Cost`, `cost_month`).

```json
{"type": "associatedCost", "id": "realtor", "name": "Realtor", "parent": "house",
 "at": "end", "rate": "0.05", "basis": "value"}
```

---

# Triggers & adjustments

## trigger

Ties a date of a target item to the date of an event item (ADR-0065).

| Field | Required | Format | Meaning, default |
|---|---|---|---|
| event | yes | id | An item with a date (see below). |
| target | yes | id | The item whose date is set. |
| action | yes | choice `start`, `end`, `startAndEnd` | `start`: the target starts or happens in the event's month (replaces its own date). `end`: its last month is the month before the event (the earlier of that and its own `endDate`). `startAndEnd`: only in the event's month. `end` and `startAndEnd` only for recurring targets (`income`, `expense`, `contribution`, `withdrawal`, `pension`, `extraPayment`). |
| on | no | choice `start`, `end` | Default `start`: the event's date. `end`: the month after its last month (recurring events, needs an `endDate`) or its sale month (property, vehicle). An event that never ends never fires. |

Dated items and the field a trigger reads or sets (`triggers.START_FIELD`): property,
vehicle `purchaseDate`; mortgage, renewal, income, expense, contribution, withdrawal,
pension, extraPayment `startDate`; account `openedDate`; retirement `retirementDate`;
sale `saleDate`; lumpSum `paymentDate`; improvement `improvementDate`; marketAdjustment,
adjustment `adjustmentDate`; transfer `transferDate`; cashBalance `balanceDate`;
associatedCost `costDate`; associatedOneOff `paymentDate`.

- Run: resolved before validation and compiling (`triggers.resolve`, inside
  `triggers.prepared`): the target's date fields are written into a copy of the scenario.
  Errors: unknown ids, a cycle, two triggers setting the same date, an event without a
  date. A target ended before its own start is left out of the run. In the event's month a
  `Triggered` state event is logged (order `OPEN + 59`); no movement.
- Code: `state_machine/triggers.py` (`resolve`, `check`, `event_month`);
  `state_machine/events/trigger.py` (`compile_trigger`, `TriggerEmitter`, `Triggered`).

```json
{"type": "trigger", "id": "t-living", "name": "Living ends at retirement",
 "event": "ret", "target": "living", "action": "end"}
```

## adjustment

A new amount for a cash flow from a date (ADR-0062).

| Field | Required | Format | Meaning, default |
|---|---|---|---|
| flow | yes | id | An `income`, `expense`, `contribution`, `withdrawal` (method `amount` or `percent`, not `annuity`), `associatedExpense` or `associatedIncome`. |
| adjustmentDate | yes | date | Within the horizon. Before the flow starts it applies once the flow runs. |
| amount | for amount flows | decimal ≥ 0 | In dollars of the adjustment date; indexed with the flow's own rate in yearly steps from that date. |
| per | no | choice | Default: the flow's `per`. |
| annualRate | for percent flows | fraction in (0, 1) | For a `percent` withdrawal, or an associated expense or income stated as a rate. |

- Run: the new amounts are known at compile time (`flows/adjustment.steps_for`,
  `rate_steps_for`) and passed to the flow's `IndexingRule` or strategy. Several
  adjustments follow each other; in one month the last in item order wins. In its month an
  `AdjustmentEmitter` (order `OPEN + 60`) logs `FlowAdjusted`; no movement of its own.
- Code: `state_machine/flows/adjustment.py` (`compile_adjustment`, `AdjustmentEmitter`,
  `FlowAdjusted`, `target_of`, `is_percent`).

```json
{"type": "adjustment", "id": "raise", "name": "Raise", "flow": "salary",
 "adjustmentDate": "2030-01-01", "amount": "100000", "per": "year"}
```

---

# Jurisdiction-specific

These types exist only in one jurisdiction. In another jurisdiction validation refuses
them ("… is not available in …"). See [jurisdictions.md](jurisdictions.md).

## contributionRoom

Canada (`CA`) only. Contribution room of one account type for one person, shared by all
their accounts of that type (ADR-0060).

| Field | Required | Format | Meaning, default |
|---|---|---|---|
| accountType | yes | choice `rrsp`, `tfsa` | |
| room | yes | decimal ≥ 0 | Room available in the as-of month. |
| roomAsOfDate | yes | date | Within the horizon. Before it nothing is checked. |
| yearlyMax | yes | decimal ≥ 0 | The year's dollar maximum (RRSP) or annual limit (TFSA) in `maxYear`. |
| maxYear | no | year, e.g. `"2026"` | Default: the year of `roomAsOfDate`. |
| incomeRate | no | fraction in [0, 1] | RRSP only. Default 0.18. |
| indexing, indexRate | no | as income | How `yearlyMax` grows. |
| owner | no | id | Whose room. One item per (person, accountType). |

- Run: in the as-of month (order `OPEN + 50`) the room is set to `room`. Each January
  after it, new room is added: RRSP min(incomeRate × last calendar year's earned income,
  the year's maximum); TFSA the year's maximum plus last year's TFSA withdrawals. The
  year's maximum is `yearlyMax` indexed from `maxYear`, rounded to $10 (RRSP) or $500
  (TFSA). Contributions (own share, then match), transfers and opening transfers into an
  account of that type are capped at the room; the excess stays in cash. No ledger lines.
  Result columns `rrspRoom`, `tfsaRoom` (household total; null before the as-of month).
- Code: `state_machine/jurisdictions/ca/room.py` (`compile_contribution_room`,
  `RoomType`, `RoomLimits`, `RoomStartEmitter`, `RoomYearEmitter`); checks in
  `jurisdictions/ca/__init__.py` `Canada.validate_item`.

```json
{"type": "contributionRoom", "id": "rrsp-room", "name": "RRSP room", "owner": "alex",
 "accountType": "rrsp", "room": "20000", "roomAsOfDate": "2027-01-01",
 "yearlyMax": "33810", "maxYear": "2026", "indexing": "inflation"}
```

## contributionLimit

United States (`US`) only. The yearly contribution limit of one account group for one
person (ADR-0071).

| Field | Required | Format | Meaning, default |
|---|---|---|---|
| limitType | yes | choice `401k`, `ira`, `hsa` | `401k` covers traditional and Roth 401(k) together; `ira` both IRAs; `hsa` the HSA. |
| yearlyLimit | yes | decimal ≥ 0 | The employee limit in `limitYear`. |
| limitYear | no | year | Default: the horizon's first year. Years before it are not checked. |
| catchUp | no | decimal ≥ 0 | Extra from the year the owner turns 50 (HSA 55). Needs the person's `birthDate`. |
| contributedSoFar | no | decimal ≥ 0 | Already contributed in the horizon's first year. |
| indexing, indexRate | no | as income | Growth of both amounts, rounded down to $500 ($50 for HSA). |
| owner | no | id | Whose limit. One item per (person, limitType). |

- Run: no emitters; the factory stores the limit on the household. Each calendar year,
  movements into the group's accounts (contribution own share, transfer, opening
  transfer) are capped at what is left; nothing carries over; the employer match is not
  capped. Result columns `k401Limit`, `iraLimit`, `hsaLimit` (left this year).
- Code: `state_machine/jurisdictions/us/limits.py` (`compile_contribution_limit`,
  `GroupLimit`, `YearlyLimits`); checks in `jurisdictions/us/__init__.py`
  `UnitedStates.validate_item`.

```json
{"type": "contributionLimit", "id": "k401", "name": "401(k) limit", "owner": "sam",
 "limitType": "401k", "yearlyLimit": "23500", "limitYear": "2025", "catchUp": "7500",
 "indexing": "inflation"}
```
