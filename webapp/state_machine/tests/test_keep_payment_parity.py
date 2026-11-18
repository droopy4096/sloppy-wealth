"""Renewal keepPayment (ADR-0043 amendment, C-M7): ``run_detailed`` (minus ``events``) and
``validate`` messages on keepPayment scenarios are golden values frozen from the iteration-1
engine (support.assert_golden); the outcome (kept / fell back) is logged in the Renew
event's detail."""
import copy
import json
import unittest

from state_machine import api

from .support import POC, assert_golden, scenario

FIXTURES = POC / "state_machine" / "fixtures"


def loan(**kw):
    return dict({"type": "mortgage", "id": "m1", "name": "M", "startDate": "2026-01-01",
                 "principal": "300000", "annualRate": "0.05", "amortizationYears": "20"}, **kw)


def renewal(date, rate, id="r1", **kw):
    return dict({"type": "renewal", "id": id, "name": "R", "mortgage": "m1",
                 "startDate": date, "annualRate": rate, "keepPayment": True}, **kw)


def extra(start, end, amount):
    return {"type": "extraPayment", "id": "x1", "name": "X", "mortgage": "m1",
            "startDate": start, "endDate": end, "monthlyAmount": amount}


SCENARIOS = {
    "kept": [loan(), renewal("2029-01-01", "0.04")],
    "kept after extras": [loan(), extra("2026-02-01", "2028-12-01", "700"),
                          renewal("2029-01-01", "0.045", penalty="900")],
    "fallback: interest": [loan(), renewal("2029-01-01", "0.3")],
    "fallback: term": [loan(), renewal("2029-01-01", "0.06")],
    "zero rate": [loan(), renewal("2027-06-01", "0")],
    "accruing month": [loan(firstPaymentDate="2026-07-01"), renewal("2026-04-01", "0.04")],
    "two renewals": [loan(), extra("2026-02-01", "2026-12-01", "2000"),
                     renewal("2027-01-01", "0.03"),
                     renewal("2030-01-01", "0.035", id="r2"),
                     renewal("2033-01-01", "0.02", id="r3", keepPayment=False)],
    "covered expenses": [loan(), extra("2026-02-01", "2028-12-01", "300"),
                         renewal("2029-01-01", "0.04")],
}


class KeepPaymentParity(unittest.TestCase):
    def check(self, s):
        new = api.run_detailed(copy.deepcopy(s))
        events = new.pop("events")
        assert_golden(self, "run_detailed without events", new)
        return events

    def test_scenarios(self):
        for name, items in SCENARIOS.items():
            settings = {"incomeMode": "expensesCovered"} if name == "covered expenses" else {}
            with self.subTest(name):
                self.check(scenario(items, end="2048-12-01", cash="50000", **settings))

    def test_fixture(self):
        s = json.loads((FIXTURES / "keep_payment.json").read_text())
        self.check(s)

    def test_renew_detail_reports_outcome(self):
        def detail(items):
            events = self.check(scenario(items, end="2030-12-01"))
            return [e["detail"] for e in events if e["event"] == "Renew"]
        self.assertRegex(detail(SCENARIOS["kept"])[0], r"keepPayment: payment \S+ kept, \d+ months left")
        self.assertIn("keepPayment fell back", detail(SCENARIOS["fallback: interest"])[0])
        self.assertIn("keepPayment fell back", detail(SCENARIOS["fallback: term"])[0])
        self.assertEqual(detail([loan(), renewal("2029-01-01", "0.04", keepPayment=False)]),
                         ["Renew m1"])

    def test_validation_messages_match(self):
        for bad in ({"keepPayment": "true"}, {"keepPayment": 1},
                    {"amortizationYears": "15"}):
            s = scenario([loan(), renewal("2029-01-01", "0.04", **bad)])
            with self.subTest(bad):
                with self.assertRaises(ValueError) as n:
                    api.validate(copy.deepcopy(s))
                assert_golden(self, "message", str(n.exception))


if __name__ == "__main__":
    unittest.main()
