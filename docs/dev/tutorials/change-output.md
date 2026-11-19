# Tutorial: add a value to the output

**What you'll build:** a new `liquid` column (cash + investments: money not tied up in
property or vehicles) in every monthly result row. It comes out of the engine, through
the JSON API, and onto the Run page's table.

Big picture first? Read the [developer intro](../README.md).

## Concepts you need
- A run returns `run_detailed()`: `rows` (one per month), `holdings`, `ledger`, `tax`
  and `events`. `state_machine/results.py` builds them. The `Recorder` emitter runs
  last each month (`Order.CLOSE`) and calls `row()`. See
  [outputs.md](../reference/outputs.md).
- The pages never call the engine. They call the **JSON API** (`webapp/api.py`), which
  sends every `Decimal` as a string. The web client (`web/client.py`) turns the fields
  listed in `NUMERIC` back into `Decimal` for the templates. See
  [api.md](../reference/api.md).
- The **golden suite** stores a SHA-256 hash of each scenario's `rows`. A new column
  changes the hash of every scenario, even though no number changed.

All commands run from `webapp/`.

## Steps

### 1. Compute the value
In `state_machine/results.py`, function `row()`, add the key:

```python
    out = {"month": month_label(m), "cash": cash, "investments": investments,
           "assets": assets, "debts": debts, "assetsNetWorth": anw,
           "netWorth": cash + anw,
           "liquid": cash + investments}     # money that is not tied up in property
```

`row()` only reads the household. Never change balances here; that is the events' job.

### 2. Convert it in the web client
The API sends `"liquid": "15000.00"`. Add the key to `NUMERIC` in `web/client.py`, or
the template gets a string and cannot compare it with zero:

```python
NUMERIC = {"assets", "assetsNetWorth", "cash", "debts", "investments", "netWorth",
           "realAssetsNetWorth", "realNetWorth", "liquid",
```

The API itself needs no change: `/api/run` returns the whole `result`, and
`_json_default` in `api.py` writes any `Decimal` as a string.

### 3. Show it on the Run page
In `web/templates/run.html`, add a heading after "Net worth (... $)":

```html
<th>Net worth ({{ summary.dollarsOf }} $)</th><th>Liquid</th>
```

and the key to the list of columns:

```html
{% for key in ["cash", "investments", "assets", "debts", "realAssetsNetWorth", "netWorth", "realNetWorth", "liquid"] %}
```

### 4. Update the spec
`webapp/SPEC.md`, section "Engine output", lists the row keys. Add
`"liquid": Decimal` after `"netWorth": Decimal`. Then rebuild the documentation tab:

```
.venv/bin/python build_docs.py
```

### 5. Write a test
Create `state_machine/tests/test_liquid.py`:

```python
import json
import unittest

import app
from state_machine import engine
from state_machine.tests.support import scenario

ITEMS = [{"type": "account", "id": "tfsa", "accountType": "tfsa",
          "openingBalance": "5000", "annualReturn": "0"},
         {"type": "property", "id": "home", "purchaseDate": "2025-01-01", "price": "300000",
          "annualAppreciation": "0"}]


class Liquid(unittest.TestCase):
    def test_row(self):
        row = engine.run_detailed(scenario(ITEMS))["rows"][0]
        self.assertEqual(row["liquid"], row["cash"] + row["investments"])
        self.assertEqual(str(row["liquid"]), "15000.00")       # the house is not liquid

    def test_api_and_run_page(self):
        client = app.app.test_client()
        answer = client.post("/api/run", data=json.dumps({"scenario": scenario(ITEMS)}),
                             content_type="application/json").get_json()
        self.assertEqual(answer["result"]["rows"][0]["liquid"], "15000.00")   # a string
        from browser import Browser
        page = Browser(scenario(ITEMS)).get("/run").data.decode()
        self.assertIn("<th>Liquid</th>", page)


if __name__ == "__main__":
    unittest.main()
```

`browser.Browser` stands in for a browser tab: it posts the scenario with each request,
as the page's JavaScript does.

### 6. Review the golden differences
```
.venv/bin/python state_machine/tools/update_golden.py --check
```

Almost every scenario is listed:

```
fixtures/us_single.json: rows differs
  golden:  '8a338a6c...'
  current: '704cbc01...'
...
CA: 241 scenarios, 163 changed/new, 0 removed
US: 2 scenarios, 2 changed/new, 0 removed
```

That is expected: each row has one more key. But `--check` prints only the *first*
field that differs, so confirm that nothing else (holdings, ledger, tax, net worth)
moved:

```
.venv/bin/python - <<'EOF'
from state_machine.tools import update_golden as g
engine = g.load_engine()
for code in g.golden_sets():
    old, new = g.load_golden(code), g.compute(engine, g.load_scenarios(code))
    other = [k for k in new if {f: v for f, v in old[k].items() if f != "rows"}
             != {f: v for f, v in new[k].items() if f != "rows"}]
    print(code, "changed beyond rows:", other)
EOF
```

```
CA changed beyond rows: []
US changed beyond rows: []
```

Only now regenerate, the scenario hashes and the WP tests' stored values:

```
.venv/bin/python state_machine/tools/update_golden.py
.venv/bin/python state_machine/tools/update_golden.py --values
```

Commit the golden files with the change. The message must say why: "rows gain a
`liquid` column; no value changed (holdings, ledger, tax hashes identical)".

### 7. Fix the test that pins the row keys
`state_machine/tests/test_wp8_results.py`, `test_kitchen_sink`, checks the exact key
order of a row. Add `"liquid"` after `"netWorth"`:

```python
        self.assertEqual(list(r["rows"][0]), ["month", "cash", "investments", "assets", "debts",
                                              "assetsNetWorth", "netWorth", "liquid", "realNetWorth",
                                              "realAssetsNetWorth"])
```

## Test it
```
.venv/bin/python -m unittest -q test_engine test_keep_payment test_ui_emitters test_api test_docs
.venv/bin/python -m unittest discover -s state_machine/tests -t .
.venv/bin/python state_machine/tools/update_golden.py --check     # 0 changed/new everywhere
```

In the app (`.venv/bin/python app.py`), load a sample and click Run: the table ends
with a "Liquid" column.

## Where to go next
- A value per holding (not per month): add it in the aggregate's `report_extra()` (it
  lands in each holding point), see `holdings/`.
- A new kind of ledger line: that is an event's job, see
  [add-item-type.md](add-item-type.md) and [ledger.md](../reference/ledger.md).
- The output formats in full: [outputs.md](../reference/outputs.md); the API:
  [api.md](../reference/api.md).
- A column that only some jurisdictions have (like contribution room): it comes from
  the jurisdiction's `limits.remaining()`, and the web client converts keys ending in
  `Room` or `Limit` automatically. See [jurisdictions.md](../reference/jurisdictions.md).
