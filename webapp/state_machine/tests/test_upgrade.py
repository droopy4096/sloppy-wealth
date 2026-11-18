"""Older input forms converted in one place (state_machine/upgrade.py).

    cd webapp && .venv/bin/python -m unittest state_machine.tests.test_upgrade
"""
import copy
import unittest
from decimal import Decimal

from state_machine import engine
from state_machine.upgrade import upgrade


def scenario(*items, **over):
    s = {"schemaVersion": 1, "jurisdiction": "CA", "horizon": {"start": "2027-01-01", "end": "2030-12-01"},
         "openingCash": "1000", "effectiveTaxRate": "0.3", "items": list(items)}
    s.update(over)
    return s


class Upgrade(unittest.TestCase):
    def test_current_scenario_is_returned_unchanged(self):
        s = scenario({"type": "income", "startDate": "2027-01-01", "amount": "1"})
        self.assertIs(upgrade(s), s)

    def test_a_file_without_jurisdiction_is_canadian(self):
        """ADR-0071: files from before jurisdictions get "CA", right after the name."""
        s = {"schemaVersion": 1, "name": "old", "horizon": {"start": "2027-01-01",
             "end": "2030-12-01"}, "openingCash": "1000", "items": []}
        up = upgrade(s)
        self.assertEqual(list(up)[:3], ["schemaVersion", "name", "jurisdiction"])
        self.assertEqual(up["jurisdiction"], "CA")
        self.assertNotIn("jurisdiction", s)
        self.assertEqual(upgrade(dict(s, jurisdiction="US"))["jurisdiction"], "US")

    def test_caller_dict_is_not_changed_and_twice_is_a_no_op(self):
        s = scenario({"type": "expense", "startDate": "2027-01-01", "monthlyAmount": "5"})
        before = copy.deepcopy(s)
        once = upgrade(s)
        self.assertEqual(s, before)
        self.assertIs(upgrade(once), once)

    def test_monthly_amount(self):
        s = upgrade(scenario({"type": "expense", "startDate": "2027-01-01", "monthlyAmount": "5"},
                             {"type": "extraPayment", "monthlyAmount": "7"}))
        self.assertEqual(s["items"][0], {"type": "expense", "startDate": "2027-01-01",
                                         "amount": "5", "per": "month"})
        self.assertEqual(s["items"][1], {"type": "extraPayment", "monthlyAmount": "7"})
        rows = engine.run(scenario({"type": "expense", "startDate": "2027-01-01",
                                    "monthlyAmount": "5"}))
        self.assertEqual(str(rows[0]["cash"]), "995.00")

    def test_even_becomes_the_unindexed_annuity(self):
        acc = {"type": "account", "id": "a", "accountType": "tfsa", "annualReturn": "0",
               "openingBalance": "1200"}
        w = {"type": "withdrawal", "id": "w", "account": "a", "method": "even",
             "startDate": "2027-01-01"}
        self.assertEqual(upgrade(scenario(acc, w))["items"][1]["method"], "annuity")
        even = engine.run(scenario(acc, w))
        annuity = engine.run(scenario(acc, dict(w, method="annuity")))
        self.assertEqual(even, annuity)
        with self.assertRaisesRegex(ValueError, "set indexing to none for method 'even'"):
            engine.validate(scenario(acc, dict(w, indexing="inflation")))

    def test_retirement_date_setting_becomes_an_event(self):
        s = upgrade(scenario(retirementDate="2028-01-01"))
        self.assertNotIn("retirementDate", s)
        self.assertEqual(s["items"], [{"type": "retirement", "name": "Retirement",
                                       "retirementDate": "2028-01-01"}])
        before = upgrade(scenario(retirementDate="2020-01-01"))["items"][0]
        self.assertTrue(before["outsideHorizon"])         # older files: before the start
        engine.validate(scenario(retirementDate="2020-01-01"))
        with self.assertRaisesRegex(ValueError, "within the horizon"):
            engine.validate(scenario({"type": "retirement", "retirementDate": "2020-01-01"}))
        with self.assertRaisesRegex(ValueError, "has both a retirement event"):
            upgrade(scenario({"type": "retirement", "retirementDate": "2028-01-01"},
                             retirementDate="2028-01-01"))
        with self.assertRaisesRegex(ValueError, "retirementDate: bad date"):
            upgrade(scenario(retirementDate="2028"))
        self.assertNotIn("retirementDate", upgrade(scenario(retirementDate="")))

    def test_property_sale_date_becomes_a_sale_item_after_it(self):
        house = {"type": "property", "id": "h", "name": "House", "purchaseDate": "2020-01-01",
                 "price": "100", "annualAppreciation": "0", "saleDate": "2028-01-01",
                 "salePrice": "150", "sellingCostRate": "0.05", "salePenalty": "7"}
        s = upgrade(scenario(house, {"type": "expense", "startDate": "2027-01-01",
                                     "amount": "1"}))
        # The selling cost becomes an associated cost of the house (ADR-0067).
        self.assertEqual([i["type"] for i in s["items"]],
                         ["property", "sale", "expense", "associatedCost"])
        self.assertEqual(s["items"][1], {"type": "sale", "name": "House", "property": "h",
                                         "saleDate": "2028-01-01", "salePrice": "150",
                                         "salePenalty": "7"})
        self.assertEqual(s["items"][3], {"type": "associatedCost", "id": "h-selling-cost",
                                         "name": "House selling cost", "parent": "h",
                                         "at": "end", "rate": "0.05", "basis": "value"})
        self.assertEqual(s["items"][0]["sellingCostRate"], "0.05")
        self.assertNotIn("saleDate", s["items"][0])
        ledger = engine.run_detailed(scenario(house))["ledger"]
        self.assertEqual({(x["kind"], x["source"], x["amount"]) for x in ledger
                          if x["month"] == "2028-01" and x["source"] != "h"},
                         {("COST", "h-selling-cost", Decimal("7.50"))})      # 5% of 150


if __name__ == "__main__":
    unittest.main()
