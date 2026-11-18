# ADR-0056: ResidenceSwitchEvent moves the principal-residence designation

- **Status:** Accepted
- **Date:** 2026-11-09
- **Relates to:** ADR-0017 (capital gains, principal residence flag), ADR-0034 (sale),
  ADR-0007 (events), ADR-0018 (order of steps); CRITIQUE.md C-P13

## Context
The principal-residence flag was all-or-nothing per property. Owning two homes over
time (e.g. a first house, then a second one) needs the designation to move between them, and
Canada exempts only part of the gain when a property was designated for some years.

## Decision
- New event **`ResidenceSwitchEvent`** (date, `to : RealEstate`). From its month the
  target property is the principal residence and no other property is.
- `RealEstate.principalResidence` gives the **initial** designation, at purchase or
  horizon start. Switch events change it over time. At most one property is designated
  at any moment (validation error otherwise).
- The event's target must be owned at its date.
- **Designated years** of a property: calendar years in which it holds the designation
  on 31 December, plus the year of its sale if it holds the designation at the sale.
  Owned years: calendar years in which it is owned at any time.
- At sale, **exempt share** = min(1, (1 + designated years) ÷ owned years) (the CRA
  "+1" formula). Taxable gain = gain × (1 − exempt share) × inclusion rate (ADR-0017).
- The engine does not optimise the designation; the user places the switches.

## Alternatives considered
- A list of designated year ranges per property: same result, harder to keep exclusive.
- A user-entered exempt share: simpler, but the user computes the formula.

## Consequences
- A property never designated is fully taxable; one designated for its whole ownership
  is fully exempt, as before.
- The year-end rule plus "+1" covers the overlap year of a move.
- For a property bought before the horizon, owned years count from its purchase date;
  the initial flag is its designation for those years.
