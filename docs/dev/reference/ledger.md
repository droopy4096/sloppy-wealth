# Ledger movements

Every balance change in a run is one ledger line, recorded by `Household.move()`
(`state_machine/household.py`) into `household.ledger` (`state_machine/ledger.py`,
ADR-0053). Nothing else changes a balance.

## Line format

`run_detailed(scenario)["ledger"]` is a list of dicts, in the order the movements happened,
with keys in this order:

| Key | Type | Meaning |
|---|---|---|
| month | `"YYYY-MM"` | Month of the movement. |
| kind | string | One of the kinds below. |
| from | holding id or `null` | Where the money comes from. `null` = outside the model. |
| to | holding id or `null` | Where it goes. `null` = outside the model. |
| amount | Decimal (string in the API) | Rounded half-even to cents. Never 0: a movement that rounds to 0 is not recorded. Valuation kinds may be negative. |
| source | item id, person id or `null` | The item that caused it (see each kind). |

Holding ids: `"cash"`, or the id of a property, vehicle, mortgage, account or pension item.

`move(kind, src, dst, amount, source)` subtracts from `src` and adds to `dst`. A mortgage
is a liability: its balance is positive when owed, so money *from* a mortgage raises the
balance (advance, interest) and money *to* it lowers the balance (payments). The sign is
flipped in one place, `Aggregate._apply` (`base.py`).

The "Cash" column below is the effect on cash: + into cash, − out of cash. "Tax" says
whether the movement feeds the tax step ([rules.md](rules.md#taxrule)). The ledger page
(`POST /api/view/ledger`) adds a signed `cash` field per line the same way.

Old kinds no longer produced: `MAINTENANCE` and `SELLING_COST` (older files' vehicle
maintenance and selling costs now give `EXPENSE` and `COST` lines, see `upgrade.py`).

## Summary

| Kind | From → to | Cash | Created by |
|---|---|---|---|
| [INCOME](#income) | outside → cash | + | income, associatedIncome, associatedOneOff |
| [EXPENSE](#expense) | cash → outside | − | expense, associatedExpense |
| [COST](#cost) | cash → outside | − | associatedCost |
| [PURCHASE](#purchase) | cash → asset | − | property, vehicle |
| [REVALUATION](#revaluation) | outside → asset or pension | 0 | property (marketValue), improvement, pension |
| [APPRECIATION](#appreciation) | outside → asset | 0 | property, vehicle |
| [IMPROVEMENT](#improvement) | cash → property | − | improvement |
| [MARKET_ADJUSTMENT](#market_adjustment) | outside → asset | 0 | marketAdjustment |
| [SALE_PRICE_DIFFERENCE](#sale_price_difference) | outside → asset | 0 | sale |
| [SALE](#sale) | asset → cash | + | sale |
| [LOAN_ADVANCE](#loan_advance) | mortgage → cash | + | mortgage |
| [LOAN_INTEREST](#loan_interest) | mortgage → outside | 0 | mortgage |
| [INTEREST_ADJUSTMENT](#interest_adjustment) | cash or outside → mortgage | − or 0 | mortgage |
| [LOAN_PAYMENT](#loan_payment) | cash or outside → mortgage | − or 0 | mortgage |
| [PREPAYMENT](#prepayment) | cash or outside → mortgage | − or 0 | extraPayment, lumpSum |
| [LOAN_PAYOFF](#loan_payoff) | cash → mortgage | − | sale |
| [PENALTY](#penalty) | cash → outside | − | sale, renewal, lumpSum |
| [OPENING_BALANCE](#opening_balance) | outside → account | 0 | account |
| [OPENING_TRANSFER](#opening_transfer) | cash → account | − | account |
| [CONTRIBUTION](#contribution) | cash or outside → account | − or 0 | contribution |
| [EMPLOYER_MATCH](#employer_match) | outside → account | 0 | contribution |
| [PENSION_CONTRIBUTION](#pension_contribution) | cash → outside | − | contribution (to a pension) |
| [TRANSFER](#transfer) | cash → account | − | transfer |
| [GRANT](#grant) | outside → account | 0 | transfer, contribution (CA RESP) |
| [RETURN](#return) | outside → account | 0 | account |
| [WITHDRAWAL](#withdrawal) | account → cash | + | withdrawal |
| [PENSION_PAYMENT](#pension_payment) | pension → cash | + | pension |
| [CASH_RECONCILIATION](#cash_reconciliation) | outside ↔ cash | ± | cashBalance |
| [TAX](#tax) | cash → outside | − | tax step |

## Income and spending

### INCOME
- outside → cash. Source: the income, associatedIncome or associatedOneOff item.
- `flows/income_expense.py` `Income`. Step `INCOME`.
- Tax: added to the owner's taxable income when the item (for associated items, the
  parent) is `taxable`; counted as earned income when `earnedIncome`.

### EXPENSE
- cash → outside. Source: the expense or associatedExpense item.
- `flows/income_expense.py` `Expense`. Step `EXPENSE`. Not deductible.

### COST
- cash → outside. Source: the associatedCost item.
- `flows/associated.py` `Cost`. Step `EXPENSE`. Not deductible.

## Properties and vehicles

### PURCHASE
- cash → asset, the price. Source: the asset id.
- `events/purchase.py` `Purchase`. Step `ACQUIRE`, purchase month. Not taxed.

### REVALUATION
- outside → asset or pension. May be negative. Source: the asset id, the improvement id,
  or the pension id.
- `events/purchase.py` `Revaluation` (marketValue − price at purchase; valueAdded − cost
  after an improvement); `holdings/pension.py` `PensionRevalued` (to the pension's value,
  step `REVALUE_PENSIONS`, every month). Not taxed.

### APPRECIATION
- outside → asset: opening value × monthly rate. Negative for a vehicle. Source: the asset id.
- `holdings/real_estate.py` `Appreciation`. Step `GROW`. Not taxed.

### IMPROVEMENT
- cash → property, the cost. Source: the improvement id.
- `events/improvement.py` `Improvement`. Step `IMPROVE`. Not taxed.

### MARKET_ADJUSTMENT
- outside → asset: value × percent, or newValue − value. May be negative. Source: the
  marketAdjustment id.
- `events/adjustment.py` `MarketAdjustment`. Step `ADJUST`. Not taxed.

### SALE_PRICE_DIFFERENCE
- outside → asset: salePrice − current value, before the sale. May be negative. Source:
  the sale id (the asset id for an older property saleDate).
- `events/sale.py` `Sale`. Step `SELL`. Not taxed.

### SALE
- asset → cash, the asset's whole value (after any price difference). Source: the sale id.
- `events/sale.py` `Sale`. Step `SELL`. Not taxed: the capital-gains rule is a no-op
  ([rules.md](rules.md#capitalgainsrule)).

## Mortgages

### LOAN_ADVANCE
- mortgage → cash, the principal. Raises the loan balance. Source: the mortgage id.
- `holdings/mortgage.py` `Mortgage.advance`, event `LoanAdvance`. Step `ACQUIRE`.

### LOAN_INTEREST
- mortgage → outside. Raises the balance. Source: the renewal in effect, else the
  mortgage id.
- Before the first payment: interest on the principal (accrual). After: interest on the
  balance before the payment. `Mortgage.accrue`, `Mortgage.charge_interest`. Step
  `SERVICE_DEBT`. Not deductible.

### INTEREST_ADJUSTMENT
- cash → mortgage (outside → mortgage in `expensesCovered` mode): the interest accrued
  before a late first payment, paid in the first payment month. Source: as LOAN_INTEREST.
- `Mortgage.settle_accrued`. Step `SERVICE_DEBT`.

### LOAN_PAYMENT
- cash → mortgage (outside → mortgage in `expensesCovered` mode): the scheduled payment,
  capped at what is owed; the last one clears the rest. Source: as LOAN_INTEREST.
- `Mortgage.pay_scheduled`. Step `SERVICE_DEBT`.

### PREPAYMENT
- To the mortgage, capped at the balance. From cash; from outside for an extraPayment in
  `expensesCovered` mode or a lumpSum with `paidFrom: outside`. Source: the extraPayment or
  lumpSum id.
- `Mortgage.prepay`, events `ExtraPrepayment`, `LumpSumPrepayment`. Step `SERVICE_DEBT`.

### LOAN_PAYOFF
- cash → mortgage, the whole balance, when the asset securing it is sold. Source: the
  sale id.
- `Mortgage.pay_off`, event `LoanPayoff` (`events/sale.py`). Step `SELL`.

### PENALTY
- cash → outside. Source: the sale, renewal or lumpSum id.
- A sale's `salePenalty` or its loans' term formula (`SalePenalty`); a renewal's
  `penalty` (`RenewalPenalty`); a lump sum's `penalty` (`LumpSumPenalty`) or, for a payoff
  without one, the term formula (`ClosurePenalty`). `events/sale.py`, `events/loan.py`.
  Not deductible.

## Accounts and pensions

### OPENING_BALANCE
- outside → account: an existing balance not modelled before (account opened inside the
  horizon, `openingFrom: outside`). Source: the account id.
- `holdings/account.py` `AccountOpening`. Step `ACQUIRE`. No tax effect, no limit.

### OPENING_TRANSFER
- cash → account (`openingFrom: cash`). The whole opening balance: it is the account's
  current state, not a contribution, so it is not capped by limits and uses no room
  (ADR-0060 amendment). Source: the account id.
- `holdings/account.py` `AccountOpening`. Step `ACQUIRE`. Not deducted and no RESP grant
  (`on_contribute` is not called).

### CONTRIBUTION
- cash → account (outside → account in `expensesCovered` mode), capped by limits.
  Source: the contribution id.
- `InvestmentAccount.accept_contribution`. Step `CONTRIBUTE`.
- Tax: a deduction of the account's contributor (owner, or spousal RRSP contributor) for
  deductible types, not in `expensesCovered` mode.

### EMPLOYER_MATCH
- outside → account: employerMatch × the share contributed, capped by CA room (not by
  US limits). Source: the contribution id.
- `InvestmentAccount.accept_contribution`. Step `CONTRIBUTE`. Neither income nor a
  deduction.

### PENSION_CONTRIBUTION
- cash → outside: a contribution whose `account` is a pension. The pension's value does
  not change. Not recorded in `expensesCovered` mode. Source: the contribution id.
- `holdings/pension.py` `Pension.accept_contribution`. Step `CONTRIBUTE`. Tax: a
  deduction of the pension's owner.

### TRANSFER
- cash → account, capped by limits; from cash in either income mode. Source: the
  transfer id.
- `events/transfer.py` `Transfer`. Step `TRANSFER`. Tax: as CONTRIBUTION (deduction for
  deductible types, not in `expensesCovered` mode).

### GRANT
- outside → account: the Canada Education Savings Grant on money put into an RESP
  (20 %, limited by grant room, $1,000 a year, $7,200 lifetime). Source: the contribution
  or transfer id.
- `jurisdictions/ca/resp.py` `pay_grant`, called from `Canada.on_contribute`. Not taxed.

### RETURN
- outside → account: opening balance × monthly rate. May be negative. Source: the account id.
- `holdings/account.py` `AccountReturn`. Step `GROW`.
- Tax: taxable income of the owner (a loss counts as 0) when the account type's returns
  are taxed (CA `nonRegistered`, US `brokerage`).

### WITHDRAWAL
- account → cash, capped at the balance. Source: the withdrawal id.
- `flows/withdrawal.py` `Withdrawal`. Step `WITHDRAW`.
- Tax: when the type's withdrawals are taxed (CA `rrsp`, US traditional 401(k) / IRA):
  taxable income of the owner, or tax at the account's `withdrawalTaxRate` if set
  (`ownRateTax` in the tax detail). TFSA withdrawals give room back the next year.

### PENSION_PAYMENT
- pension → cash. Paid also in `expensesCovered` mode. Source: the pension id.
- `holdings/pension.py` `PensionPaid`. Step `PENSION_PAY`. Tax: taxable income of the
  owner when the pension is `taxable` (default).

## Cash and tax

### CASH_RECONCILIATION
- outside → cash when cash was below the stated balance; cash → outside when above.
  Source: the cashBalance id.
- `events/cash_balance.py` `CashReconciled`. Order `TAX + 50` (after the tax step). Not
  taxed.

### TAX
- cash → outside: the month's tax, one line per person. Source: `null` with one person,
  the person id with several. Not recorded when it rounds to 0.
- `rules/tax.py` `TaxRule.apply`. Step `TAX`. See [rules.md](rules.md#taxrule).
