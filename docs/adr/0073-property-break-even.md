# ADR-0073: Property break-even and rent equivalent

- **Status:** Proposed (design agreed 2026-11-18, Q-49)
- **Date:** 2026-11-18
- **Relates to:** ADR-0024 / ADR-0047 (early-closure penalty), ADR-0031 / ADR-0034 (sale),
  ADR-0067 (associated expenses and costs), ADR-0053 (output model)

## Context
The owner wants a calculator per property: each month, what would a sale bring compared
with everything paid for the property so far? Two figures:
- **break-even**: net proceeds of a hypothetical sale that month (market value − selling
  costs − mortgage balance − early-closure penalty) minus the **net investment** (all
  paid for the property so far); positive = ahead;
- **rent equivalent**: (net investment − net proceeds) / months owned, the money "lost"
  per month, i.e. the rent that would have cost the same; it should turn negative
  over time.

## Decision
1. **Source (Q-49 a, owner 2026-11-18): from the run.** The figures are read from the
   run's ledger and holdings (what was actually paid for the property each month, its
   value and mortgage balance), with a hypothetical sale computed beside it every month;
   the run is not changed. A page like Run, not a builder card figure.
2. **Net investment (Q-49 b, owner 2026-11-18): two variants, shown as distinct
   columns** (with break-even and rent equivalent for each):
   - **ownership costs**: down payment (price − mortgage advance), closing costs
     (associated costs at the start), every mortgage payment, prepayment and lump sum,
     penalties, improvements, and the property's (and its mortgages') associated
     expenses, except those flagged as also paid when renting (e.g. utilities: a new
     associated-expense flag);
   - **all linked costs**: the same with every associated expense and cost, flagged or
     not.
   No forgone return on the down payment.
3. **Before the horizon (Q-49 c, owner 2026-11-18): start at the horizon.** For a
   property bought before the horizon start, the equity at the start (value − mortgage
   balance) is the initial investment and months owned count from the horizon start;
   the past is not estimated. (A property bought inside the horizon counts from its
   purchase, with its down payment and closing costs.)
4. **Early-closure penalty (Q-49 d, owner 2026-11-18): a formula, used by both.** A
   mortgage, and each renewal for its own term, may give `termMonths` (term length from
   its start) and a penalty method: a flat amount, a % of the interest left in the term
   (the schedule's interest from the month of sale to the term's end), or N months'
   interest (3 is common in Canada). After the term ends there is no penalty. The
   break-even's hypothetical sale uses it every month; a real sale (or lump-sum
   payoff) uses it when its own `salePenalty` / `penalty` is blank. Files without a
   term give the same results as before. This amends ADR-0047.
5. **Selling costs (Q-49 e, owner 2026-11-18): the property's associated costs at its
   end (ADR-0067)**, applied to each month's market value (a rate) or as they are (an
   amount). Nothing new to enter; the page notes when a property has none.
6. **Presentation (Q-49 f, owner 2026-11-18): a Break-even page** beside Run (per
   holding, ledger), with a property picker and a link from each property card. At the
   top, the month each variant first breaks even and the current figures; a line chart
   of break-even and rent equivalent (both variants) over the months; below, the
   monthly table: months owned, market value, selling costs, mortgage balance, penalty,
   net proceeds, then net investment, break-even and rent equivalent for each variant.

## Alternatives considered
- Estimated from the items like the builder cards: approximate (prepayments,
  adjustments, triggers).
- Both: more to build for little gain.
- Net investment with the forgone return on the down payment and extra costs: one more
  assumption (a rate); not now.
- Before the horizon: estimating the past from the items with an override field, or a
  manual figure only.
- Penalty formula for the break-even only (real sales keep ADR-0047's manual amount);
  or only the flat and remaining-interest methods.
- New property fields for selling costs: duplicates associated costs (ADR-0067).
- Presentation as a table only, or as columns on the Run page (too wide with several
  properties).

## Consequences
- New fields: `termMonths`, `penaltyMethod` with `penaltyAmount` / `penaltyRate` /
  `penaltyMonths` on mortgages and renewals;
  `alsoWhenRenting` on associated expenses. Diagram 02 v0.56; glossary: Break-even,
  Rent equivalent.
- A real sale's penalty changes only for files that give a term and no manual penalty.

## Implementation notes (2026-11-18, `poc/sm-break-even`)
- Field names: `penaltyMethod` `flat` / `interestLeft` / `monthsInterest` with
  `penaltyAmount` / `penaltyRate` (a fraction, % in the form) / `penaltyMonths` (rather
  than one `penaltyValue`, so the rate can be a percentage field).
- The penalty is computed by the loan (`Mortgage.penalty_at`, term in effect: its own or
  its latest renewal's); the run records it on the loan's holdings points
  (`closingPenalty`, only for loans with a term) for the break-even, and uses it for a
  sale or lump-sum payoff without a manual penalty. Renewals keep their manual
  `penalty` for breaking the previous term.
- `state_machine/break_even.py` reads the ledger and holdings; the page is
  `/run/break-even` (`web/break_even_draw.py` draws the chart; the rent-equivalent panel
  is scaled from the 12th month, as the first months' figures are huge by nature).
  Amounts are nominal.
- Owner's request 2026-11-18: the chart was not helpful and is dropped
  (`web/break_even_draw.py` removed); the page is the summary and the monthly table.
- Owner's choice 2026-11-18: short column titles, each with its formula as a tooltip:
  Month, Owned (mo), Value, Sale costs, Loan balance, Penalty, Net proceeds, then
  Invested, Gain and Rent eq. for "owner" costs and for "all" costs (the summary uses
  the same words).
- Owner's request 2026-11-18: one click from each property: a chart icon (purple) with
  the other icons on the property's card and on its row in both builder views.
