# ADR-0007: Monthly time model on real dates with independent, shiftable events

- **Status:** Accepted
- **Date:** 2026-11-04

## Context
Mortgages, rent, salaries and contributions happen monthly. Strategies mostly differ in
*when* things happen, and the user needs to move them in time easily.

## Decision
- The engine steps in **monthly periods** on **real calendar dates**.
- Decisions and events (start of double mortgage payments, purchase, sale, lump-sum
  prepayment, retirement, ...) are **first-class, dated objects**.
- Every date is **independent and absolute**: there is no anchoring of one date to another.
- Shifting is handled by **tooling**: operations that shift one or several objects, possibly
  of different types, by an offset, followed by a recomputation of the projection.

## Alternatives considered
- Yearly periods: too coarse for mortgage amortisation and prepayment.
- Relative time ("month N"): makes tax years, ages and calendar events awkward.
- Anchored or relative dates with a dependency graph: rejected, because it adds complexity
  and the time-shift tooling covers the same need explicitly.

## Consequences
- Every dated object needs a common way to be shifted (e.g. a shared "time-shiftable"
  interface), which the shift tooling works with.
- Yearly concerns (tax year, annual limits) are handled as events at year boundaries inside
  the monthly stepping.
