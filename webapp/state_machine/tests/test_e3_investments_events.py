"""E3: investments as emitters (INTERFACES §10). Order keys, event kinds and the
"emit nothing when nothing happens" rule; parity itself is in test_wp5_investments.
Run from webapp/:  .venv/bin/python -m unittest state_machine.tests.test_e3_investments_events
"""
import copy
import unittest
from collections import Counter

from state_machine import compiler
from state_machine.clock import Order
from state_machine.emitters import Emitter

from .support import scenario

WP5 = {"AccountAtStartEmitter", "AccountOpeningEmitter", "AccountReturnEmitter",
       "TransferEmitter", "ContributionEmitter", "WithdrawalEmitter"}


def acct(id, type="tfsa", **kw):
    return dict({"type": "account", "id": id, "accountType": type, "annualReturn": "0.05"},
                **kw)


ITEMS = [
    acct("a", "rrsp", openingBalance="1000"),                                   # 0
    acct("b", "tfsa", openingBalance="500", openedDate="2026-03-01",
         openingFrom="cash"),                                                   # 1
    {"type": "transfer", "id": "x", "account": "a", "amount": "100",
     "transferDate": "2026-02-01"},                                             # 2
    {"type": "contribution", "id": "c", "account": "b", "startDate": "2026-01-01",
     "amount": "50"},                                                           # 3
    {"type": "withdrawal", "id": "w", "account": "b", "method": "even",
     "startDate": "2026-01-01", "endDate": "2026-12-01"},                       # 4
]


def run(items, **kw):
    household, runner = compiler.compile_scenario(copy.deepcopy(scenario(items, **kw)))
    runner.run(household)
    return household, runner


class E3Emitters(unittest.TestCase):
    def test_keys_and_emitter_types(self):
        _, runner = run(ITEMS)
        mine = {e.name: e for e in runner.emitters() if e.name in WP5}
        self.assertEqual(set(mine), WP5)
        self.assertTrue(all(isinstance(e, Emitter) for e in mine.values()))
        self.assertEqual(mine["AccountAtStartEmitter"].key, (Order.INITIAL, 0, 0))
        self.assertEqual(mine["AccountOpeningEmitter"].key, (Order.ACQUIRE, 1, 0))
        self.assertEqual(mine["TransferEmitter"].key, (Order.TRANSFER, 2, 0))
        self.assertEqual(mine["ContributionEmitter"].key, (Order.CONTRIBUTE, 3, 0))
        self.assertEqual(mine["WithdrawalEmitter"].key, (Order.WITHDRAW, 4, 0))
        returns = [e.key for e in runner.emitters() if e.name == "AccountReturnEmitter"]
        self.assertEqual(returns, [(Order.GROW, 0, 0), (Order.GROW, 1, 0)])

    def test_event_kinds_and_counts(self):
        hh, _ = run(ITEMS)
        recs = [r for r in hh.events.records if r["emitter"] in WP5]
        kinds = {r["event"]: r["kind"] for r in recs}
        self.assertEqual(kinds, {"AccountAtStart": "lifecycle", "AccountOpening": "lifecycle",
                                 "AccountReturn": "valuation", "Transfer": "flow",
                                 "Contribution": "flow", "Withdrawal": "flow"})
        n = Counter(r["event"] for r in recs)
        # 24 months; b exists from 2026-03 (in `opened` from 2026-04).
        self.assertEqual(n["AccountAtStart"], 1)
        self.assertEqual(n["AccountOpening"], 1)
        self.assertEqual(n["Transfer"], 1)
        self.assertEqual(n["Contribution"], 22)         # waits for b (2026-03 .. 2027-12)
        self.assertEqual(n["Withdrawal"], 10)           # b has a balance 2026-03 .. 2026-12
        self.assertEqual(n["AccountReturn"], 24 + 21)
        self.assertEqual(recs[0]["month"], None)
        for r in recs:
            start, end = r["ledger"]
            if r["event"] != "AccountAtStart":
                self.assertGreater(end, start, r)       # every emitted event moved money
            self.assertEqual(r["source"], {"AccountAtStart": "a", "AccountOpening": "b",
                                           "Transfer": "x", "Contribution": "c",
                                           "Withdrawal": "w"}.get(r["event"], r["source"]))

    def test_withdrawal_skips_empty_account(self):
        hh, _ = run([acct("t"), {"type": "withdrawal", "id": "w", "account": "t",
                                 "method": "amount", "startDate": "2026-01-01",
                                 "amount": "10"}])
        self.assertFalse([r for r in hh.events.records if r["event"] == "Withdrawal"])

    def test_withdrawal_caps_at_balance_when_applied(self):
        hh, _ = run([acct("t", openingBalance="25", annualReturn="0"),
                     {"type": "withdrawal", "id": "w", "account": "t", "method": "amount",
                      "startDate": "2026-01-01", "amount": "10"}])
        amounts = [str(e["amount"]) for e in hh.ledger.entries if e["kind"] == "WITHDRAWAL"]
        self.assertEqual(amounts, ["10.00", "10.00", "5.00"])
        self.assertEqual(len([r for r in hh.events.records if r["event"] == "Withdrawal"]), 3)


if __name__ == "__main__":
    unittest.main()
