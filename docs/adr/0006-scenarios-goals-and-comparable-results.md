# ADR-0006: Scenarios, goals and comparable projection results as the core concepts

- **Status:** Accepted
- **Date:** 2026-11-04

## Context
This is a planning tool. The user builds several alternative strategies and compares their
outcomes to choose the best one. Rent vs buy is one example of such a comparison.

## Decision
- A **Scenario** is a named set of assets, liabilities, cash flows, assumptions (rate
  series) and dated events. Each scenario defines its own **horizon**.
- A scenario may define **Goals**, i.e. target conditions such as "accumulate $1M in
  retirement funds" or "reach $3k monthly pension income". Goals are evaluated against the
  projection.
- Running a scenario produces a **ProjectionResult** in a standard structure (timeline and
  metrics) that can be compared with others.
- **Scenario comparison** is a core capability. Specialised calculators such as rent vs buy
  are expressed as comparisons between scenarios, not as separate code paths.

## Alternatives considered
- Separate standalone calculators: rejected, because their logic would be duplicated and
  their results could not be compared.

## Consequences
- Results from scenarios with different horizons must still be comparable, which needs
  rules for aligning or truncating the timelines.
- Goal evaluation needs a design of its own: whether a goal was reached, when it was
  reached, and the shortfall if not.
- Comparing scenarios with different horizons is still open (see open-questions Q-04).

## Amendment (2026-11-04): goals are observed, not solved
- The engine **watches** goals during a projection and **reports when each goal is met**
  (the period/date it is first met). An unmet goal is reported as such.
- The engine does **not** search for inputs that would meet a goal. Solving or optimising
  for goals is the job of a possible separate *consumer* engine that calls this one
  repeatedly. That engine is **out of scope**.
- Consequence: goals act like observers on the projection timeline. The engine's API must
  stay cheap to call repeatedly and must not depend on hidden state, so a future optimiser
  can drive it.
