# ADR-0045: Rates are fractions in JSON, percentages in the UI, and are range-checked

- **Status:** Accepted
- **Date:** 2026-11-07
- **Amends:** ADR-0040 (validation)

## Context
In the PoC a mortgage rate typed as `3.79` was read as 379% a year. Nothing failed: the
payment was almost all interest and the principal never fell. Saved files are meant to be
edited by hand (ADR-0008), so the same confusion would recur at every boundary.

## Decision
- In JSON (save files and interchange), every rate is a **fraction written as a string**,
  e.g. `"0.0379"`, like money values (ADR-0009).
- **User interfaces** accept and display rates as **percentages** (`3.79`). Converting
  between the two happens only in the UI.
- The engine **rejects implausible rates** with a readable message naming the field and
  the expected form:
  - interest, tax and selling-cost rates: 0 ≤ rate < 1;
  - appreciation, depreciation, indexing and inflation rates: −1 < rate < 1.
- Validation therefore has three outcomes: a missing essential field (error), an
  implausible value (error), or an omitted optional field (neutral default) (ADR-0040).

## Alternatives considered
- Percentages in JSON: readable, but every consumer must remember to divide by 100.
- Accept either and guess (a value above 1 is a percentage): ambiguous for small rates
  such as 0.5 (half a percent or 50%?).

## Consequences
- Old files with percentages fail loudly instead of running.
- Rates of 100% or more cannot be expressed. That is acceptable for this tool.
