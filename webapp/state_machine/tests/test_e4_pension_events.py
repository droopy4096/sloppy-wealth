"""E4 pensions as event emitters: emitter keys, event kinds and the event log (D-E4).
Run from webapp/:
    .venv/bin/python -m unittest state_machine.tests.test_e4_pension_events
"""
import unittest

from state_machine import api, compiler
from state_machine.clock import Order
from state_machine.holdings.pension import (PensionCreation, PensionPayment,
                                            PensionRevaluation)

from .support import scenario

PENSION = {"type": "pension", "id": "db", "name": "DB plan", "amount": "1200",
           "per": "month", "startDate": "2026-06-01", "endDate": "2027-03-01"}


def pension(**kw):
    return dict(PENSION, **kw)


def run(s):
    with compiler.isolated_registry(empty=False):
        if "retirement" not in compiler.registered_types():
            compiler.item_type("retirement")(lambda item, ctx: [])
        return api.simulate(s)


def pension_events(hh, source="db"):
    return [r for r in hh.events.records if r["source"] == source]


class PensionEmitters(unittest.TestCase):
    def test_emitters_and_keys(self):
        items = [{"type": "expense", "id": "x", "amount": "10", "startDate": "2026-01-01"},
                 pension()]
        with compiler.isolated_registry(empty=False):
            _hh, runner = compiler.compile_scenario(scenario(items))
        mine = [e for e in runner.emitters() if e.source == "db"]
        self.assertEqual([type(e) for e in mine],
                         [PensionCreation, PensionPayment, PensionRevaluation])
        self.assertEqual([e.key for e in mine],
                         [(Order.INITIAL, 1, 0), (Order.PENSION_PAY, 1, 0),
                          (Order.REVALUE_PENSIONS, 1, 0)])
        self.assertEqual([e.CATEGORY for e in mine], ["initial", "recurring", "recurring"])

    def test_creation_event(self):
        hh = run(scenario([pension()], annualInflation="0.02"))
        first = pension_events(hh)[0]
        self.assertEqual((first["month"], first["event"], first["kind"], first["emitter"]),
                         (None, "PensionCreated", "lifecycle", "PensionCreation"))
        self.assertEqual(first["ledger"][0], first["ledger"][1])   # no movement

    def test_no_inflation_only_payments(self):
        # No inflation, no indexing: the value falls exactly by each payment, so the
        # revaluation emits nothing; payments only in the window (2026-06..2027-03).
        hh = run(scenario([pension()]))
        monthly = [r for r in pension_events(hh) if r["month"] is not None]
        self.assertEqual({(r["event"], r["kind"]) for r in monthly},
                         {("PensionPaid", "flow")})
        self.assertEqual([r["month"] for r in monthly],
                         ["2026-%02d" % m for m in range(6, 13)]
                         + ["2027-%02d" % m for m in range(1, 4)])
        for r in monthly:
            start, end = r["ledger"]
            self.assertEqual(end - start, 1)
            self.assertEqual(hh.ledger.entries[start]["kind"], "PENSION_PAYMENT")

    def test_revaluation_events_carry_their_lines(self):
        hh = run(scenario([pension()], annualInflation="0.03"))
        reval = [r for r in pension_events(hh) if r["event"] == "PensionRevalued"]
        self.assertTrue(reval)
        self.assertEqual({r["kind"] for r in reval}, {"valuation"})
        lines = [hh.ledger.entries[r["ledger"][0]] for r in reval]
        self.assertTrue(all(r["ledger"][1] - r["ledger"][0] == 1 for r in reval))
        self.assertEqual({e["kind"] for e in lines}, {"REVALUATION"})
        self.assertEqual(len(lines), sum(1 for e in hh.ledger.entries
                                         if e["kind"] == "REVALUATION"))

    def test_no_empty_events(self):
        hh = run(scenario([pension(startDate="2030-01-01", endDate="2031-01-01")],
                          annualInflation="0.02"))
        for r in pension_events(hh):
            if r["month"] is not None:
                self.assertNotEqual(r["ledger"][0], r["ledger"][1], r)
        self.assertNotIn("PensionPaid", {r["event"] for r in pension_events(hh)})

    def test_covered_mode_still_pays(self):
        hh = run(scenario([pension()], incomeMode="expensesCovered"))
        self.assertIn("PensionPaid", {r["event"] for r in pension_events(hh)})


if __name__ == "__main__":
    unittest.main()
