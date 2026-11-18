# ADR-0016: A reference birth date, with ages as a way of entering dates

- **Status:** Accepted
- **Date:** 2026-11-04

## Context
Plans are naturally stated in ages ("retire at 60", "plan until 80"), while the engine works
on absolute dates (ADR-0007).

## Decision
- The economic unit has a **reference birth date**: the person whose age the plan is
  framed around.
- Ages are a way of **entering** dates. Authoring tooling converts "age 60" into an
  absolute period when the value is entered. The scenario stores only absolute dates.

## Alternatives considered
- Storing ages and resolving them in the engine: that brings back anchored dates, which
  ADR-0007 rejected.
- No ages at all: inconvenient for retirement planning.

## Consequences
- Changing the reference birth date does **not** move dates already entered. Time-shift
  tooling can move them if needed (ADR-0007).
- Views can still *display* ages next to periods, derived from the reference birth date.
- With a family as the economic unit, only one person's age frames the plan; consistent
  with ADR-0002.
