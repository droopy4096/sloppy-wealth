# State-machine engine: interfaces (WP1–WP9, emitter model E0–E7)

> References to `engine.py` / "the reference" point to iteration 1 on branch
> poc/python-flask (tag poc-iteration-1).

> **The engine is an event-emitter model** (D-E1..D-E4): item factories build emitters
> (§4, §6), the `ScenarioRunner` walks them by order key every month (§5) and applies
> their events, logging each one (§10.7). §10 is the detailed contract. The pre-emitter
> clock handlers (`Handler`, `Event`, `Process`, `InitialEvent`, `Phase`) and their
> adapter were removed in E7 (§10.8).

Binding for every work package. Inputs: DECISIONS.md (D1–D5), FEASIBILITY.md (§2 phases,
§6 packages), OBJECTS.md (formulas, ledger kinds, hazards: **read the section of your WP
there before coding**). The reference is `webapp/engine.py`; `repr(run_detailed(s))` and
`validate` errors must be identical.

## 1. Ground rules

- Branch `poc/sm-wpN-<name>` from `poc/state-machine` (after WP0), one worktree per agent.
  Never touch `main` or `poc/python-flask`. Commit messages `sm-wpN: ...`; add files by
  explicit path; never add the owner's personal scenario files (see `.gitignore`), `diagrams/svg/`.
- **Edit only the files your WP owns (§2).** No edits to WP0 files: if the core lacks
  something, work around it locally (in your own module) and report it; WP9 reconciles.
  Wiring happens only through the registration decorators (§6), which are auto-discovered.
- The package never imports `webapp/engine.py` (D4). Only `tests/` and `tools/` may load it,
  as module `engine_ref`, through `tests/support.reference()` (or the same mechanism).
- Copy the reference arithmetic expression for expression. Use `arith.py`/`dates.py`;
  do not re-derive or rearrange a formula; never change the Decimal context.
- Raw JSON truthiness decides "given / not given" (`item.get(x)`), exactly as the
  reference does (OBJECTS conventions, §9.1).
- Internal imports are relative (`from ..arith import money`). Python 3.14, stdlib only.

## 2. File ownership

| WP | Owns (creates/edits only these) | Item types it registers |
|----|---------------------------------|-------------------------|
| WP0 core (done) | `__init__.py`, `arith.py`, `dates.py`, `base.py`, `ledger.py`, `household.py`, `clock.py`, `compiler.py`, `api.py`, `engine.py`, `holdings/cash.py`, all `*/__init__.py`, `run_reference_tests.py`, `tests/support.py`, `tests/test_core.py`, `INTERFACES.md` | – |
| WP1 validation | `validation.py`, `tests/test_wp1_validation.py` | – |
| WP2 harness | `tools/diff_engines.py`, `tools/record_scenarios.py` (recorder shim), `fixtures/` (synthetic kitchen-sink scenario, D5; recorded fixtures stay local/untracked unless synthetic), `tests/test_wp2_harness.py` | – |
| WP3 real assets | `holdings/real_estate.py`, `holdings/vehicle.py`, `events/purchase.py`, `events/improvement.py`, `events/adjustment.py`, `events/sale.py`, `rules/capital_gains.py`, `tests/test_wp3_real_assets.py` | `property`, `vehicle`, `improvement`, `marketAdjustment`, `sale` |
| WP4 debt | `holdings/mortgage.py`, `events/loan.py` (LoanAdvance, Renewal, LumpSum, ExtraPayment, service process), `tests/test_wp4_debt.py` | `mortgage`, `renewal`, `extraPayment`, `lumpSum` |
| WP5 investments | `holdings/account.py`, `events/transfer.py`, `flows/contribution.py`, `flows/withdrawal.py`, `rules/investment.py`, `tests/test_wp5_investments.py` | `account`, `transfer`, `contribution`, `withdrawal` |
| WP6 pensions | `holdings/pension.py`, `tests/test_wp6_pensions.py` | `pension` |
| WP7 flows & rules | `flows/income_expense.py`, `rules/tax.py`, `rules/indexing.py` (optional IndexingRule object over `arith.indexed`/`indexing_rate`), `events/retirement.py`, `tests/test_wp7_flows_tax.py` | `income`, `expense`, `retirement` |
| WP8 results | `results.py`, `tests/test_wp8_results.py` | – (a scenario setup hook) |
| WP9 integration | anything; reconciles WP gaps, runs parity | – |

FEASIBILITY §6 had `events/acquire.py` shared by WP3/4/5; it is split per WP above.
`rules/compounding.py` and `rules/income_mode.py` are not needed: compounding is
`arith.power`/`arith.monthly_rate`, the income mode is `household.covered` /
`household.recurring_source`.

## 3. Household API (`household.py`)

Built by the compiler from the raw scenario; one per run.

Scenario settings (verbatim `Simulation.__init__`, read-only for WPs):

| attribute | value |
|---|---|
| `scenario` | raw dict |
| `start`, `end` | horizon month indexes (inclusive) |
| `inflation` | `Decimal(str(annualInflation or "0"))` |
| `tax_rate`, `retirement_tax_rate` | as reference (number `0` retirementTaxRate = no switch) |
| `retirement` | retirement month index or None (**look-ahead**, D2) |
| `retirement_date` | `'YYYY-MM-DD'` or `''` |
| `base` | `base_month(scenario)` |
| `covered` | `incomeMode == "expensesCovered"` |

Runtime state:

| attribute / method | meaning |
|---|---|
| `retired` | False until the RetirementEvent (WP7) sets it True |
| `current_tax_rate` | `retirement_tax_rate if retired else tax_rate` |
| `recurring_source` | `None if covered else "cash"` (source of LOAN_PAYMENT, INTEREST_ADJUSTMENT, recurring PREPAYMENT, CONTRIBUTION) |
| `month` | current month index (None during INITIAL) |
| `ledger` | `Ledger`; `ledger.entries` is the reference `ledger` list |
| `tax` | `TaxAccumulator` (§7) |
| `opened` | list, frozen in OPEN: non-cash aggregates existing at the start of the month, holdings order |
| `opening` | `{id: balance}` of `opened` (growth base, percent-withdrawal base) |
| `points_opening` | `{id: balance}` of every aggregate incl. cash at the start of the month (results `opening`; missing id = created this month → `None`) |
| `ext` | dict for per-WP private state, key = your module name. Prefer state on your own handler/aggregate objects. |

Aggregates (D1: events create them; stored and iterated by slot = item index):

| method | semantics |
|---|---|
| `add(aggregate)` | add a newly created aggregate (its `item_index` = your `ctx.ordinal`). Same id again → replaces the object, keeps the slot. |
| `get(id)` | aggregate or **None if not created yet** (reference: `balance is None`) |
| `hh[id]`, `id in hh` | KeyError if missing / membership |
| `cash` | the Cash aggregate |
| `aggregates(*kinds)` | existing aggregates in holdings order (cash first), optionally filtered by kind |
| `opened_aggregates(*kinds)`, `is_opened(id)` | the frozen `opened` list / membership |
| `loans_secured_by(asset_id)` | existing liabilities with `secured_by == asset_id`, holdings order (caller applies `and loan.balance`) |
| `move(kind, src, dst, amount, source=None)` | **the only way to change a balance.** `amount = money(amount)`; if it is 0, nothing is recorded and `Decimal('0.00')` is returned; else `src` balance −amount, `dst` +amount (a liability's sign flipped in `Aggregate._apply`), ledger entry `{month, kind, from, to, amount, source}` appended; returns the rounded amount. `src`/`dst` are ids or None (outside). Negative amounts are recorded. |
| `begin_month(m)` | core OPEN step (called by the runner only) |

## 4. Base classes (`base.py`) and the emitter model (`emitters.py`)

```python
class Aggregate:                      # a holding
    kind: str                         # class attr: cash|property|vehicle|mortgage|account|pension
    secured_by = None                 # Mortgage: id of the securing asset or None
    def __init__(self, id, name, item_index, balance)   # balance a Decimal, never None
    liability -> bool                 # kind in LIABILITIES
    group -> str                      # GROUPS[kind]
    report_rate -> Decimal | None     # the points' "rate" (override!)
    def accept_contribution(self, household, amount, source, match)   # account, pension
class Rule:                           # marker base for calculators (TaxRule, ...)
```

Constants: `HOLDING_TYPES`, `LIABILITIES = ("mortgage",)`, `GROUPS`.

Holding attributes other modules rely on: `id`, `name` (`item.name or id`), `kind`,
`balance`, `item_index`, `report_rate`; Mortgage `secured_by`; Property/Vehicle `sold`
(bool); Account `account_type` (`"tfsa"|"rrsp"|"nonRegistered"`) and
`withdrawal_tax_rate` (Decimal or None).

Everything that happens to the household over time is an **emitter** (one form input →
1..n emitters, built by the item's factory, §6) that emits **events** (one change of the
household each; `apply` mutates through `household.move` and may return follow-up
events). Types and rules: §10.1; follow-ups §10.5; amounts resolved at apply time §10.6;
the event log §10.7. Aggregates are created by events (D1), never by factories.

| Emitter class | Schedule | Used for |
|---|---|---|
| `InitialEmitter` | `Initial()`, order < 0 | carry-in property/vehicle, account at start, pension creation |
| `OneShotEmitter` | `Once(month)` | purchase, loan advance, account opening, transfer |
| `RecurringEmitter` | `Window(first, last)` (or any Schedule) | income, expense, contribution, withdrawal, loan service, growth, maintenance, pension payment/revaluation |
| `ModifierEmitter` | any | renewal, extraPayment, lumpSum (mortgage); sale, improvement, marketAdjustment (asset), §10.4 |
| `ScenarioEmitter` | any | retirement, tax step, results recorder (ordinal SCENARIO) |

| Event class (`KIND`) | Events in the engine |
|---|---|
| `LifecycleEvent` (`lifecycle`) | Purchase, CarryIn, LoanAdvance, AccountOpening, AccountAtStart, PensionCreated, Sale, LoanPayoff |
| `FlowEvent` (`flow`) | Income, Expense, ScheduledPayment, InterestAdjustment, ExtraPrepayment, LumpSumPrepayment, RenewalPenalty, LumpSumPenalty, SalePenalty, Improvement, Transfer, Contribution, Withdrawal, Maintenance, PensionPaid |
| `ValuationEvent` (`valuation`) | Appreciation, AccountReturn, LoanInterest, AccrueInterest, Revaluation, MarketAdjustment, PensionRevalued |
| `StateEvent` (`state`) | Retirement, Renew, TaxStepEvent |

## 5. Order key and the month loop (`clock.py`, `runner.py`)

`ScenarioRunner` (`runner.py`) holds every registered emitter. `run(household)`:

1. **INITIAL step**: every emitter with a negative order, in key order, asked
   `due(None)` / `emit(None, household)` (`household.month` is None; no movements).
2. **Each month** `m` of the horizon: `household.begin_month(m)` (core OPEN step: month,
   tax reset, opened/opening snapshots), then every emitter with order ≥ 0 whose
   `due(m)` is true, sorted by the **order key `(order, ordinal, sub)`**. Each event is
   applied as soon as it is produced, its follow-ups depth-first (§10.5), and logged.

- `order`: a `clock.Order` number (table in §10.2) or any int between two of them
  (`Order.SERVICE_DEBT + 50`). The numbers are `ORDER_STEP` (100) apart and reproduce the
  reference's intra-month step order.
- `ordinal` = `ctx.ordinal`, assigned by the compiler: the item index; for a holding item
  the **slot** (index of the first holding item with that id); for a modifier at its
  host, the host's slot (§10.4). Scenario-level emitters (setup hooks) get `SCENARIO = -1`.
- `sub` disambiguates two emitters at one `(order, ordinal)` (class `SUB`, instance
  `sub=`, or `sub_order(stage, index)` for modifiers).
- A duplicate key raises ValueError at registration; registering anything that is not
  an `emitters.Emitter` raises TypeError. `runner.schedule()` lists the keys,
  `runner.steps()` groups emitters by order number.

Contribution room (ADR-0060) runs at order OPEN+50 (after the retirement event, before
income) at its item's ordinal: sub 0 RoomStartEmitter, sub 1 RoomYearEmitter.

Cash balance (ADR-0063) runs at order TAX+50 (after the tax step, before CLOSE) at its
item's ordinal; cash flow adjustments (ADR-0062) log at OPEN+60.

Scenario-level subs: OPEN/-1/n RetirementEmitter of the n-th person (ADR-0061; 0 with
one person); TAX/-1/0 TaxEmitter (one step for every person); CLOSE/-1/0 results
Recorder. Pick a free sub for any new scenario-level emitter.

## 6. Compiler (`compiler.py`): registration

```python
from ..compiler import item_type, scenario_setup

@item_type("vehicle")                      # exactly one factory per type (else ValueError)
def compile_vehicle(item, ctx):            # returns/yields Emitters; may return None
    yield from compile_real_asset(Vehicle, item, ctx)
    yield MaintenanceEmitter(ctx.id)

@scenario_setup("results", order=90)       # runs before item factories, (order, name) order
def setup_results(env):                    # yields Emitters, registered with ordinal SCENARIO
    yield Recorder()
```

Every module in `holdings/`, `flows/`, `events/`, `rules/` and `results.py` is imported
by `discover()` before the first compile; just create your file. The compiler sets each
emitter's `ordinal` (`ctx.ordinal`, or the host's slot for a modifier), `index`
(`ctx.index`; None for setup hooks) and `source` (`ctx.id` unless the emitter set one).
After every factory has run it calls `emitter.prepare(env)` for all emitters in key
order (cross-item facts, §10.3).

`ItemContext ctx`: `item` (raw dict), `index`, `id` (`item.get("id") or f"item{n}"`),
`ordinal` (use as the aggregate's `item_index`), `name` (`item.name or id`),
`household`, `env` (CompileContext).
`CompileContext env`: `scenario`, `items`, `household`, `runner`, `start`, `end`,
`retirement` (month or None), `retirement_date`, `properties` (`{id: property item}`, last
wins, for `mortgage_start`), `sales` (`property_sales(items, retirement_date)`), `slot`,
`owner`, `emitters_for(item_id)`, `modifiers_of(host, cls=None)` (valid in `prepare`),
and `bucket(name, key) -> list` (shared list between factories; no production module
needs it any more).

Compile rules:
- Factories run in item order; holding types (`HOLDING_TYPES`) are compiled only for the
  **last** item with a given id, at the **first** item's slot (reference dict semantics).
- Factories never move money and never add aggregates (D1: events create them, at
  INITIAL or later). Read-only use of `household` settings is fine.
- Resolve retirement anchors at compile time from `env.retirement` exactly as `prepare()`
  does (`startsAtRetirement`, `endsAtRetirement` → `last = min(last, retirement-1)`, blank
  start of pension/withdrawal, `atRetirement` of sale/lumpSum/transfer). `household.retired`
  is for the tax rate only.
- The `retirement` item type yields nothing: the setup hook `wp7.retirement_tax` yields one
  RetirementEmitter per person with a retirement, and the TaxEmitter.
- Older input forms (scenario `retirementDate`, a property's own `saleDate`, withdrawal
  method `even`, `monthlyAmount`) are converted by `upgrade.upgrade(scenario)`, called at the
  start of `validate` and `compile_scenario`; the rest of the engine knows only the current
  forms. A converted `retirementDate` outside the horizon is an event with
  `outsideHorizon: true`.
- `compile_scenario(scenario) -> (household, runner)`; it does not validate.
- Tests: `with compiler.isolated_registry(): ...` gives an empty registry (restored after).

## 7. Tax state (`household.tax_of(person)`, one `TaxAccumulator` per person, ADR-0061) — used by WP5, WP6, WP7

| member | use |
|---|---|
| `add_taxable(amount)` | taxable income; pass the **rounded amount returned by `move`** (income gross, pension payment, rrsp withdrawal without own rate, nonRegistered `max(Decimal(0), ret)`) |
| `add_deduction(amount)` | rrsp contribution / transfer and pension contribution, only when not covered |
| `add_own_rate_tax(amount)` | rrsp withdrawal with own rate: `amt * withdrawal_tax_rate`, **unrounded** |
| `taxable`, `deductions`, `extra_tax` | month sums, `Decimal(0)` after OPEN reset |
| `pool` | carried-forward deductions; only TaxRule reads/writes it |
| `detail` | `{month_label: {...}}` written by TaxRule (keys and order: OBJECTS §4.9), read by WP8 |

Each flow adds to its owner's accumulator: `household.tax_of(owner)` (income and pension
owner, account owner; RRSP deductions to the account's contributor; `None` = the first
person). TaxRule (WP7) runs §4.9 verbatim once per person, with `rate =
person.current_tax_rate` and `retired = person.retired`, and
`household.move("TAX", "cash", None, due + money(extra_tax), source)` (source `None` with
one person, else the person id).
WP7 hazard: an older file's `retirementDate` may lie **before** the horizon start (its
event is marked `outsideHorizon`); the reference then treats every month as retired. The
RetirementEvent must give `retired == (retirement is not None and month >= retirement)`
in every month (e.g. fire at `max(retirement, start)`).

## 8. Results (WP8)

- `results.assemble(household) -> {"rows", "holdings", "ledger", "tax"}`, called by
  `api.run_detailed` after `clock.run`. `ledger` is `household.ledger.entries`; `tax` is
  `household.tax_detail` (the person's detail with one person, else sums + `persons`).
- WP8 registers `@scenario_setup("results", order=90)` yielding a CLOSE Process (sub 0)
  that each month appends the row (`cash`, totals by kind over `household.aggregates()`
  as in `Simulation.row`) and, for every existing aggregate, a point
  `{"month", "opening": household.points_opening.get(id), "closing": balance, "rate": report_rate}`;
  state in `household.ext["results"]`.
- Holdings list: one entry per aggregate in `household.aggregates()` order at the end
  (every holding item is created within the horizon after validation), fields `id`,
  `name`, `kind`, `group`, `points`; loans get `interest`, `paid`, `principalPaid` from
  the ledger scan (defaults `Decimal(0)`, not `0.00`). Then `add_real_net_worth` (port it
  into results.py).

## 9. Testing

Commands (from `webapp/`):

```
.venv/bin/python -m unittest discover -s state_machine/tests -t .     # all WP unit tests + golden
.venv/bin/python -m unittest -q test_engine                          # the 151 iteration-1 tests
```

**Parity, now frozen.** During WP0–E7 the reference (`webapp/engine.py`) was on this
branch: `run_reference_tests.py` ran the unchanged `webapp/test_engine.py` on the facade,
WP2's `tools/diff_engines.py` compared `repr(run_detailed(s))` and validate outcomes of
both engines, and the WP tests compared with `tests/support.reference()`. With iteration 1
removed, `test_engine.py` imports `state_machine.engine` directly, and every comparison
is frozen as golden data recorded while both engines agreed: `tests/test_golden.py`
(239 scenarios in `tests/golden/scenarios.json`, hashes in `golden.json`) and
`support.assert_golden` (the WP tests' intermediate values, `golden/values.json`).
`tools/update_golden.py` regenerates them after an intended change (§10.9).

**Per-WP unit tests** (`tests/test_wpN_*.py`). Helpers in `tests/support.py`:
`scenario(items, ...)`, `sample(name)`, `without_tax(ledger)`, `balances(hh)`,
`assert_golden(test, label, value)`; `api.simulate(s)` compiles and runs the engine
without validation/results. Golden values hash `repr` (exponents matter). The table
below is the original brief ("equal to the reference" is now "equal to the golden value"):
stand in for item types of other WPs with small fake aggregates/emitters in the test.

| WP | Must test |
|----|-----------|
| WP1 | identical outcome (exception type + message, or None) to the reference `validate` for every reference test scenario (`tests/support` + samples) and a mutation table covering each check in OBJECTS §8 incl. the KeyError cases |
| WP2 | (harness removed with iteration 1; replaced by `test_golden.py`) |
| WP3 | ledger (without TAX) and balances equal to the reference for: purchase in horizon with/without marketValue; pre-horizon property/vehicle; improvement then percent adjustment same month; newValue adjustment (no growth that month); sale with salePrice, selling cost, penalty, legacy saleDate, sale at retirement; vehicle maintenance incl. covered mode; sale paying off a (fake) secured loan |
| WP4 | ledger/balances equal to reference for: advance month (no service), regular amortisation to zero (last payment clears), firstPaymentDate accrual + INTEREST_ADJUSTMENT (covered and not), renewal with/without amortizationYears and penalty, renewal during accrual, extra payments (endsAtRetirement), lump sum amount/payOff/outside/penalty-even-when-zero, extras dropped while accruing, mortgage listed before its property |
| WP5 | account at start / opened later from cash or outside / zero balance; transfer (rrsp deduction, covered); contribution with match, rrsp deduction, covered; withdrawal amount/percent/even incl. opening-month fallback, latch, cap at balance; rrsp own-rate vs taxable; nonRegistered return taxable (tax state asserted, TAX lines excluded) |
| WP6 | pension value at start-1 and revaluation (negative allowed), payment indexing from base date, blank start = retirement, endsAtRetirement, taxable flag, `accept_contribution` (covered and not) |
| WP7 | income/expense indexing, quarter/year divisors, amountIn base, starts/endsAtRetirement, covered mode; TaxRule detail and TAX line equal to reference incl. pool carry-forward and retirement rate switch (also legacy retirementDate before start) |
| WP8 | rows/holdings/ledger/tax shapes and reprs equal to the reference for a cash-only scenario and for hand-built households with fake aggregates and ledgers (loan interest/paid sums, `Decimal('0')` defaults, opening None in creation month, real net worth with dollarsOf) |
| WP9 | `test_engine.py` all green; `test_golden.py` clean on samples, fixtures and the test-suite scenarios |

## 10. Event-emitter contract (E0 core, E1–E6 conversions, E7 cleanup)

Decisions: DECISIONS.md D-E1..D-E4. Conceptual model: `diagrams/06-event-emitter-conceptual.mmd`.
Core modules (E0 owns them; ask the coordinator for changes): `clock.py` (order table),
`emitters.py` (Schedule, Event, Emitter, categories, EventLog), `runner.py`
(ScenarioRunner), `compiler.py`, `household.py`, `api.py`.

### 10.1 Types

```python
# emitters.py
class Schedule: due(month) -> bool          # month None = the INITIAL step
Initial()            # due only in the INITIAL step
Once(month)          # one month (None = never)
Window(first=None, last=None)               # first <= m <= last; EVERY_MONTH = Window()
Anniversary(first, every=12, last=None)     # every `every` months from `first`
Never()              # NEVER, INITIAL, EVERY_MONTH are ready-made instances

class Event(ABC):                           # one change of the household
    KIND = "event"                          # subclasses: LifecycleEvent "lifecycle",
                                            # FlowEvent "flow", ValuationEvent "valuation",
                                            # StateEvent "state"
    key = None; source = None               # filled by the runner (emitter's / parent's)
    def apply(self, household) -> list[Event] | None   # mutate; return follow-ups (D-E3)
    name -> class name; describe() -> str   # compact text for the log (override freely)

class Emitter(ABC):                         # one form input -> 1..n emitters
    ORDER = None                            # REQUIRED: clock.Order number or any int
    SUB = 0
    def __init__(self, schedule=None, *, order=None, sub=None, source=None)
    order, sub, schedule, source            # instance values (order/sub override class)
    ordinal, index                          # set at registration: never set them
    key -> (order, ordinal, sub)
    due(month) -> schedule.due(month)       # override for state-free extra conditions
    emit(month, household) -> iterable[Event] | None   # may READ state, never write it
    prepare(env)                            # after all factories ran (cross-item facts)

OneShotEmitter(month, **kw)                 # Once(month); .month
InitialEmitter(**kw)                        # Initial(); ORDER must be negative (Order.INITIAL)
RecurringEmitter(first=None, last=None, schedule=None, **kw)    # Window(first, last)
ModifierEmitter(host, schedule=None, *, stage=None, **kw)       # D-E1, §10.4
ScenarioEmitter(schedule=None, **kw)        # scenario level (setup hooks), ordinal SCENARIO
sub_order(stage, index=0) = stage * SUB_STRIDE + index           # SUB_STRIDE = 1_000_000
```

Always call `super().__init__(...)` in an emitter. Emitters may keep their own strategy
state (e.g. the withdrawal latch / anniversary), never household state.

### 10.2 ORDER table (`clock.Order`)

Negative orders form the INITIAL step (once, `month` None, before the first month). Then
each month: `household.begin_month(m)` (core OPEN step), then every emitter with
order ≥ 0 in key order `(order, ordinal, sub)` (§5). To put something between two
steps use an intermediate number (e.g. `Order.SERVICE_DEBT + 50`); never renumber
existing ones without a parity run.

| Order | Name | Emitters (ordinal) | Reference |
|---|---|---|---|
| -100 | INITIAL | CarryInEmitter property/vehicle · AccountAtStartEmitter · PensionCreation (slot) | `prepare()` |
| 0 | OPEN | core `begin_month`; then RetirementEmitter (SCENARIO, sub 0) | `step` L776–782 |
| 100 | INCOME | IncomeEmitter (item index) | L829 |
| 200 | PENSION_PAY | PensionPayment (slot) | L811 |
| 300 | ACQUIRE | PurchaseEmitter (+REVALUATION) · LoanAdvanceEmitter · AccountOpeningEmitter (slot) | L840 |
| 400 | IMPROVE | ImprovementEmitter (modifier, own item index, `AT_HOST = False`) | L856 |
| 500 | ADJUST | MarketAdjustmentEmitter (modifier, own item index, `AT_HOST = False`) | L862 |
| 600 | SELL | SaleEmitter (modifier at the asset's slot) → LoanPayoff* → SalePenalty | L871 |
| 700 | TRANSFER | TransferEmitter (item index) | L890 |
| 800 | SERVICE_DEBT | RenewalEmitter (stage 0) · LoanServiceEmitter (host, stage 1) · ExtraPaymentEmitter / LumpSumEmitter (stage 2), all at the mortgage slot | L899, L969 |
| 900 | EXPENSE | ExpenseEmitter (item index) | L902 |
| 1000 | MAINTAIN | MaintenanceEmitter (vehicle slot) | L906 |
| 1100 | CONTRIBUTE | ContributionEmitter (item index) → `target.accept_contribution` | L915 |
| 1200 | WITHDRAW | WithdrawalEmitter (item index) | L938 |
| 1300 | GROW | AppreciationEmitter (property/vehicle), AccountReturnEmitter (slot; only if opened, on `hh.opening[id]`) | L1007 |
| 1400 | REVALUE_PENSIONS | PensionRevaluation (slot) | L823 |
| 1500 | TAX | TaxEmitter (SCENARIO, sub 0) | L1021 |
| 1600 | CLOSE | results Recorder (SCENARIO, sub 0; logs no event) | `run` L1055–1062 |

Converters (historical): E1 real assets, E2 debt, E3 investments, E4 pensions, E5
flows/tax/retirement/results, E6 UI (events view, modifier grouping), E7 removal of the
legacy adapter and final docs.

### 10.3 How a factory returns emitters

```python
@item_type("income")
def compile_income(item, ctx):                 # unchanged registration (§6)
    yield IncomeEmitter(first, last, ...)       # ordinal = ctx.ordinal, source = ctx.id,
                                                # index = ctx.index: all set by the compiler
@scenario_setup("tax", order=50)
def setup_tax(env):
    yield TaxEmitter()                          # ordinal SCENARIO, source None, index None
```

- A factory returns Emitters only (anything else: TypeError at registration).
- Two emitters of one item at one order need distinct `sub`s (duplicate key → ValueError).
- `source` defaults to `ctx.id`; pass `source=` to override (e.g. a property's own legacy
  `saleDate` sale uses the asset id, as today).
- Retirement anchoring (`startsAtRetirement`, `endsAtRetirement`, `atRetirement`, blank
  pension start) stays resolved **at compile time** from `env.retirement`, as today.
- After every factory has run the compiler calls `emitter.prepare(env)` for all emitters
  in key order. Lookups available there: `env.emitters_for(item_id)` (emitters with that
  `source`, key order) and `env.modifiers_of(host, cls=None)` (modifiers of a host, item
  order). `env.bucket` still exists, but no production module uses it.

### 10.4 Modifiers attached to a host (D-E1)

```python
class RenewalEmitter(ModifierEmitter):
    ORDER = Order.SERVICE_DEBT       # the order of the host action it modifies
    STAGE = 0                        # 0 before the host's own step, 2 after, ...
    def __init__(self, item, ...): super().__init__(item["mortgage"], Once(month), ...)
```

- `host` = the host item id. `AT_HOST = True` (default): the compiler sets
  `ordinal = env.slot[host]` (the host holding's slot; unknown host → ValueError);
  `AT_HOST = False`: own item index (improvement, marketAdjustment: the reference loops
  items there, not holdings).
- `sub` defaults to `sub_order(stage, own item index)`: modifiers of one host sort by
  stage, then item order. The host's own emitter at that order uses
  `sub=sub_order(1)` (or any stage between its modifiers' stages).
- Mortgage (E2): renewal stage 0 → service stage 1 (gate, accrue or settle + interest +
  payment) → extraPayment/lumpSum stage 2 in item order. Hazards to keep:
  - **Last renewal in a month wins**: in `prepare`, a renewal finds its siblings via
    `env.modifiers_of(host, RenewalEmitter)` and is due only if no later sibling has the
    same month.
  - **The gate is the service's**: renewal and extras run only if the loan existed and
    was opened at the start of the month and `balance > 0` *when service starts*; extras
    also not while accruing (`month < first_pay`). A lump sum's penalty is charged even
    when its prepayment rounds to 0, also after the last payment cleared the balance — so
    extras must not re-test `balance > 0` after the payment. Have the service emitter
    record the month it serviced (e.g. on its host emitter, found via
    `env.emitters_for(host)`) and let stage-2 modifiers test that.
- Sale (E1): a ModifierEmitter with host = the asset (`AT_HOST`, ORDER SELL). Exactly one
  sale per asset (`dates.property_sales` raises otherwise); an older file's property
  `saleDate` arrives as a sale item (upgrade.py).

### 10.5 Follow-up events (D-E3)

`Event.apply` returns follow-ups; the runner applies each immediately, depth-first,
before the next event of the same emitter (and before the next emitter). Follow-ups
inherit the parent's `key` and `source` unless they set their own, and are logged with
`cause` = the parent's log index. Sale:

```python
class Sale(LifecycleEvent):
    def apply(self, hh):
        ... SALE_PRICE_DIFFERENCE, SALE, capital gains, SELLING_COST (as today) ...
        return [LoanPayoff(loan.id) for loan in hh.loans_secured_by(self.asset_id)
                if loan.balance] + [SalePenalty(self.penalty)]
class LoanPayoff(LifecycleEvent):           # the loan settles itself
    def apply(self, hh): hh[self.loan_id].pay_off(hh, self.source)
```

Ledger order stays SALE…, SELLING_COST, LOAN_PAYOFF per loan (holdings order), PENALTY.

### 10.6 State-dependent amounts

Compute every amount that depends on balances **in `apply`**, not in `emit`: the
household changes within the month (a sale pays a loan before servicing, a contribution
lands before a withdrawal, tax needs the month's accumulator). `emit` decides *whether*
and *what* (gates, schedule, strategy); `apply` resolves *how much* and calls
`household.move`. `emit` may be a generator: each yielded event is applied before the
generator resumes, so later events of one emitter see the earlier ones' effect.
Rounding, zero-move and `Decimal('0')` vs `Decimal('0.00')` quirks stay where they are
today (in `move` and the aggregates' methods). Emit nothing in months where nothing
happens (the log should only hold events that did something or changed state).

### 10.7 Event log (D-E4)

`household.events` (an `EventLog`) gets one record per applied event, in application
order; `api.run_detailed` returns `{"rows", "holdings", "ledger", "tax", "events"}` with
`events = household.events.records` (`results.assemble` is unchanged). Record keys, in
this order:

| key | value |
|---|---|
| `month` | `'YYYY-MM'`, or None in the INITIAL step |
| `key` | `(order, ordinal, sub)` tuple |
| `emitter` | emitter `name` (class name) |
| `event` | event `name` (class name) |
| `kind` | `lifecycle` / `flow` / `valuation` / `state` |
| `source` | scenario item id, or None (scenario level) |
| `cause` | index of the parent record for a follow-up, else None |
| `ledger` | `(start, end)`: `ledger[start:end]` are the movements this event's own `apply` made (follow-ups have their own ranges; ranges tile the ledger in order) |
| `detail` | `event.describe()` |

### 10.8 The legacy adapter (removed in E7)

From E0 to E6 `ScenarioRunner.register` wrapped old clock handlers (`base.Handler`:
`Event`, `Process`, `InitialEvent`, each declaring a `clock.Phase`) in a `LegacyEmitter`
at order `Order[phase.name]` that emitted one opaque `legacy` event per firing. Once every
factory returned emitters, E7 deleted the adapter, the handler classes, `clock.Phase`,
`MONTHLY_PHASES` and `order_of_phase`; `clock.Order` keeps the same numbers (former
phase × 100). `register` now raises TypeError for anything that is not an `Emitter`, and
no `legacy` kind appears in the event log. Old name → new: phase → `Order` number;
`Event` (dated) → `OneShotEmitter` + an `Event` subclass; `Process` → `RecurringEmitter`;
`InitialEvent` → `InitialEmitter`; `runner.phases()` → `runner.steps()`; `env.clock` → `env.runner`.

### 10.9 Gate for every change (zero diff)

Before each commit, from `webapp/`:

```
.venv/bin/python -m unittest -q test_engine test_keep_payment test_ui_emitters test_api test_docs  # OK
.venv/bin/python -m unittest discover -s state_machine/tests -t .   # OK, incl. test_golden
```

A golden failure is a behaviour change. If it is intended: review it
(`.venv/bin/python state_machine/tools/update_golden.py --check` lists the scenarios that
differ; the failing WP tests name their golden value), then regenerate
(`update_golden.py`, `update_golden.py --values`) and commit the golden files with the
change, saying why. Until iteration 1 was removed the gate was
`run_reference_tests.py`, `record_scenarios.py` and `diff_engines.py` (0 diverged);
those tools are on the tag only. After removal: 151 + 24 app tests OK; 214 package tests
OK (239 golden scenarios, 724 golden values).

E0 baseline: 151 OK; diff 240 scenarios (162 identical, 78 identically invalid, 0
diverged; 242 with the user's two local files); 204 package tests OK. After E7: 151 OK;
242 scenarios with the two local files (164 identical, 78 identically invalid, 0
diverged); 229 package tests OK; `test_docs` + `test_ui_emitters` 12 OK. The harness
ignores `events` (it says so in its output). Tests that assert schedule keys use
`Order` numbers; keep the intent of a test when converting (same movements, same order).
