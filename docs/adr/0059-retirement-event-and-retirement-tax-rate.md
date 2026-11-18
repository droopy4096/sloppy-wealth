# ADR-0059: A RetirementEvent triggers everything tied to retirement, including the tax rate

- **Status:** Accepted
- **Date:** 2026-11-09
- **Relates to:** ADR-0052 (retirement date, pensions), ADR-0017 (effective tax rate),
  ADR-0035 (tax-deferred withdrawals), ADR-0039/0049 (withdrawals), ADR-0038 (sweeps),
  ADR-0007 (events)
- **Amends:** ADR-0052 (`Scenario.retirementDate`; accounts not tied to retirement)

## Context
In the user's baseline, a defined-benefit pension after retirement was taxed at the
working-years rate (30%) instead of a lower retirement rate (about 20%). One flat rate
for a whole life overstates tax in retirement. Retirement also switches many things at
once (salaries end, pensions and draws start, some expenses start), and the user wants
one item that triggers them all.

## Decision
- New event **`RetirementEvent`** (date). At most one per scenario. Its month is the
  **retirement month**. It replaces `Scenario.retirementDate`; files that still carry
  `retirementDate` are read as an implicit RetirementEvent (not both: validation error).
- From the retirement month:
  - Salaries and other cash flows with `endsAtRetirement` stop (the month before);
    cash flows with `startsAtRetirement` start (ADR-0052 amendments, unchanged).
  - **Pensions** without their own start date start (unchanged).
  - **Withdrawals** from accounts (retirement funds) **without their own start date**
    start. A withdrawal with a start date keeps it. (Changes ADR-0052's "accounts are
    not tied to it".)
  - The tax rate switches from `effectiveTaxRate` to **`retirementTaxRate`**.
- **`Scenario.retirementTaxRate`** (rate; optional; default: `effectiveTaxRate`, i.e. no
  switch; listed as an applied default). It applies to all taxable income and
  deductions from the retirement month: pensions, salaries still running, non-registered
  income, and tax-deferred withdrawals without their own `withdrawalTaxRate` (an
  account's own rate still wins, ADR-0035). It is a two-segment form of the
  effectiveTaxRate series (ADR-0017).
- Shifting or sweeping the RetirementEvent moves all of the above together (ADR-0038).

## Alternatives considered
- A tax rate per pension (like `withdrawalTaxRate`): fixes the pension only, not other
  income after retirement.
- Keep `retirementDate` as a scenario field: works, but the user wants retirement as a
  visible event among the items, shiftable like other events.

## Consequences
- Without a RetirementEvent nothing is tied to retirement: pensions and withdrawals need
  their own start dates (validation error otherwise), and one tax rate applies.
- Liquidation tax (ADR-0031) and per-sale rates (ADR-0017) are unaffected.

## Amendment (2026-11-09): every end date may be a date, none, or retirement
- Every item with an end date (income, expense, contribution, withdrawal, extra
  mortgage payment, pension) ends in one of three ways, chosen explicitly in authoring:
  - **on a date** (`endDate`),
  - **never** (perpetual: runs to the horizon end or until exhausted),
  - **at retirement** (`endsAtRetirement`: stops the month before the RetirementEvent).
- `endsAtRetirement` therefore extends from income, expenses and contributions to
  withdrawals, extra mortgage payments and pensions (e.g. a bridge benefit started early
  that stops at retirement).
- JSON stays lenient for older files: if both `endDate` and `endsAtRetirement` are set,
  the earlier applies; without a RetirementEvent, `endsAtRetirement` has no effect.
- Authoring defaults: salaries and contributions "at retirement"; everything else "never".

## Amendment (2026-11-09): a sale may happen at retirement
- A `SaleEvent` may set **`atRetirement`** instead of a date: it happens in the
  RetirementEvent's month and moves with it (e.g. downsizing when retiring). A sale has
  either a date or `atRetirement`, not both; `atRetirement` without a RetirementEvent is
  a validation error.
- All rules that refer to the sale month (mortgage payoff, renewals before the sale,
  improvements and market adjustments before the sale) use the retirement month.

## Amendment (2026-11-09): a lump-sum prepayment may happen at retirement and pay off the loan
- A `LumpSumPrepayment` may set **`atRetirement`** instead of a date (same rules as a
  sale at retirement).
- It may set **`payOff`** instead of an amount: it pays the loan's whole outstanding
  balance in that month (after that month's scheduled payment), so the user need not
  know the balance in advance. Its penalty field applies as for any lump sum (ADR-0047).

## Amendment (2026-11-09): a one-off transfer may happen at retirement
- A `OneOffTransfer` (ADR-0025) may set **`atRetirement`** instead of a date (same rules
  as a sale at retirement), e.g. moving sale proceeds into an RRSP when retiring.
- A transfer into a tax-deferred account is a deduction as before (ADR-0048).
