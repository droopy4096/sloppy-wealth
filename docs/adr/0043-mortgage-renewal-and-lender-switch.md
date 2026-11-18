# ADR-0043: Mortgage renewal and switching lenders at a term boundary

- **Status:** Accepted
- **Date:** 2026-11-07
- **Amends:** ADR-0019 (MortgageTerm), ADR-0029 (payment recalculation)

## Context
A mortgage is renewed at the end of each term, usually at a new rate. At renewal the
borrower can also move the mortgage to another institution, which typically means a new
amortisation period as well as a new rate. Porting a mortgage to another property is
**not** needed (the sale closes the loan, ADR-0034).

## Decision
- A **renewal** is the start of a new `MortgageTerm` in the mortgage's `TermScheduleRate`
  (ADR-0019). A term has a start, a length and a rate.
- A term may also carry an optional **`amortizationMonths`**. When given, the remaining
  amortisation is **reset** to it at the term start. When omitted, the amortisation simply
  continues (remaining = original − months elapsed).
- **Switching to another institution** is modelled as a renewal whose term sets a new rate
  and a new amortisation. The lender's identity is not modelled; the mortgage stays the
  same holding with the same balance, so goals and tallies attached to it carry on.
- At each term start the engine **recalculates the scheduled payment** (ADR-0029) from the
  opening balance of that month, the new monthly rate and the remaining amortisation. The
  new rate applies to that month's interest.
- **Switching fees** (legal, appraisal, discharge) are optional one-off costs, modelled
  with a `OneOffTransfer` (ADR-0025) in the switch month. A switch at a term boundary has no
  early closure penalty. A switch **inside** a term is an early closure: the penalty rule
  applies (its formula is still to be defined).
- The final scheduled payment of the amortisation clears any rounding remainder.

## Alternatives considered
- Model a switch as closing the old mortgage and opening a new one (a new loan funding a
  lump-sum payoff): works with existing pieces, but splits one debt into two holdings, breaks
  goals attached to the mortgage, and makes the common case clumsy.
- Allow only a new rate at renewal: cannot express a lender switch with a new amortisation.

## Consequences
- `MortgageTerm` gains `amortizationMonths [0..1]` in the domain model.
- Increasing the balance at a switch (refinancing to take equity out) is not covered; it
  would still be a new loan. Revisit if needed.
- Prepayments made before a renewal lower the recalculated payment at that renewal, because
  the payment is derived from the balance then (consistent with ADR-0029).

## Amendment (2026-11-09): renewal may keep the payment (C-M7)
- `MortgageTerm` gains **`keepPayment : bool = false`**. When true, the scheduled payment
  before the renewal (excluding extra monthly prepayments) is kept; the new rate applies,
  and the remaining amortisation is **derived** from the balance, rate and payment. Time
  saved by prepayments is kept.
- `keepPayment` and `amortizationMonths` are mutually exclusive (validation error).
- If the kept payment does not cover the new rate's interest within the original
  remaining amortisation, the payment is recalculated as usual and the result warns.
- Default false keeps the behaviour above: prepayment savings become a lower payment.
