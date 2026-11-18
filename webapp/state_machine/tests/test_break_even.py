"""Property break-even and rent equivalent (ADR-0073).

    cd webapp && .venv/bin/python -m unittest state_machine.tests.test_break_even
"""
import unittest
from decimal import Decimal

from state_machine import engine
from state_machine.break_even import break_even, properties

D = Decimal


def scenario(*items, **over):
    s = {"schemaVersion": 1, "name": "be", "jurisdiction": "CA",
         "horizon": {"start": "2027-01-01", "end": "2045-12-01"},
         "openingCash": "300000", "effectiveTaxRate": "0.3", "dollarsOf": "2030-01-01",
         "items": list(items)}
    s.update(over)
    return s


HOUSE = {"type": "property", "id": "h", "name": "House", "purchaseDate": "2027-01-01",
         "price": "500000", "annualAppreciation": "0.04"}
LOAN = {"type": "mortgage", "id": "m", "name": "Loan", "property": "h", "principal": "400000",
        "annualRate": "0.05", "amortizationYears": "25", "termMonths": "60",
        "penaltyMethod": "monthsInterest", "penaltyMonths": "3"}
TAX = {"type": "associatedExpense", "id": "tax", "parent": "h", "amount": "300", "per": "month"}
UTIL = {"type": "associatedExpense", "id": "util", "parent": "h", "amount": "250",
        "per": "month", "alsoWhenRenting": True}
CLOSING = {"type": "associatedCost", "id": "close", "parent": "h", "at": "start",
           "amount": "8000"}
REALTOR = {"type": "associatedCost", "id": "sell", "parent": "h", "at": "end", "rate": "0.05",
           "basis": "value"}


def view(*items, pid="h", **over):
    s = scenario(*items, **over)
    return break_even(s, engine.run_detailed(s), pid)


class FirstMonth(unittest.TestCase):
    def test_every_figure(self):
        r = view(HOUSE, LOAN, TAX, UTIL, CLOSING, REALTOR)["rows"][0]
        self.assertEqual((r["month"], r["monthsOwned"], r["value"], r["sellingCosts"],
                          r["balance"]), ("2027-01", 1, D("500000.00"), D("25000.00"),
                                          D("400000.00")))
        s = scenario(HOUSE, LOAN)
        rate = next(h for h in engine.run_detailed(s)["holdings"] if h["id"] == "m")["points"][0]["rate"]
        self.assertEqual(r["penalty"], (3 * D(400000) * rate).quantize(D("0.01")))   # 3 months
        self.assertEqual(r["netProceeds"], r["value"] - r["sellingCosts"] - r["balance"] - r["penalty"])
        # Down payment 100000 + closing 8000 + tax 300; utilities only in "all".
        self.assertEqual(r["ownership"]["netInvestment"], D("108300.00"))
        self.assertEqual(r["all"]["netInvestment"], D("108550.00"))
        for v in ("ownership", "all"):
            self.assertEqual(r[v]["breakEven"], r["netProceeds"] - r[v]["netInvestment"])
            self.assertEqual(r[v]["rentEquivalent"], -r[v]["breakEven"])   # 1 month


class OverTime(unittest.TestCase):
    def test_payments_accumulate_and_rent_equivalent_turns_negative(self):
        out = view(HOUSE, LOAN, TAX, UTIL, CLOSING, REALTOR)
        rows = out["rows"]
        self.assertEqual(len(rows), 228)
        second = rows[1]
        payment = next(x for x in engine.run_detailed(scenario(HOUSE, LOAN, TAX, UTIL, CLOSING,
                                                               REALTOR))["ledger"]
                       if x["kind"] == "LOAN_PAYMENT")["amount"]
        self.assertEqual(second["ownership"]["netInvestment"],
                         rows[0]["ownership"]["netInvestment"] + payment + D(300))
        self.assertEqual(second["ownership"]["rentEquivalent"],
                         (-second["ownership"]["breakEven"] / 2).quantize(D("0.01")))
        self.assertLess(rows[-1]["ownership"]["rentEquivalent"], 0)
        months = out["summary"]["breakEvenMonth"]
        self.assertLess(months["ownership"], months["all"])
        self.assertEqual(out["summary"]["current"]["month"], "2030-01")
        self.assertEqual(next(r for r in rows if r["month"] == "2032-01")["penalty"], D("0.00"))

    def test_a_real_sale_ends_the_table(self):
        sale = {"type": "sale", "id": "s", "property": "h", "saleDate": "2035-06-01"}
        out = view(HOUSE, LOAN, sale)
        self.assertEqual(out["rows"][-1]["month"], "2035-05")
        self.assertTrue(any("Sold in 2035-06" in n for n in out["notes"]))


class BeforeTheHorizon(unittest.TestCase):
    def test_equity_at_the_start_is_the_investment(self):
        old = dict(HOUSE, purchaseDate="2015-01-01", price="400000")
        s = scenario(old, TAX)
        result = engine.run_detailed(s)
        out = break_even(s, result, "h")
        first = out["rows"][0]
        opening = next(h for h in result["holdings"] if h["id"] == "h")["points"][0]["opening"]
        self.assertEqual(first["monthsOwned"], 1)
        # The value at the horizon start (no mortgage) plus the first month's tax.
        self.assertEqual(first["ownership"]["netInvestment"], opening + D(300))
        self.assertTrue(any("Bought before the horizon" in n for n in out["notes"]))


class Notes(unittest.TestCase):
    def test_missing_selling_costs_and_term(self):
        notes = " ".join(view(HOUSE, dict(LOAN, termMonths="", penaltyMethod=""))["notes"])
        self.assertIn("No selling costs", notes)
        self.assertIn("No early-closure penalty", notes)

    def test_properties_listed(self):
        other = dict(HOUSE, id="c", name="Cottage")
        self.assertEqual(properties(scenario(HOUSE, other)), [("h", "House"), ("c", "Cottage")])


if __name__ == "__main__":
    unittest.main()
