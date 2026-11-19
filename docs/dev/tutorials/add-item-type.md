# Tutorial: add a new item type

**What you'll build:** a `gift` item: a one-off amount of cash the household receives on
a date (not taxed). It will run in the engine, be checked by validation, and appear in
the builder's "+ Add" bar.

Big picture first? Read the [developer intro](../README.md).

## Concepts you need
- A scenario is a JSON file with a list of **items** (`income`, `property`, ...). Each
  item type has a **factory** registered with `@item_type("name")`. It turns the item
  into one or more **emitters**. See [items.md](../reference/items.md).
- An **emitter** decides *whether* something happens in a month (`emit()`; it only
  reads state). An **event** does it (`apply()`). The runner walks the emitters every
  month in order of their `ORDER` number (`state_machine/clock.py`).
- Every balance change goes through `household.move(kind, from, to, amount, source)`.
  It writes one ledger line. `None` means "outside the household". See
  [ledger.md](../reference/ledger.md).
- Money is `decimal.Decimal`, rounded to cents with `arith.money`.
- New modules under `holdings/`, `events/`, `flows/` and `rules/` are found
  automatically. No registry to edit.

All commands run from `webapp/`.

## Steps

### 1. Write the emitter, the event and the factory
Create `state_machine/events/gift.py`:

```python
"""Gift (``type: "gift"``): a one-off amount of cash received on ``giftDate``.
Not income, not taxed."""
from ..arith import D, money
from ..clock import Order
from ..compiler import item_type
from ..dates import month_index
from ..emitters import FlowEvent, OneShotEmitter


class GiftReceived(FlowEvent):
    """GIFT: outside -> cash."""

    def __init__(self, amount):
        self.amount = amount

    def apply(self, household):
        household.move("GIFT", None, "cash", self.amount, self.source)

    def describe(self):
        return f"gift {self.amount}"


class GiftEmitter(OneShotEmitter):
    ORDER = Order.INCOME + 50        # after income, before pension payments

    def __init__(self, month, amount, **kw):
        super().__init__(month, **kw)
        self.amount = amount

    def emit(self, month, household):
        return (GiftReceived(self.amount),)


@item_type("gift")
def compile_gift(item, ctx):
    yield GiftEmitter(month_index(item["giftDate"], "giftDate"),
                      money(D(item["amount"])))
```

Notes:
- `OneShotEmitter` is due in exactly one month. For a monthly flow use
  `RecurringEmitter` (see `flows/income_expense.py`).
- `Order` steps are 100 apart. `Order.INCOME + 50` puts the gift between two steps.
- The runner fills in `self.source` (the item id), so the ledger line names the item.

### 2. Validate it
In `state_machine/validation.py`, add the required fields to `REQUIRED`:

```python
    # A one-off gift received in cash.
    "gift": ["giftDate", "amount"],
```

A field ending in `Date` is checked as a date, any other as a number. Add the
remaining checks in `validate()`, next to the `cashBalance` check:

```python
        if kind == "gift":
            if dec(item, "amount", where) <= 0:
                raise ValueError(f"{where}: amount must be positive")
            if not start <= month_index(item["giftDate"], where) <= end:
                raise ValueError(f"{where}: giftDate must be within the horizon")
```

### 3. Put it in the builder
The builder builds its forms from `schema.py`. Add the type in four places:

```python
# FIELDS: the form's fields, in JSON key order
    "gift": ["giftDate", "amount"],

# LEGENDS: the form's title
    "gift": "Gift: a one-off amount of cash received (not taxed)",

# HINTS: optional help after a field label
    ("gift", "giftDate"): "the month the cash arrives",

# ADD_GROUPS: which group of the "+ Add" bar lists it
    ("Income & pensions", ["income", "pension", "associatedIncome", "associatedOneOff", "gift"]),
```

`schema.py` asserts that every type in `FIELDS` is in exactly one `ADD_GROUPS` entry
(and one `FORM_GROUPS` entry, which picks up new types automatically). If the item
belongs on another item's card (like a contribution on an account), also add it to
`CARD_ADDS`, `NEEDS` and `LINK_FIELD`.

### 4. Document it in the spec
`webapp/SPEC.md` is the binding description of the JSON format. Add a bullet under
"Scenario JSON", after "Cash balance":

```markdown
- Gift: `{"type": "gift", "giftDate", "amount"}`: a one-off amount (positive) received
  into cash in the month of `giftDate` (within the horizon), after the month's income. A
  `GIFT` movement from outside: not income, not taxed.
```

Then rebuild the in-app documentation tab (`test_docs` fails when it is stale):

```
.venv/bin/python build_docs.py
```

### 5. Write a unit test
Create `state_machine/tests/test_gift.py`:

```python
import unittest
from decimal import Decimal

from state_machine import engine
from state_machine.tests.support import scenario


def gift(date="2026-06-01", amount="5000"):
    return {"type": "gift", "id": "g", "name": "From grandma",
            "giftDate": date, "amount": amount}


class Gift(unittest.TestCase):
    def test_cash_arrives_in_its_month(self):
        r = engine.run_detailed(scenario([gift()]))
        cash = {row["month"]: row["cash"] for row in r["rows"]}
        self.assertEqual(cash["2026-05"], Decimal("10000"))
        self.assertEqual(cash["2026-06"], Decimal("15000.00"))
        line = [x for x in r["ledger"] if x["kind"] == "GIFT"]
        self.assertEqual([(x["from"], x["to"], x["amount"], x["source"]) for x in line],
                         [(None, "cash", Decimal("5000.00"), "g")])

    def test_validation(self):
        with self.assertRaisesRegex(ValueError, "amount must be positive"):
            engine.validate(scenario([gift(amount="0")]))
        with self.assertRaisesRegex(ValueError, "giftDate must be within the horizon"):
            engine.validate(scenario([gift(date="2030-01-01")]))
        with self.assertRaisesRegex(ValueError, "missing field 'giftDate'"):
            engine.validate(scenario([{"type": "gift", "amount": "1"}]))


if __name__ == "__main__":
    unittest.main()
```

`support.scenario(items)` wraps items in a 2026-01 to 2027-12 scenario with 10,000 cash.

```
.venv/bin/python -m unittest state_machine.tests.test_gift
```

### 6. Give triggers and the timeline its date
`state_machine/triggers.py` `START_FIELD` maps each item type to the field holding its
date. Triggers use it to set the date, and the timeline (`timeline.py`) uses it to place
the item. Add the gift:

```python
               "associatedOneOff": "paymentDate", "gift": "giftDate"}
```

An item with an `endDate` also goes into `RECURRING`. An item with no dates at all (like
`person`) goes into `SKIPPED` in `timeline.py` instead. If you forget,
`test_ui_emitters.EveryItemTypeIsWired` fails and names the type.

## Test it
Run the three gates:

```
.venv/bin/python -m unittest -q test_engine test_keep_payment test_ui_emitters test_api test_docs
.venv/bin/python -m unittest discover -s state_machine/tests -t .
.venv/bin/python state_machine/tools/update_golden.py --check
```

The golden check must print `0 changed/new` for every set. A new item type is not in
any existing scenario, so no existing result changes. If one does, you changed
behaviour by accident.

To see it in the app: `.venv/bin/python app.py`, open http://127.0.0.1:5000, click
"+ Add", pick `gift` under "Income & pensions", then Run. The ledger page for that
month shows a `GIFT` line and a `GiftReceived` event.

## Optional polish
- Show it in the builder card's estimate column: `cards.py` `_estimate()`.
- A colour on the timeline: `web/timeline_draw.py`.

## Where to go next
- Every item type and its fields: [items.md](../reference/items.md).
- Movement kinds: [ledger.md](../reference/ledger.md).
- An item that depends on balances: compute the amount in `apply()`, as
  `events/cash_balance.py` does.
- A tax effect: [add-rule.md](add-rule.md).
- Conventions and the golden suite: `CLAUDE.md` at the repository root.
