# ADR-0067: Associated expenses and costs (items that live with a parent)

- **Status:** Proposed (design agreed 2026-11-13, Q-42; implemented on `poc/sm-triggers`,
  tag `sm-triggers-before-associated` marks the state before it)
- **Date:** 2026-11-13
- **Relates to:** ADR-0040 amendments (`attachedTo`), ADR-0065 (triggers, amendment
  2026-11-13), ADR-0062 (adjustments), domain model `Cost` / `FixedCost` / `VariableCost`

## Context
Costs that belong to another item are modelled in several ways: the vehicle's own
`annualMaintenance` / `maintenanceIncrease`, the sale's `sellingCostRate`, and (on
`poc/sm-triggers`) an expense tied to its asset or income by a pair of triggers ("With X"
/ "Ends with X", formerly `attachedTo`). None can be a share of the parent's value, and
one-off costs at a purchase (e.g. US closing costs) have no place. The owner asked for
two item types whose lifecycle depends entirely on a parent item and that can use the
parent's data.

## Decision
1. **Two item types:** an *associated expense* (recurring) and an *associated cost*
   (one-off). Each names its parent; its lifecycle comes entirely from the parent (an
   associated expense runs from the parent's start to its end; no triggers needed).
2. **Associated items replace the trigger pair** for "belongs to" ties: older
   `attachedTo` files convert to associated expenses. Triggers stay for "happens when"
   ties between otherwise unrelated items (e.g. Retirement -> end of a salary).
3. **Amount: a fixed sum or a percentage** of data **looked up from the parent**.
4. **What a percentage looks up (Q-42a): a small menu per parent type** (`basis`):
   property / vehicle: its current value or its purchase price (for a cost at its sale:
   the sale price); account: its balance; income: its amount; mortgage: its principal or
   its remaining balance. Live values (current value, balance) are the run's values.
5. **When an associated cost happens (Q-42b):** `at` the parent's start (e.g. closing
   costs on a purchase, a mortgage setup fee), its end (e.g. selling costs, a discharge
   fee), or on its own date while the parent exists (e.g. a planned repair); a dated cost
   is dropped if the parent does not exist by then.
6. **Parents (Q-42c): any item with a lifetime**: property, vehicle, account, mortgage,
   and the recurring items (income, expense, contribution, withdrawal, pension, extra
   payment). A fixed amount works with any of them; a percentage only where decision 4
   gives a basis.
7. **Indexing (Q-42d):** a fixed amount has the usual indexing (none / inflation /
   custom, yearly on its anniversary, ADR-0013); a percentage is not indexed: it follows
   the parent's value (growth, depreciation, market adjustments).
8. **Adjustments (Q-42e), as for flows (ADR-0062):** a fixed amount gets a new amount
   from a date (indexing restarts from it); a percentage gets a new rate from a date (as
   percent withdrawals), e.g. maintenance from 1% to 2% of the value at age 10.
9. **Migration (Q-42f): convert on load, remove the old fields** (as the at-retirement
   fields, ADR-0065): a vehicle's `annualMaintenance` + `maintenanceIncrease` become a
   fixed yearly associated expense with a custom index; a sale's `sellingCostRate`
   becomes an associated cost at the parent's end, a percentage of the sale price. Net
   worth is unchanged; ledger lines change kind and source, so the golden suite gets a
   reviewed regeneration.
10. **Booking (Q-42g): a plain cash outflow**, not tax-deductible and not added to the
    asset's value (closing costs lower net worth on the purchase, as selling costs do).
    Purchase and selling costs are the future cost basis (ACB) adjustments once capital
    gains are modelled (C-M8); nothing is recorded for that now.
11. **Value timing (Q-42h):** a percentage associated expense is a yearly rate: the
    yearly amount is the basis on the parent's start and on each anniversary x rate, paid
    1/12 monthly (as percent withdrawals, ADR-0049). An associated cost uses the basis in
    its month: the price at a purchase, the sale price at a sale, the value at the start
    of the month on its own date.

## Alternatives considered
- **Triggers for every tie** (ADR-0065 amendment): no percentage amounts; two items per
  tie. Kept for "happens when" ties only.
- **Built-in cost fields per item type** (status quo): one field per case, no
  adjustments, no closing costs.
- **Look up any parent field by name**: cannot reach live values (current value,
  balance); easy to choose nonsense.
- **Capitalized purchase costs**: closing costs into the asset's value or cost basis;
  deferred with capital gains (C-M8).

## Consequences
- Two new item types; `attachedTo`, a vehicle's `annualMaintenance` /
  `maintenanceIncrease` and a sale's `sellingCostRate` are converted on load and leave
  the forms. The golden suite's ledger lines change kind and source (reviewed
  regeneration); net worth is unchanged.
- The domain model's `Cost` / `FixedCost` / `VariableCost` become `AssociatedExpense` and
  `AssociatedCost` (diagram 02 v0.53).
- Implemented on `poc/sm-triggers` (2026-11-13): `flows/associated.py`, conversions in
  `upgrade.py`; rows, holdings and tax of all golden scenarios and the owner's files are
  unchanged (ledger relabelled). Not built: an associated cost at the end of a mortgage
  paid off by its schedule (only at its property's sale); `amount` basis for recurring
  parents other than income.

