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



class Financed(unittest.TestCase):
    """ADR-0074 amendment: a loan may finance a vehicle; its interest is a cost of
    ownership (the principal is already the purchase price)."""
    LOAN = {"type": "mortgage", "id": "carloan", "name": "Car loan", "property": "car",
            "principal": "32000", "annualRate": "0.069", "amortizationYears": "5"}

    def test_interest_counts_and_the_loan_starts_with_the_vehicle(self):
        s = scenario(CAR, self.LOAN)
        result = engine.run_detailed(s)
        self.assertEqual(next(x["month"] for x in result["ledger"]
                              if x["kind"] == "LOAN_ADVANCE"), "2027-01")
        out = cost_of_ownership(s, result, "car")
        interest = sum(x["amount"] for x in result["ledger"] if x["kind"] == "LOAN_INTEREST")
        last = out["rows"][-1]
        self.assertTrue(out["financed"])
        self.assertEqual(last["interestSoFar"], interest)
        self.assertEqual(last["paidSoFar"], D(40000) + interest)
        self.assertFalse(view(CAR)["financed"])

    def test_selling_the_vehicle_pays_its_loan_off(self):
        sale = {"type": "sale", "id": "s", "property": "car", "saleDate": "2029-01-01"}
        result = engine.run_detailed(scenario(CAR, self.LOAN, sale))
        self.assertIn(("2029-01", "LOAN_PAYOFF"), {(x["month"], x["kind"]) for x in result["ledger"]})

    def test_unknown_asset_still_refused(self):
        from state_machine import validation
        with self.assertRaisesRegex(ValueError, "refers to unknown property 'nope'"):
            validation.validate(scenario(CAR, dict(self.LOAN, property="nope")))


if __name__ == "__main__":
    unittest.main()
