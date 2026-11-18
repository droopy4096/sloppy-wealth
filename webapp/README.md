# Wealth planner: Python PoC

## Iterations
| Iteration | Engine | Where |
|---|---|---|
| **2 (current)** | Event-emitter state machine: household main object, emitters, events, rules ([state_machine/README.md](state_machine/README.md)) | `webapp/state_machine/` |
| 1 (retired) | Monolithic monthly `Simulation` (`engine.py`) | not in this repository |

Iteration 2 is the PoC; iteration 1 is not part of this repository. Its results are frozen
in the golden suite (`state_machine/tests/golden/`, see [Tests](#tests)): every sample,
fixture and test scenario gives the same rows, holdings, ledger and tax as iteration 1
did. References to `engine.py` / "the reference" in the design documents point to
iteration 1 on the tag.

A barebones Flask proof of concept to test the mechanics of the planning model
(ADRs in `../docs/adr/`). Binding spec: [SPEC.md](SPEC.md). `state_machine/` does the
monthly calculation (`from state_machine import engine`); `api.py` is the JSON API
(the only user of the engine) and `web/` the pages, a client of the API (ADR-0069). The
sections below describe the UI and scenario format (they started with iteration 1).

Run: `cd webapp && .venv/bin/python app.py` (http://127.0.0.1:5000). Without a venv, first
`python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`.

Pages: `/` builder (settings and items), `/run` monthly table with links to
`/run/holdings` (one holding month by month; loans show interest and principal paid) and
`/run/ledger?month=YYYY-MM` (every movement of a month), `/save` and `/load`
(scenario JSON), `/compare` (two uploaded scenarios side by side, same horizon required,
with a net worth delta column).

Event-emitter model (D-E1, D-E4): the builder lists modifiers (mortgage, property/vehicle
and account changes) indented under their host and groups their forms per host type; the
saved file keeps its order. The engine's `run_detailed()` returns an `events` log; the
ledger page adds an "Events this month" table (order key, event, kind, caused-by item,
follow-ups indented under their cause, links to the movements each event made), placed
at the end of the page.

Samples: `samples/single-house.json` (buy a house with a mortgage) and
`samples/rent.json` (rent instead, same horizon and income), and
`samples/single-house-prepay.json` (the house with $500/month extra for 5 years and a
$20,000 lump sum in 2030-06): load them or compare them.

Mortgage prepayments: once a mortgage exists, the builder shows "Extra monthly payment"
(date range) and "Lump-sum payment" (one date) forms. The scheduled payment stays the
same; prepayments shorten the loan. Deleting a mortgage deletes its prepayments and
renewals.

Baseline scenario for testing (synthetic): `samples/household-baseline.json` (2019-08 to 2055-12, two
properties, two mortgages with a 2026 renewal, four jobs, living expenses, 30% tax, 2.2%
inflation).

A property can have a market value different from its price (blank = price): cash pays
the price, the property starts at the market value.

Mortgage and property: a mortgage picks the property it is secured by ("none" is allowed);
with a blank start date it starts in the purchase month. A property can have a sale date
and a selling cost %: the sale credits the value less selling costs to cash and pays off
the linked mortgage. Deleting a property deletes its mortgages. Sample:
`samples/single-house-sold.json` (sold in 2037 with 5% selling costs).

Mortgage renewals: "Renewal or switch to another lender" sets a new rate from a date and
recalculates the payment over the remaining amortization. Fill in amortizationYears to
restart the amortization, e.g. when moving to another institution. Sample:
`samples/single-house-renewals.json` (renew at 4.75% in 2029, switch lender at 4.25% over a
new 25 years in 2034).

Inflation: set "Inflation (%)" in the scenario settings. The run and compare tables show
an extra "Net worth (YYYY-MM $)" column: net worth in dollars of the base date, set in
"Show real values in dollars of" (blank = the horizon start; e.g. today's date for
today's dollars). It only affects reporting.

Income mode: "not modelled (expenses covered)" in the scenario settings ignores income
and assumes all monthly payments and expenses are paid from outside, with nothing left
over. Mortgages still amortise; cash changes only on purchases, mortgage advances, lump
sums and sales (a lump sum can be paid from cash or from outside money, chosen when it is
added). Net worth then shows what the assets and debts alone do.

Income tax: set "Income tax (%)" in the scenario settings, a single flat effective rate.
Income items marked taxable ("yes, before tax", the form default) are credited after
that tax; "no, after tax" items are credited as entered. Income and expense amounts can be
entered per month or per year (a yearly amount is spread evenly over 12 months).

Income and expense items can be indexed: none (fixed), inflation (the scenario's rate) or
a custom % per year. Indexed amounts step up once a year on the anniversary of the item's
start date; the amount entered is in dollars of that start month.

Simplifications compared with the ADRs:
- the operating cash account earns no return and there are no sweep rules (ADR-0030);
- cash can go negative (no shortfall capping, ADR-0015);
- one flat income tax rate; no capital gains tax on sales; no liquidation net worth;
- no goals, tallies or tags yet;
- indexing only on income, expenses, contributions, withdrawals and pensions.

Result levels (ADR-0053): the run table, per-holding detail and the movement ledger.
Columns (ADR-0050): Cash | Investments (accounts and pension values) | Property &
vehicles | Debts | Assets net worth (base-date dollars) | Net worth | Net worth
(base-date dollars).

Item types: property (optional market value), sale (of a property, paying off its
mortgages, or of a vehicle), market adjustment (a one-off % change or a set value), mortgage (linked to a property,
optional first payment date), renewal, extra monthly payment, lump sum, improvement,
vehicle (optional yearly maintenance increase), income, expense, account (RRSP, TFSA, non-registered), contribution, withdrawal
(fixed amount, percent, annuity; amount and annuity can be indexed), guaranteed pension.

## Tests

From `webapp/`:

    .venv/bin/python -m unittest -q test_engine test_keep_payment test_ui_emitters test_api test_docs
    .venv/bin/python -m unittest discover -s state_machine/tests -t .   # engine, incl. golden

`test_engine` (the iteration-1 suite, now on iteration 2), `test_keep_payment`,
`test_ui_emitters` (events view, modifier grouping) and `test_docs` test the app and the
engine through its public API. `state_machine/tests/` holds the engine's unit tests and
the golden suite:

- `test_golden.py` replays every scenario of `state_machine/tests/golden/scenarios.json`
  (samples, fixtures and the scenarios `test_engine` uses) and compares the SHA-256 of
  `rows`, `holdings`, `ledger` and `tax` (or the validation error) with `golden.json`,
  frozen from iteration 1;
- the WP unit tests check intermediate results against golden values
  (`golden/values.json`, also frozen from iteration 1).

After an intended behaviour change, review what changed
(`.venv/bin/python state_machine/tools/update_golden.py --check`, and the failing tests),
then regenerate (`update_golden.py`, `update_golden.py --values`) and commit the golden
files with the change, saying why.

Documentation tab: `/docs` shows the planning docs, ADRs, critique, PoC and state-machine
documents and the rendered diagrams. They are pre-compiled into `static/docs/` by
`.venv/bin/python build_docs.py` (needs mermaid-cli `mmdc` for changed diagrams: `$MMDC`,
`mmdc` on PATH, or a copy cached by `npx @mermaid-js/mermaid-cli`); rerun it after
editing any document or diagram. `test_docs.py` fails when `static/docs/` is stale.
