# ADR-0002: Personal tool planning for a single economic unit

- **Status:** Accepted
- **Date:** 2026-11-04

## Context
We need to decide who the system serves, since that drives auth, tenancy and data ownership.

## Decision
- The system is a **personal planning tool**: no multi-user support, no tenancy, no auth.
- Calculations are done for a **single economic unit**: an individual or an entire family
  treated as one unit. All assets, liabilities, incomes and expenses belong to that unit.

## Alternatives considered
- Self-hosted distribution for others: not a goal now.
- Hosted multi-user product or advisor tool: out of scope.
- Modelling individual household members separately: rejected for now (see Consequences).

## Consequences
- The domain model needs no Person/Household hierarchy; the root is one economic unit.
- **Watch item:** some Canadian rules are per individual (TFSA/RRSP contribution room,
  pension income splitting). Under simple tax modelling (ADR-0004) this is acceptable; if
  modelling ever needs per-person rules, this ADR will need to be superseded.

## Amendment (2026-11-11): persons inside the economic unit (ADR-0061)
The watch item is triggered: a second earner needs per-person rules. This ADR is not
superseded. The household stays one economic unit for money: cash, assets, liabilities,
expenses and net worth are shared, and results stay household-level. Inside it, `person`
items own income, accounts, pensions, contribution room and a retirement date, and are
taxed separately (ADR-0061). A file without persons has one implicit person.
