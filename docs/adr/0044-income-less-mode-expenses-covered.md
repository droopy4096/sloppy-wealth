# ADR-0044: Income-less mode, where expenses are assumed covered

- **Status:** Accepted
- **Date:** 2026-11-07
- **Relates to:** ADR-0040 (minimal input), ADR-0042 (free income net of modelled payments)

## Context
Many questions are about what the holdings do (appreciation, amortisation, equity,
sales), not about the household budget. Entering income and every expense just to keep
cash from drifting is a burden, and an incomplete budget makes cash, and so net worth,
misleading: leftover income piles up, or missing income drives cash negative.

## Decision
- A scenario has an **income mode**: `modelled` (the default, as before) or
  `expensesCovered`.
- In `expensesCovered`:
  - **Income cash flows are ignored**, and so is income tax.
  - **Recurring outgoings are assumed paid from outside the model**, leaving no free money:
    scheduled loan payments, extra monthly loan payments, expenses and costs. They still
    take effect on the holdings (loans amortise, prepayments shorten them) but do not
    move the operating account.
  - **One-off events still go through the operating account**: purchases, loan advances,
    lump-sum prepayments, sales with their selling costs and loan payoffs.
- Net worth in this mode means "what the holdings and the one-off decisions did", with
  the household budget factored out.

## Alternatives considered
- Enter a "free income" exactly equal to the expenses (ADR-0042, `netOf`): needs the payment
  amounts by hand or a netting rule, and goes stale at renewals and prepayments.
- Let cash go negative and ignore it: hides real shortfalls among the artefacts.

## Consequences
- Shortfall capping (ADR-0015) only applies to one-off events in this mode.
- Comparisons between a scenario in this mode and one with modelled income are not
  like-for-like; a comparison view should show each scenario's income mode (as it does
  inflation, ADR-0028 amendment).
- Treating lump sums as paid from the operating account (not covered) is a choice made
  while building the PoC: a lump sum is a one-off decision funded from savings.

## Amendment (2026-11-07): the source of a lump sum is chosen per lump sum
- Each lump-sum prepayment says where its money comes from: the **operating account**
  (default) or **outside the model** (e.g. a gift or a bonus that is not modelled). Outside
  money reduces the loan without moving the operating account.
- This applies in both income modes, and replaces the PoC choice noted under Consequences.

## Amendment (2026-11-07): contributions and withdrawals of accounts
- **Contributions** into accounts (RRSP, TFSA, investments) are recurring outgoings and are
  **covered from outside**: the money lands in the account; the operating account does not
  move.
- **Withdrawals** from accounts are **moves between holdings**, not income: the account
  falls and the operating account rises by the same amount.
- **Taxes on holdings still apply**: withdrawal tax (ADR-0035) and capital gains tax
  (ADR-0017). Only tax on ignored income disappears.
- With no taxable income, the contribution deduction (ADR-0048) has nothing to reduce, so
  it has no effect in this mode. Withdrawals are taxed but contributions are not deducted;
  comparisons between this mode and modelled income should keep that in mind.

## Amendment (2026-11-08): only income from outside the holdings is ignored (Q-32)
- The mode ignores **income cash flows from outside the model's holdings** (salaries and
  other income items): the outside budget replaces them.
- **Guaranteed pension payments still happen.** A pension is a holding (ADR-0052), so its
  payments are moves from the pension's value into the operating account, like account
  withdrawals (amendment above), and are taxed as such.
- Net worth stays consistent: after the retirement date the pension's value turns into
  cash month by month instead of disappearing.
