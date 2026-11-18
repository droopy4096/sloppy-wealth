# ADR-0047: The early closure penalty is a manual amount

- **Status:** Accepted
- **Date:** 2026-11-07
- **Amends:** ADR-0024 (penalty rule on loans), ADR-0034 (sale settlement), ADR-0043
  (lender switch inside a term)

## Context
Breaking a mortgage inside its term (a sale, or a switch to another lender) costs a
penalty. Canadian lenders charge 3 months' interest, or for fixed rates the greater of that
and an interest rate differential whose method varies by lender and depends on future
rates. A formula would be either too crude or too speculative.

## Decision
- There is **no penalty formula**. The loan's `earlyClosurePenalty : PenaltyRule` is
  removed.
- The event that breaks a loan carries an optional **`penalty : Money`**, entered by hand
  (e.g. the lender's quote or an estimate):
  - `SaleEvent.penalty`: per secured loan settled by the sale (ADR-0034 step 3);
  - a `MortgageTerm` that starts a switch inside the current term:
    `MortgageTerm.penalty`;
  - `LumpSumPrepayment.penalty`: for a prepayment beyond the lender's privileges.
- The amount is **in dollars of the event date** (nominal on that date, as for cash flows,
  ADR-0013 amendment); it is not indexed.
- It is paid from the same account as the settlement (the sale proceeds, or the loan's
  `paymentFrom`) and recorded as its own movement. Omitted means 0 (ADR-0040).
- The engine does not check whether the event falls inside a term; entering a penalty is
  the user's statement that it does.

## Alternatives considered
- 3 months' interest by default: simple, but silently understates fixed-rate penalties.
- Interest rate differential with a comparison rate: needs lender-specific rules and a
  forecast of future rates.

## Consequences
- `termAt(period)` (ADR-0019) is no longer needed for penalties; it remains available.
- A scenario that breaks a mortgage without entering a penalty shows none.

## Amendment (2026-11-09): warning on an in-term closure with no penalty (C-P20)
- When a secured loan is closed **before its current term ends** (sale, early renewal or
  lender switch) and **no penalty is entered**, the result carries a warning: "<loan>
  closed <n> months before term end with no penalty entered".
- No amount and no default are added; the penalty stays manual.

## Amendment (2026-11-09): penalty source with outside lump sums (C-M12)
- A penalty is always paid from the loan's `paymentFrom`, even when the lump sum itself
  comes from outside (ADR-0044). Outside money only reduces the loan.

## Amendment 2026-11-18 (ADR-0073, Q-49 d)
A mortgage or renewal may now describe its penalty as a formula for its term
(`termMonths` and a method: flat amount, % of the interest left in the term, or N months'
interest). A real sale or lump-sum payoff uses it when its own manual penalty is blank;
a manual amount still wins. Files without a term are unchanged.
