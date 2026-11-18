# PoC iteration 2: event-emitter state machine

The current PoC (iteration 2). It re-implements iteration 1 (a monolithic `engine.py`,
retired and not in this repository) as an event-driven state machine with event
emitters, with interface parity and identical results. Iteration 1's results are frozen
in the golden suite (`tests/golden/`). In the design documents, `engine.py` / "the
reference" means iteration 1.

## Result
| Check | Outcome |
|---|---|
| Iteration-1 suite `webapp/test_engine.py` (151 tests, incl. Flask pages) on this engine | 151/151 pass |
| Before iteration 1 was removed: differential harness on samples (6), fixtures (11), scenarios recorded from the test suite (224) and the user's local files (2, not committed) | 243/243 identical (`run_detailed` byte-identical or same validation error); 0 diverged |
| Golden suite `tests/test_golden.py`: samples (6), fixtures (11), test-suite scenarios (222) frozen from iteration 1 | 239/239 match: 161 run outputs (SHA-256 of `rows`, `holdings`, `ledger`, `tax`), 78 validation errors (type and message) |
| Package unit tests (WP0–WP8, E0–E5, golden; incl. 300 random real-asset scenarios and 724 golden values frozen from iteration 1) | 214/214 pass |
| App tests (`test_keep_payment`, `test_ui_emitters`, `test_docs`) | 24/24 pass |
| Event log of `samples/household-baseline.json` (then a personal baseline) / `fixtures/kitchen_sink.json` | 3,489 / 3,135 events, kinds lifecycle, flow, valuation, state only |

## Design
The engine is an **event-emitter model** (DECISIONS D-E1..D-E4, INTERFACES.md §§4–6, §10;
diagram `diagrams/06-event-emitter-conceptual.mmd`).

- **Household** (`household.py`): the main object. Holds cash, the aggregates (keyed and
  iterated by holding slot), the ledger (`move`, the only way to change a balance), the
  tax accumulator (taxable, deductions, own-rate tax, carry-forward pool, detail), month
  state (`retired`, current tax rate, covered mode) and the event log.
- **Aggregates** (`holdings/`): Cash, RealEstate, Vehicle, Mortgage, InvestmentAccount,
  Pension. Each carries what its transitions need and references its rules. Events
  **create** aggregates (D1); nothing exists before its creating event.
- **Emitters** (`emitters.py`; built in `holdings/`, `events/`, `flows/`, `rules/tax.py`,
  `results.py`): one form input becomes 1..n emitters, built by the item type's factory
  (`@item_type` in `compiler.py`). An emitter has a schedule (Initial, Once, Window,
  Anniversary) and an order key `(order, ordinal, sub)`: `order` from `clock.Order`
  (INITIAL −100, OPEN 0, INCOME 100, … TAX 1500, CLOSE 1600, reproducing the reference's
  intra-month order; any int in between inserts a new step), `ordinal` = the item's
  holding slot or index. Kinds: InitialEmitter, OneShotEmitter, RecurringEmitter,
  ScenarioEmitter (retirement, tax step, results recorder) and **ModifierEmitter**
  (renewal, extra payment, lump sum, sale, improvement, market adjustment), which acts at
  its host's position (D-E1).
- **Runner** (`runner.py`): the ScenarioRunner sorts emitters by key, runs the INITIAL
  step once, then each month asks every due emitter for its events in key order and
  applies each event at once; an event's follow-ups (sale → loan payoff → penalty) are
  applied depth-first right after it (D-E3). Only Emitters can be registered.
- **Events** (`emitters.Event` subclasses next to their emitters): LifecycleEvent
  (purchase, advance, opening, sale, payoff), FlowEvent (income, expense, payments,
  contributions, withdrawals, transfers, penalties), ValuationEvent (growth, interest,
  revaluation, market adjustment), StateEvent (retirement, renewal, tax step). `emit`
  decides whether and what; `apply` computes state-dependent amounts and moves money.
- **Event log** (D-E4): every applied event is recorded with month, key, emitter, event,
  kind, source item, cause (parent of a follow-up) and its ledger range;
  `run_detailed()["events"]` returns it (not part of the golden results).
- **Rules** (`rules/`): TaxRule (rates, retirement switch, pool), IndexingRule,
  investment income / withdrawal tax / deduction rules, CapitalGainsRule (no-op: C-M8 gap).
- **Results** (`results.py`), **validation** (`validation.py`, a verbatim port), public
  **facade** `engine.py` / `api.py` with the reference's symbols.
- **UI** (`webapp/api.py`, the JSON API, `from state_machine import engine`; the pages in
  `webapp/web/` use only the API; the same contract as the
  iteration-1 engine): the ledger page shows the month's events in application order with
  follow-ups indented and links to their ledger movements; the builder
  lists modifiers under their host item and groups the add-forms per host type
  (mortgage, property/vehicle, account changes).

Background: `FEASIBILITY.md`, `EMITTERS_FEASIBILITY.md`, `DECISIONS.md` (D1–D5,
D-E1..D-E4), `OBJECTS.md` (inventory of every object, formula and fragile behaviour),
`INTERFACES.md` (contracts used by the parallel work packages and emitter phases).

## Run
From `webapp/`:
```
.venv/bin/python app.py                                                   # Flask UI
.venv/bin/python -m unittest -q test_engine test_keep_payment test_ui_emitters test_api test_docs
.venv/bin/python -m unittest discover -s state_machine/tests -t .         # unit tests + golden
.venv/bin/python state_machine/tools/update_golden.py --check             # list golden differences
```

Golden suite (`tests/golden/`): `scenarios.json` (every sample, fixture and scenario the
iteration-1 test suite used; synthetic data), `golden.json` (per scenario the validation
error, or row count, last netWorth and SHA-256 of `repr()` of `rows`, `holdings`,
`ledger`, `tax`) and `values.json` (the WP unit tests' golden values, `support.assert_golden`:
the intermediate results they once compared with iteration 1). All were frozen while both
engines gave identical results. A failure means behaviour changed: if the change is
intended, review it (`update_golden.py --check`, the failing tests' messages), then
regenerate with `update_golden.py` (scenario hashes) and `update_golden.py --values` (WP
values) and commit the golden files with the change, saying why. `--add FILE` adds a
synthetic scenario file; never add personal scenarios. Those files are Canada's set; each
other jurisdiction has its own in `tests/golden/<code>/` (ADR-0071); `--check` covers all
sets, `--jurisdiction CODE` picks one (and is where `--add` writes).

## Contributing a jurisdiction (ADR-0071)
A tax jurisdiction is a package `jurisdictions/<code>/` (ISO 3166 alpha-2, lower case);
`ca/` (Canada) and `us/` (United States) are the examples. Nothing in the core is edited.

1. **Declare it** in `jurisdictions/<code>/__init__.py`: a `Jurisdiction` subclass with
   `@jurisdiction("XX")`, its `name`, and `account_types` (code -> `AccountType(code,
   label, Treatment(deductible, returns_taxed, withdrawal_taxed), short)`; `DEFERRED`,
   `EXEMPT` and `TAXABLE` cover the usual cases). The default hooks `on_contribute`,
   `on_return`, `on_withdraw` follow the flags; override one only for a rule they cannot
   express, calling `super()` for the rest.
2. **Limits** (optional): a `ContributionLimits` subclass (`cap`, `note_earned`,
   `note_withdrawal`, `remaining`, `columns` named `...Room` or `...Limit`) as `limits`.
   Its settings are usually an own item type.
3. **Own item types** (optional): list them in `item_types`, with `required` fields
   (`choice_fields` for those that are not numbers or dates), `owned_types`,
   `form_fields`, `legends`, `hints`, `selects`, `add_groups`, `head_adds`, and checks
   in `validate_item`. Register each factory with `@item_type` in a module of the
   package (it is imported automatically).
4. **Wording**: `labels` (`deductions`, `pool`, `earned`), and `legends` / `hints` for
   core fields it words differently.
5. **Sample and golden set**: `jurisdictions/<code>/sample.json` (synthetic; uses every
   account type and own item type), then
   `update_golden.py --jurisdiction XX --add state_machine/jurisdictions/<code>/sample.json`
   (more synthetic fixtures welcome).
6. **Tests**: `tests/test_conformance.py` must pass unchanged; add your own unit tests
   (see `tests/test_us.py`). Run the gates in "Run" above.

## Observations
- Size: about 3,600 lines in the package outside `tests/` and `tools/` (426 of them the
  verbatim validation copy) vs 1,130 for iteration 1; the structure is spread over ~30 small modules. Removing the legacy handler
  layer (E7) took out about 140 lines.
- Most ledger lines come from recurring emitters (growth, interest, payments, flows), not
  dated one-offs, so the gain is in structure (where each behaviour lives, how rules
  attach, an explainable event log), not simpler arithmetic.
- Identical results required reproducing reference quirks deliberately (OBJECTS.md
  lists them: JSON number 0 read as "not given", KeyError for some bad input, the
  late-first-payment window, Decimal('0') vs Decimal('0.00') in loan detail, ...).
  These are candidates for cleanup, each a deliberate change of the golden results.
- Iteration 2 is the PoC going forward; iteration 1 is frozen on its tag.
