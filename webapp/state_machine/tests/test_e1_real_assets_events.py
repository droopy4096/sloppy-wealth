"""E1 real assets as emitters: event log records (D-E4), follow-ups (D-E3), order keys
(INTERFACES §10.2) and modifier placement (D-E1).

Run from webapp/:
    .venv/bin/python -m unittest state_machine.tests.test_e1_real_assets_events
"""
import unittest

from state_machine import api, compiler
from state_machine.clock import Order
from state_machine.emitters import sub_order
from state_machine.events.adjustment import MarketAdjustmentEmitter
from state_machine.events.improvement import ImprovementEmitter
from state_machine.events.purchase import CarryInEmitter, PurchaseEmitter
from state_machine.events.sale import SaleEmitter
from state_machine.holdings.real_estate import AppreciationEmitter
from state_machine.flows.associated import AssociatedExpenseEmitter

from .support import scenario
from .test_wp3_real_assets import car, house, loan


ANY = object()


def records(hh, month=ANY, source=ANY):
    """Event records of ``month`` ('YYYY-MM', None = the INITIAL step) and ``source``."""
    return [r for r in hh.events.records
            if (month is ANY or r["month"] == month) and (source is ANY or r["source"] == source)]


class EventLog(unittest.TestCase):
    def test_purchase_and_revaluation_follow_up(self):
        hh = api.simulate(scenario([house(marketValue=520000)]))
        mar = records(hh, "2026-03", "h")
        self.assertEqual([(r["event"], r["kind"], r["cause"]) for r in mar],
                         [("Purchase", "lifecycle", None),
                          ("Revaluation", "valuation", hh.events.records.index(mar[0]))])
        self.assertEqual(mar[0]["key"], (int(Order.ACQUIRE), 0, 0))
        self.assertEqual(mar[0]["emitter"], "PurchaseEmitter")
        kinds = [hh.ledger.entries[i]["kind"] for r in mar for i in range(*r["ledger"])]
        self.assertEqual(kinds, ["PURCHASE", "REVALUATION"])
        # No growth event in the purchase month (the asset did not exist at its start).
        self.assertNotIn("Appreciation", [r["event"] for r in mar])
        apr = records(hh, "2026-04", "h")
        self.assertEqual([(r["event"], r["kind"]) for r in apr], [("Appreciation", "valuation")])

    def test_carry_in_in_initial_step(self):
        hh = api.simulate(scenario([house(date="2015-07-01"), car(date="2023-05-01")]))
        initial = records(hh, None)
        self.assertEqual([(r["event"], r["kind"], r["source"], r["key"]) for r in initial],
                         [("CarryIn", "lifecycle", "h", (int(Order.INITIAL), 0, 0)),
                          ("CarryIn", "lifecycle", "v", (int(Order.INITIAL), 1, 0))])
        self.assertEqual(initial[0]["ledger"][0], initial[0]["ledger"][1])   # no movement

    def test_covered_vehicle_emits_no_maintenance(self):
        # Maintenance is an associated expense of the vehicle (ADR-0067), appended after
        # the items by upgrade.py: index 1, source "v-maintenance".
        hh = api.simulate(scenario([car()], incomeMode="expensesCovered"))
        self.assertNotIn("v-maintenance", [r["source"] for r in hh.events.records])
        hh = api.simulate(scenario([car()]))
        m = [r for r in hh.events.records if r["source"] == "v-maintenance"]
        self.assertEqual((m[0]["event"], m[0]["kind"]), ("Expense", "flow"))
        self.assertEqual(m[0]["key"], (int(Order.EXPENSE), 1, 0))

    def test_improvement_and_adjustment_are_modifiers_at_own_index(self):
        hh = api.simulate(scenario([
            house(),
            dict(type="improvement", id="i", property="h", improvementDate="2026-09-01",
                 cost=30000),
            dict(type="marketAdjustment", id="a", property="h", adjustmentDate="2026-09-01",
                 newValue=610000)]))
        sep = [r for r in records(hh, "2026-09") if r["source"] in ("i", "a")]
        self.assertEqual([(r["event"], r["source"], r["key"]) for r in sep],
                         [("Improvement", "i", (int(Order.IMPROVE), 1, sub_order(0, 1))),
                          ("Revaluation", "i", (int(Order.IMPROVE), 1, sub_order(0, 1))),
                          ("MarketAdjustment", "a", (int(Order.ADJUST), 2, sub_order(0, 2)))])
        self.assertEqual(sep[1]["cause"], hh.events.records.index(sep[0]))
        # valueAdded defaults to the cost: the revaluation moves nothing.
        self.assertEqual(sep[1]["ledger"][0], sep[1]["ledger"][1])

    def test_sale_follow_ups_pay_off_loans_then_penalty(self):
        hh = api.simulate(scenario([
            loan("m1", "h", principal=200000), house(),
            loan("m2", "h", principal=50000, startDate="2026-06-01"),
            dict(type="sale", id="s", property="h", saleDate="2027-07-01",
                 sellingCostRate=0.04, salePenalty=5000)]))
        sale = [r for r in hh.events.records if r["event"] == "Sale"]
        self.assertEqual(len(sale), 1)
        i = hh.events.records.index(sale[0])
        chain = hh.events.records[i:i + 4]
        self.assertEqual([(r["event"], r["kind"], r["cause"], r["source"]) for r in chain],
                         [("Sale", "lifecycle", None, "s"),
                          ("LoanPayoff", "lifecycle", i, "s"),
                          ("LoanPayoff", "lifecycle", i, "s"),
                          ("SalePenalty", "flow", i, "s")])
        # The sale sits at the asset's slot (1), sub = sub_order(0, sale item index 3).
        self.assertEqual(sale[0]["key"], (int(Order.SELL), 1, sub_order(0, 3)))
        moves = [[(hh.ledger.entries[k]["kind"], hh.ledger.entries[k]["to"])
                  for k in range(*r["ledger"])] for r in chain]
        # The selling cost is an associated cost (ADR-0067): paid later in the month.
        self.assertEqual(moves, [[("SALE", "cash")],
                                 [("LOAN_PAYOFF", "m1")], [("LOAN_PAYOFF", "m2")],
                                 [("PENALTY", None)]])
        cost = [r for r in hh.events.records if r["source"] == "h-selling-cost"]
        self.assertEqual([(r["event"], r["key"][0]) for r in cost], [("Cost", int(Order.EXPENSE))])
        self.assertTrue(all(hh[m].balance == 0 for m in ("m1", "m2")))


class Compile(unittest.TestCase):
    def emitters(self, items, **kw):
        _hh, runner = compiler.compile_scenario(scenario(items, **kw))
        return runner.emitters()

    def test_emitter_classes_and_keys(self):
        es = self.emitters([car(date="2020-01-01"), house(saleDate="2027-01-01"),
                            dict(type="sale", id="sv", property="v", saleDate="2027-05-01")])
        got = {(type(e).__name__, e.source, e.key) for e in es
               if isinstance(e, (CarryInEmitter, PurchaseEmitter, SaleEmitter,
                                 AppreciationEmitter, AssociatedExpenseEmitter))}
        self.assertEqual(got, {
            ("CarryInEmitter", "v", (int(Order.INITIAL), 0, 0)),
            ("AppreciationEmitter", "v", (int(Order.GROW), 0, 0)),
            # Maintenance: an associated expense appended after the items (ADR-0067).
            ("AssociatedExpenseEmitter", "v-maintenance", (int(Order.EXPENSE), 4, 0)),
            ("SaleEmitter", "sv", (int(Order.SELL), 0, sub_order(0, 3))),
            ("PurchaseEmitter", "h", (int(Order.ACQUIRE), 1, 0)),
            # Older files' saleDate: a sale item right after the property (upgrade.py).
            ("SaleEmitter", "h", (int(Order.SELL), 1, sub_order(0, 2))),
            ("AppreciationEmitter", "h", (int(Order.GROW), 1, 0))})

    def test_undated_or_orphan_sale_items_emit_nothing(self):
        es = self.emitters([house(), dict(type="sale", id="s", property="h"),
                            dict(type="sale", id="x", property="nope", saleDate="2027-01-01")])
        self.assertEqual([e for e in es if isinstance(e, SaleEmitter)], [])

    def test_modifier_hosts(self):
        es = self.emitters([house(), dict(type="improvement", property="h",
                                          improvementDate="2026-05-01", cost=1),
                            dict(type="marketAdjustment", property="h",
                                 adjustmentDate="2026-05-01", percent=0.1)])
        mods = [e for e in es if isinstance(e, (ImprovementEmitter, MarketAdjustmentEmitter))]
        self.assertEqual([(e.host, e.ordinal) for e in mods], [("h", 1), ("h", 2)])


if __name__ == "__main__":
    unittest.main()
