# ADR-0055: OAS clawback, GIS and pension income splitting are not modelled

- **Status:** Accepted
- **Date:** 2026-11-09
- **Relates to:** ADR-0002 (one economic unit), ADR-0004 (tax seam), ADR-0017 (flat
  rate), ADR-0037 (retirement-income goals), ADR-0052 (pensions); CRITIQUE.md C-P9

## Context
These rules depend on each person's income, and the model has one household and one
flat rate. Without a record, the bias they cause stays invisible.

## Decision
- **OAS** is counted at its full amount, **before the recovery tax** (clawback: 15% of a
  person's net income above about $93k).
- **GIS** and other income-tested benefits are not modelled.
- **Pension income splitting** is not modelled. Its effect, if any, is assumed to be
  inside the user's chosen effective tax rate.
- A later per-person tax rule can add them behind the jurisdiction seam (ADR-0004).

## Consequences
- Retirement income and goals (ADR-0037) are **overstated** when a person's income
  exceeds the clawback threshold (large RRIF withdrawals, DB pension), and
  **understated** for low-income households that would receive GIS.
- The user should lower the OAS amount by hand when a clawback is expected.
