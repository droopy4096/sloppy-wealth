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

## Amendment (2026-11-11): an expense may be attached to an asset (carrying costs)
- An expense item may name the asset it belongs to: `attachedTo` (a property or a
  vehicle). It is paid only while that asset is owned: not before its purchase, and not
  from the month it is sold (any sale: on a date or at retirement), like a vehicle's
  maintenance. A blank startDate then means "from the purchase".
- This is the domain model's `Cost` (`attachedTo: Asset`, FixedCost) built as an expense
  item; carrying costs stay expense items, so the C-P11 rule above holds (not part of the
  property entry). Typical use: property tax, home insurance, condo fees, utilities.
- Property tax as a share of the property's value (a VariableCost on value) is not built;
  a fixed amount with indexing is used instead.

## Amendment (2026-11-11, later): an expense may be attached to an income
- `attachedTo` may also name an income item: the expense is paid only in the months that
  income runs (its start to its end, including "ends at retirement" of its owner), so it
  follows the income when its dates change. A blank startDate means the income's start.
- Typical use: costs that exist only with a job (group insurance premiums, union or
  professional dues, commuting). Treated as an ordinary expense: not tax-deductible.
- Not the same as `netOf` (ADR-0042, deferred), which grosses up an income stated net.
- On `poc/sm-triggers` (experiment), `attachedTo` is replaced by triggers (ADR-0065
  amendment 2026-11-13); older files are converted on load.
