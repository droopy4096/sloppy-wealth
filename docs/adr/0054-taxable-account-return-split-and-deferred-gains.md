# ADR-0054: Taxable-account returns split into taxed income and deferred capital growth

- **Status:** Accepted
- **Date:** 2026-11-09
- **Relates to:** ADR-0017 (capital gains, flat rate), ADR-0004 (tax seam),
  ADR-0031 (liquidation net worth), ADR-0018 (order of steps), ADR-0048 (deductions);
  CRITIQUE.md C-P1
- **Amends:** ADR-0017 amendment ("income earned in taxable accounts")

## Context
Until now, the whole return of a TAXABLE (non-registered) account was taxed in full,
every month, at the flat rate. Property gains get the inclusion rate and are taxed only
at sale. The difference biases rent vs buy toward buying: $50k at 6% for 25 years at
30% ends at about $140k taxed monthly versus about $190k with deferral and 50% inclusion.

## Decision
- A TAXABLE account gains:
  - **`incomeYield`** (rate series, yearly; optional): the part of `returnRate` paid out as
    interest or dividends. Default: equal to `returnRate`, i.e. all income (today's
    behaviour, e.g. a GIC). Listed as an applied default (ADR-0040, ADR-0053).
  - **`openingCostBasis`** (Money; optional): default = opening balance.
- Each month the return on the opening balance splits into:
  - **income** = opening balance × monthly `incomeYield`: taxable in full at the flat
    rate in that month's tax step. It stays in the account (reinvested) and **adds to
    the cost basis**.
  - **growth** = total return − income: not taxed, no change to the cost basis. It may be
    negative.
- **Cost basis** (average cost): contributions and transfers in add their amount.
  A withdrawal or transfer out of amount *w* from balance *B* with basis *C*:
  - realised gain = *w* × (*B* − *C*) / *B*
  - basis falls by *w* × *C* / *B*
  - tax = max(0, realised gain) × inclusion rate × flat rate, in that month's tax step.
    A realised loss gives no credit (ADR-0017).
- Negative income (a negative `incomeYield`) is not allowed; range check per ADR-0045.
- **Liquidation net worth** (ADR-0031) also deducts the tax on the unrealised gain of
  every TAXABLE account: max(0, *B* − *C*) × inclusion rate × flat rate.
- HoldingSeries (ADR-0053) shows each TAXABLE account's cost basis.

## Alternatives considered
- A single "taxable share of return" factor: cheap, but still taxes monthly with no
  deferral, so it removes only part of the bias.
- Keep full monthly taxation and record the bias: rejected; rent vs buy is a core use.

## Consequences
- Rent vs buy compares deferred gains on both sides.
- TFSA and tax-deferred accounts are unchanged.
- Tax is booked when the gain is realised (month of withdrawal), not at the next filing,
  same simplification as ADR-0017.
- Unrealised gains on a TAXABLE account are visible only through liquidation net worth.
