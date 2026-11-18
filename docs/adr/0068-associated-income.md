# ADR-0068: Associated income (income that lives with an income or a pension)

- **Status:** Proposed (design agreed 2026-11-14, Q-43; implemented on `poc/sm-triggers`, tag
  `sm-triggers-before-associated-income` marks the state before it)
- **Date:** 2026-11-14
- **Relates to:** ADR-0067 (associated expenses and costs), ADR-0062 (adjustments),
  ADR-0020 (income gross / net), ADR-0021 (`per`)

## Context
A salary bonus is today an ordinary income item (e.g. "Employer bonus", 2,000 per quarter,
ending at retirement). Its total is right, but it does not follow the salary: a raise or
an adjustment of the salary does not change it, and its end must be kept in step by hand
or by a trigger. Bonuses are usually a share of the base salary, paid while the job
lasts. The owner asked for an *associated income*, as ADR-0067 does for expenses: an
income whose lifecycle comes from its parent and whose amount can be looked up from it.
Real-world cases with a pension parent are fewer but exist (13th / 14th month pensions,
retiree benefit allowances, pension-linked top-ups); a DB bridge benefit (ends at 65) and
a survivor pension (starts when the parent ends) do not fit a pure associated item.

## Decision
1. **Parents (Q-43a): income and pension.** An associated income lives from its parent's
   start to its end, as an associated expense does (ADR-0067 decision 1).
2. **Amount (Q-43b): a fixed sum or a percentage**, as for associated expenses (ADR-0067
   decisions 3 and 11): a fixed amount (`amount`, `per`), or a yearly rate of the
   parent's yearly amount (its raises, indexing and adjustments included), taken on the
   parent's start and on each anniversary.
3. **Payment timing (Q-43c): monthly or in arrears as a lump.** `paid`: `monthly` (spread
   evenly, as other flows) or `lump`: the whole period's amount (`per` quarter or year)
   in one payment at the end of each period, i.e. on each quarterly or yearly
   anniversary of the parent's start, never in its first month (start 2026-08, per
   quarter: 2026-11, 2027-02, ...). Only full periods are paid: when the parent ends
   partway through a period, that period's lump is forfeited (as a bonus is when one
   leaves before its date).
4. **One-offs (Q-43d): a second type, the associated one-off income** (working name
   `associatedOneOff`), mirroring the associated cost (ADR-0067 decision 5): paid `at`
   the parent's start (signing bonus), its end, i.e. its last month (severance), or on its
   own date while the parent exists (retention bonus); a fixed amount or a percentage of
   the parent's yearly amount in that month.
5. **Tax and owner (Q-43e): inherited from the parent**: taxable, earned income (RRSP
   room, ADR-0060) and owner (ADR-0061) are the parent's; the forms have no such fields.
6. **Indexing and adjustments (Q-43f): as for associated expenses** (ADR-0067 decisions
   7 and 8): a fixed amount has the usual indexing from the parent's start and an
   adjustment gives a new amount; a percentage is not indexed (it follows the parent's
   amount) and an adjustment gives a new rate (e.g. a bonus target from 10% to 15%).
7. **Migration (Q-43g): none.** Nothing in a file says which income is the bonus of which
   salary; existing bonus incomes keep running as plain incomes and are re-created as
   associated income by hand.

## Alternatives considered
- **A plain income item** (status quo): does not follow the salary's amount or end.
- **A "paid as a lump" option on income**: fixes payment timing only; the lump timing
  is part of associated income instead (decision 3).
- **Pro-rated or full lump for a partial last period**: rejected; a bonus is usually
  forfeited when one leaves before its date.
- **Own tax / owner fields**: rejected; a bonus is taxed like its salary.
- **Converting bonus incomes on load by name**: fragile; may mis-attach.

## Consequences
- Two new item types (`associatedIncome`, `associatedOneOff`), mirroring ADR-0067's; the
  `amount` basis is extended to pensions. Recurring flows gain a first lump payment rule
  (in arrears, full periods only), for associated income only.
- No conversion on load: existing files and the golden suite are unchanged.
- Domain model: `AssociatedIncome` and `AssociatedOneOffIncome` (diagram 02 v0.54).
- Implemented on `poc/sm-triggers` (2026-11-14): `flows/associated_income.py`. Details
  settled in the implementation: a lump is the rounded sum of the period's unrounded
  monthly shares (2,000 a quarter pays 2,000, not 3 x 666.67); the last full period's
  lump is paid in the month after the parent's last month (in arrears), if within the
  horizon; a one-off at the parent's end needs an endDate within the horizon.
