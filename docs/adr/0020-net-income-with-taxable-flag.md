# ADR-0020: Income is entered net, with an optional taxable flag

- **Status:** Accepted
- **Date:** 2026-11-04

## Context
The simple tax model (ADR-0004, ADR-0017) has no income-tax brackets. Salary is usually
known as take-home pay, while other income such as rent is received gross and taxed
later.

## Decision
- Income cash flows are entered **net (after tax)** by default.
- An income cash flow can be flagged **taxable**. The engine then taxes it at the flat
  effective tax rate in the tax step (ADR-0018 step 7).

## Consequences
- Salary is entered as take-home pay. Rent, and any other gross income, is flagged
  taxable.
- Expenses that reduce taxable rental income (deductions) are not modelled.

## Amendment (2026-11-07): defaults differ between files and entry screens
- In **JSON**, an income cash flow without `taxable` is after tax (`taxable = false`), the
  neutral default (ADR-0040): omitting the flag never invents a tax.
- **Authoring screens** pre-fill new income as **taxable** (gross), because salaries are
  usually known gross. This is a UI default only; pensions already known net and "free
  income" are entered with taxable switched off.
- Tax on taxable income is still computed in the **tax step** (ADR-0018 step 7), together
  with every other tax. The PoC deducts it as income arrives (withholding); within a month
  the result is the same, and the PoC will be aligned later.
