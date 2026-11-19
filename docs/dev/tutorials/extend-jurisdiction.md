# Tutorial: extend a jurisdiction (add an account type)

**What you'll build:** Canada's FHSA (First Home Savings Account) as a new account type:
contributions deducted from taxable income, growth and withdrawals not taxed. It will
appear in the account form's dropdown, pass validation and run.

Big picture first? Read the [developer intro](../README.md).

## Concepts you need
- A **jurisdiction** is a package under `state_machine/jurisdictions/<code>/` (`ca/`,
  `us/`). It holds everything country-specific: account types, tax treatment,
  contribution limits, own item types and form wording. The core never names a country.
  See [jurisdictions.md](../reference/jurisdictions.md).
- An **account type** is an `AccountType(code, label, Treatment, short)`. The
  `Treatment` has three flags: `deductible`, `returns_taxed`, `withdrawal_taxed`.
  The default hooks (`on_contribute`, `on_return`, `on_withdraw`) follow the flags, so
  a plain account type needs no code.
- The builder's account dropdown, validation and the account cards read
  `account_types`. You do not edit `schema.py` or `validation.py`.
- **Conformance test** (`tests/test_conformance.py`): every jurisdiction must ship a
  `sample.json` that uses **every** account type, and that sample must be in its
  **golden set**. See [items.md](../reference/items.md#account) for the account item.

All commands run from `webapp/`.

## Steps

### 1. Declare the account type
In `state_machine/jurisdictions/ca/__init__.py`, import `Treatment` and define the
flags (no ready-made constant fits: `DEFERRED` taxes withdrawals, `EXEMPT` has no
deduction):

```python
from .. import DEFERRED, EXEMPT, TAXABLE, AccountType, Jurisdiction, Treatment, jurisdiction
from . import resp
from .room import ROOM_TYPES, RoomLimits

# FHSA: contributions deductible, growth and qualifying withdrawals tax-free.
FHSA = Treatment(deductible=True, returns_taxed=False, withdrawal_taxed=False)
```

Add it to `Canada.account_types`, after `resp`:

```python
        "fhsa": AccountType("fhsa", "FHSA (first home savings, deductible and tax-free)",
                            FHSA, "FHSA"),
```

The label shows in the dropdown, the short name on the account card.

### 2. Update the wording
Still in `Canada`, the legend and hints that list the account types:

```python
        "account": "Account: RRSP, TFSA, FHSA, RESP or non-registered",
...
        ("transfer", "account"): "RRSP, TFSA, FHSA or non-registered; into an RRSP or FHSA "
                                 "it is deducted",
```

### 3. Run the conformance test
```
.venv/bin/python -m unittest state_machine.tests.test_conformance
```

It fails:

```
FAIL: test_sample_validates_runs_and_is_golden (...) (jurisdiction='CA')
AssertionError: Items in the second set but not the first: ...
```

The sample does not use `fhsa` yet.

### 4. Use it in the sample
Edit `state_machine/jurisdictions/ca/sample.json` (synthetic data only). Add an account
after `kid-resp`, and a contribution after `c-tfsa`:

```json
    {"type": "account", "id": "ben-fhsa", "name": "Ben's FHSA", "owner": "ben",
     "accountType": "fhsa", "openingBalance": "8000", "annualReturn": "0.04"},
```

```json
    {"type": "contribution", "id": "c-fhsa", "account": "ben-fhsa", "startDate": "2027-01-01",
     "amount": "8000", "per": "year"},
```

The conformance test now fails one line later: the sample in the golden set is the old
one.

### 5. Review the golden differences, then update the set
First look, without writing:

```
.venv/bin/python state_machine/tools/update_golden.py --check --jurisdiction CA \
    --add state_machine/jurisdictions/ca/sample.json
```

```
jurisdictions/ca/sample.json: lastNetWorth, rows, holdings, ledger, tax differ
  lastNetWorth: golden '553661.41', current '577513.98'
tests/Accounts.test_validation_and_cascade_37f125db: error differ
  error: golden {'message': 'item ROTH: accountType must be one of tfsa, rrsp, nonRegistered, resp', ...}, current {... 'message': 'item ROTH: accountType must be one of tfsa, rrsp, nonRegistered, resp, fhsa'}
CA: 241 scenarios, 2 changed/new, 0 removed
```

Explain every line before you accept it:
- the sample changed because you added an account to it (more savings, so a higher
  net worth);
- an old error message now lists one more account type.

Both are intended. Nothing else changed, so no existing scenario computes differently.
Now write:

```
.venv/bin/python state_machine/tools/update_golden.py --jurisdiction CA \
    --add state_machine/jurisdictions/ca/sample.json
```

The golden suite is the project's regression guard. Its files are committed with the
change, and the commit message must say why the results changed. Never regenerate to
silence a difference you cannot explain.

### 6. Test the treatment
Create `state_machine/tests/test_fhsa.py`:

```python
import unittest
from decimal import Decimal

from state_machine import engine
from state_machine.tests.support import scenario

ITEMS = [
    {"type": "income", "id": "job", "startDate": "2026-01-01", "amount": "6000",
     "per": "month", "taxable": True},
    {"type": "account", "id": "fhsa", "accountType": "fhsa", "openingBalance": "10000",
     "annualReturn": "0.06"},
    {"type": "contribution", "id": "c", "account": "fhsa", "startDate": "2026-01-01",
     "amount": "500", "per": "month"},
    {"type": "withdrawal", "id": "w", "account": "fhsa", "method": "amount",
     "amount": "2000", "per": "month", "startDate": "2027-06-01", "endDate": "2027-06-01"},
]


class Fhsa(unittest.TestCase):
    def test_treatment(self):
        tax = engine.run_detailed(scenario(ITEMS, effectiveTaxRate="0.3"))["tax"]
        self.assertEqual(tax["2026-01"]["deductions"], Decimal("500.00"))   # deducted
        self.assertEqual(tax["2026-01"]["taxable"], Decimal("6000.00"))     # return not taxed
        self.assertEqual(tax["2027-06"]["taxable"], Decimal("6000.00"))     # withdrawal not taxed


if __name__ == "__main__":
    unittest.main()
```

## Test it
```
.venv/bin/python -m unittest -q test_engine test_keep_payment test_ui_emitters test_api test_docs
.venv/bin/python -m unittest discover -s state_machine/tests -t .
.venv/bin/python state_machine/tools/update_golden.py --check     # 0 changed/new everywhere
```

In the app (`.venv/bin/python app.py`), the account form of a Canadian scenario offers
"FHSA (first home savings, deductible and tax-free)". A US scenario does not, and
validation refuses `"accountType": "fhsa"` there.

## Not covered here
- **Limits.** Canada's contribution room (`ca/room.py`) knows only `rrsp` and `tfsa`.
  An FHSA limit would extend `RoomLimits`.
- **Rules the flags cannot express** (for example, tax on a non-qualifying withdrawal):
  override a hook. See [add-rule.md](add-rule.md).

## Where to go next
- The plug-in API in full: [jurisdictions.md](../reference/jurisdictions.md) and
  `state_machine/jurisdictions/__init__.py`.
- A whole new country: [new-jurisdiction.md](new-jurisdiction.md).
- Account fields only one type takes (like the RESP's grant history): the `fields=`
  argument of `AccountType`, see `ca/resp.py`.
