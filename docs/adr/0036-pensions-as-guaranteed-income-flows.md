# ADR-0036: Guaranteed pensions are income cash flows; RRIF rules are not modelled

- **Status:** Accepted; amended by ADR-0052 (pension value in net worth, retirement date)
- **Date:** 2026-11-05

## Context
Retirement money comes either as a finite pot (RRSP) or as guaranteed income until death
(defined-benefit pension, CPP/OAS-like), usually indexed to inflation.

## Decision
- A **pension** is an income `CashFlow` from outside into an account. It starts at the
  pension start date, ends at the horizon end (the planned lifespan), is `InflationIndexed`
  (or `CustomRate` for partial indexing) and is flagged taxable (ADR-0020).
- A pension has **no holding and no value in net worth** (no commuted value). Retirement
  options are compared with income tallies (ADR-0037), not net worth.
- **RRSP to RRIF conversion and minimum withdrawals are not modelled.** The user is
  responsible for withdrawals large enough to meet the minimums.

## Consequences
- Net worth understates the wealth of someone who relies on a pension. This is a known
  limitation, and comparisons of retirement options should use income-based goals.
- Watch items: RRIF minimums (Q-13), pension commuted value (Q-14), annuity purchase
  (Q-15).
