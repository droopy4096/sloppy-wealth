"""Scenario commands and derived views (ADR-0069 decision 3), without the web layer.

    cd webapp && .venv/bin/python -m unittest state_machine.tests.test_ops
"""
import copy
import unittest
from decimal import Decimal

from state_machine import engine, ops, views


def scenario(*items):
    return {"schemaVersion": 1, "name": "ops",
            "horizon": {"start": "2027-01-01", "end": "2030-12-01"},
            "openingCash": "1000", "effectiveTaxRate": "0.3",
            "items": [{"type": "income", "id": "job", "name": "Job", "startDate": "2027-01-01",
                       "amount": "6000", "per": "month", "taxable": True}, *items]}


HOUSE = {"type": "property", "id": "h", "name": "House", "purchaseDate": "2028-01-01",
         "price": "100000", "annualAppreciation": "0"}
LOAN = {"type": "mortgage", "id": "m", "name": "Loan", "property": "h", "principal": "50000",
        "annualRate": "0.05", "amortizationYears": "25"}
RETIRE = {"type": "retirement", "id": "r", "name": "Retire", "retirementDate": "2030-01-01"}


class Commands(unittest.TestCase):
    def test_input_is_never_changed(self):
        s = scenario(HOUSE, LOAN)
        before = copy.deepcopy(s)
        ops.add_item(s, {"type": "expense", "startDate": "2027-01-01", "amount": "1"})
        ops.toggle_item(s, "h")
        ops.delete_item(s, "h")
        ops.settings(s, {"name": "x", "horizon": s["horizon"], "openingCash": "1"})
        ops.update_item(s, "h", {"name": "Other"})
        self.assertEqual(s, before)

    def test_add_gives_an_id_and_a_name(self):
        r = ops.add_item(scenario(), {"type": "expense", "startDate": "2027-01-01",
                                      "amount": "1"})
        self.assertTrue(r["ok"])
        added = r["scenario"]["items"][-1]
        self.assertEqual((added["name"], len(added["id"])), ("Expense", 8))

    def test_refused_change_returns_the_scenario_unchanged_with_the_message(self):
        s = scenario()
        r = ops.add_item(s, {"type": "expense", "startDate": "2027-13-01", "amount": "1"})
        self.assertEqual((r["ok"], r["scenario"]), (False, s))
        self.assertIn("bad date", r["messages"][0])
        self.assertFalse(ops.add_item(s, {"name": "no type"})["ok"])
        self.assertFalse(ops.add_item(s, {"type": "expense", "id": "job"})["ok"])
        self.assertEqual(ops.toggle_item(s, "zz")["messages"], ["no item 'zz'"])

    def test_waiting_for_a_trigger_then_switched_on_by_it(self):
        s = scenario(RETIRE)
        r = ops.add_item(s, {"type": "expense", "id": "e", "amount": "100", "per": "month"})
        self.assertTrue(r["ok"])
        self.assertIs(r["scenario"]["items"][-1]["enabled"], False)
        self.assertIn("Added switched off", r["messages"][0])
        r = ops.add_item(r["scenario"], {"type": "trigger", "event": "r", "target": "e",
                                         "action": "start"})
        self.assertTrue(r["ok"])
        self.assertNotIn("enabled", next(i for i in r["scenario"]["items"] if i["id"] == "e"))

    def test_update_keeps_id_and_links(self):
        s = scenario(HOUSE, LOAN)
        r = ops.update_item(s, "h", {"name": "Home", "price": "120000"})
        self.assertTrue(r["ok"])
        house = r["scenario"]["items"][1]
        self.assertEqual((house["id"], house["name"], house["price"]), ("h", "Home", "120000"))
        self.assertEqual(r["scenario"]["items"][2]["property"], "h")     # the loan still links
        cleared = ops.update_item(s, "job", {"amount": "7000"}, clear=["taxable"])
        self.assertNotIn("taxable", cleared["scenario"]["items"][0])
        self.assertEqual(cleared["scenario"]["items"][0]["amount"], "7000")

    def test_update_refusals(self):
        s = scenario(HOUSE)
        bad = ops.update_item(s, "h", {"purchaseDate": "2028-13-01"})
        self.assertEqual((bad["ok"], bad["scenario"]), (False, s))
        self.assertIn("bad date", bad["messages"][0])
        self.assertIn("type cannot change", ops.update_item(s, "h", {"type": "vehicle"})["messages"][0])
        self.assertEqual(ops.update_item(s, "zz", {})["messages"], ["no item 'zz'"])

    def test_toggle(self):
        off = ops.toggle_item(scenario(HOUSE), "h")["scenario"]
        self.assertIs(off["items"][1]["enabled"], False)
        self.assertNotIn("enabled", ops.toggle_item(off, "h")["scenario"]["items"][1])

    def test_delete_cascades_and_refuses_a_broken_result(self):
        r = ops.delete_item(scenario(HOUSE, LOAN), "h")
        self.assertEqual([i["id"] for i in r["scenario"]["items"]], ["job"])
        pension = {"type": "pension", "id": "p", "name": "P", "amount": "1", "per": "month"}
        r = ops.delete_item(scenario(RETIRE, pension), "r")
        self.assertFalse(r["ok"])
        self.assertIn("needs a startDate or a retirement event", r["messages"][0])

    def test_settings(self):
        r = ops.settings(scenario(), {"name": " ", "horizon": {"start": "2027-01-01",
                                                               "end": "2029-12-01"},
                                      "openingCash": "5", "effectiveTaxRate": "0.25"})
        self.assertTrue(r["ok"])
        s = r["scenario"]
        self.assertEqual((s["name"], s["incomeMode"], s["annualInflation"],
                          s["retirementTaxRate"]), ("Untitled", "modelled", "0", ""))
        self.assertFalse(ops.settings(scenario(), {"horizon": {"start": "x"}})["ok"])

    def test_load(self):
        r = ops.load(dict(scenario(), items=[{"type": "expense", "startDate": "2027-01-01",
                                              "monthlyAmount": "5"}]))
        self.assertTrue(r["ok"])
        self.assertEqual(r["scenario"]["items"][0]["amount"], "5")     # upgraded
        self.assertIn("id", r["scenario"]["items"][0])
        self.assertEqual(ops.load([])["messages"], ["not a JSON object"])
        self.assertIn("schemaVersion", ops.load({"schemaVersion": 9})["messages"][0])


class Views(unittest.TestCase):
    def test_builder_view(self):
        s = scenario(HOUSE, LOAN, RETIRE,
                     {"type": "trigger", "id": "t", "name": "At retirement", "event": "r",
                      "target": "job", "action": "end"})
        v = views.builder_view(s)
        self.assertEqual((v["starts"]["m"], v["starts"]["t"]), ("2028-01", "2030-01"))
        order = [(i["id"], nested) for i, nested in v["ordered"]]
        self.assertEqual(order, [("job", False), ("t", True), ("h", False), ("m", False),
                                 ("r", False)])
        self.assertEqual(v["set_by"], {"job:endDate": "At retirement"})
        self.assertEqual(v["names"]["earner"], {"job": "Job (income)"})
        self.assertEqual(v["off"], {})

    def test_ledger_month_leaves_the_result_unchanged(self):
        s = scenario()
        result = engine.run_detailed(s)
        before = copy.deepcopy(result["ledger"])
        m = views.ledger_month(s, result, "2027-02")
        self.assertEqual(result["ledger"], before)
        self.assertEqual(m["month"], "2027-02")
        self.assertEqual(m["net_cash"], sum(x["cash"] for x in m["movements"]
                                            if x["cash"] is not None))
        self.assertGreater(m["net_cash"], Decimal(0))
        self.assertEqual(views.ledger_month(s, result, "1999-01")["month"], "2027-01")


if __name__ == "__main__":
    unittest.main()
