"""Vehicle cost of ownership per month (ADR-0074).

    cd webapp && .venv/bin/python -m unittest state_machine.tests.test_vehicle_cost
"""
import unittest
from decimal import Decimal

from state_machine import engine
from state_machine.vehicle_cost import cost_of_ownership, vehicles

D = Decimal


def scenario(*items):
    return {"schemaVersion": 1, "name": "car", "jurisdiction": "CA",
            "horizon": {"start": "2027-01-01", "end": "2036-12-01"},
            "openingCash": "100000", "effectiveTaxRate": "0.3", "dollarsOf": "2030-01-01",
            "items": list(items)}


CAR = {"type": "vehicle", "id": "car", "name": "Car", "purchaseDate": "2027-01-01",
       "price": "40000", "annualDepreciation": "0.15"}
FUEL = {"type": "associatedExpense", "id": "fuel", "parent": "car", "amount": "200",
        "per": "month"}
INSURANCE = {"type": "associatedExpense", "id": "ins", "parent": "car", "amount": "1200",
             "per": "year"}


def view(*items, vid="car"):
    s = scenario(*items)
    return cost_of_ownership(s, engine.run_detailed(s), vid)


class Figures(unittest.TestCase):
    def test_first_month_and_the_formula(self):
        rows = view(CAR, FUEL, INSURANCE)["rows"]
        first = rows[0]
        self.assertEqual((first["paidSoFar"], first["netValue"], first["costPerMonth"]),
                         (D("40300.00"), D("40000.00"), D("300.00")))
        for r in rows:
            self.assertEqual(r["costPerMonth"],
                             ((r["paidSoFar"] - r["netValue"]) / r["monthsOwned"]).quantize(D("0.01")))
        self.assertEqual(rows[-1]["paidSoFar"], D(40000) + 120 * D(300))

    def test_selling_costs_reduce_the_value(self):
        fee = {"type": "associatedCost", "id": "fee", "parent": "car", "at": "end",
               "amount": "500"}
        first = view(CAR, fee)["rows"][0]
        self.assertEqual((first["sellingCosts"], first["netValue"], first["costPerMonth"]),
                         (D("500.00"), D("39500.00"), D("500.00")))

    def test_a_sale_ends_the_table_and_before_the_horizon(self):
        sale = {"type": "sale", "id": "s", "property": "car", "saleDate": "2030-06-01"}
        out = view(CAR, sale)
        self.assertEqual(out["rows"][-1]["month"], "2030-05")
        s = scenario(dict(CAR, purchaseDate="2024-01-01"), FUEL)
        result = engine.run_detailed(s)
        out = cost_of_ownership(s, result, "car")
        opening = next(h for h in result["holdings"] if h["id"] == "car")["points"][0]["opening"]
        self.assertEqual(out["rows"][0]["paidSoFar"], opening + D(200))
        self.assertEqual(out["rows"][0]["monthsOwned"], 1)
        self.assertTrue(any("Bought before the horizon" in n for n in out["notes"]))

    def test_summary_and_listing(self):
        out = view(CAR, FUEL)
        self.assertEqual(out["summary"]["current"]["month"], "2030-01")
        self.assertEqual(out["summary"]["last"]["month"], "2036-12")
        self.assertEqual(vehicles(scenario(CAR)), [("car", "Car")])
        self.assertIn("No running costs", " ".join(view(CAR)["notes"]))


if __name__ == "__main__":
    unittest.main()
