# ADR-0041: Time shifts move the start, the end, or both

- **Status:** Accepted
- **Date:** 2026-11-05
- **Amends:** ADR-0007 (time-shift tooling), ADR-0038 (variant sweeps)

## Context
In a retirement sweep, the exit plan (sale, pension, drawdowns) moves as a whole, but the
working-life cash flows (income, contributions) only need their **end** moved to the new
retirement date.

## Decision
- Each selection in a shift (by tag or by object) has a mode: **START | END | BOTH**
  (default BOTH).
  - BOTH moves every date of the object (start, end, event date, segment boundaries).
  - START or END moves only that bound of objects that have a start and an end (cash
    flows, goal active windows). On events (a single date), START and END both mean the
    event date.
- A variant sweep combines selections, e.g. `exit` with BOTH and `work` with END.

## Consequences
- Shifting a start past its end, or an end before its start, is a validation error in
  the authoring tooling.
