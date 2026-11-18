# ADR-0009: Decimal representation of money

- **Status:** Accepted
- **Date:** 2026-11-04

## Context
Floating-point arithmetic introduces representation errors that accumulate over hundreds
of monthly periods.

## Decision
- Money is represented as a **decimal** type, never as binary floating point.
- **Standard accounting rounding rules** apply.

## Consequences
- The future implementation language needs a solid decimal type or library (an input to
  the language ADR).
- JSON serialisation must not convert money to floats; amounts are likely serialised as
  strings.

## Amendment (2026-11-04): rounding mode and precision
- Rounding mode: **half-even (banker's rounding)**.
- Money precision: **2 decimal places**.
- **Every money movement is rounded as it happens**: each interest accrual, payment, cost
  and transfer is rounded to 2 decimal places when it is computed in a period. Balances are
  therefore always exact sums of rounded movements, the way real account statements are.
- **Rates and percentages are not rounded**; they keep full decimal precision.
