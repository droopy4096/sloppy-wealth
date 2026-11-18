# ADR-0019: Rates come from rate generators; each holding declares its compounding

- **Status:** Accepted
- **Date:** 2026-11-04
- **Refines:** ADR-0005 (the rate series is now one kind of rate generator)

## Context
Real rate histories are more complex than one series of dated segments. A mortgage might
run 2 years at one rate, renew for 5 years at another, then for 3 years at a third.
Canadian fixed-rate mortgages also compound semi-annually by law, whereas accounts usually
compound monthly or annually.

## Decision
- Every rate in the model is provided by a **RateGenerator**: a function from period to
  rate, `rateFor(period)`.
- Implementations include:
  - **ConstantRate**
  - **SegmentedRate**: dated segments, i.e. the original "rate series" of ADR-0005.
  - **TermScheduleRate**: an ordered sequence of terms, each with a start, a length in
    months and a rate. It models mortgage renewals (2y, then 5y, then 3y). It also
    exposes `termAt(period)`.
- New behaviours mean new implementations. A probabilistic generator is where
  Monte Carlo plugs in (the rate source seam of ADR-0005).
- Each holding declares its **compounding convention** (e.g. MONTHLY, SEMI_ANNUAL, ANNUAL).
  The engine converts the annual rate from the generator into a monthly rate using that
  convention. Mortgages default to SEMI_ANNUAL.

## Alternatives considered
- A single global conversion (r/12 everywhere): wrong for Canadian mortgages.
- Mortgage terms as a separate structure next to the rate: the term boundaries and rates
  would be duplicated.

## Consequences
- The mortgage's early closure penalty rule uses `termAt(period)` to tell whether a
  sale or payoff happens inside a term, and how much of the term remains.
- Generators are time-shiftable (ADR-0007): shifting one moves all its segments or terms.
