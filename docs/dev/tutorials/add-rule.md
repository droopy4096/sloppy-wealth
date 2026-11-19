# Tutorial: add a rule

**What you'll build:** a US tax rule: a 10% additional tax when someone takes money out
of a tax-deferred account (401(k), traditional IRA) before age 59½. You will write the
rule as a small calculator and plug it into the US jurisdiction's `on_withdraw` hook.

Big picture first? Read the [developer intro](../README.md).

## Concepts you need
- A **rule** is a calculator (a `base.Rule` subclass). It computes a number; it does
  not decide *when* (emitters do) or move money (events do). Examples:
  `rules/indexing.py` (a flow's yearly step-up), `rules/tax.py` (the monthly tax step).
  See [rules.md](../reference/rules.md).
- Tax is collected during the month in each person's **tax accumulator**
  (`household.tax_of(person)`): `add_taxable`, `add_deduction`, `add_own_rate_tax`.
  The tax step at `Order.TAX` turns it into one `TAX` ledger line. See
  [ledger.md](../reference/ledger.md#tax).
- Country-specific tax belongs to a **jurisdiction**. Account events call its hooks
  `on_contribute`, `on_return` and `on_withdraw` with the rounded amount. The default
  hooks follow the account type's `Treatment` flags; override one for anything the flags
  cannot say. See [jurisdictions.md](../reference/jurisdictions.md).
- Where the code goes: generic calculators in `state_machine/rules/`; a rule of one
  country in its package (`state_machine/jurisdictions/us/`).

All commands run from `webapp/`.

> In this project a new tax rule is a design decision. Record it in an ADR (`docs/adr/`)
> and agree it with the owner before you merge. This tutorial shows the mechanics.

## Steps

### 1. Write the rule
Create `state_machine/jurisdictions/us/early.py`:

```python
"""United States: the 10% additional tax on early withdrawals (before age 59 1/2) from a
tax-deferred account. Simplified: no exceptions (disability, first home, ...)."""
from decimal import Decimal

from ...base import Rule
from ...dates import month_index


class EarlyWithdrawalTax(Rule):
    """``tax(amount, month, birth)``: the additional tax on ``amount`` taken out in
    ``month`` by a person born in month ``birth`` (month indexes); 0 from age 59 1/2 or
    without a birth date."""
    RATE = Decimal("0.10")
    AGE_MONTHS = 59 * 12 + 6

    def tax(self, amount, month, birth):
        if birth is None or month - birth >= self.AGE_MONTHS:
            return Decimal(0)
        return amount * self.RATE


def birth_month(scenario, pid):
    """Month index of person ``pid``'s birthDate, or None."""
    for item in scenario.get("items", []):
        if item.get("type") == "person" and item.get("id") == pid and item.get("birthDate"):
            return month_index(item["birthDate"], "birthDate")
    return None
```

The engine counts months as integers (`dates.month_index("2030-01-01")`), so an age is
a subtraction. The rule is plain arithmetic: easy to test alone.

### 2. Call it from the hook
In `state_machine/jurisdictions/us/__init__.py`, import it:

```python
from .early import EarlyWithdrawalTax, birth_month
```

and override `on_withdraw` in `UnitedStates` (before `validate_item`):

```python
    early_withdrawal = EarlyWithdrawalTax()

    def on_withdraw(self, household, account, amount):
        """The usual tax (the flags), plus the early-withdrawal tax on a tax-deferred
        account before 59 1/2."""
        super().on_withdraw(household, account, amount)
        treatment = self.treatment(account)
        if treatment and treatment.withdrawal_taxed:
            birth = birth_month(household.scenario, account.owner)
            extra = self.early_withdrawal.tax(amount, household.month, birth)
            household.tax_of(account.owner).add_own_rate_tax(extra)
```

- Call `super()` first: the flags still do their part (the withdrawal is taxable income).
- `add_own_rate_tax` adds tax at a fixed rate, kept unrounded until the tax step. It
  shows in the month's tax detail as `ownRateTax`.
- The hook runs inside the `Withdrawal` event's `apply()` (`flows/withdrawal.py`), right
  after `household.move`. So `amount` is what actually left the account.

### 3. Test the rule and the engine
Create `state_machine/tests/test_early_withdrawal.py`:

```python
import unittest
from decimal import Decimal

from state_machine import engine
from state_machine.jurisdictions.us.early import EarlyWithdrawalTax
from state_machine.tests.support import scenario


class Rule(unittest.TestCase):
    def test_before_and_after_59_and_a_half(self):
        rule, born = EarlyWithdrawalTax(), 1980 * 12        # January 1980
        self.assertEqual(rule.tax(Decimal("1000"), born + 59 * 12 + 5, born), Decimal("100.00"))
        self.assertEqual(rule.tax(Decimal("1000"), born + 59 * 12 + 6, born), Decimal("0"))
        self.assertEqual(rule.tax(Decimal("1000"), born, None), Decimal("0"))


def run(birth, account_type):
    items = [{"type": "person", "id": "pat", "birthDate": birth},
             {"type": "account", "id": "ira", "accountType": account_type,
              "openingBalance": "50000", "annualReturn": "0"},
             {"type": "withdrawal", "id": "w", "account": "ira", "method": "amount",
              "amount": "1000", "per": "month", "startDate": "2026-03-01",
              "endDate": "2026-03-01"}]
    s = scenario(items, jurisdiction="US", effectiveTaxRate="0.2")
    return engine.run_detailed(s)["tax"]["2026-03"]


class InTheEngine(unittest.TestCase):
    def test_young_owner_pays_the_extra_tax(self):
        tax = run("1990-01-01", "traditionalIra")
        self.assertEqual(tax["incomeTax"], Decimal("200.00"))     # 20% of 1000
        self.assertEqual(tax["ownRateTax"], Decimal("100.00"))    # + 10% early withdrawal

    def test_older_owner_and_roth_do_not(self):
        self.assertEqual(run("1960-01-01", "traditionalIra")["ownRateTax"], Decimal("0.00"))
        self.assertEqual(run("1990-01-01", "rothIra")["ownRateTax"], Decimal("0.00"))


if __name__ == "__main__":
    unittest.main()
```

```
.venv/bin/python -m unittest state_machine.tests.test_early_withdrawal
```

### 4. Review the golden difference
This is a behaviour change, so the golden suite notices:

```
.venv/bin/python state_machine/tools/update_golden.py --check
```

```
CA: 241 scenarios, 0 changed/new, 0 removed
jurisdictions/us/sample.json: lastNetWorth differs
  golden:  '1085572.70'
  current: '1084372.70'
US: 2 scenarios, 1 changed/new, 0 removed
```

Explain it before you accept it. In the US sample, Kim (born 1985) withdraws $6,000 a
year ($500 a month) from a traditional IRA from 2030. 10% of $500 for the 24 months to
the end of 2031 is $1,200, exactly the drop in net worth. Canada is untouched. Then:

```
.venv/bin/python state_machine/tools/update_golden.py --jurisdiction US
```

Commit `tests/golden/us/golden.json` with the change and say why in the message.

## Test it
```
.venv/bin/python -m unittest -q test_engine test_keep_payment test_ui_emitters test_api test_docs
.venv/bin/python -m unittest discover -s state_machine/tests -t .
.venv/bin/python state_machine/tools/update_golden.py --check     # 0 changed/new everywhere
```

Also update the "Not modelled yet" list in the `us/__init__.py` docstring, `webapp/SPEC.md`
and `docs/IMPLEMENTATION_STATUS.md`.

## When a rule needs its own monthly step
A hook runs only when an account event calls it. A rule that must run every month on
its own, with no item behind it, needs a **scenario-level emitter**. The monthly tax
step is registered this way, in `events/retirement.py`:

```python
@scenario_setup("wp7.retirement_tax", order=50)
def setup_retirement_and_tax(env):
    ...
    yield TaxEmitter()
```

- `@scenario_setup(name, order)` (in `compiler.py`) runs once per scenario, before the
  item factories. It yields emitters.
- The emitter subclasses `ScenarioEmitter` and sets `ORDER` (here `Order.TAX`). Its
  `emit()` returns one event, `TaxStepEvent`, whose `apply()` calls `TaxRule.apply`.
- Give each scenario emitter at the same `ORDER` a distinct `SUB`: the order key
  `(order, ordinal, sub)` must be unique.

Use this for rules such as a yearly levy on the whole household. For anything tied to
one item, use that item's emitter (see [add-item-type.md](add-item-type.md)).

## Where to go next
- The rules that exist and what calls them: [rules.md](../reference/rules.md).
- The hook API and the `Treatment` flags: [jurisdictions.md](../reference/jurisdictions.md).
- Month order (`clock.Order`) and the order key: `state_machine/INTERFACES.md`.
- Every formula and its deliberate quirks: `state_machine/OBJECTS.md`.
