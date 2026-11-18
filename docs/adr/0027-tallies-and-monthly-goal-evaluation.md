# ADR-0027: Tallies, and goals evaluated every month by the stepping stage

- **Status:** Accepted
- **Date:** 2026-11-04
- **Refines:** ADR-0010 (goal observation moves into the monthly stepping stage),
  ADR-0014 (goal conditions are expressed over tallies)

## Context
The rent vs buy break-even goal needs running quantities that are not plain holding
balances, e.g. the owner's net gain and the cumulative rent paid. The user wants goals to
be evaluated **each month by the executor of the schedule**, attached to objects that
keep their own running tallies.

## Decision
- A **Tally** is a named running quantity that the monthly stepping stage updates once per
  period, after the period closes. Its value for each period is stored in that period's
  closed state.
- Kinds of tally (extensible):
  - **HoldingMetric**: VALUE, BALANCE, COST_BASIS, SHORTFALL of one holding (ADR-0014).
  - **NetWorth**: total, or liquidation-adjusted (see R3).
  - **TagSum**: cumulative movements carrying a tag, filtered by direction (e.g. all
    outflows tagged `housing:buy`).
  - **Derived**: a formula over other tallies, e.g.
    ownerNetGain = (VALUE(home) − BALANCE(mortgage)) − TagSum(housing:buy, outflows).
- A **Goal** is attached to one or more tallies and evaluates its condition **every month**,
  as the last step of the period (new step 9 after close in ADR-0018). REACH and MAINTAIN
  semantics are unchanged (ADR-0014).
- Global and local goals (ADR-0014) become special cases: a global goal is attached to a
  NetWorth tally, a local goal to a HoldingMetric tally.

## Consequences
- ADR-0010's post-stepping "goal observation" stage only collects goal outcomes into the
  result.
- Tallies "update their internal value" conceptually, but the value is part of each closed
  period's state, so stages stay pure (ADR-0010) and the state stays serialisable
  (ADR-0008).
- Tallies may only read the current closed period and earlier ones. Derived tallies are
  evaluated in dependency order, with no cycles.

## Resolved open points
- **Cross-scenario tallies**: scenarios are run in lockstep as a set, and goals may attach
  to tallies from any scenario in the set (ADR-0028).
- **Goals only observe**: a goal decides met or not met (or held or violated), and the
  engine reports the period. Goals never trigger actions. ADR-0006 stands; conditional or
  reactive events are out of scope.
