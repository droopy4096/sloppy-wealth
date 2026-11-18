"""Test helpers shared by the WP unit tests.

Golden values: the WP tests once compared intermediate results (ledger, balances, holding
state, validation outcomes, arith/dates results) with the iteration-1 engine (engine.py on
branch poc/python-flask, tag poc-iteration-1). Those comparisons are frozen: when both
engines agreed, the value each test computed was recorded as a hash in
``golden/values.json``; ``assert_golden(test, label, value)`` checks the SHA-256 of
``repr(value)`` against it, keyed by test id and call number. After an intended behaviour
change, review the failures, then regenerate with
``tools/update_golden.py --values`` (runs this suite with GOLDEN_UPDATE=1).
"""
import atexit
import copy
import hashlib
import json
import os
from pathlib import Path

POC = Path(__file__).resolve().parents[2]
SAMPLES = POC / "samples"
VALUES = Path(__file__).resolve().parent / "golden" / "values.json"
UPDATE = os.environ.get("GOLDEN_UPDATE") == "1"
_values = None
_recorded = {}


def sample(name):
    return json.loads((SAMPLES / name).read_text())


def scenario(items, start="2026-01-01", end="2027-12-01", cash="10000", **settings):
    """A minimal scenario around ``items`` (deep-copied)."""
    s = {"horizon": {"start": start, "end": end}, "openingCash": cash,
         "items": copy.deepcopy(items)}
    s.update(settings)
    return s


def without_tax(ledger):
    """Ledger entries other than TAX."""
    return [e for e in ledger if e["kind"] != "TAX"]


def balances(household):
    """{id: balance} of the household, holdings order."""
    return {a.id: a.balance for a in household.aggregates()}


# ---------- golden values ----------
def _digest(value):
    return hashlib.sha256(repr(value).encode()).hexdigest()[:24]


def _load():
    global _values
    if _values is None:
        _values = json.loads(VALUES.read_text()) if VALUES.exists() else {}
    return _values


def _save():
    if _recorded:
        values = dict(_load(), **_recorded)
        VALUES.write_text(json.dumps(values, indent=0, sort_keys=True) + "\n")


if UPDATE:
    atexit.register(_save)


def assert_golden(test, label, value):
    """``repr(value)`` must hash to the golden value of (test id, call number, label)."""
    n = getattr(test, "_golden_calls", 0) + 1
    test._golden_calls = n
    key = f"{test.id().removeprefix('state_machine.tests.')}#{n}"
    digest = f"{label}:{_digest(value)}"
    if UPDATE:
        _recorded[key] = digest
        return
    expected = _load().get(key)
    if expected is None:
        test.fail(f"no golden value for {key} ({label}); see tools/update_golden.py --values")
    if expected != digest:
        shown = repr(value)
        test.fail(f"golden value {key} differs: expected {expected}, got {digest}\n"
                  f"  current value: {shown[:500]}{'...' if len(shown) > 500 else ''}")
