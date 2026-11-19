# Run outputs

`state_machine.engine.run_detailed(scenario)` (facade `state_machine/api.py`) validates
the scenario (`ValueError` with a readable message if invalid), compiles and runs it, and
returns:

```python
{"rows": [...], "holdings": [...], "ledger": [...], "tax": {...}, "events": [...]}
```

`run(scenario)` returns only `rows`. `simulate(scenario)` runs without validating and
returns the `Household` (for tests). The result is assembled by `results.assemble`
(`state_machine/results.py`); `events` is added by `run_detailed`.

Amounts are `Decimal`. The JSON API (`POST /api/run`) sends them as decimal strings;
`web/client.py` turns the known numeric keys back into `Decimal`.

## rows

One dict per month of the horizon, the state at the **end** of the month (after the tax
step and cash balances), recorded by `results.Recorder` at `Order.CLOSE`.

| Column | Meaning |
|---|---|
| month | `"YYYY-MM"`. |
| cash | Cash balance. May be negative. |
| investments | Sum of account balances and pension values. |
| assets | Sum of property and vehicle values. |
| debts | Sum of mortgage balances (positive = owed). |
| assetsNetWorth | investments + assets − debts (wealth held outside cash, ADR-0050). |
| netWorth | cash + assetsNetWorth. |
| *limit columns* | Only when the scenario has a limits item: CA `rrspRoom`, `tfsaRoom` (room left at month end; `None` before the room's as-of month); US `k401Limit`, `iraLimit`, `hsaLimit` (left this calendar year; `None` before `limitYear`). Household totals over persons. From `jurisdiction.limits.remaining`. |
| realNetWorth | netWorth in dollars of the base date (`dollarsOf`, default horizon start): netWorth / (1 + annualInflation)^((m − base)/12), rounded. Equal to netWorth without inflation. |
| realAssetsNetWorth | assetsNetWorth deflated the same way. |

## holdings

One entry per holding, in slot order: cash first, then each holding item (account,
pension, mortgage, property, vehicle) at the position of its first item. Holdings that
never come into existence still have an entry with empty `points`.

| Key | Meaning |
|---|---|
| id | `"cash"` or the item id. |
| name | Display name. |
| kind | `cash`, `property`, `vehicle`, `mortgage`, `account`, `pension`. |
| group | `cash`, `property` (property and vehicle), `debts`, `investments` (account and pension). |
| points | One per month the holding exists, see below. |

Point fields:

| Field | Holdings | Meaning |
|---|---|---|
| month | all | `"YYYY-MM"`. |
| opening | all | Balance at the start of the month; `None` in the month it was created. |
| closing | all | Balance at the end of the month. |
| rate | all | Monthly rate (property, vehicle, account, mortgage: the current one, after renewals); the annual indexing rate for a pension; `None` for cash. |
| interest | mortgage | LOAN_INTEREST of the month. |
| paid | mortgage | LOAN_PAYMENT + PREPAYMENT + LOAN_PAYOFF + INTEREST_ADJUSTMENT of the month. |
| principalPaid | mortgage | paid − interest. |
| closingPenalty | mortgage with a term | The penalty if the loan were closed after this month (ADR-0073). |

## ledger

Every movement, in order. Format and kinds: [ledger.md](ledger.md).

## tax

`{"YYYY-MM": detail}`, one detail per month, written by `TaxRule` (`rules/tax.py`):

| Key | Meaning |
|---|---|
| taxable | Taxable income of the month. |
| deductions | Deductions of the month. |
| poolIn | Carried-forward deductions before the step. |
| used | Deductions used against taxable income. |
| poolOut | Carried forward to next month. |
| rate | Rate applied (`None` in the household sum when there are several persons). |
| retired | Whether the person was retired (`None` in the household sum). |
| incomeTax | rate × (taxable − used), rounded. |
| ownRateTax | Tax at accounts' own withdrawal rates. |
| total | incomeTax + ownRateTax (the TAX movement). |
| persons | Only with several persons: `{person id: detail}`; the other keys are then household sums. |

## events

The event log (D-E4): every applied event in order (`emitters.EventLog.records`).

| Key | Meaning |
|---|---|
| month | `"YYYY-MM"`, or `None` for the INITIAL step (holdings existing at the start). |
| key | Order key `(order, ordinal, sub)` of the emitter (a list in JSON). |
| emitter | Emitter class name, e.g. `IncomeEmitter`. |
| event | Event class name, e.g. `Income`. |
| kind | `lifecycle`, `flow`, `valuation` or `state`. |
| source | Item id (or `None` for scenario-level events). |
| cause | Index of the event that produced it as a follow-up, else `None`. |
| ledger | `(start, end)`: the ledger lines it produced, `ledger[start:end]`. |
| detail | One-line description, e.g. `"income 5000.00 taxable"`. |

## Derived views

Computed from a scenario or a run; nothing here changes the run.

| View | Module | API | What it gives |
|---|---|---|---|
| Builder view | `state_machine/views.py` `builder_view` | `POST /api/view/builder` | Each item's effective start (`starts`), display order with modifiers under their host (`ordered`), off items and why (`off`), dates set by triggers (`set_by`), choices for reference fields (`names`), `summary`, `cards`, the upgraded items by id. |
| Cards and estimates | `state_machine/cards.py` `cards` | inside the builder view | Items grouped by person and category; per item an estimated monthly figure for the base month (own indexing, percentages of their stated basis, mortgage payments from their terms; taxable inflows after tax). No engine run. |
| Summary | `views.summary` | builder view, run, compare | `dollarsOf` (base month), `retirement` (first person's), `retirements` per person when several. |
| Ledger month | `views.ledger_month` | `POST /api/view/ledger` | One month: movements with signed `cash`, `net_cash`, balances, tax detail, events with follow-up depth. |
| Break-even | `state_machine/break_even.py` `break_even` | `POST /api/view/break-even` | Per month a property is owned: hypothetical sale's net proceeds (value − selling costs − mortgage balance − closing penalty) vs net investment, in variants `ownership` (without `alsoWhenRenting` expenses) and `all`; break-even and rent equivalent (ADR-0073). |
| Vehicle cost of ownership | `state_machine/vehicle_cost.py` `cost_of_ownership` | `POST /api/view/vehicle-cost` | Per month a vehicle is owned: paid so far (purchase or carried-in value, associated expenses and costs, loan interest and penalties), net value, cost per month = (paid − net value) / months owned (ADR-0074). |
| Timeline | `webapp/timeline.py` `layout` | `POST /api/timeline` | Lanes, links, dots, arrows, guides of every item on a time axis (ADR-0066); drawn by `web/timeline_draw.py`. |
