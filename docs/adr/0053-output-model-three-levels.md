# ADR-0053: The result has three levels: main table, per-holding detail, movement ledger

- **Status:** Accepted, provisional: to be reviewed once real results are inspected
- **Date:** 2026-11-08
- **Relates to:** ADR-0028 (scenario sets), ADR-0027 (tallies), ADR-0050 (columns),
  ADR-0040 (applied defaults); diagram `05-output-model.mmd`

## Context
The PoC showed only totals, so a user could not check whether a mortgage principal was
falling. Tag-based tallies and goals also need the individual money movements.

## Decision
- A run returns a **SetResult** with one **ScenarioResult** per scenario and the set-level
  goal results.
- Each ScenarioResult states the settings that shape its numbers (base date, inflation,
  income mode) and the **defaults applied** to omitted fields.
- It has three levels of detail:
  1. **PeriodRow**: the main table (ADR-0050) plus liquidation net worth; any metric can be
     shown in base-date dollars.
  2. **HoldingSeries**: per holding and month: opening, closing, cost basis; for loans,
     interest, principal paid and the current rate.
  3. **Movement** ledger: every money movement with kind, from, to, amount, source item and
     tags. Tag sums are computed from it, and any figure can be traced to it.
- Tally series, goal results (status and first met/violated period) and shortfalls
  (period, account, amount, cause) complete the result.

## Alternatives considered
- No ledger, tags summed directly into tallies: smaller, but numbers cannot be traced.

## Consequences
- The ledger is the bulk of the result (about 15–30 movements a month over 400+ months);
  views may request only the levels they need.
- To be reviewed after the PoC produces these levels.
