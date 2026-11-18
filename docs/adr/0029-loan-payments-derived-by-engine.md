# ADR-0029: The engine derives scheduled loan payments

- **Status:** Accepted
- **Date:** 2026-11-04

## Context
With term renewals at new rates (ADR-0019), a loan's scheduled payment changes over its
life. A hand-entered payment cash flow goes wrong after the first term.

## Decision
- A loan **derives its scheduled monthly payment** with the standard amortisation formula,
  from the outstanding balance, the monthly rate (per its compounding convention) and the
  remaining amortisation.
- The payment is **recalculated whenever the rate changes**: at each term start of a
  `TermScheduleRate`, and at each segment boundary of another rate generator. Each
  recalculation uses the remaining amortisation at that point.
- The loan has **`paymentFrom : Account`**. Its scheduled payment is a derived debit in the
  liability-payments priority group (ADR-0018 step 5).
- **Prepayments** (extra cash flows to the loan, lump sums) do not change the scheduled
  payment. They shorten the remaining amortisation, which is the usual Canadian practice.
- The last payment is capped at the outstanding balance.

## Consequences
- Scenarios no longer contain payment cash flows for loans. The two-houses walkthrough is
  updated accordingly.
- "Double payments from July 2027" is an extra cash flow to the loan, subject to its
  prepayment options.

## Amendment (2026-11-07): the final payment clears the balance
- The **last scheduled payment of the amortisation** is the exact amount still owed: the
  remaining balance plus that month's interest. It may be slightly more or less than the
  regular payment. This is how lenders settle the final instalment.
- Reason: every payment is rounded to the cent (ADR-0009), so a level payment leaves a
  small remainder (e.g. $0.39 on a $560,000, 25-year mortgage in the PoC). Without this
  rule the loan would run one extra month and loan goals would be reported late.
- The same rule applies at the end of a reset amortisation (ADR-0043). Prepayments that
  end the loan early are still capped at the amount owed.

## Amendment (2026-11-07): when the first payment falls
- By default the **first scheduled payment falls in the month after the advance**, which is
  the usual practice for monthly Canadian mortgages. Interest for that first month is
  charged in the first payment.
- A loan may give an optional **`firstPaymentDate`** to override this (e.g. a lender that
  sets the first payment two months out).
- The interest adjustment for an advance in the middle of a month is not modelled; the
  engine works in whole months (ADR-0007).
- Consequence: in the month of a financed purchase no loan payment is made. Comparisons
  (e.g. rent vs buy) show this in their first month.

## Amendment (2026-11-09): fixed-payment variable and interest-only loans not supported (C-P15)
- Decision: **not modelled for now.** Every loan recalculates its payment on a rate change
  to keep the amortisation (amortising only).
- Not expressible:
  - **Fixed-payment variable mortgage**: payment kept at rate changes, amortisation
    stretches, balance can grow past the trigger rate.
  - **Interest-only loan / HELOC**: interest paid, principal outstanding until repaid
    or sold.
- Reason: the user's mortgages are fixed-rate, renewed at fixed rates.
- Watch item: add a loan `paymentMode` (AMORTIZING default, FIXED_PAYMENT, INTEREST_ONLY)
  if a variable-rate mortgage or HELOC is planned.

## Amendment (2026-11-09): interest adjustment before a late first payment (C-M6)
- When `firstPaymentDate` is later than the month after the advance, the interest
  accrued from the advance until the month before the first payment is an **interest
  adjustment**: paid in cash from `paymentFrom` on the first payment date, booked as
  interest. It is not capitalised.
- The balance at the first payment is the principal; the scheduled payment is computed
  from it over the full amortisation, which **starts at the first payment**.
- Follows Canadian lender practice (interest adjustment date). Fixes the PoC balloon
  payment.

## Amendment (2026-11-09): prepayments shorten the amortisation until the next renewal (C-M7)
- The Decision's "They shorten the remaining amortisation" holds **until the next
  renewal**. At a renewal the remaining amortisation resets to original − elapsed
  (ADR-0043), so the saving returns as a lower payment, unless the renewal keeps the
  payment (ADR-0043 amendment 2026-11-09).
