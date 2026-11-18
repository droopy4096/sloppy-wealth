# ADR-0005: Deterministic projections with time-varying rate series

- **Status:** Accepted
- **Date:** 2026-11-04

## Context
Assumptions such as inflation, appreciation, investment return and variable cost
percentages drive every projection. Planning needs "what if the rate changes in 2028"
without necessarily needing statistical simulation.

## Decision
- Every assumption is supplied as a **rate series over time** (e.g. 4% until 2027-12, then
  2.5%), and a constant is just the simplest series.
- Projections are **deterministic**: the same scenario always gives the same result.
- Rates are obtained through a **rate-source seam**, so a probabilistic source
  (Monte Carlo) can be added later.

## Alternatives considered
- Constant rates only: too limited for planning.
- Probabilistic from the start: premature.

## Consequences
- The engine never reads a raw rate number; it always asks "what is the rate for period P".
- Monte Carlo later means running the same scenario many times with different rate sources
  and aggregating the results. The result model (ADR-0006) should allow aggregation later.
