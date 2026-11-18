# ADR-0037: Tallies per period, and goals with an active window

- **Status:** Accepted
- **Date:** 2026-11-05
- **Amends:** ADR-0027 (TagSum), ADR-0014 (goal evaluation)

## Context
"At least $3k monthly retirement income" needs the inflow *in the current period*, and
it should only be checked from retirement onward. A MAINTAIN goal evaluated from the start
of the horizon would be violated in the working years.

## Decision
- `TagSumTally` gains **`window : PERIOD | CUMULATIVE`**. PERIOD is the sum within the
  current period; CUMULATIVE is the running total from the start (the previous behaviour,
  and the default).
- Goals gain an optional **active window**: `activeFrom : Period [0..1]` and
  `activeUntil : Period [0..1]`. Outside the window the goal is not evaluated. REACH
  looks for the first period it is met inside the window; MAINTAIN must hold for the whole
  window.

## Consequences
- Example: MAINTAIN, TagSum(retirement-income, IN, PERIOD) ≥ $3k (real), activeFrom =
  the retirement date.
- Both new fields can be shifted with the shift tool (ADR-0007).
