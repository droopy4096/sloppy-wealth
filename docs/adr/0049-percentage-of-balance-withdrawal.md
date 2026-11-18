# ADR-0049: Withdrawal as a percentage of the balance, reset yearly

- **Status:** Accepted
- **Date:** 2026-11-07
- **Relates to:** ADR-0039 (even drawdown), ADR-0035 (withdrawal tax), ADR-0013 (yearly
  step on the anniversary)

## Context
Funds (RRSP, TFSA, investments) could be drawn by a fixed amount or by an even drawdown
over the remaining horizon (ADR-0039). Planning also needs "withdraw X% a year", where the
income follows the fund's performance.

## Decision
- A new cash flow, **`PercentWithdrawal`**: `from : Account`, `start : Period`,
  `end : Period [0..1]`, `annualRate : RateGenerator`.
- On the start period and on **each anniversary** of it, the yearly amount is set to
  **balance at the opening of that period × annual rate**; it is paid as **1/12 each
  month** (ADR-0021) until the next anniversary.
- Amounts are **gross**; tax applies as for any withdrawal (ADR-0035). A month's payment is
  capped at the balance (ADR-0015).
- The yearly reset on the anniversary is the same cadence as indexing (ADR-0013
  amendment), so the model has one rhythm for yearly changes. RRIF minimum withdrawals
  follow the same pattern (rate × balance at the start of the year).

## Alternatives considered
- Recalculated every month: income changes every month.
- The classic "4% rule" (a fixed amount from the starting balance, indexed to inflation):
  can be added later as an option; not needed now.

## Consequences
- A percentage withdrawal never fully empties the fund; an even drawdown (ADR-0039) does.
- Retirement income tallies (ADR-0037) include these withdrawals by tag, like any other
  withdrawal.
