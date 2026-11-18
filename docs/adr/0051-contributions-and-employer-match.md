# ADR-0051: Contributions are cash flows into an account, with an optional employer match

- **Status:** Accepted
- **Date:** 2026-11-07
- **Relates to:** ADR-0012 (cash flows), ADR-0021 (per month/quarter/year), ADR-0048
  (deduction)

## Context
Saving into an RRSP, TFSA or investment account needs a contribution level, and group
RRSPs often add an employer match.

## Decision
- A **contribution** is a `CashFlow` from the operating account (or another account) into
  the target account: amount, `per`, start, optional end, indexing. No new engine concept;
  authoring offers a dedicated form.
- A contribution may have **`employerMatch : Decimal [0..1]`** (a fraction, ADR-0045). Each
  period the employer adds `employerMatch × the contribution paid` into the same account,
  from outside the model. It follows the contribution automatically when the contribution
  changes, is indexed or stops.
- The employer share is neither taxable income nor a deduction (ADR-0048 amendment).
- Matching caps (e.g. "up to 5% of salary") are not modelled; the user sets the
  contribution so that the match is right.

## Alternatives considered
- A separate inflow entered by hand: goes stale when the contribution changes.

## Consequences
- In income-less mode (ADR-0044) the contribution is covered from outside and the match
  still lands in the account.
