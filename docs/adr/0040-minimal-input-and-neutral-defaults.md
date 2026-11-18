# ADR-0040: The engine must work with minimal input, using neutral defaults

- **Status:** Accepted
- **Date:** 2026-11-05
- **Amends:** ADR-0016 (reference birth date becomes optional)

## Context
Not every scenario has to reflect everything. Many questions only need the important
points, e.g. "free income per year" instead of salary and detailed expenses. The model
has grown rich, but it must not demand all that detail.

## Decision
- **Every element is optional.** A scenario can contain only what matters to the question.
- When an element is present, only its **essential fields** are required (e.g. a mortgage
  needs balance, rate and amortisation). Every other field has a **neutral default** that
  contributes nothing: rates 0 (inflation, appreciation, returns, tax, selling cost), no
  costs, no indexing (FixedNominal), compounding by holding-type default, owned = true.
- **An implicit operating account** ("cash") exists in every scenario. Unless they are set
  explicitly, income lands there, and paymentFrom, paidFrom, proceedsTo and taxPaidFrom
  default to it.
- The **reference birth date is optional**. The horizon can be given in dates or as years
  from today; ages are only an authoring convenience (ADR-0016).
- Crude modelling is a first-class use: e.g. a single "monthly expenses" cash flow, or
  only "free income" (income minus expenses) instead of both.

## Consequences
- JSON schemas mark only essential fields as required; defaults are part of the schema
  (ADR-0008).
- Validation distinguishes "missing essential field" (an error) from "omitted optional
  detail" (the neutral default).
- Results should list which defaults were applied, so users can see what was assumed.

## Amendment (2026-11-05): the value rate of an asset is essential
- Every `Asset` (real estate, vehicle) **must** declare its value rate (appreciation or
  depreciation). 0 is allowed, but only when stated explicitly. An asset whose value
  silently stays flat would distort net worth and every comparison built on it.

## Amendment (2026-11-09): selling cost rate is essential for real estate (C-P11)
- Every `RealEstate` **must** declare `sellingCostRate` (ADR-0031). 0 is allowed, but only
  when stated explicitly. A silent 0 makes sales and liquidation net worth free and
  favours buying.
- **Carrying costs** (property tax, insurance, maintenance, condo fees) are **not part of
  the property entry**. They must be included in the living expenses (or their own
  expense cash flows) instead; otherwise owning looks cheaper than it is. Authoring
  screens and the schema description for RealEstate state this.
- No warning is raised for a property without attached costs (avoids prompting double
  counting).
