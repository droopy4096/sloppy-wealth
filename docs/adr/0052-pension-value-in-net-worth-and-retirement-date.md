# ADR-0052: A guaranteed pension has a value in net worth; scenarios have a retirement date

- **Status:** Accepted
- **Date:** 2026-11-07
- **Amends:** ADR-0036 (pension has no holding and no value), ADR-0050 (result columns)
- **Resolves:** Q-14, Q-31

## Context
ADR-0036 gave a defined-benefit pension no value in net worth, so a member relying on one
looked poorer than someone with the same wealth in an RRSP. The horizon end already stands
for the end of life (ADR-0036, ADR-0039), so the pension's remaining payments are known.

## Decision
- A **guaranteed pension** is a holding, **`PensionEntitlement`**, with:
  - the pension amount and its indexing (inflation, or a custom rate, ADR-0013);
  - payments from the scenario's **retirement date** to the **horizon end** (end of life);
  - taxable income when paid (ADR-0020).
- Its **value at each period** is the sum of the payments still to come, from
  the later of that period and the retirement date until the horizon end, valued without discounting
  (see the amendment below, Q-36). Before retirement the value covers the whole stream; it then
  falls as payments are received and reaches 0 at the horizon end.
- This value **counts in net worth** and in assets net worth (ADR-0050).
- A **`Scenario.retirementDate`** is added. Guaranteed pensions start on it. RRSP, TFSA and
  other accounts are **not** tied to it: their withdrawals keep their own dates (fixed
  amounts, even drawdown ADR-0039, percent withdrawal ADR-0049).
- The retirement date is a date like any other, so it can be shifted and swept to answer
  "when can I retire" (ADR-0038, ADR-0041).

## Alternatives considered
- No value (ADR-0036 as it was): understates pension-reliant wealth.
- A separate "net worth including pension" figure: keeps net worth cash-honest, but the
  user prefers the pension inside net worth.
- A commuted value entered by hand: correct only on the statement date.

## Consequences
- Net worth now includes a value that cannot be spent as cash; liquidation net worth
  (ADR-0031) should exclude it, since a pension is normally not sold (to confirm with the
  output model, Q-34).
- The pension income flows into the operating account from the retirement date, as before.

## Amendment (2026-11-08): no discounting; amount in today's dollars (Q-36)
- The pension **amount is stated in today's dollars** (the scenario's base date, ADR-0013),
  as pension statements quote it, and grows with its indexing until the retirement date.
  This is an exception to "an amount is in dollars of its own start date" (ADR-0013
  amendment), which still applies to other cash flows.
- The value is **not discounted** (a 0% real rate): it is the sum of the remaining payments
  expressed in base-date dollars. For a fully inflation-indexed pension this is simply
  **monthly amount (today's dollars) × months remaining**; nominal columns convert it with
  the inflation rate.
- This mirrors the even drawdown (ADR-0039), which also assumes no return: a pension worth
  $900,000 and a $900,000 fund drawn down evenly give the same income over the same months.
- The value is higher than a market commuted value. A discount rate may be added later as
  an option if market-style values are wanted.

## Amendment (2026-11-08): income can end at the retirement date (Q-37)
- An income cash flow has **`endsAtRetirement : bool`**. When true, it stops in the month
  before the scenario's retirement date, unless its own end date is earlier. With no
  retirement date set, it runs to its own end date or the horizon end.
- JSON default is **false** (neutral, ADR-0040); authoring screens pre-fill **true** for
  salaries.
- Shifting the retirement date therefore moves salaries' end and pensions' start
  together, which is what a "when can I retire" sweep needs (ADR-0038).

## Amendment (2026-11-08): where the value is shown (Q-38)
- Shown inside the Investments column and excluded from liquidation net worth
  (ADR-0050 amendment). This confirms the consequence noted above.

## Amendment (2026-11-08): member contributions (Q-33a)
- A member's contributions to a defined-benefit plan are **`Contribution`s (ADR-0051) to the
  `PensionEntitlement`**: money leaves the operating account and is a **deduction**
  (ADR-0048, same month).
- They **do not change the pension's value**, which comes from the promised benefit.
- They can use `endsAtRetirement` (amendment above) to stop when employment ends.

## Amendment (2026-11-08): own start and end dates (Q-33b)
- A `PensionEntitlement` has an optional **`start`** (default: the scenario's retirement
  date) and an optional **`end`** (default: the horizon end).
- A **bridge benefit** is a second entitlement with an end date (e.g. the month before 65).
  **CPP and OAS** are entitlements with their own start date (e.g. the month of the 65th
  birthday).
- The value counts only the payments between the entitlement's own start and end.
- Moving the retirement date moves entitlements without their own start; those with a
  fixed start stay put.

## Amendment (2026-11-08): cash flows can start at retirement; expenses too
- Any income or expense cash flow may be tied to the retirement date: **`endsAtRetirement`**
  (stops the month before) or **`startsAtRetirement`** (starts in the retirement month), not
  both. With `startsAtRetirement` its own start date is optional and used only when the
  scenario has no retirement date.
- Typical use: living expenses at one level while working and another in retirement, as
  two items that switch over at the retirement date and move with it in sweeps.
- Authoring offers one choice per item (not tied / ends / starts), income defaulting to
  "ends".

## Amendment (2026-11-09): discounted value, after tax in liquidation net worth (C-P4)
Supersedes the Q-36 amendment's "not discounted" and the Q-38 exclusion from liquidation
net worth. The Q-36 rationale ("mirrors the even drawdown") was wrong, and the value sat
pre-tax beside after-tax TFSA balances while no figure showed it after tax.
- Scenario setting **`pensionDiscountRate`** (real rate, yearly; default **2%**, about the
  long-term real bond yield; listed as an applied default, ADR-0040/0053).
- The value is the **present value of the remaining payments** at that real rate, in
  base-date dollars, then converted to the period's dollars for nominal columns. For a
  fully indexed pension: amount × (1 − (1 + d)^−n) / d, with *d* the monthly real rate
  and *n* the months remaining; at 0% it is amount × n (the previous rule).
- Net worth: the discounted value, in the Investments column (unchanged placement).
- **Liquidation net worth includes** the discounted value × (1 − effective tax rate).
- The amount still sits in today's dollars (Q-36 first bullet, unchanged).

### Consequences
- $1,500/month for 25 years: about $354k at 2% instead of $450k.
- Setting the rate to 0% restores the earlier undiscounted value.

## Amendment (2026-11-09): no early/late adjustment; warning only (C-P5)
- A pension's amount does **not** change with its start date: no early-retirement
  reduction, no late-start increase, no CPP/OAS adjustment factors. The user enters the
  amount that applies to the start date being modelled.
- **Warning:** when a PensionEntitlement starts at the retirement date (no own start) and
  the retirement date is varied (a sweep, ADR-0038, or scenarios in one set with
  different retirement dates), the result carries "pension amount does not vary with
  start date; enter the amount for each date". The same applies when a pension's own
  start differs between scenarios of a set.

### Consequences
- Retirement-date sweeps overstate early retirement unless the user enters a reduced
  amount per scenario. The bias is known and flagged, not modelled.
- An adjustment-rate rule or an amount-by-start-date table can be added later without
  changing existing inputs.

## Amendment (2026-11-09): the amount's dollars are fixed by the base date (C-P14)
- The pension amount is in dollars of `Scenario.baseDate`, which is now input only
  (ADR-0013 amendment 2026-11-09). Viewing results in other dollars uses
  `displayDollarsOf` and does not change the pension.

## Amendment (2026-11-09): drift within a year (C-M13)
- In real (base-date or display) columns the pension value drifts down by up to one
  year's inflation within each year and steps back at the anniversary, because payments
  step yearly (ADR-0013) while deflation is monthly. This is intended: the value matches
  the payments actually made.

## Amendment (2026-11-09): retirement is an event (ADR-0059)
- `Scenario.retirementDate` is replaced by a **RetirementEvent**; every "at the retirement
  date" above means its month. Withdrawals without their own start date now start at it,
  and the tax rate switches to `retirementTaxRate`.
