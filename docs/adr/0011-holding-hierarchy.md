# ADR-0011: Accounts, assets and liabilities share a common Holding base

- **Status:** Accepted
- **Date:** 2026-11-04

## Context
Accounts (TFSA, RRSP, cash), assets (real estate, vehicles) and liabilities (mortgage)
all carry a value that changes each period through rates and movements. Net worth,
comparisons and goals all aggregate across them.

## Decision
- A common base concept, **Holding**, has specialised subtypes:
  - **Account**: holds money, has a tax treatment, and takes contributions, withdrawals
    and returns.
  - **Asset**: a non-cash value with appreciation or depreciation, plus fixed and variable
    costs.
  - **Liability**: a negative value, with interest, a payment schedule, prepayments and
    penalties.
- Net worth is the sum over all holdings.

## Alternatives considered
- Separate, unrelated types: every aggregation and every rate-application step would have
  to be duplicated for each type.

## Consequences
- The monthly stepping steps and goal observation can work on holdings in general and
  specialise only where needed.
- A goal such as "retirement funds ≥ $1M" needs a way to select holdings (by subtype,
  tax treatment or tag). Selectors are to be designed in the domain model.
