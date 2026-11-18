# ADR-0035: Taxing tax-deferred withdrawals, and which account pays tax

- **Status:** Accepted
- **Date:** 2026-11-05
- **Amends:** ADR-0017 (single flat rate), ADR-0018 step 7

## Context
RRSP withdrawals are taxed, often in a lower bracket than working income. The tax step
deducted tax without naming the account that pays it.

## Decision
- A tax-deferred account may specify its own **`withdrawalTaxRate : RateGenerator [0..1]`**.
  If it is not set, the scenario's effective tax rate applies (ADR-0017).
- Withdrawal cash flows are **gross**: the stated amount leaves the account, and tax on it
  is charged separately in the tax step. The engine does not gross amounts up; if a net
  amount is wanted, the user enters the grossed-up figure.
- The scenario has **`taxPaidFrom : Account`**. Every tax computed in the tax step (and
  the capital gains tax on a sale) is debited from it, under the capping and shortfall
  rule (ADR-0015).

## Consequences
- ADR-0017's "one flat rate" becomes "one flat rate by default, overridable for each
  tax-deferred account".
- A shortfall on `taxPaidFrom` signals that the plan cannot afford its taxes.
