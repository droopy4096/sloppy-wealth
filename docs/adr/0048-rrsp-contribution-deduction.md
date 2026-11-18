# ADR-0048: Contributions to tax-deferred accounts are deducted in the same month

- **Status:** Accepted
- **Date:** 2026-11-07
- **Relates to:** ADR-0017 (flat rate), ADR-0020 (taxable income), ADR-0035 (tax-deferred
  withdrawals), ADR-0018 (tax step)

## Context
RRSP contributions reduce taxable income. The model taxed withdrawals from tax-deferred
accounts (ADR-0035) but gave no deduction for contributions, so a $500/month contribution
cost $500 of cash instead of about $350 at a 30% rate.

## Decision
- Money moved **into a `TAX_DEFERRED` account** from outside it (a contribution cash flow
  or one-off transfer) is a **deduction** in the period it is made. Only the member's own
  contributions count; see the amendment on employer contributions below.
- In the tax step (ADR-0018 step 7) the period's taxable income is reduced by the
  deductions: tax = rate × max(0, taxable income − deductions). The deduction cannot make
  the tax negative; any excess is lost (no carry-forward).
- Same-month treatment matches payroll and group-RRSP deductions at source. A yearly
  refund the following April would give the same yearly total a few months later, at the
  cost of carrying state across years.
- Contribution room is not checked (Q-06, watch item).

## Alternatives considered
- Yearly refund in April: more realistic for self-directed contributions, but needs
  per-year accumulation and a dated refund event.
- No deduction: overstates the cost of saving in an RRSP.

## Consequences
- Transfers between tax-deferred accounts (e.g. RRSP to RRSP) are not deductions.
- With the income-less mode (ADR-0044) there is no taxable income, so deductions have no
  effect (see Q-29).

## Amendment (2026-11-07): employer contributions are not deductions
- An employer contribution is taxable to the employee and deductible, so the two cancel
  out. It is therefore **neither taxable income nor a deduction** in the model.
- Only the member's own contributions are deducted.

## Amendment (2026-11-08): pension plan contributions are deductions too
- A member's contribution to a defined-benefit pension plan (ADR-0052 amendment) is a
  deduction under the same rule as a contribution to a `TAX_DEFERRED` account.

## Amendment (2026-11-09): refund credit when income is entered after tax (C-P2)
- In **modelled-income mode**, a deduction that finds no taxable income to reduce is not
  lost. The excess becomes a **refund credit**: credit = rate × max(0, deductions −
  taxable income), paid into the operating account in the same tax step. Equivalently,
  tax = rate × (taxable income − deductions) may be negative.
- Reason: income entered after tax (the JSON default, ADR-0020) had tax withheld at
  source; the contribution earns that tax back. Without the credit, a $500/month RRSP
  contribution at 30% lost about $1,800 a year.
- In **income-less mode** (ADR-0044) the excess stays lost: no tax was withheld.
- The ledger books the credit as a tax movement from outside to cash, sourced to the
  contribution(s).

### Consequences
- The "any excess is lost" rule above now applies only to income-less mode.
- Simplification: the model assumes withheld tax at the flat rate covers the credit; it
  does not check that the after-tax income was large enough to have withheld it.

## Amendment (2026-11-09, later): carry-forward pool replaces the refund credit (C-P2 revisited)
Supersedes the refund-credit amendment above. An uncapped credit paid cash for tax that
was never withheld: a $300k RRSP transfer in a month with $2,000 of pension income
would have paid about $60k.
- A deduction the period's taxable income cannot absorb goes into a **carried-forward
  pool** (undeducted contributions, as CRA allows without time limit).
- Each tax step applies the period's deductions plus the pool against taxable income
  from any source, down to 0: tax = rate × max(0, taxable − deductions − pool). What is
  not used stays in the pool. Tax is never negative and nothing is paid out.
- The pool also works in income-less mode (ADR-0044): withdrawals' taxable amounts use
  it. Anything left at the horizon end is lost.
- Consequence: salary entered after tax gets the benefit of its contributions only
  later, against taxable retirement income, not as yearly refunds. Authoring defaults
  salaries to before-tax (ADR-0020), so this mainly affects hand-written JSON.

## Amendment (2026-11-11): deductions and the pool are per person (ADR-0061)
An RRSP contribution reduces only the taxable income of the person whose room it uses:
the account's owner, or its `contributor` for a spousal RRSP. Each person has their own
carried-forward pool; unused deductions never move between persons (Canada has no joint
filing).
