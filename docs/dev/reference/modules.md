# Code map

Python 3, standard library plus Flask (`webapp/requirements.txt`). All code is under
`webapp/`.

## Dependency direction

```
browser (web/static/web.js, sessionStorage)
   │  form posts
   ▼
web/  (pages.py, client.py, timeline_draw.py, templates/)   no engine imports
   │  client.call / client.get  (in-process or WEB_API_URL)
   ▼
api.py  (/api/...)  + schema.py, timeline.py
   │
   ▼
state_machine/  (engine: ops, views, engine facade, compiler, runner, ...)
   │
   ▼
state_machine/jurisdictions/<code>/  (country rules, plug-ins)
```

`web/` talks only to the API. `api.py`, `schema.py` and `timeline.py` import the engine.
Inside the engine, plug-in modules (`holdings/`, `flows/`, `events/`, `rules/`,
`jurisdictions/`) import the core; the core never imports a plug-in by name (they are
found by `compiler.discover()`).

## webapp/

| Module | Responsibility |
|---|---|
| `app.py` | Flask app: registers the `api` and `web` blueprints; 1 MB body limit. Run: `.venv/bin/python app.py`. |
| `api.py` | The JSON API ([api.md](api.md)): commands, runs, views; error handling, limits, gzip. |
| `schema.py` | Item-type form schema: `FIELDS`, `LEGENDS`, `HINTS`, `SELECTS`, `PERCENT_FIELDS`, groups; `merged(code)` and `describe(code)` add a jurisdiction's own types and wording. |
| `timeline.py` | Timeline model (`layout`, ADR-0066) served by `/api/timeline`. |
| `browser.py` | Test stand-in for a browser tab: keeps the scenario and posts it with each request. |
| `build_docs.py` | Pre-compiles `docs/` Markdown and Mermaid into `static/docs/` for the Help tab and `/docs/dev`. |
| `samples/` | Sample scenario files. |
| `test_*.py` | App-level tests (API, engine sanity, docs, UI). |

## webapp/web/

| Module | Responsibility |
|---|---|
| `pages.py` | Flask blueprint with the pages (builder, flat builder, run, holdings, ledger, break-even, vehicle cost, timeline, load, new, compare, docs); converts form text to JSON values. |
| `client.py` | The only way to the engine: calls the API, converts numeric strings to `Decimal`. |
| `timeline_draw.py` | Draws the timeline model as SVG (horizontal) or a git-graph style list. |
| `templates/` | Jinja templates (`_items.html` shared by both builders). |
| `static/web.js` | Keeps the scenario in sessionStorage, posts it, swaps in the returned page. |

## webapp/state_machine/ (the engine)

| Module | Responsibility |
|---|---|
| `engine.py`, `api.py` | Public facade: `validate`, `run`, `run_detailed`, `simulate`, `upgrade` and helpers. |
| `ops.py` | Scenario commands for the API: load, settings, add, update, toggle, delete, limits. |
| `views.py` | Derived views: builder view, summary, ledger month, events view. |
| `cards.py` | Builder cards and per-item monthly estimates (no run). |
| `break_even.py` | Property break-even from a run (ADR-0073). |
| `vehicle_cost.py` | Vehicle cost of ownership from a run (ADR-0074). |
| `upgrade.py` | Converts older scenario forms to current ones. |
| `enabled.py` | `enabled: false` and its cascade (`active`, `off_reasons`). |
| `triggers.py` | Resolves triggers into target dates; `prepared()` = upgrade + active + resolve. |
| `validation.py` | `validate(scenario)`: required fields and checks; calls the jurisdiction's `validate_item`. |
| `compiler.py` | `@item_type`, `@scenario_setup`, `discover()`, `compile_scenario()` (Household + runner with emitters), `CompileContext`, `ItemContext`. |
| `runner.py` | `ScenarioRunner`: INITIAL step, then each month every due emitter in key order; applies events and follow-ups depth-first; logs them. |
| `emitters.py` | `Emitter` kinds (`OneShotEmitter`, `InitialEmitter`, `RecurringEmitter`, `ModifierEmitter`, `ScenarioEmitter`), schedules (`Once`, `Window`, ...), `Event` kinds (`LifecycleEvent`, `FlowEvent`, `ValuationEvent`, `StateEvent`), `EventLog`. |
| `clock.py` | `Order`: the steps of a month (below). |
| `household.py` | `Household` (holdings, ledger, persons, month state), `move()`, `Person`, `TaxAccumulator`. |
| `ledger.py` | `Ledger`: the list of movements ([ledger.md](ledger.md)). |
| `base.py` | `Aggregate` (a holding), `Rule`, `HOLDING_TYPES`, `GROUPS`. |
| `persons.py` | Owner, contributor and retirement-person rules on the raw scenario. |
| `dates.py` | Month indexes and labels, base month, retirement dates, sales, mortgage start, flow windows. |
| `arith.py` | Decimal formulas ([rules.md](rules.md#arithmetic)). |
| `results.py` | Records rows and holdings points each month; `assemble()` builds the result ([outputs.md](outputs.md)). |
| `holdings/` | Holding item types: `account.py`, `pension.py`, `real_estate.py` (property), `vehicle.py`, `mortgage.py` (the `Mortgage` aggregate), `cash.py`. |
| `events/` | One-off and lifecycle items: `purchase.py`, `sale.py`, `loan.py` (mortgage, renewal, extraPayment, lumpSum), `improvement.py`, `adjustment.py` (marketAdjustment), `transfer.py`, `cash_balance.py`, `retirement.py`, `trigger.py`. |
| `flows/` | Recurring flows: `income_expense.py`, `contribution.py`, `withdrawal.py`, `adjustment.py` (cash-flow adjustment), `associated.py`, `associated_income.py`. |
| `rules/` | `tax.py`, `indexing.py`, `capital_gains.py`, `person.py` ([rules.md](rules.md)). |
| `jurisdictions/` | Plug-in API and the `ca/`, `us/` packages ([jurisdictions.md](jurisdictions.md)). |
| `tests/` | Engine unit tests, conformance test, golden suite (`tests/golden/`). |
| `tools/update_golden.py` | Regenerates or checks golden results. |
| `fixtures/` | Synthetic scenarios used by tests. |
| `README.md`, `INTERFACES.md`, `OBJECTS.md`, `DECISIONS.md` | Engine design docs. |

Where each item type lives: the "Code" line of each section in [items.md](items.md).

## Month order

Every emitter has the key `(order, ordinal, sub)`; the runner fires them in key order
(`clock.py`). `ordinal` is the item index (for holdings and their modifiers: the
holding's slot; `-1` for scenario-level emitters). Steps are 100 apart:

| Order | Value | What runs |
|---|---|---|
| INITIAL | -100 | Once before the first month: holdings that exist at the start (accounts, pensions, assets bought before). |
| OPEN | 0 | `Household.begin_month` (not an emitter); `RetirementEmitter`. |
| (OPEN + 50) | 50 | CA contribution room start and yearly room. |
| (OPEN + 59) | 59 | Trigger log entries. |
| (OPEN + 60) | 60 | Cash-flow adjustment log entries. |
| INCOME | 100 | Income, associated income and one-offs. |
| PENSION_PAY | 200 | Pension payments. |
| ACQUIRE | 300 | Purchases, loan advances, account openings. |
| IMPROVE | 400 | Improvements. |
| ADJUST | 500 | Market adjustments. |
| SELL | 600 | Sales, loan payoffs, sale penalties. |
| TRANSFER | 700 | One-off transfers. |
| SERVICE_DEBT | 800 | Per mortgage: renewal, interest and payment, then extra payments and lump sums. |
| EXPENSE | 900 | Expenses, associated expenses and costs. |
| MAINTAIN | 1000 | Unused (vehicle maintenance is now an associated expense). |
| CONTRIBUTE | 1100 | Contributions. |
| WITHDRAW | 1200 | Withdrawals. |
| GROW | 1300 | Appreciation and account returns on opening balances. |
| REVALUE_PENSIONS | 1400 | Pension revaluation. |
| TAX | 1500 | Tax step. |
| (TAX + 50) | 1550 | Cash balance reconciliation. |
| CLOSE | 1600 | Results row and holdings points. |
