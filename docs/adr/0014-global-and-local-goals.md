# ADR-0014: Global and local goals

- **Status:** Accepted
- **Date:** 2026-11-04

## Context
Goals are observed during a projection, and the engine reports when they are met
(ADR-0006). Some goals concern the whole economic unit, while others concern a single
holding. They also differ in whether today's dollars or nominal dollars make sense.

## Decision
- **Global goal**: evaluated against the economic unit as a whole, based on net worth.
  Typically expressed in **real (today's) dollars**, e.g. "net worth ≥ $2M in today's
  dollars".
- **Local goal**: attached to one specific holding (an account, asset or liability). It
  states which condition that holding should reach. Typically **nominal**, e.g.
  "mortgage paid off", "interest paid off", or "house value exceeds the amount invested
  into the house".
- Every goal declares its value basis (nominal or real). The basis has a default per goal
  type: real for global goals, nominal for local goals.

## Consequences
- Local goals are **conditions over a holding's metrics**, not just a threshold on its
  balance. Holdings must expose metrics such as value, balance, cumulative amount invested
  and cumulative interest paid.
- Global goals need net worth in each period, in both nominal and real dollars.

## Amendment (2026-11-04): simplifications
- **The value basis is fixed by goal type**: global goals are always real, local goals are
  always nominal, and there is no override. This is the simplest option to implement;
  overrides can be added later if needed.
- Local conditions can **compare metric to metric** as well as metric to threshold.
  Example: "house value exceeds amount invested", where *amount invested* = purchase price +
  costs paid on the asset (the asset's cost basis, accumulated over time).
- The "interest paid off" example is dropped.

## Amendment (2026-11-04): goal kinds
- Every goal has a **kind**:
  - **REACH**: met the first time its condition becomes true. The engine reports the
    period it is first met, or "not met within horizon".
  - **MAINTAIN**: the condition must hold for the whole horizon. The engine reports the
    first period it is violated, or "held throughout".
- Example: "the retirement fund lasts until age 80" is a MAINTAIN goal, e.g. no shortfall
  on the bank account (see ADR-0015).

## Amendment (2026-11-05): basis of goals that are neither global nor local
- Goals on other tallies (TagSum, Derived; ADR-0027) are neither global nor local presets,
  so they **declare their basis explicitly** (NOMINAL or REAL). Global and local goals keep
  their fixed basis.
