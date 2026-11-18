"""E5: income/expense/retirement/tax/recorder emitters and their event-log records
(D-E4: domain events only, nothing logged for the results recorder). Run from webapp/:
    .venv/bin/python -m unittest state_machine.tests.test_e5_events
"""
import copy
import unittest

from state_machine import api, compiler
from state_machine.clock import SCENARIO, Order
from state_machine.events.retirement import RetirementEmitter
from state_machine.flows.income_expense import ExpenseEmitter, IncomeEmitter
from state_machine.results import Recorder
from state_machine.rules.tax import TaxEmitter

from .support import scenario


def inc(id, amount="1000", **kw):
    return dict({"type": "income", "id": id, "amount": amount, "startDate": "2026-01-01"}, **kw)


def exp(id, amount="400", **kw):
    return dict({"type": "expense", "id": id, "amount": amount, "startDate": "2026-01-01"}, **kw)


def run(s):
    hh = api.simulate(copy.deepcopy(s))
    return hh, hh.events.records


class Emitters(unittest.TestCase):
    def test_classes_and_keys(self):
        s = scenario([inc("a"), {"type": "retirement", "retirementDate": "2026-05-01"},
                      exp("b")], end="2026-12-01")
        _, runner = compiler.compile_scenario(s)
        got = [(type(e), e.key) for e in runner.emitters()]
        self.assertEqual(got, [(RetirementEmitter, (int(Order.OPEN), SCENARIO, 0)),
                               (IncomeEmitter, (int(Order.INCOME), 0, 0)),
                               (ExpenseEmitter, (int(Order.EXPENSE), 2, 0)),
                               (TaxEmitter, (int(Order.TAX), SCENARIO, 0)),
                               (Recorder, (int(Order.CLOSE), SCENARIO, 0))])


class EventLog(unittest.TestCase):
    def test_month_records(self):
        s = scenario([inc("job", "5000", taxable=True), exp("rent", "1800"),
                      {"type": "retirement", "retirementDate": "2026-02-01"}],
                     end="2026-03-01", effectiveTaxRate=0.3, retirementTaxRate=0.1)
        hh, recs = run(s)
        got = [(r["month"], r["event"], r["kind"], r["source"]) for r in recs]
        self.assertEqual(got, [
            ("2026-01", "Income", "flow", "job"), ("2026-01", "Expense", "flow", "rent"),
            ("2026-01", "TaxStepEvent", "state", None),
            ("2026-02", "Retirement", "state", None),
            ("2026-02", "Income", "flow", "job"), ("2026-02", "Expense", "flow", "rent"),
            ("2026-02", "TaxStepEvent", "state", None),
            ("2026-03", "Income", "flow", "job"), ("2026-03", "Expense", "flow", "rent"),
            ("2026-03", "TaxStepEvent", "state", None)])
        # The recorder logs nothing, yet rows were recorded.
        self.assertFalse([r for r in recs if r["key"][0] == int(Order.CLOSE)])
        self.assertEqual(len(api.run_detailed(s)["rows"]), 3)
        # Each event's ledger slice holds its own movement.
        kinds = [[x["kind"] for x in hh.ledger.entries[slice(*r["ledger"])]] for r in recs]
        self.assertEqual(kinds[:4], [["INCOME"], ["EXPENSE"], ["TAX"], []])

    def test_nothing_emitted_when_nothing_happens(self):
        # Covered mode: no flow events; tax still steps every month.
        _, recs = run(scenario([inc("job", "5000", taxable=True), exp("rent", "1800")],
                               end="2026-02-01", incomeMode="expensesCovered"))
        self.assertEqual([r["event"] for r in recs], ["TaxStepEvent"] * 2)
        # Amounts rounding to 0: no event, except taxable income (adds 0.00 to taxable).
        _, recs = run(scenario([inc("a", "0.004"), exp("c", "0.004"),
                                inc("b", "0.05", per="year", taxable=True)],
                               end="2026-01-01", effectiveTaxRate=0.1))
        self.assertEqual([(r["event"], r["source"], r["ledger"]) for r in recs],
                         [("Income", "b", (0, 0)), ("TaxStepEvent", None, (0, 0))])
        # Retirement after the horizon never fires; before it, fires in the first month.
        _, recs = run(scenario([inc("j", "1")], end="2026-02-01", retirementDate="2031-01-01"))
        self.assertNotIn("Retirement", [r["event"] for r in recs])
        hh, recs = run(scenario([inc("j", "1")], end="2026-02-01", retirementDate="2020-01-01"))
        self.assertEqual([r["month"] for r in recs if r["event"] == "Retirement"], ["2026-01"])
        self.assertTrue(hh.first.retired)


if __name__ == "__main__":
    unittest.main()
