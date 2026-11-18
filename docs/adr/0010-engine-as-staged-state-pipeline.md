# ADR-0010: The engine is a pipeline of pure stages, with one monthly stepping stage

- **Status:** Accepted
- **Date:** 2026-11-04

## Context
The engine is stateless per invocation (ADR-0003), and state is exchanged as versioned JSON
(ADR-0008). The final projection is naturally built up in layers: first a calendar, then
events placed on it, then tallies, then account values, and so on.

Some quantities depend on each other from month to month: variable costs as a % of a value
that is itself being projected, mortgage interest on the previous balance, surplus cash
swept into accounts, and withdrawals that depend on balances and trigger tax. A strict
"one stage covers the whole timeline" layering cannot express these.

## Decision
- The engine is a **pipeline of stages**. Each stage receives the **entire state** and
  returns a **new, enriched state**. Stages are **pure**: they never modify their input.
- The pipeline has two levels:
  1. **Whole-timeline stages** that depend only on earlier layers:
     calendar (monthly periods from start to horizon), then event placement (dated events
     and recurring cash flows on the calendar).
  2. **One monthly stepping stage**: for each month in order, a fixed sequence of
     **steps** runs and reads the *closed* state of the previous month (e.g. apply rates,
     accrue interest, apply costs, settle cash flows, sweep or withdraw, apply tax,
     close the month). All feedback between months is contained here.
  3. **Whole-timeline stages after stepping**: goal observation (when each goal is first
     met), then assembling the result.
- The state at every stage boundary has the same serialisable shape as the exported
  state, so it can be **captured or injected at any boundary** (ADR-0008).

## Alternatives considered
- Strict layers with no feedback: too limiting (costs as a % of value, cash sweeps,
  withdrawals).
- Iterating stages to convergence: slow, hard to reason about, and harder to make
  reproducible.
- A single monolithic simulation loop: harder to inspect, test and inject into partway.

## Consequences
- Each stage can be tested in isolation, from a JSON fixture of the state before it to the
  state after it.
- Because stages are pure, intermediate states can be captured and replayed, and scenarios
  can share earlier stage outputs.
- Within the stepping stage, the **order of steps** inside a month is a design decision
  of its own (to be made with the domain model). It defines the accounting semantics, e.g.
  whether interest accrues before or after a payment.
- Immutability costs memory and copying (360+ periods per scenario). That is acceptable at
  this scale; the implementation may use structural sharing.
