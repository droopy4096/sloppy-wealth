# ADR-0038: "When does it become possible?" is answered by variant sweeps in authoring tooling

- **Status:** Accepted
- **Date:** 2026-11-05
- **Builds on:** ADR-0006 (no solving), ADR-0028 (scenario sets), ADR-0032 (composition)

## Context
Questions like "how many years until I can sell one property and retire?" ask for a date.
The engine only observes; it never solves (ADR-0006).

## Decision
- The **authoring tooling** offers a **variant sweep**. From a base scenario, a set of
  objects to move (by tag, ADR-0023) and a range of offsets (e.g. +0 to +20 years, step 1),
  it generates a **scenario set** with one variant per offset. The variants share the
  horizon and goals.
- The engine runs the set in lockstep (ADR-0028) and reports goal outcomes for each
  variant.
- The answer is the **earliest variant whose goals hold**. Picking it is done by the
  tooling or the view, not the engine.

## Consequences
- No change to the engine. The sweep reuses the shift tool's logic (ADR-0007).
- A sweep of a few dozen variants of a ~400-month horizon is cheap.
- A readiness tally (a quick single-run estimate) remains a possible later addition.
