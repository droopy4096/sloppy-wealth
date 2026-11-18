# ADR-0017: A simple capital gains rule on asset sales

- **Status:** Accepted
- **Date:** 2026-11-04

## Context
Selling an asset that has appreciated, such as a second property, is taxable in Canada,
and leaving that out overstates the proceeds. ADR-0004 covered only the tax treatment of
accounts.

## Decision
- The tax-rules interface (ADR-0004) gains a rule for **asset sales**:
  - capital gain = sale price − cost basis
  - taxable gain = capital gain × **inclusion rate** (from the jurisdiction's rules)
  - tax = taxable gain × the scenario's **effective tax rate** (an assumption, as a rate
    series)
- RealEstate has a **principal residence** flag. A sale of a principal residence is exempt.
- A capital loss produces no tax and no credit (simplification).

## Consequences
- Scenarios need an **effective tax rate** assumption. It is also the natural rate for
  other simple tax effects (taxable account income, RRSP withdrawals). See Q-09.
- Timing simplification: the tax is deducted **at the sale**, from the proceeds, instead
  of at the next tax filing.
- Only one property should be marked as principal residence at a time. This is a
  validation rule, not enforced by the engine.

## Amendment (2026-11-04): one flat rate
- A **single effective tax rate** (rate series) applies to *every* taxable effect in the
  simple tax model: taxable capital gains, income earned in taxable accounts, and
  withdrawals from tax-deferred accounts. There are no separate rates per effect.

## Amendment (2026-11-09): taxable-account income
- "Income earned in taxable accounts" now means the account's **income yield** only.
  Capital growth in a TAXABLE account is deferred and taxed at the inclusion rate when
  withdrawn (ADR-0054).

## Amendment (2026-11-09): per-sale tax rate (C-P6)
- `SaleEvent` gains an optional **`taxRate`**: the rate applied to that sale's taxable
  gain instead of the effective rate. Default: the scenario's effective rate. Same
  pattern as the per-account withdrawal rate (ADR-0035).
- Reason: a large one-off gain lands in the top brackets (about 53.5% in Ontario);
  the flat rate understates it.

## Amendment (2026-11-09): partial exemption by designated years (C-P13)
- The principal-residence flag is the initial designation only. The designation moves
  with `ResidenceSwitchEvent` (ADR-0056); a sale is exempt in the share
  (1 + designated years) ÷ owned years, capped at 1.
