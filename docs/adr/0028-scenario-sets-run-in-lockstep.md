# ADR-0028: Scenarios are run in lockstep as a scenario set

- **Status:** Accepted
- **Date:** 2026-11-04
- **Refines:** ADR-0003 (the unit of invocation), ADR-0006 (comparison), ADR-0010 (stepping)

## Context
Comparison goals such as the rent vs buy break-even need tallies from two scenarios
(owner's net gain from *buy*, rent spent from *rent*) in the same month. Duplicating rent
as a notional cash flow in the buy scenario was rejected.

## Decision
- The engine's unit of invocation is a **ScenarioSet**: one or more scenarios plus
  **set-level goals**. A single scenario is a set of one.
- Whole-timeline stages (calendar, event placement) run per scenario.
- The **monthly stepping stage steps every scenario in the set together**, period by period:
  1. for each scenario, steps 1–8 of ADR-0018 (each scenario on its own),
  2. update tallies for each scenario,
  3. evaluate scenario-level goals (own tallies), then **set-level goals** (tallies from any
     scenario, referenced as `scenarioId.tallyId`).
- **Isolation invariant**: scenarios never affect each other. No money, events or values
  cross scenario boundaries; only goals *read* across them.

## Alternatives considered
- A notional (tally-only) rent cash flow in the buy scenario: duplicates assumptions.
- Evaluating comparisons after each scenario has run on its own: cannot support goals that
  are evaluated monthly (ADR-0027).

## Consequences
- Lockstep needs a shared calendar: **all scenarios in a set share the same horizon**, and
  this is validated on input. This resolves Q-04: comparing scenarios with different
  horizons is not supported.
- A set is still stateless and self-contained (ADR-0003): set in, result for the set out.
- Comparison results and break-even periods are part of the set result.
- Scenarios in a set cannot run in parallel within one invocation. This is acceptable at
  this scale.

## Amendment (2026-11-07): inflation may differ between scenarios
- Scenarios in a set **may use different inflation rates**. The shared horizon does not
  extend to a shared inflation assumption.
- Any comparison view that shows real (today's-dollar) values **displays each scenario's
  inflation rate** next to its results, so the reader can see that the real figures are
  deflated differently. Nothing is normalised automatically.
- Found while testing the Python PoC, where each scenario carries its own `annualInflation`.

## Amendment (2026-11-09): real figures are per-scenario purchasing power (C-P17)
- Each scenario converts to real dollars at **its own inflation**, so its real figures
  are purchasing power in that scenario's world. Set-level real goals and comparisons
  rely on that meaning; there is no shared set deflator.
- Using a different inflation rate as a proxy for something else (e.g. a cost shock)
  changes the yardstick too; model such shocks with cash-flow indexing instead.
