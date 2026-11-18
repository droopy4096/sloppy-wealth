# ADR-0039: Even drawdown of a pot over the remaining lifetime

- **Status:** Accepted
- **Date:** 2026-11-05

## Context
In retirement, spending is funded from several pots (RRSP, investments that hold the
sale proceeds). Fixed withdrawals from each pot cause false shortfalls when one pot empties
before another. A top-up waterfall was considered. The user chose a simpler rule: spread
the money available at retirement evenly over the time the person has left to live.

## Decision
- A **DrawdownCashFlow** draws from one account, starting at a given period, until the
  horizon end (the estimated death).
- Its monthly amount is **fixed at its start**: balance of the account at the start ÷
  number of months remaining until the horizon end.
- Each pot gets its own drawdown. All pots are spread over the same remaining period, so
  they run out together, and there are no false shortfalls.
- Retirement income = guaranteed income (e.g. pension) + the sum of drawdowns. Goals
  test it with a PERIOD TagSum tally (ADR-0037).

## Alternatives considered
- A top-up rule (waterfall over ordered sources): more realistic but more complex. Kept
  as a possible later refinement.
- Recomputing the amount every month (balance ÷ remaining months): follows returns, but
  income varies month by month.

## Consequences
- Returns earned after the start are not part of the fixed amount, so a small balance
  remains at the end. That makes the estimate slightly conservative.
- The amount is nominal and fixed, so its real value falls with inflation. Goals in real
  dollars will show the decline over time.
- Withdrawals from tax-deferred pots are taxed as usual (ADR-0035).

## Amendment (2026-11-09): annuity at the expected return, recomputed yearly (C-P3)
The Consequences above were wrong: at 5% over 25 years the "small balance" left is about
1.43× the starting balance, and income was understated by about 40%. The user reopened
the decision and chose an annuity.
- The monthly amount is the **annuity payment** that brings the balance to zero at the
  horizon end, using the account's expected `returnRate` (monthly equivalent *r*) over
  the *n* months remaining: amount = B × r / (1 − (1 + r)^−n); if r = 0, B / n.
- It is **recomputed on each anniversary** of its start (ADR-0013 yearly step) from the
  actual balance and the months remaining, so returns that differ from expectation are
  spread over the remaining years. The amount is fixed within each year.
- Optional **`indexed`** flag: the stream rises with the scenario's inflation at each
  anniversary (a growing annuity), giving a flat real income. The first payment is lower.
  This is the one withdrawal method where indexing is allowed (C-M16 rejects indexing on
  percent withdrawals and fixed draws only).
- The final payment clears the remaining balance; nothing is left at the horizon end.
- Expected return for a TAXABLE account ignores the tax on its income yield (ADR-0054);
  the yearly recompute absorbs the difference.

### Consequences (replace the first bullet above)
- The pot is used up exactly at the horizon end, under the expected return.
- Unindexed: nominal income is flat within each year and changes only with returns;
  its real value still falls. Indexed: real income is about flat.

## Amendment (2026-11-11): two independent settings; `even` retired
The user split the drawdown into two independent settings on a withdrawal:
- **How much**: a given amount (`method: amount`, runs until the account is empty) or
  derived so the account is spent down by the end of the draw (`method: annuity`, the
  annuity of the amendment above).
- **Shape**: `indexing` (none | inflation | custom). With indexing the payment rises each
  anniversary to keep its purchasing power; without it the dollars stay level.
  Allowed on `amount` and `annuity`; still rejected on `percent` (C-M16).

Banking precedents: given + level = a systematic withdrawal plan (SWP); given + indexed =
the "4% rule" (Bengen 1994); derived + level = a term-certain annuity; derived + indexed =
an indexed term-certain annuity, recomputed yearly as in the "annually recalculated
virtual annuity" (Waring & Siegel 2015).

- **`even` is retired.** Older files with `method: even` are read as an unindexed
  `annuity` (the app converts them on load; the engine accepts `even` as an alias).
  Results change: `even` divided the balance by the months left and ignored returns.
- The `indexed` flag of the amendment above is the existing `indexing` field.
- Defaults taken from the proposal: the account's own `annualReturn`; recompute on each
  anniversary of the draw's first month; the first payment is set from the *current*
  balance in the first month with a balance (after same-month transfers), not the
  opening balance; ordinary (end-of-month) annuity, matching the engine's return on the
  opening balance.
- The final month withdraws the whole balance. That month's return is credited after it,
  so about one month's return stays in the account ("nothing left" becomes "about one
  month's return").
