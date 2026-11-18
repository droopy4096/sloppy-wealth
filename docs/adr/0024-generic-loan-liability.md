# ADR-0024: A generic Loan liability, with Mortgage as a specialisation

- **Status:** Accepted
- **Date:** 2026-11-04

## Context
Vehicle purchases may be financed. Only `Mortgage` existed as a liability.

## Decision
- Hierarchy: `Liability` → `Loan` → `Mortgage`.
- `Loan`: amortising, an interest rate generator, amortisation in months, optional
  `securedBy` asset, prepayment options, early closure penalty rule. Default compounding
  MONTHLY.
- `Mortgage`: a loan secured by real estate, with a `TermScheduleRate` and SEMI_ANNUAL
  compounding by default (ADR-0019).
- Settlement on sale (ADR-0018 step 4) applies to **every loan secured by the sold asset**,
  not only mortgages.

## Consequences
- A car loan is a `Loan` with securedBy = the vehicle. Selling the vehicle settles the loan.
