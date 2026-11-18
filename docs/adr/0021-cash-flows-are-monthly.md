# ADR-0021: Cash flows are monthly; annual amounts are spread evenly

- **Status:** Accepted
- **Date:** 2026-11-04

## Context
Some costs are naturally annual (maintenance, insurance, property tax). We had to choose
between adding a frequency to cash flows and spreading annual amounts over the months.

## Decision
- Every cash flow is **monthly**. There is no frequency attribute.
- Annual amounts and annual percentage rates are spread evenly: monthly amount = annual / 12.
  Authoring tooling may accept annual input and convert it.

## Alternatives considered
- A frequency field (MONTHLY / ANNUAL plus a month of occurrence): more realistic cash
  timing, but more model and more stepping logic.

## Consequences
- Spreading is gentle on cash timing, so shortfalls caused by a lumpy annual bill are not
  visible. Real lump-sum items can still be entered as one-off events.
- Frequency can be added later as a new attribute with default MONTHLY, without breaking
  existing scenarios.

## Amendment (2026-11-07): amounts may be stated per month, quarter or year
- A cash flow states its amount **per month** (default), **per quarter** or **per year**
  (`per`). The stated figure is kept in the JSON, so files show contract figures such as
  $120,000 a year and stay easy to edit (ADR-0008).
- The engine still works monthly: a quarterly amount is applied as 1/3 and a yearly one
  as 1/12 **every month**, each monthly movement rounded (ADR-0009). Indexing applies to
  the stated figure.
- Quarterly and yearly amounts are **spread evenly**, not paid in one go. A "paid in one
  go" option (e.g. a bonus every March) can be added later if cash timing within a quarter
  or year matters.
- No other frequencies (weekly, bi-weekly) (ADR-0007).
- This replaces "there is no frequency attribute" above; conversion is no longer left to
  authoring tools.
