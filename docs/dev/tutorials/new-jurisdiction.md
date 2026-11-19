# Tutorial: add a new jurisdiction

**What you'll build:** a minimal United Kingdom jurisdiction (`GB`) with two account
types, an ISA (tax-free) and a SIPP (tax-deferred pension), its sample scenario and
golden set. Users can then pick "United Kingdom" when they start a new scenario.

Big picture first? Read the [developer intro](../README.md).

## Concepts you need
- A scenario names its tax **jurisdiction** (`"jurisdiction": "CA"`; no field means
  Canada). The jurisdiction supplies account types, how each is taxed, contribution
  limits, own item types and wording. See
  [jurisdictions.md](../reference/jurisdictions.md).
- A jurisdiction is a package `state_machine/jurisdictions/<code>/` with a class
  registered by `@jurisdiction("<CODE>")`. The code is ISO 3166 alpha-2 (so `GB`, not
  `UK`). Packages are found automatically; nothing in the core is edited.
- Tax treatment comes from three `Treatment` flags. `DEFERRED`, `EXEMPT` and `TAXABLE`
  cover the usual cases.
- `tests/test_conformance.py` checks every registered jurisdiction. It must pass
  **unchanged**. It needs a `sample.json` that uses every account type, and a golden set.
- This tutorial walks through steps 1, 5 and 6 of "Contributing a jurisdiction" in
  `state_machine/README.md`. Steps 2 to 4 (limits, own item types, wording) are optional.

All commands run from `webapp/`.

## Steps

### 1. Declare the jurisdiction
Create `state_machine/jurisdictions/gb/__init__.py`:

```python
"""United Kingdom (tutorial example): an ISA (tax-free) and a SIPP (personal pension,
tax-deferred). No contribution limits and no own item types yet."""
from .. import DEFERRED, EXEMPT, AccountType, Jurisdiction, jurisdiction


@jurisdiction("GB")
class UnitedKingdom(Jurisdiction):
    name = "United Kingdom"
    account_types = {
        "isa": AccountType("isa", "ISA (tax-free)", EXEMPT, "ISA"),
        "sipp": AccountType("sipp", "SIPP (personal pension, tax-deferred)", DEFERRED, "SIPP"),
    }
    labels = {"deductions": "Deductions this month (SIPP, pension plan)",
              "pool": "SIPP and pension plan contributions",
              "earned": "counts as earned income (salary)"}
    legends = {"account": "Account: ISA or SIPP"}
```

- `account_types`: code -> `AccountType(code, label, treatment, short)`. The code is
  what the scenario stores in `accountType`; the label is the dropdown text.
- `labels`: wording the ledger and forms use. `legends` overrides a core form title.
- Without `limits`, nothing is capped.

### 2. Write a sample scenario
Create `state_machine/jurisdictions/gb/sample.json`. Synthetic data only. It must set
`"jurisdiction": "GB"` and use every account type:

```json
{
  "schemaVersion": 1,
  "name": "United Kingdom sample (conformance)",
  "jurisdiction": "GB",
  "horizon": {"start": "2027-01-01", "end": "2031-12-01"},
  "openingCash": "20000",
  "effectiveTaxRate": "0.25",
  "annualInflation": "0.02",
  "items": [
    {"type": "income", "id": "job", "name": "Salary", "startDate": "2027-01-01",
     "amount": "4500", "per": "month", "taxable": true, "indexing": "inflation"},
    {"type": "expense", "id": "living", "name": "Living", "startDate": "2027-01-01",
     "amount": "2800", "per": "month", "indexing": "inflation"},
    {"type": "account", "id": "isa", "name": "Stocks and shares ISA", "accountType": "isa",
     "openingBalance": "15000", "annualReturn": "0.05"},
    {"type": "account", "id": "sipp", "name": "SIPP", "accountType": "sipp",
     "openingBalance": "40000", "annualReturn": "0.05"},
    {"type": "contribution", "id": "c-isa", "account": "isa", "startDate": "2027-01-01",
     "amount": "500", "per": "month"},
    {"type": "contribution", "id": "c-sipp", "account": "sipp", "startDate": "2027-01-01",
     "amount": "400", "per": "month"},
    {"type": "withdrawal", "id": "w-isa", "account": "isa", "method": "amount",
     "amount": "6000", "per": "year", "startDate": "2030-04-01", "endDate": "2030-04-01"}
  ]
}
```

Item formats: [items.md](../reference/items.md).

### 3. Run the conformance test
```
.venv/bin/python -m unittest state_machine.tests.test_conformance
```

Everything passes except:

```
FAIL: test_sample_validates_runs_and_is_golden (...) (jurisdiction='GB')
AssertionError: 'GB' not found in ['CA', 'US'] : a golden set (tests/golden/<code>/)
```

So the sample validates and runs; only the golden set is missing.

### 4. Create the golden set
```
.venv/bin/python state_machine/tools/update_golden.py --jurisdiction GB \
    --add state_machine/jurisdictions/gb/sample.json
```

```
jurisdictions/gb/sample.json: new
GB: 1 scenarios, 1 changed/new, 0 removed
written: .../state_machine/tests/golden/gb/golden.json
```

This creates `tests/golden/gb/scenarios.json` (the scenarios) and `golden.json` (a
hash of each one's rows, holdings, ledger and tax). From now on any change to these
results makes `test_golden` fail, until someone reviews and explains it. More
synthetic fixtures are welcome: `--add` more files the same way.

### 5. Add your own unit tests
Create `state_machine/tests/test_gb.py`:

```python
import unittest
from decimal import Decimal

from state_machine import engine, jurisdictions
from state_machine.tests.support import scenario

ITEMS = [
    {"type": "income", "id": "job", "startDate": "2026-01-01", "amount": "4000",
     "per": "month", "taxable": True},
    {"type": "account", "id": "isa", "accountType": "isa", "openingBalance": "10000",
     "annualReturn": "0.06"},
    {"type": "account", "id": "sipp", "accountType": "sipp", "annualReturn": "0.06"},
    {"type": "contribution", "id": "c", "account": "sipp", "startDate": "2026-01-01",
     "amount": "300", "per": "month"},
]


class UnitedKingdom(unittest.TestCase):
    def test_registered(self):
        self.assertEqual(jurisdictions.get("GB").name, "United Kingdom")

    def test_sipp_deducted_isa_not_taxed(self):
        tax = engine.run_detailed(scenario(ITEMS, jurisdiction="GB",
                                           effectiveTaxRate="0.2"))["tax"]
        self.assertEqual(tax["2026-01"]["deductions"], Decimal("300.00"))
        self.assertEqual(tax["2026-01"]["taxable"], Decimal("4000.00"))   # ISA return not taxed

    def test_canadian_types_refused(self):
        bad = dict(ITEMS[1], accountType="tfsa")
        with self.assertRaisesRegex(ValueError, "accountType must be one of isa, sipp"):
            engine.validate(scenario([bad], jurisdiction="GB"))


if __name__ == "__main__":
    unittest.main()
```

## Test it
```
.venv/bin/python -m unittest -q test_engine test_keep_payment test_ui_emitters test_api test_docs
.venv/bin/python -m unittest discover -s state_machine/tests -t .
.venv/bin/python state_machine/tools/update_golden.py --check
```

The last command now lists three sets: `CA`, `GB` and `US`, each with `0 changed/new`.

In the app (`.venv/bin/python app.py`): "New scenario" offers United Kingdom, the
account form offers ISA and SIPP, and loading `gb/sample.json` runs.

## Where to go next
- Contribution limits (an ISA allowance, say): a `ContributionLimits` subclass as
  `limits`. Copy the shape of `us/limits.py`; its `columns` must end in `Room` or
  `Limit` and then show on the Run page.
- Own item types (like Canada's `contributionRoom`): `item_types`, `required`,
  `form_fields`, `legends`, `add_groups` and `validate_item`, with an `@item_type`
  factory in a module of the package. See [add-item-type.md](add-item-type.md) for the
  factory.
- A tax rule the flags cannot express: override `on_withdraw` and friends. See
  [add-rule.md](add-rule.md).
- The full API: [jurisdictions.md](../reference/jurisdictions.md).
