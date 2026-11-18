# ADR-0015: Debits are capped at available funds, and the unpaid part is a shortfall

- **Status:** Accepted
- **Date:** 2026-11-04

## Context
In a drawdown scenario (e.g. pension withdrawals in retirement), a cash flow can need more
than its source account holds. The engine has to define what happens then.

## Decision
- A debit from an account is **capped at the funds available** in that period. The
  account balance never goes below zero.
- The unpaid remainder is recorded as a **shortfall** on that cash flow for that period.
- Shortfalls are part of the projection result: per period, per cash flow and in total.
- The cumulative shortfall is a holding metric (SHORTFALL), so goals can use it, e.g. a
  MAINTAIN goal "bank account SHORTFALL = 0" (ADR-0014).

## Alternatives considered
- Letting the balance go negative and reporting when it is depleted: simpler, but it hides
  how badly the plan falls short.
- Funding the shortfall automatically from other accounts (a withdrawal waterfall):
  powerful, but it is a strategy decision. It is left out for now and could later be
  added as an explicit model element.

## Consequences
- The rule applies to every debit from an account, including liability payments. A
  shortfall on a mortgage payment means the plan cannot afford the mortgage. For now it
  is reported only; there is no modelling of default or arrears.
- When several debits compete for the same account in one month, the **order** in which
  they are paid decides which ones fall short. This feeds into Q-08 (order of steps within
  a month).
