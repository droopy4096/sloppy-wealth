# ADR-0058: Assets and loans that start before the horizon

- **Status:** Accepted
- **Date:** 2026-11-09
- **Relates to:** ADR-0025 (purchase), ADR-0029 (mortgage schedule), ADR-0043 (renewals),
  ADR-0057 (accounts before the horizon); CRITIQUE.md C-M5

## Context
Assets bought before the horizon were already supported in the PoC (grown from their
purchase date), but loans had to start inside the horizon. The only workaround, a new
mortgage at horizon start, booked a fake loan advance and overstated net worth by the
principal. A plan started from today makes every existing mortgage pre-horizon.

## Decision
- **Assets** bought before the horizon start enter at their value **grown from the
  purchase date** at their value rate (and any pre-horizon improvements or market
  adjustments). No cash is booked for the purchase. (Records existing PoC behaviour.)
- **Loans** that start before the horizon are **replayed**: the engine runs the schedule
  from the loan's own start, with its entered terms and renewals (ADR-0043), up to the
  horizon start, **without booking any cash** (no advance, no payments). The horizon
  starts with the replayed balance, rate, term and remaining amortisation.
- Optional **`balanceAtHorizonStart`**: overrides the replayed balance to match a
  statement (e.g. unentered prepayments). The scheduled payment is then recalculated
  from that balance over the remaining amortisation.
- Accounts are not replayed (ADR-0057): their opening value is the balance at horizon
  start.

## Consequences
- No fake advance; net worth at horizon start reflects the real debt.
- Lump-sum prepayments dated before the horizon are applied in the replay; without them
  the override is the way to match a statement.
