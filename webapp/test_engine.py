"""Sanity checks for the PoC engine and form. Run: .venv/bin/python -m unittest -v"""
import copy
import io
import json
import re
import unittest
from unittest import mock
from decimal import Decimal
from pathlib import Path

import app
from browser import Browser
from state_machine import engine
from state_machine.engine import money

HERE = Path(__file__).parent
HOUSE = json.loads((HERE / "samples" / "single-house.json").read_text())


def house(**horizon):
    s = copy.deepcopy(HOUSE)
    s["horizon"].update(horizon)
    return s


class MortgageMath(unittest.TestCase):
    def setUp(self):
        # Extend the horizon so all 300 payments (2027-02 .. 2052-01) fall inside it.
        self.rows = engine.run(house(end="2052-03-01"))

    def test_payment_matches_textbook_formula(self):
        # Canadian mortgage: semi-annual compounding, monthly payments, float cross-check.
        r = (1 + 0.0379 / 2) ** (1 / 6) - 1
        expected = 560000 * r / (1 - (1 + r) ** -300)
        _, payment, _ = engine.mortgage_terms(HOUSE["items"][1])
        self.assertAlmostEqual(float(payment), expected, places=2)
        self.assertEqual(payment, Decimal("2882.31"))

    def test_first_payment_split(self):
        r = (1 + 0.0379 / 2) ** (1 / 6) - 1
        interest = round(560000 * r, 2)
        principal_paid = 2882.31 - interest
        self.assertEqual(self.rows[0]["debts"], Decimal("560000.00"))  # no payment in the start month
        self.assertAlmostEqual(float(self.rows[1]["debts"]), 560000 - principal_paid, places=2)

    def test_principal_decreases_every_month_and_reaches_zero(self):
        debts = [r["debts"] for r in self.rows]
        for a, b in zip(debts[1:300], debts[2:301]):
            self.assertLess(b, a)
        self.assertGreater(debts[299], 0)                # 299 payments made, one left
        self.assertEqual(debts[300], Decimal("0.00"))     # 300th payment in 2052-01
        self.assertEqual(self.rows[300]["month"], "2052-01")

    def test_cash_moves_by_income_minus_payment(self):
        self.assertEqual(self.rows[0]["cash"], Decimal("13500.00"))  # 150000 - 700000 + 560000 + 3500
        for prev, cur in zip(self.rows[1:299], self.rows[2:300]):
            self.assertEqual(cur["cash"] - prev["cash"], Decimal("3500") - Decimal("2882.31"))

    def test_net_worth_identity(self):
        for r in self.rows:
            self.assertEqual(r["netWorth"], r["cash"] + r["assets"] - r["debts"])
            self.assertEqual(r["assetsNetWorth"], r["assets"] - r["debts"])
            self.assertEqual(r["netWorth"], r["cash"] + r["assetsNetWorth"])

    def test_assets_net_worth_column_shown(self):
        client = Browser()
        client.get("/")
        client.scenario = copy.deepcopy(HOUSE)
        page = client.get("/run").data
        self.assertIn(b"<th>Assets net worth (2027-01 $)</th>", page)
        self.assertIn(b"140,000.00", page)                       # 2027-01: 700,000 - 560,000

    def test_assets_net_worth_in_base_date_dollars(self):
        s = house()
        s["annualInflation"] = "0.02"
        s["dollarsOf"] = "2029-01-01"
        rows = engine.run(s)
        self.assertEqual(rows[24]["realAssetsNetWorth"], rows[24]["assetsNetWorth"])
        self.assertAlmostEqual(float(rows[36]["realAssetsNetWorth"]),
                               float(rows[36]["assetsNetWorth"]) / 1.02, delta=0.01)


class PropertyGrowth(unittest.TestCase):
    def test_five_percent_a_year(self):
        rows = engine.run(house())
        self.assertAlmostEqual(float(rows[12]["assets"]), 735000, delta=0.05)
        self.assertAlmostEqual(float(rows[24]["assets"]), 771750, delta=0.10)


class RateInputs(unittest.TestCase):
    def test_engine_rejects_percent_typed_as_fraction(self):
        s = house()
        s["items"][1]["annualRate"] = "3.79"
        with self.assertRaisesRegex(ValueError, "annualRate must be a fraction"):
            engine.run(s)

    def test_form_takes_percentages(self):
        client = Browser()
        client.get("/")
        client.post("/settings", data={"name": "t", "start": "2027-01-01",
                                        "end": "2028-12-01", "openingCash": "150000"})
        client.post("/items/add", data={"type": "property", "name": "H",
                                         "purchaseDate": "2027-01-01", "price": "700000",
                                         "annualAppreciation": "5"})
        client.post("/items/add", data={"type": "mortgage", "name": "M",
                                         "startDate": "2027-01-01", "principal": "560000",
                                         "annualRate": "3.79", "amortizationYears": "25"})
        scenario = client.scenario
        self.assertEqual(Decimal(scenario["items"][1]["annualRate"]), Decimal("0.0379"))
        self.assertEqual(Decimal(scenario["items"][0]["annualAppreciation"]), Decimal("0.05"))
        self.assertIn(b"3.79%", client.get("/").data)
        rows = engine.run(scenario)
        self.assertLess(rows[2]["debts"], rows[1]["debts"])


def with_items(*extra, **horizon):
    s = house(**horizon)
    s["items"].extend(extra)
    return s


class Prepayments(unittest.TestCase):
    PAYMENT = Decimal("2882.31")

    def test_extra_monthly_payment_in_date_range(self):
        base = engine.run(house())
        rows = engine.run(with_items({"type": "extraPayment", "id": "x", "mortgage": "mtg",
                                      "startDate": "2028-01-01", "endDate": "2028-12-01",
                                      "monthlyAmount": "500"}))
        # Identical until the range starts.
        self.assertEqual(rows[11], base[11])
        # Inside the range, cash falls by 500 more each month and so does the debt (plus saved interest).
        for k in range(12, 24):
            self.assertEqual(rows[k]["cash"] - rows[k - 1]["cash"], 3500 - self.PAYMENT - 500)
        self.assertEqual(rows[25]["cash"] - rows[24]["cash"], 3500 - self.PAYMENT)  # range over
        saved = base[23]["debts"] - rows[23]["debts"]
        self.assertGreater(saved, Decimal("6000"))           # 12 x 500 plus interest avoided
        self.assertLess(saved, Decimal("6200"))

    def test_lump_sum_on_date(self):
        base = engine.run(house())
        rows = engine.run(with_items({"type": "lumpSum", "id": "l", "mortgage": "mtg",
                                      "paymentDate": "2028-01-01", "amount": "50000"}))
        self.assertEqual(rows[11], base[11])
        self.assertEqual(base[12]["debts"] - rows[12]["debts"], Decimal("50000.00"))
        self.assertEqual(base[12]["cash"] - rows[12]["cash"], Decimal("50000.00"))
        # Payment unchanged afterwards (ADR-0029), so the loan is paid off earlier.
        self.assertEqual(rows[14]["cash"] - rows[13]["cash"], 3500 - self.PAYMENT)
        payoff = next(r["month"] for r in rows if r["debts"] == 0)
        self.assertLess(payoff, "2050-01")

    def test_prepayment_capped_at_balance(self):
        rows = engine.run(with_items({"type": "lumpSum", "id": "l", "mortgage": "mtg",
                                      "paymentDate": "2027-03-01", "amount": "9999999"}))
        self.assertEqual(rows[2]["debts"], Decimal("0.00"))
        self.assertEqual(rows[2]["netWorth"], rows[2]["cash"] + rows[2]["assets"])
        # Cash paid exactly what was owed, nothing more.
        owed_plus_payment = rows[1]["debts"] + (rows[1]["debts"] * engine.mortgage_terms(
            HOUSE["items"][1])[0]).quantize(Decimal("0.01"))
        self.assertEqual(rows[1]["cash"] + 3500 - rows[2]["cash"], owed_plus_payment)

    def test_validation(self):
        with self.assertRaisesRegex(ValueError, "unknown mortgage"):
            engine.run(with_items({"type": "lumpSum", "mortgage": "nope",
                                   "paymentDate": "2028-01-01", "amount": "1"}))
        with self.assertRaisesRegex(ValueError, "after the mortgage start"):
            engine.run(with_items({"type": "lumpSum", "mortgage": "mtg",
                                   "paymentDate": "2027-01-01", "amount": "1"}))

    def test_form_and_cascade_delete(self):
        client = Browser()
        client.get("/")
        client.scenario = copy.deepcopy(HOUSE)
        page = client.get("/").data
        self.assertIn(b'<option value="mtg">House mortgage</option>', page)
        client.post("/items/add", data={"type": "lumpSum", "name": "Bonus", "mortgage": "mtg",
                                         "paymentDate": "2030-06-01", "amount": "20000"})
        client.post("/items/add", data={"type": "extraPayment", "name": "Double", "mortgage": "mtg",
                                         "startDate": "2030-01-01", "endDate": "",
                                         "monthlyAmount": "2882.31"})
        kinds = [i["type"] for i in client.scenario["items"]]
        self.assertEqual(kinds[-2:], ["lumpSum", "extraPayment"])
        self.assertEqual(client.get("/run").status_code, 200)
        client.post("/items/mtg/delete")
        self.assertEqual([i["type"] for i in client.scenario["items"]], ["property", "income"])


class RealNetWorth(unittest.TestCase):
    def test_no_inflation_means_real_equals_nominal(self):
        for r in engine.run(house()):
            self.assertEqual(r["realNetWorth"], r["netWorth"])

    def test_deflated_to_start_month_dollars(self):
        s = house()
        s["annualInflation"] = "0.02"
        rows = engine.run(s)
        self.assertEqual(rows[0]["realNetWorth"], rows[0]["netWorth"])
        self.assertAlmostEqual(float(rows[12]["realNetWorth"]),
                               float(rows[12]["netWorth"]) / 1.02, delta=0.01)
        self.assertAlmostEqual(float(rows[299]["realNetWorth"]),
                               float(rows[299]["netWorth"]) / 1.02 ** (299 / 12), delta=0.01)
        # Reporting only: nominal results are unchanged.
        self.assertEqual([r["netWorth"] for r in rows], [r["netWorth"] for r in engine.run(house())])

    def test_percent_rejected_and_form_converts(self):
        s = house()
        s["annualInflation"] = "2"
        with self.assertRaisesRegex(ValueError, "annualInflation"):
            engine.run(s)
        client = Browser()
        client.get("/")
        client.scenario = copy.deepcopy(HOUSE)
        client.post("/settings", data={"name": "t", "start": "2027-01-01", "end": "2051-12-01",
                                        "openingCash": "150000", "annualInflation": "2"})
        self.assertEqual(Decimal(client.scenario["annualInflation"]), Decimal("0.02"))
        self.assertIn(b'value="2"', client.get("/").data)
        page = client.get("/run").data
        self.assertIn(b"Net worth (2027-01 $)", page)
        self.assertIn(b"Inflation 2%", page)


class Indexing(unittest.TestCase):
    def cash_steps(self, scenario):
        rows = engine.run(scenario)
        return [rows[k]["cash"] - rows[k - 1]["cash"] for k in range(1, len(rows))]

    def test_default_is_fixed(self):
        s = house()
        s["annualInflation"] = "0.02"
        steps = self.cash_steps(s)
        self.assertEqual(steps[0], steps[200])

    def test_inflation_indexed_income_steps_up_yearly(self):
        s = house()
        s["annualInflation"] = "0.02"
        s["items"][2]["indexing"] = "inflation"
        steps = self.cash_steps(s)            # steps[k] is the change in month k+1
        payment = Decimal("2882.31")
        self.assertEqual(steps[10] + payment, Decimal("3500.00"))    # 2027-12
        self.assertEqual(steps[11] + payment, Decimal("3570.00"))    # 2028-01: +2%
        self.assertEqual(steps[22] + payment, Decimal("3570.00"))    # 2028-12
        self.assertEqual(steps[23] + payment, Decimal("3641.40"))    # 2029-01: +2% again
        # Its real value stays flat at 3,500 in start-month dollars.
        self.assertAlmostEqual(float(steps[23] + payment) / 1.02 ** 2, 3500, delta=0.01)

    def test_custom_rate_and_anniversary_of_item_start(self):
        s = with_items({"type": "expense", "id": "rent", "name": "Rent",
                        "startDate": "2030-07-01", "monthlyAmount": "1000",
                        "indexing": "custom", "indexRate": "0.03"})
        base = self.cash_steps(house())
        steps = self.cash_steps(s)
        k = 12 * 3 + 6 - 1                     # step index for 2030-07
        self.assertEqual(base[k] - steps[k], Decimal("1000.00"))
        self.assertEqual(base[k + 11] - steps[k + 11], Decimal("1000.00"))   # 2031-06
        self.assertEqual(base[k + 12] - steps[k + 12], Decimal("1030.00"))   # 2031-07

    def test_validation_and_form(self):
        s = house()
        s["items"][2]["indexing"] = "custom"
        s["items"][2]["indexRate"] = "3"
        with self.assertRaisesRegex(ValueError, "indexRate"):
            engine.run(s)
        s["items"][2]["indexing"] = "yearly"
        with self.assertRaisesRegex(ValueError, "indexing must be"):
            engine.run(s)
        client = Browser()
        client.get("/")
        client.scenario = copy.deepcopy(HOUSE)
        client.post("/items/add", data={"type": "expense", "name": "Rent",
                                         "startDate": "2027-01-01", "amount": "2600", "per": "month",
                                         "indexing": "custom", "indexRate": "3"})
        item = client.scenario["items"][-1]
        self.assertEqual((item["indexing"], Decimal(item["indexRate"])), ("custom", Decimal("0.03")))
        self.assertIn(b'<option value="inflation">', client.get("/").data)


class IncomeTaxAndAnnualAmounts(unittest.TestCase):
    PAYMENT = Decimal("2882.31")

    def income(self, **fields):
        s = house()
        s["items"][2].update(fields)
        return s

    def first_steps(self, s):
        rows = engine.run(s)
        return rows[0]["cash"], rows[1]["cash"] - rows[0]["cash"] + self.PAYMENT

    def test_flat_tax_on_taxable_income_only(self):
        s = self.income(amount="5000", per="month", taxable=True)
        s["effectiveTaxRate"] = "0.30"
        self.assertEqual(self.first_steps(s)[1], Decimal("3500.00"))      # 5000 - 30%
        s["items"][2]["taxable"] = False                                   # after-tax income
        self.assertEqual(self.first_steps(s)[1], Decimal("5000.00"))

    def test_no_rate_means_no_tax(self):
        s = self.income(amount="5000", per="month", taxable=True)
        self.assertEqual(self.first_steps(s)[1], Decimal("5000.00"))

    def test_annual_amount_spread_monthly(self):
        s = self.income(amount="60000", per="year", taxable=True)
        s["effectiveTaxRate"] = "0.30"
        self.assertEqual(self.first_steps(s)[1], Decimal("3500.00"))      # 60000/12 = 5000, -30%
        s = with_items({"type": "expense", "id": "tax", "name": "Property tax",
                        "startDate": "2027-01-01", "amount": "4800", "per": "year"})
        self.assertEqual(engine.run(house())[0]["cash"] - engine.run(s)[0]["cash"], Decimal("400.00"))

    def test_legacy_monthly_amount_still_works(self):
        s = self.income()
        s["items"][2].pop("amount"); s["items"][2].pop("per")
        s["items"][2]["monthlyAmount"] = "3500"
        self.assertEqual(engine.run(s), engine.run(house()))

    def test_validation_and_form(self):
        s = house()
        s["effectiveTaxRate"] = "30"
        with self.assertRaisesRegex(ValueError, "effectiveTaxRate"):
            engine.run(s)
        with self.assertRaisesRegex(ValueError, "per must be"):
            engine.run(self.income(per="week"))
        client = Browser()
        client.get("/")
        client.scenario = copy.deepcopy(HOUSE)
        client.post("/settings", data={"name": "t", "start": "2027-01-01", "end": "2051-12-01",
                                        "openingCash": "150000", "effectiveTaxRate": "30"})
        client.post("/items/add", data={"type": "income", "name": "Salary",
                                         "startDate": "2027-01-01", "amount": "120000",
                                         "per": "year", "taxable": "yes", "indexing": "none"})
        sc = client.scenario
        self.assertEqual(Decimal(sc["effectiveTaxRate"]), Decimal("0.30"))
        self.assertEqual({k: sc["items"][-1][k] for k in ("amount", "per", "taxable")},
                         {"amount": "120000", "per": "year", "taxable": True})
        self.assertIn(b"taxable=yes", client.get("/").data)
        self.assertIn(b"Income tax 30%", client.get("/run").data)


class Renewals(unittest.TestCase):
    def renew(self, rate, amort="", **horizon):
        return with_items({"type": "renewal", "id": "rn", "name": "Renewal", "mortgage": "mtg",
                           "startDate": "2032-01-01", "annualRate": rate,
                           "amortizationYears": amort}, **horizon)

    @staticmethod
    def payoff(rows):
        return next(r["month"] for r in rows if r["debts"] == 0)

    @staticmethod
    def payment_in(rows, k):
        return rows[k - 1]["cash"] + 3500 - rows[k]["cash"]

    K = 60   # row index of 2032-01; 59 payments made before it, 241 left

    def test_same_rate_changes_nothing_material(self):
        base = engine.run(house(end="2052-06-01"))
        rows = engine.run(self.renew("0.0379", end="2052-06-01"))
        self.assertEqual(self.payoff(rows), self.payoff(base))
        self.assertLessEqual(abs(self.payment_in(rows, self.K) - self.payment_in(base, self.K)),
                             Decimal("0.01"))

    def test_new_rate_recalculates_payment_over_remaining_amortization(self):
        rows = engine.run(self.renew("0.055", end="2052-06-01"))
        r = engine.monthly_rate("0.055")
        expected = engine.annuity(rows[self.K - 1]["debts"], r, 241)
        self.assertEqual(self.payment_in(rows, self.K), expected)
        self.assertGreater(expected, Decimal("2882.31"))
        self.assertEqual(self.payment_in(rows, self.K + 30), expected)   # level afterwards
        self.assertEqual(self.payoff(rows), "2052-01")                   # same end date

    def test_switch_lender_resets_amortization(self):
        rows = engine.run(self.renew("0.045", amort="25", end="2057-06-01"))
        r = engine.monthly_rate("0.045")
        expected = engine.annuity(rows[self.K - 1]["debts"], r, 300)
        self.assertEqual(self.payment_in(rows, self.K), expected)
        self.assertLess(expected, Decimal("2882.31"))                    # stretched out
        self.assertEqual(self.payoff(rows), "2056-12")                   # 300 payments from 2032-01

    def test_validation_and_form(self):
        with self.assertRaisesRegex(ValueError, "after the mortgage start"):
            engine.run(with_items({"type": "renewal", "mortgage": "mtg",
                                   "startDate": "2027-01-01", "annualRate": "0.05"}))
        two = self.renew("0.05")
        two["items"].append(dict(two["items"][-1], id="rn2"))
        with self.assertRaisesRegex(ValueError, "same month"):
            engine.run(two)
        client = Browser()
        client.get("/")
        client.scenario = copy.deepcopy(HOUSE)
        self.assertIn(b"Renewal or switch to another lender", client.get("/").data)
        client.post("/items/add", data={"type": "renewal", "name": "5y renewal", "mortgage": "mtg",
                                         "startDate": "2032-01-01", "annualRate": "4.5",
                                         "amortizationYears": ""})
        item = client.scenario["items"][-1]
        self.assertEqual((item["type"], Decimal(item["annualRate"])), ("renewal", Decimal("0.045")))
        self.assertEqual(client.get("/run").status_code, 200)


class PropertyLinkAndSale(unittest.TestCase):
    def linked(self, **prop):
        s = house(end="2040-12-01")
        s["items"][0].update(prop)
        s["items"][1]["property"] = "house"
        return s

    def test_linked_mortgage_starts_with_purchase(self):
        s = self.linked()
        s["items"][1]["startDate"] = ""
        self.assertEqual(engine.run(s), engine.run(house(end="2040-12-01")))

    def test_sale_pays_off_linked_mortgage(self):
        rows = engine.run(self.linked(saleDate="2037-01-01", sellingCostRate="0.05"))
        k = 120                                                   # 2037-01
        before = rows[k - 1]
        value = money(before["assets"])
        expected = before["cash"] + 3500 + value - money(value * Decimal("0.05")) - before["debts"]
        self.assertEqual(rows[k]["cash"], expected)               # no mortgage payment that month
        self.assertEqual((rows[k]["assets"], rows[k]["debts"]), (Decimal("0.00"), Decimal("0.00")))
        self.assertEqual(rows[k + 1]["cash"] - rows[k]["cash"], Decimal("3500.00"))
        self.assertEqual(rows[-1]["assets"], Decimal("0.00"))

    def test_unlinked_mortgage_survives_sale(self):
        s = self.linked(saleDate="2037-01-01")
        del s["items"][1]["property"]
        rows = engine.run(s)
        self.assertEqual(rows[120]["assets"], Decimal("0.00"))
        self.assertGreater(rows[120]["debts"], 0)

    def test_validation(self):
        s = self.linked()
        s["items"][1]["property"] = "nope"
        with self.assertRaisesRegex(ValueError, "unknown property"):
            engine.run(s)
        with self.assertRaisesRegex(ValueError, "saleDate must be after"):
            engine.run(self.linked(saleDate="2027-01-01"))
        s = self.linked(saleDate="2030-01-01")
        s["items"][1]["startDate"] = "2031-01-01"
        with self.assertRaisesRegex(ValueError, "after its property is sold"):
            engine.run(s)
        s = house()
        del s["items"][1]["startDate"]
        s["items"][1].pop("property", None)
        with self.assertRaisesRegex(ValueError, "link it to a property"):
            engine.run(s)

    def test_market_value_differs_from_price(self):
        s = self.linked(marketValue="900000")
        base, rows = engine.run(self.linked()), engine.run(s)
        self.assertEqual(rows[0]["cash"], base[0]["cash"])             # cash paid the price
        self.assertEqual(rows[0]["assets"], Decimal("900000.00"))       # value starts higher
        self.assertEqual(rows[0]["netWorth"] - base[0]["netWorth"], Decimal("200000.00"))

    def test_form_and_cascade_delete(self):
        client = Browser()
        client.get("/")
        client.scenario = copy.deepcopy(HOUSE)
        client.scenario["items"] = [client.scenario["items"][0], client.scenario["items"][2]]
        self.assertIn(b'<option value="house">House</option>', client.get("/").data)
        client.post("/items/add", data={"type": "mortgage", "name": "M", "property": "house",
                                         "startDate": "", "principal": "560000",
                                         "annualRate": "3.79", "amortizationYears": "25"})
        mid = client.scenario["items"][-1]["id"]
        client.post("/items/add", data={"type": "renewal", "name": "R", "mortgage": mid,
                                         "startDate": "2032-01-01", "annualRate": "4.5",
                                         "amortizationYears": ""})
        self.assertEqual(len(client.scenario["items"]), 4)
        self.assertIn(b"property=House", client.get("/").data)
        self.assertEqual(engine.run(client.scenario)[0]["debts"], Decimal("560000.00"))
        client.post("/items/house/delete")
        self.assertEqual([i["type"] for i in client.scenario["items"]], ["income"])


class ExpensesCovered(unittest.TestCase):
    def covered(self, s):
        s["incomeMode"] = "expensesCovered"
        return s

    def test_cash_moves_only_on_events(self):
        s = self.covered(with_items(
            {"type": "expense", "id": "e", "name": "Living", "startDate": "2027-01-01",
             "amount": "2000", "per": "month"},
            {"type": "extraPayment", "id": "x", "mortgage": "mtg",
             "startDate": "2028-01-01", "monthlyAmount": "500"},
            {"type": "lumpSum", "id": "l", "mortgage": "mtg",
             "paymentDate": "2030-01-01", "amount": "10000"}))
        rows = engine.run(s)
        self.assertEqual(rows[0]["cash"], Decimal("10000.00"))        # 150000 - 700000 + 560000
        self.assertEqual(rows[35]["cash"], Decimal("10000.00"))       # 2029-12: unchanged
        self.assertEqual(rows[36]["cash"], Decimal("0.00"))           # 2030-01: lump sum from cash
        self.assertEqual(rows[-1]["cash"], Decimal("0.00"))

    def test_debt_and_assets_follow_the_normal_schedule(self):
        s = with_items({"type": "extraPayment", "id": "x", "mortgage": "mtg",
                        "startDate": "2028-01-01", "monthlyAmount": "500"})
        normal, covered = engine.run(s), engine.run(self.covered(copy.deepcopy(s)))
        self.assertEqual([r["debts"] for r in covered], [r["debts"] for r in normal])
        self.assertEqual([r["assets"] for r in covered], [r["assets"] for r in normal])

    def test_sale_still_settles_through_cash(self):
        s = house(end="2040-12-01")
        s["items"][0].update(saleDate="2037-01-01", sellingCostRate="0.05")
        rows = engine.run(self.covered(s))
        before = rows[119]
        value = before["assets"]
        self.assertEqual(rows[120]["cash"],
                         before["cash"] + value - money(value * Decimal("0.05")) - before["debts"])

    def test_validation_and_form(self):
        s = house()
        s["incomeMode"] = "none"
        with self.assertRaisesRegex(ValueError, "incomeMode"):
            engine.run(s)
        client = Browser()
        client.get("/")
        client.scenario = copy.deepcopy(HOUSE)
        client.post("/settings", data={"name": "t", "start": "2027-01-01", "end": "2051-12-01",
                                        "openingCash": "150000", "incomeMode": "expensesCovered"})
        self.assertEqual(client.scenario["incomeMode"], "expensesCovered")
        self.assertIn(b"Income not modelled", client.get("/run").data)


class LumpSumSource(unittest.TestCase):
    def lump(self, paid_from, mode="modelled"):
        s = with_items({"type": "lumpSum", "id": "l", "mortgage": "mtg",
                        "paymentDate": "2030-01-01", "amount": "10000", "paidFrom": paid_from})
        s["incomeMode"] = mode
        return engine.run(s)

    def test_outside_money_reduces_debt_but_not_cash(self):
        for mode in ("modelled", "expensesCovered"):
            cash_paid, outside = self.lump("cash", mode), self.lump("outside", mode)
            self.assertEqual([r["debts"] for r in outside], [r["debts"] for r in cash_paid])
            self.assertEqual(outside[36]["cash"] - cash_paid[36]["cash"], Decimal("10000.00"))
            self.assertEqual(outside[36]["netWorth"] - cash_paid[36]["netWorth"], Decimal("10000.00"))

    def test_default_is_cash_and_bad_value_rejected(self):
        s = with_items({"type": "lumpSum", "id": "l", "mortgage": "mtg",
                        "paymentDate": "2030-01-01", "amount": "10000"})
        self.assertEqual(engine.run(s), self.lump("cash"))
        s["items"][-1]["paidFrom"] = "bank"
        with self.assertRaisesRegex(ValueError, "paidFrom"):
            engine.run(s)

    def test_form_offers_the_choice(self):
        client = Browser()
        client.get("/")
        client.scenario = copy.deepcopy(HOUSE)
        self.assertIn(b'<option value="outside">', client.get("/").data)
        client.post("/items/add", data={"type": "lumpSum", "name": "Gift", "mortgage": "mtg",
                                         "paymentDate": "2030-01-01", "amount": "10000",
                                         "paidFrom": "outside"})
        self.assertEqual(client.scenario["items"][-1]["paidFrom"], "outside")


class BaseDate(unittest.TestCase):
    def run_with(self, dollars_of):
        s = house()
        s["annualInflation"] = "0.02"
        s["dollarsOf"] = dollars_of
        return engine.run(s)

    def test_blank_means_horizon_start(self):
        self.assertEqual(self.run_with(""), self.run_with("2027-01-01"))

    def test_base_month_is_unchanged_and_earlier_months_are_inflated(self):
        rows = self.run_with("2029-01-01")
        self.assertEqual(rows[24]["realNetWorth"], rows[24]["netWorth"])          # 2029-01
        self.assertAlmostEqual(float(rows[0]["realNetWorth"]),
                               float(rows[0]["netWorth"]) * 1.02 ** 2, delta=0.01)
        self.assertAlmostEqual(float(rows[36]["realNetWorth"]),
                               float(rows[36]["netWorth"]) / 1.02, delta=0.01)

    def test_moving_the_base_scales_every_month_alike(self):
        start, later = self.run_with(""), self.run_with("2030-01-01")
        for k in (0, 100, 299):
            self.assertAlmostEqual(float(later[k]["realNetWorth"]),
                                   float(start[k]["realNetWorth"]) * 1.02 ** 3, delta=0.02)

    def test_validation_and_form(self):
        s = house()
        s["dollarsOf"] = "2026-13-01"
        with self.assertRaisesRegex(ValueError, "dollarsOf"):
            engine.run(s)
        client = Browser()
        client.get("/")
        client.scenario = copy.deepcopy(HOUSE)
        client.post("/settings", data={"name": "t", "start": "2027-01-01", "end": "2051-12-01",
                                        "openingCash": "150000", "annualInflation": "2",
                                        "dollarsOf": "2030-06-01"})
        self.assertEqual(client.scenario["dollarsOf"], "2030-06-01")
        page = client.get("/run").data
        self.assertIn(b"Net worth (2030-06 $)", page)
        self.assertIn(b"real values in dollars of 2030-06", page)


class Alignment(unittest.TestCase):
    """ADR-0045 rate ranges, ADR-0021 quarterly amounts, ADR-0029 first payment date,
    ADR-0047 penalties."""

    def test_quarterly_amount_spread_over_three_months(self):
        s = with_items({"type": "expense", "id": "q", "name": "Bonus tax", "startDate": "2027-01-01",
                        "amount": "900", "per": "quarter"})
        self.assertEqual(engine.run(house())[0]["cash"] - engine.run(s)[0]["cash"], Decimal("300.00"))

    def test_rate_ranges(self):
        s = house()
        s["items"][1]["annualRate"] = "-0.01"
        with self.assertRaisesRegex(ValueError, "annualRate must be a fraction between 0 and 1"):
            engine.run(s)
        s = house()
        s["items"][0]["annualAppreciation"] = "-0.10"      # falling prices are allowed
        self.assertLess(engine.run(s)[12]["assets"], Decimal("700000"))

    def test_first_payment_date(self):
        s = house()
        s["items"][1]["firstPaymentDate"] = "2027-03-01"
        r = engine.run_detailed(s)
        rows = r["rows"]
        self.assertEqual(rows[1]["cash"] - rows[0]["cash"], Decimal("3500.00"))   # no payment in 2027-02
        self.assertGreater(rows[1]["debts"], Decimal("560000.00"))                 # interest accrued
        # 2027-03: the interest adjustment is paid in cash, then the regular payment.
        adj = [x for x in r["ledger"] if x["kind"] == "INTEREST_ADJUSTMENT"]
        self.assertEqual([x["month"] for x in adj], ["2027-03"])
        self.assertEqual(rows[2]["cash"] - rows[1]["cash"],
                         3500 - Decimal("2882.31") - adj[0]["amount"])
        s["items"][1]["firstPaymentDate"] = "2027-01-01"
        with self.assertRaisesRegex(ValueError, "firstPaymentDate must be after"):
            engine.run(s)

    def test_penalties(self):
        base = house(end="2040-12-01")
        base["items"][0].update(saleDate="2037-01-01")
        with_penalty = copy.deepcopy(base)
        with_penalty["items"][0]["salePenalty"] = "8000"
        a, b = engine.run(base), engine.run(with_penalty)
        self.assertEqual(a[120]["cash"] - b[120]["cash"], Decimal("8000.00"))
        renew = {"type": "renewal", "id": "rn", "mortgage": "mtg", "startDate": "2030-01-01",
                 "annualRate": "0.0379"}
        r0 = engine.run(with_items(dict(renew)))
        r = engine.run(with_items(dict(renew, penalty="5000")))
        self.assertEqual(r0[36]["cash"] - r[36]["cash"], Decimal("5000.00"))
        self.assertEqual(r0[36]["debts"], r[36]["debts"])
        l = with_items({"type": "lumpSum", "id": "l", "mortgage": "mtg", "paymentDate": "2030-01-01",
                        "amount": "10000", "penalty": "300"})
        l0 = with_items({"type": "lumpSum", "id": "l", "mortgage": "mtg", "paymentDate": "2030-01-01",
                         "amount": "10000"})
        self.assertEqual(engine.run(l0)[36]["cash"] - engine.run(l)[36]["cash"], Decimal("300.00"))
        ledger = engine.run_detailed(l)["ledger"]
        self.assertIn(("PENALTY", Decimal("300.00")),
                      [(x["kind"], x["amount"]) for x in ledger if x["month"] == "2030-01"])


class Improvements(unittest.TestCase):
    def improve(self, **fields):
        item = {"type": "improvement", "id": "reno", "name": "Basement", "property": "house",
                "improvementDate": "2030-01-01", "cost": "50000"}
        item.update(fields)
        return with_items(item)

    def test_cost_from_cash_value_added_defaults_to_cost(self):
        base, rows = engine.run(house()), engine.run(self.improve())
        self.assertEqual(base[36]["cash"] - rows[36]["cash"], Decimal("50000.00"))
        self.assertEqual(rows[36]["assets"] - base[36]["assets"], Decimal("50000.00"))
        self.assertEqual(rows[36]["netWorth"], base[36]["netWorth"])

    def test_value_added_above_cost_is_a_gain(self):
        base, rows = engine.run(house()), engine.run(self.improve(valueAdded="80000"))
        self.assertEqual(rows[36]["netWorth"] - base[36]["netWorth"], Decimal("30000.00"))
        # The added value appreciates with the property afterwards.
        self.assertGreater(rows[48]["assets"] - base[48]["assets"], Decimal("80000.00"))

    def test_financed_by_a_linked_mortgage(self):
        s = self.improve(cost="300000", valueAdded="450000")
        s["items"].append({"type": "mortgage", "id": "build", "name": "Build loan",
                           "property": "house", "startDate": "2030-01-01", "principal": "300000",
                           "annualRate": "0.0379", "amortizationYears": "30"})
        base, rows = engine.run(house()), engine.run(s)
        self.assertEqual(rows[36]["cash"], base[36]["cash"])          # loan paid the build
        self.assertEqual(rows[36]["debts"] - base[36]["debts"], Decimal("300000.00"))

    def test_validation(self):
        with self.assertRaisesRegex(ValueError, "unknown property"):
            engine.run(self.improve(property="nope"))
        with self.assertRaisesRegex(ValueError, "on or after the purchase|before the horizon"):
            engine.run(self.improve(improvementDate="2026-01-01"))

    def test_baseline_lakeside_is_one_property(self):
        s = json.loads((HERE / "samples" / "household-baseline.json").read_text())
        kinds = [i["type"] for i in s["items"]]
        self.assertEqual(kinds.count("property"), 2)
        self.assertIn("improvement", kinds)
        self.assertGreaterEqual(min(r["cash"] for r in engine.run(s)), 0)


class RetirementDate(unittest.TestCase):
    def scenario(self, retire="", ends=True):
        s = house()
        s["retirementDate"] = retire
        s["items"][2]["endsAtRetirement"] = ends
        return s

    def test_salary_stops_the_month_before_retirement(self):
        rows = engine.run(self.scenario("2040-01-01"))
        k = 13 * 12                                             # 2040-01
        self.assertEqual(rows[k - 1]["cash"] - rows[k - 2]["cash"], 3500 - Decimal("2882.31"))
        self.assertEqual(rows[k]["cash"] - rows[k - 1]["cash"], -Decimal("2882.31"))

    def test_without_retirement_date_or_flag_nothing_changes(self):
        base = engine.run(house())
        self.assertEqual(engine.run(self.scenario("", True)), base)
        self.assertEqual(engine.run(self.scenario("2040-01-01", False)), base)

    def test_moving_the_retirement_date_moves_the_end(self):
        early, late = engine.run(self.scenario("2035-01-01")), engine.run(self.scenario("2045-01-01"))
        self.assertEqual(late[-1]["cash"] - early[-1]["cash"], 120 * Decimal("3500"))

    def test_form(self):
        client = Browser()
        client.get("/")
        client.scenario = copy.deepcopy(HOUSE)
        client.post("/settings", data={"name": "t", "start": "2027-01-01", "end": "2051-12-01",
                                        "openingCash": "150000", "retirementTaxRate": "20"})
        client.post("/items/add", data={"type": "retirement", "name": "Retire",
                                         "retirementDate": "2045-06-01"})
        client.post("/items/add", data={"type": "income", "name": "Job", "startDate": "2027-01-01",
                                         "amount": "100000", "per": "year", "taxable": "yes",
                                         "indexing": "none"})
        sc = client.scenario
        job, ret = sc["items"][-1]["id"], sc["items"][-2]["id"]
        client.post("/items/add", data={"type": "trigger", "name": "Job ends", "event": ret,
                                         "target": job, "action": "end"})      # ADR-0065
        sc = client.scenario
        self.assertEqual((engine.retirement_date(sc), sc["items"][-1]["action"]),
                         ("2045-06-01", "end"))
        self.assertEqual(Decimal(sc["retirementTaxRate"]), Decimal("0.2"))
        self.assertNotIn("retirementDate", sc)
        page = client.get("/run").data
        self.assertIn(b"Retirement: 2045-06", page)
        self.assertIn(b"tax switches to 20%", page)


class EndChoices(unittest.TestCase):
    """ADR-0059 amendment: an end is a date, never, or retirement, for every item with one."""

    def scenario(self, *items):
        s = with_items(*items)
        s["items"].append({"type": "retirement", "id": "ret", "name": "Retire",
                           "retirementDate": "2035-01-01"})
        return s

    def test_extra_payment_and_pension_end_at_retirement(self):
        r = engine.run_detailed(self.scenario(
            {"type": "extraPayment", "id": "x", "mortgage": "mtg", "startDate": "2028-01-01",
             "monthlyAmount": "500", "endsAtRetirement": True},
            {"type": "pension", "id": "bridge", "name": "Bridge", "amount": "1000",
             "startDate": "2033-01-01", "endsAtRetirement": True}))
        months = lambda src: [x["month"] for x in r["ledger"] if x["source"] == src]
        self.assertEqual(months("x")[-1], "2034-12")
        self.assertEqual(months("bridge")[0], "2033-01")
        pay = [x["month"] for x in r["ledger"] if x["kind"] == "PENSION_PAYMENT"]
        self.assertEqual(pay[-1], "2034-12")

    def test_pension_starting_at_retirement_cannot_end_there(self):
        with self.assertRaisesRegex(ValueError, "ends 2034-12, before its effective start 2035-01"):
            engine.run(self.scenario({"type": "pension", "id": "db", "name": "DB",
                                      "amount": "1000", "endsAtRetirement": True}))

    def test_form_end_is_a_date_or_a_trigger(self):
        # ADR-0065: a blank endDate means never; ending at retirement is a trigger.
        client = Browser()
        client.get("/")
        client.scenario = self.scenario()
        add = lambda **f: client.post("/items/add", data={
            "type": "expense", "name": "E", "startDate": "2028-01-01",
            "amount": "100", "per": "month", "indexing": "none", **f})
        add(endDate="")
        add(endDate="2030-01-01")
        items = client.scenario["items"]
        self.assertEqual([i["endDate"] for i in items[-2:]], ["", "2030-01-01"])
        client.post("/items/add", data={"type": "trigger", "name": "Stop", "event": "ret",
                                         "target": items[-2]["id"], "action": "end"})
        paid = [x["month"] for x in engine.run_detailed(client.scenario)["ledger"]
                if x["source"] == items[-2]["id"]]
        self.assertEqual(paid[-1], "2034-12")
        self.assertIn("action=end (month before)", client.get("/").data.decode())


class AmountInBaseDollars(unittest.TestCase):
    """ADR-0013 amendment: a future expense stated in today's (base-date) dollars."""

    def scenario(self, amount_in, indexing="none", start="2030-01-01"):
        return plain(annualInflation="0.02", dollarsOf="2027-01-01",
                     items=[{"type": "expense", "id": "e", "name": "Retired living",
                             "startDate": start, "amount": "4000", "amountIn": amount_in,
                             "indexing": indexing}])

    def paid(self, s):
        return {x["month"]: x["amount"] for x in engine.run_detailed(s)["ledger"]
                if x["kind"] == "EXPENSE"}

    def test_start_dollars_is_the_default(self):
        self.assertEqual(self.paid(self.scenario("start"))["2030-01"], Decimal("4000.00"))
        self.assertEqual(self.paid(self.scenario(""))["2030-01"], Decimal("4000.00"))

    def test_base_dollars_inflated_to_the_start(self):
        p = self.paid(self.scenario("base"))
        self.assertEqual(p["2030-01"], money(Decimal(4000) * Decimal("1.02") ** 3))
        self.assertEqual(p["2031-01"], p["2030-01"])                  # not indexed after
        p = self.paid(self.scenario("base", "inflation"))
        self.assertEqual(p["2031-01"], money(Decimal(4000) * Decimal("1.02") ** 3 * Decimal("1.02")))

    def test_real_value_at_start_equals_todays_amount(self):
        s = self.scenario("base", start="2031-07-01")
        expense = self.paid(s)["2031-07"]
        self.assertAlmostEqual(float(expense) / 1.02 ** 4.5, 4000, delta=0.01)

    def test_validation_and_form(self):
        with self.assertRaisesRegex(ValueError, "amountIn must be start or base"):
            engine.run(self.scenario("today"))
        client = Browser()
        client.get("/")
        client.scenario = plain()
        client.post("/items/add", data={"type": "expense", "name": "Retired", "starts": "date",
                                         "startDate": "2030-01-01", "ends": "never",
                                         "amount": "4000", "per": "month", "amountIn": "base",
                                         "indexing": "inflation"})
        self.assertEqual(client.scenario["items"][-1]["amountIn"], "base")
        self.assertIn("amountIn=today&#39;s $", client.get("/").data.decode())


class SaleAtRetirement(unittest.TestCase):
    """ADR-0059 amendment: a sale may happen in the retirement month."""

    def scenario(self, retire="2035-01-01", **sale):
        s = with_items({"type": "sale", "id": "sell", "name": "Downsize", "property": "house",
                        **sale})
        if retire:
            s["items"].append({"type": "retirement", "id": "ret", "retirementDate": retire})
        return s

    def sold_in(self, s):
        return next(x["month"] for x in engine.run_detailed(s)["ledger"] if x["kind"] == "SALE")

    def test_same_as_a_dated_sale_and_moves_with_retirement(self):
        at = self.scenario(atRetirement=True)
        dated = self.scenario(saleDate="2035-01-01")
        self.assertEqual(engine.run(at), engine.run(dated))
        self.assertEqual(self.sold_in(self.scenario("2040-06-01", atRetirement=True)), "2040-06")

    def test_validation(self):
        with self.assertRaisesRegex(ValueError, "no retirement event"):
            engine.run(self.scenario("", atRetirement=True))
        with self.assertRaisesRegex(ValueError, "saleDate or atRetirement, not both"):
            engine.run(self.scenario(atRetirement=True, saleDate="2035-01-01"))
        with self.assertRaisesRegex(ValueError, "missing field 'saleDate'"):
            engine.run(self.scenario())
        s = self.scenario(atRetirement=True)                  # renewal after the sale month
        s["items"].append({"type": "renewal", "id": "rn", "mortgage": "mtg",
                           "startDate": "2036-01-01", "annualRate": "0.05"})
        with self.assertRaisesRegex(ValueError, "after the sale of House"):
            engine.run(s)

    def test_form(self):
        client = Browser()
        client.get("/")
        client.scenario = self.scenario()
        client.scenario["items"] = [i for i in client.scenario["items"] if i["type"] != "sale"]
        # ADR-0065: without a date the sale is kept switched off until a trigger dates it.
        page = client.post("/items/add", data={"type": "sale", "name": "Downsize",
                                                "property": "house", "saleDate": ""},
                           follow_redirects=True).data.decode()
        self.assertIn("Added switched off: add a trigger that sets its saleDate", page)
        item = client.scenario["items"][-1]
        self.assertEqual((item["enabled"], item["saleDate"]), (False, ""))
        ret = next(i["id"] for i in client.scenario["items"] if i["type"] == "retirement")
        client.post("/items/add", data={"type": "trigger", "name": "At retirement",
                                         "event": ret, "target": item["id"], "action": "start"})
        item = next(i for i in client.scenario["items"] if i["id"] == item["id"])
        self.assertNotIn("enabled", item)                     # switched on by the trigger
        self.assertIn("SALE", {x["kind"] for x in engine.run_detailed(client.scenario)["ledger"]})


class LumpSumAtRetirement(unittest.TestCase):
    """ADR-0059 amendment: a lump sum at retirement, and a full payoff."""

    def scenario(self, retire="2035-01-01", **lump):
        s = with_items({"type": "lumpSum", "id": "l", "name": "Pay off", "mortgage": "mtg",
                        **lump})
        if retire:
            s["items"].append({"type": "retirement", "id": "ret", "retirementDate": retire})
        return s

    def test_pay_off_at_retirement_clears_the_loan(self):
        r = engine.run_detailed(self.scenario(atRetirement=True, payOff=True))
        k = 96                                                 # 2035-01
        self.assertGreater(r["rows"][k - 1]["debts"], 0)
        self.assertEqual(r["rows"][k]["debts"], Decimal("0.00"))
        pre = [x for x in r["ledger"] if x["kind"] == "PREPAYMENT"]
        self.assertEqual([x["month"] for x in pre], ["2035-01"])

    def test_same_as_dated_amount(self):
        a = engine.run(self.scenario(atRetirement=True, amount="50000"))
        b = engine.run(self.scenario(paymentDate="2035-01-01", amount="50000"))
        self.assertEqual(a, b)

    def test_validation(self):
        with self.assertRaisesRegex(ValueError, "no retirement event"):
            engine.run(self.scenario("", atRetirement=True, payOff=True))
        with self.assertRaisesRegex(ValueError, "amount or payOff, not both"):
            engine.run(self.scenario(paymentDate="2035-01-01", payOff=True, amount="5"))
        with self.assertRaisesRegex(ValueError, "paymentDate or atRetirement, not both"):
            engine.run(self.scenario(paymentDate="2035-01-01", atRetirement=True, payOff=True))
        with self.assertRaisesRegex(ValueError, "missing field 'paymentDate'"):
            engine.run(self.scenario(payOff=True))

    def test_form(self):
        client = Browser()
        client.get("/")
        client.scenario = self.scenario(paymentDate="2030-01-01", amount="1000")
        client.post("/items/add", data={"type": "lumpSum", "name": "Pay off", "mortgage": "mtg",
                                         "paymentDate": "", "covers": "all", "amount": "5",
                                         "paidFrom": "cash"})
        item = client.scenario["items"][-1]
        self.assertEqual((item["enabled"], item["paymentDate"], item["payOff"], item["amount"]),
                         (False, "", True, ""))
        client.post("/items/add", data={"type": "trigger", "name": "At retirement",
                                         "event": "ret", "target": item["id"], "action": "start"})
        page = client.get("/").data.decode()
        self.assertIn("covers=whole balance", page)
        self.assertNotIn("(off)", page)


class OneOffTransfer(unittest.TestCase):
    """ADR-0025 one-off transfer from cash into an account; at retirement (ADR-0059)."""

    def scenario(self, kind="rrsp", retire="2030-01-01", **t):
        s = plain()
        s["items"] += [account(kind, balance="0", ret="0"),
                       {"type": "transfer", "id": "t", "name": "Top up", "account": "acct",
                        "amount": "50000", **t}]
        if retire:
            s["items"].append({"type": "retirement", "id": "ret", "retirementDate": retire})
        return s

    def test_moves_cash_into_the_account_at_retirement(self):
        r = engine.run_detailed(self.scenario("tfsa", atRetirement=True))
        k = 36                                                 # 2030-01
        self.assertEqual(r["rows"][k - 1]["investments"], Decimal("0.00"))
        self.assertEqual(r["rows"][k]["investments"], Decimal("50000.00"))
        self.assertEqual(r["rows"][k]["netWorth"] - r["rows"][k - 1]["netWorth"],
                         r["rows"][k - 1]["netWorth"] - r["rows"][k - 2]["netWorth"])
        self.assertEqual(engine.run(self.scenario("tfsa", transferDate="2030-01-01")), r["rows"])

    def test_into_an_rrsp_is_a_deduction(self):
        tax = lambda s: next(x["amount"] for x in engine.run_detailed(s)["ledger"]
                             if x["kind"] == "TAX" and x["month"] == "2028-01")
        self.assertEqual(tax(self.scenario("tfsa", transferDate="2028-01-01", amount="1000")),
                         Decimal("1800.00"))
        self.assertEqual(tax(self.scenario("rrsp", transferDate="2028-01-01", amount="1000")),
                         Decimal("1500.00"))                   # (6000 - 1000) x 30%

    def test_validation(self):
        with self.assertRaisesRegex(ValueError, "no retirement event"):
            engine.run(self.scenario(retire="", atRetirement=True))
        with self.assertRaisesRegex(ValueError, "transferDate or atRetirement, not both"):
            engine.run(self.scenario(atRetirement=True, transferDate="2030-01-01"))
        with self.assertRaisesRegex(ValueError, "missing field 'transferDate'"):
            engine.run(self.scenario())
        with self.assertRaisesRegex(ValueError, "amount must be positive"):
            engine.run(self.scenario(transferDate="2030-01-01", amount="0"))

    def test_form(self):
        client = Browser()
        client.get("/")
        client.scenario = self.scenario(transferDate="2029-01-01")
        client.post("/items/add", data={"type": "transfer", "name": "Proceeds", "account": "acct",
                                         "transferDate": "", "amount": "300000"})
        item = client.scenario["items"][-1]
        self.assertEqual((item["enabled"], item["transferDate"]), (False, ""))
        client.post("/items/add", data={"type": "trigger", "name": "At retirement",
                                         "event": "ret", "target": item["id"], "action": "start"})
        self.assertIn("Proceeds", client.get("/").data.decode())
        self.assertNotIn("enabled", client.scenario["items"][-2])


class DeductionCarryForward(unittest.TestCase):
    """C-P2 revisited (ADR-0048): unused deductions carry forward; tax never negative."""

    def test_large_rrsp_transfer_shelters_later_months(self):
        s = plain()                                       # salary 6000 taxable at 30%
        s["items"] += [account(balance="0", ret="0"),
                       {"type": "transfer", "id": "t", "account": "acct",
                        "transferDate": "2027-01-01", "amount": "15000"}]
        paid = {x["month"]: x["amount"] for x in engine.run_detailed(s)["ledger"]
                if x["kind"] == "TAX"}
        # 15000 of deductions: 6000 used in Jan, 6000 in Feb, 3000 in Mar.
        self.assertNotIn("2027-01", paid)                 # no tax, and no cash credit
        self.assertNotIn("2027-02", paid)
        self.assertEqual(paid["2027-03"], Decimal("900.00"))   # (6000 - 3000) x 30%
        self.assertEqual(paid["2027-04"], Decimal("1800.00"))  # pool used up
        tax = engine.run_detailed(s)["tax"]
        self.assertEqual((tax["2027-01"]["deductions"], tax["2027-01"]["poolOut"]),
                         (Decimal("15000.00"), Decimal("9000.00")))
        self.assertEqual((tax["2027-02"]["poolIn"], tax["2027-02"]["used"], tax["2027-02"]["poolOut"]),
                         (Decimal("9000.00"), Decimal("6000.00"), Decimal("3000.00")))

    def test_ledger_page_shows_the_pool(self):
        s = plain()
        s["items"] += [account(balance="0", ret="0"),
                       {"type": "transfer", "id": "t", "account": "acct",
                        "transferDate": "2027-01-01", "amount": "15000"}]
        client = Browser()
        client.get("/")
        client.scenario = s
        page = client.get("/run/ledger?month=2027-02").data.decode()
        self.assertIn("Deduction pool carried forward", page)
        self.assertIn("3,000.00", page)


class RetirementEvent(unittest.TestCase):
    """ADR-0059: one event triggers everything tied to retirement, and the tax rate."""

    def scenario(self, **over):
        s = plain(effectiveTaxRate="0.30", annualInflation="0", **over)
        s["items"][0]["endsAtRetirement"] = True
        s["items"] += [
            {"type": "retirement", "id": "ret", "name": "Retire", "retirementDate": "2030-01-01"},
            {"type": "pension", "id": "db", "name": "DB", "amount": "2000"},
            account(ret="0", withdrawalTaxRate=""),
            {"type": "withdrawal", "id": "w", "account": "acct", "method": "amount",
             "amount": "1000"}]
        return s

    def test_same_as_the_old_setting(self):
        s = self.scenario()
        old = copy.deepcopy(s)
        old["items"] = [i for i in old["items"] if i["type"] != "retirement"]
        old["retirementDate"] = "2030-01-01"
        self.assertEqual(engine.run(s), engine.run(old))

    def test_pension_and_withdrawal_without_start_begin_at_retirement(self):
        r = engine.run_detailed(self.scenario())
        first = lambda kind: next(x["month"] for x in r["ledger"] if x["kind"] == kind)
        self.assertEqual((first("PENSION_PAYMENT"), first("WITHDRAWAL")), ("2030-01", "2030-01"))
        last_salary = [x["month"] for x in r["ledger"] if x["kind"] == "INCOME"][-1]
        self.assertEqual(last_salary, "2029-12")

    def test_tax_switches_to_the_retirement_rate(self):
        tax = lambda s: {x["month"]: x["amount"] for x in engine.run_detailed(s)["ledger"]
                         if x["kind"] == "TAX"}
        same = tax(self.scenario())
        lower = tax(self.scenario(retirementTaxRate="0.20"))
        self.assertEqual(lower["2029-12"], Decimal("1800.00"))       # salary 6000 at 30%
        self.assertEqual(same["2030-01"], Decimal("900.00"))         # (2000 + 1000) at 30%
        self.assertEqual(lower["2030-01"], Decimal("600.00"))        # (2000 + 1000) at 20%

    def test_account_own_withdrawal_rate_still_wins(self):
        s = self.scenario(retirementTaxRate="0.20")
        s["items"][3]["withdrawalTaxRate"] = "0.10"
        tax = next(x["amount"] for x in engine.run_detailed(s)["ledger"]
                   if x["kind"] == "TAX" and x["month"] == "2030-01")
        self.assertEqual(tax, Decimal("500.00"))                     # 2000 x 20% + 1000 x 10%

    def test_validation(self):
        s = self.scenario()
        s["items"].append({"type": "retirement", "id": "r2", "retirementDate": "2031-01-01"})
        with self.assertRaisesRegex(ValueError, "only one retirement event"):
            engine.run(s)
        s = self.scenario(retirementDate="2030-01-01")
        with self.assertRaisesRegex(ValueError, "both a retirement event and a retirementDate"):
            engine.run(s)
        s = self.scenario()
        s["items"] = [i for i in s["items"] if i["type"] not in ("retirement", "pension")]
        with self.assertRaisesRegex(ValueError, "w: needs a startDate or a retirement event"):
            engine.run(s)
        with self.assertRaisesRegex(ValueError, "retirementTaxRate must be a fraction"):
            engine.run(self.scenario(retirementTaxRate="20"))
        s = self.scenario()
        s["items"][1]["retirementDate"] = "2050-01-01"
        with self.assertRaisesRegex(ValueError, "within the horizon"):
            engine.run(s)

    def test_loading_an_older_file_makes_the_event(self):
        import io
        s = self.scenario()
        s["items"] = [i for i in s["items"] if i["type"] != "retirement"]
        s["retirementDate"] = "2030-01-01"
        client = Browser()
        client.get("/")
        client.post("/load", data={"file": (io.BytesIO(json.dumps(s).encode()), "old.json")},
                    content_type="multipart/form-data")
        sc = client.scenario
        self.assertNotIn("retirementDate", sc)
        self.assertEqual([i["retirementDate"] for i in sc["items"] if i["type"] == "retirement"],
                         ["2030-01-01"])


def plain(**over):
    """A scenario with only cash and a taxable salary, for account tests."""
    s = {"schemaVersion": 1, "name": "plain",
         "horizon": {"start": "2027-01-01", "end": "2036-12-01"},
         "openingCash": "0", "effectiveTaxRate": "0.30",
         "items": [{"type": "income", "id": "job", "name": "Job", "startDate": "2027-01-01",
                    "amount": "6000", "per": "month", "taxable": True}]}
    s.update(over)
    return s


def account(kind="rrsp", balance="100000", ret="0.06", **extra):
    a = {"type": "account", "id": "acct", "name": kind.upper(), "accountType": kind,
         "openingBalance": balance, "annualReturn": ret}
    a.update(extra)
    return a


class Accounts(unittest.TestCase):
    def test_opening_balance_grows_from_the_first_month(self):
        rows = engine.run(plain(items=[account(ret="0.06")]))
        self.assertAlmostEqual(float(rows[11]["investments"]), 100000 * 1.06, delta=0.10)
        self.assertEqual(rows[0]["netWorth"], rows[0]["cash"] + rows[0]["investments"])

    def test_rrsp_contribution_is_deducted_and_matched(self):
        s = plain()
        s["items"] += [account(balance="0", ret="0"),
                       {"type": "contribution", "id": "c", "account": "acct",
                        "startDate": "2027-01-01", "amount": "900", "employerMatch": "0.5"}]
        rows = engine.run(s)
        # Salary 6000 taxed at 30% on (6000 - 900): cash = 6000 - 900 - 1530.
        self.assertEqual(rows[0]["cash"], Decimal("3570.00"))
        self.assertEqual(rows[0]["investments"], Decimal("1350.00"))   # 900 + 450 match

    def test_tfsa_contribution_is_not_deducted(self):
        s = plain()
        s["items"] += [account("tfsa", balance="0", ret="0"),
                       {"type": "contribution", "id": "c", "account": "acct",
                        "startDate": "2027-01-01", "amount": "900"}]
        self.assertEqual(engine.run(s)[0]["cash"], Decimal("3300.00"))  # 6000 - 900 - 1800

    def test_rrsp_withdrawal_is_taxed_tfsa_is_not(self):
        for kind, expected in (("rrsp", "2800.00"), ("tfsa", "4000.00")):
            s = plain(items=[account(kind, ret="0"),
                             {"type": "withdrawal", "id": "w", "account": "acct",
                              "startDate": "2027-01-01", "method": "amount", "amount": "4000"}])
            self.assertEqual(engine.run(s)[0]["cash"], Decimal(expected), kind)

    def test_own_withdrawal_tax_rate(self):
        s = plain(items=[account(ret="0", withdrawalTaxRate="0.20"),
                         {"type": "withdrawal", "id": "w", "account": "acct",
                          "startDate": "2027-01-01", "method": "amount", "amount": "4000"}])
        self.assertEqual(engine.run(s)[0]["cash"], Decimal("3200.00"))

    def test_percent_withdrawal_resets_yearly(self):
        s = plain(items=[account("tfsa", ret="0.10"),
                         {"type": "withdrawal", "id": "w", "account": "acct",
                          "startDate": "2027-01-01", "method": "percent", "annualRate": "0.04"}])
        r = engine.run_detailed(s)
        w = [x["amount"] for x in r["ledger"] if x["kind"] == "WITHDRAWAL"]
        self.assertEqual(w[0], Decimal("333.33"))             # 100000 x 4% / 12
        self.assertEqual(w[11], w[0])                          # same all year
        self.assertGreater(w[12], w[0])                        # reset on the anniversary

    def test_even_drawdown_empties_the_account(self):
        s = plain(items=[account("tfsa", balance="12000", ret="0"),
                         {"type": "withdrawal", "id": "w", "account": "acct",
                          "startDate": "2036-01-01", "method": "even"}])
        rows = engine.run(s)
        self.assertEqual(rows[-1]["investments"], Decimal("0.00"))
        self.assertEqual(rows[-12]["investments"], Decimal("11000.00"))

    def test_non_registered_returns_are_taxed(self):
        s = plain(items=[account("nonRegistered", ret="0.12")])
        r = engine.run_detailed(s)
        ret = next(x["amount"] for x in r["ledger"] if x["kind"] == "RETURN")
        self.assertEqual(r["rows"][0]["cash"], money(Decimal(0) - ret * Decimal("0.30")))

    def test_income_less_mode(self):
        s = plain(incomeMode="expensesCovered")
        s["items"] += [account(ret="0"),
                       {"type": "contribution", "id": "c", "account": "acct",
                        "startDate": "2027-01-01", "amount": "900", "employerMatch": "0.5"},
                       {"type": "withdrawal", "id": "w", "account": "acct",
                        "startDate": "2027-01-01", "method": "amount", "amount": "1000"}]
        rows = engine.run(s)
        # Contribution covered, match from outside, withdrawal moved to cash and taxed.
        self.assertEqual(rows[0]["investments"], Decimal("100350.00"))
        self.assertEqual(rows[0]["cash"], Decimal("700.00"))

    def test_validation_and_cascade(self):
        with self.assertRaisesRegex(ValueError, "accountType"):
            engine.run(plain(items=[account("roth")]))
        with self.assertRaisesRegex(ValueError, "unknown account"):
            engine.run(plain(items=[{"type": "withdrawal", "account": "x",
                                     "startDate": "2027-01-01", "method": "even"}]))
        client = Browser()
        client.get("/")
        client.scenario = plain(items=[account()])
        client.post("/items/add", data={"type": "contribution", "name": "RRSP", "account": "acct",
                                         "startDate": "2027-01-01", "amount": "900", "per": "month",
                                         "employerMatch": "50", "ends": "retirement",
                                         "indexing": "none"})
        item = client.scenario["items"][-1]
        self.assertEqual(Decimal(item["employerMatch"]), Decimal("0.5"))
        self.assertIn(b"<th>Investments</th>", client.get("/run").data)
        client.post("/items/acct/delete")
        self.assertEqual(client.scenario["items"], [])


class PhaseZeroWithdrawals(unittest.TestCase):
    """C-M1: percent withdrawal on an empty or unopened account."""

    def test_empty_account_gives_zero_without_crash(self):
        s = plain(items=[account("tfsa", balance="0", ret="0"),
                         {"type": "withdrawal", "id": "w", "account": "acct",
                          "startDate": "2027-01-01", "method": "percent", "annualRate": "0.04"},
                         {"type": "contribution", "id": "c", "account": "acct",
                          "startDate": "2027-03-01", "amount": "1000"}])
        r = engine.run_detailed(s)
        w = {x["month"]: x["amount"] for x in r["ledger"] if x["kind"] == "WITHDRAWAL"}
        self.assertNotIn("2027-06", w)                  # 0 for the first year
        self.assertEqual(w["2028-01"], money(Decimal("10000") * Decimal("0.04") / 12))

    def test_cannot_start_before_the_account_opens(self):
        s = plain(items=[account("tfsa", openedDate="2028-01-01", openingFrom="cash"),
                         {"type": "withdrawal", "id": "w", "account": "acct",
                          "startDate": "2027-01-01", "method": "percent", "annualRate": "0.04"}])
        with self.assertRaisesRegex(ValueError, "before its account TFSA opens 2028-01"):
            engine.run(s)


class PhaseZeroWithdrawalIndexing(unittest.TestCase):
    """C-M16: indexing is rejected on percent withdrawals (and on "even" in older files);
    a fixed amount or an annuity can be indexed (ADR-0039 amendment 2026-11-11)."""

    def test_rejected_on_percent_and_even(self):
        for method, extra in (("percent", {"annualRate": "0.04"}), ("even", {})):
            w = {"type": "withdrawal", "id": "w", "account": "acct", "startDate": "2027-01-01",
                 "method": method, "indexing": "inflation", **extra}
            with self.assertRaisesRegex(ValueError, "indexing applies only to methods 'amount' "
                                                    "and 'annuity'"):
                engine.run(plain(items=[account("tfsa"), w]))
            w["indexing"] = "none"
            engine.run(plain(items=[account("tfsa"), w]))
        for extra in ({"method": "amount", "amount": "500"}, {"method": "annuity"}):
            engine.run(plain(items=[account("tfsa"),
                                    {"type": "withdrawal", "id": "w", "account": "acct",
                                     "startDate": "2027-01-01", "indexing": "inflation",
                                     **extra}]))


class AnnuityWithdrawal(unittest.TestCase):
    """ADR-0039 amendment 2026-11-11: method annuity spends the account down by the end of
    the draw; with indexing the payment keeps its purchasing power."""

    def draws(self, indexing="none", **acct):
        s = plain(annualInflation="0.02",
                  items=[account("tfsa", **acct),
                         {"type": "withdrawal", "id": "w", "account": "acct",
                          "startDate": "2027-01-01", "method": "annuity", "indexing": indexing}])
        r = engine.run_detailed(s)
        return [x["amount"] for x in r["ledger"] if x["kind"] == "WITHDRAWAL"], r["rows"]

    def test_factor_equals_the_plain_sum(self):
        from state_machine.flows.withdrawal import annuity_factor
        for r, g, n in ((Decimal("0.005"), Decimal("0.02"), 125), (Decimal("0.004"), 0, 120),
                        (Decimal(0), Decimal("0.03"), 30), (Decimal(0), Decimal(0), 7)):
            v = 1 / (1 + r)
            total = sum((1 + g) ** (k // 12) * v ** (k + 1) for k in range(n))
            self.assertAlmostEqual(annuity_factor(r, Decimal(g), n), total, places=20)
        # q = 1: growth equal to the yearly discount.
        r = Decimal("0.005")
        g = (1 + r) ** 12 - 1
        v = 1 / (1 + r)
        total = sum((1 + g) ** (k // 12) * v ** (k + 1) for k in range(30))
        self.assertAlmostEqual(annuity_factor(r, g, 30), total, places=20)

    def test_level_annuity_empties_the_account(self):
        w, rows = self.draws()
        self.assertEqual(len(w), 120)
        self.assertEqual(w[12], w[0])                       # level payment
        self.assertEqual(w[0], money(Decimal("100000") * (Decimal("1.06") ** (Decimal(1) / 12) - 1)
                                     / (1 - (Decimal("1.06") ** (Decimal(1) / 12)) ** -120)))
        # About one month's return is left (credited after the final withdrawal).
        self.assertLess(rows[-1]["investments"], w[-1] * Decimal("0.01"))

    def test_indexed_annuity_keeps_purchasing_power(self):
        w, rows = self.draws("inflation")
        self.assertEqual(w[11], w[0])                       # fixed within the year
        for year in range(1, 9):
            self.assertAlmostEqual(float(w[12 * year] / w[12 * (year - 1)]), 1.02, places=4)
        self.assertLess(w[0], self.draws()[0][0])           # starts below the level annuity
        self.assertLess(rows[-1]["investments"], w[-1] * Decimal("0.01"))

    def test_same_month_transfer_counts_and_even_is_an_unindexed_annuity(self):
        items = [account("tfsa", balance="0", ret="0.05"),
                 {"type": "transfer", "id": "x", "account": "acct", "amount": "50000",
                  "transferDate": "2030-01-01"},
                 {"type": "withdrawal", "id": "w", "account": "acct",
                  "startDate": "2030-01-01", "method": "annuity"}]
        annuity = engine.run_detailed(plain(items=items))
        w = [x for x in annuity["ledger"] if x["kind"] == "WITHDRAWAL"]
        self.assertEqual(w[0]["month"], "2030-01")
        self.assertGreater(w[0]["amount"], Decimal("500"))   # 50000 over 84 months
        items[2]["method"] = "even"
        self.assertEqual(engine.run_detailed(plain(items=items))["ledger"], annuity["ledger"])

    def test_app_loads_even_as_annuity(self):
        s = plain(items=[account("tfsa"), {"type": "withdrawal", "id": "w", "account": "acct",
                                            "startDate": "2030-01-01", "method": "even"}])
        client = Browser()
        client.post("/load", data={"file": (io.BytesIO(json.dumps(s).encode()), "old.json")},
                    content_type="multipart/form-data")
        self.assertEqual(client.scenario["items"][-1]["method"], "annuity")


class PhaseZeroSales(unittest.TestCase):
    """C-M2: a sale before the horizon start is rejected, not silently skipped."""

    def test_sale_before_the_horizon_is_rejected(self):
        s = house()
        s["items"].append({"type": "property", "id": "old", "name": "Old house",
                           "purchaseDate": "2010-01-01", "price": "300000",
                           "annualAppreciation": "0.03"})
        s["items"].append({"type": "sale", "id": "sell", "property": "old",
                           "saleDate": "2018-05-01"})
        with self.assertRaisesRegex(ValueError, "Old house on 2018-05 is before the horizon "
                                                "start 2027-01; remove the asset"):
            engine.run(s)


class PhaseZeroTax(unittest.TestCase):
    """C-M9: a non-registered loss does not reduce tax on salary."""

    def test_negative_return_gives_no_credit(self):
        s = plain(effectiveTaxRate="0.30",
                  items=[account("nonRegistered", balance="1000000", ret="-0.10")])
        s["items"].append({"type": "income", "id": "job", "name": "Job",
                           "startDate": "2027-01-01", "amount": "10000", "taxable": True})
        r = engine.run_detailed(s)
        tax = next(x["amount"] for x in r["ledger"] if x["kind"] == "TAX")
        self.assertEqual(tax, Decimal("3000.00"))       # 30% of the salary only


class PhaseZeroFirstPayment(unittest.TestCase):
    """C-M6: a late first payment is not a balloon at the end."""

    def test_no_balloon_and_interest_adjustment_paid(self):
        s = house(end="2052-12-01")
        s["items"][1]["firstPaymentDate"] = "2027-07-01"      # 5 months of interest only
        r = engine.run_detailed(s)
        pays = [x for x in r["ledger"] if x["kind"] == "LOAN_PAYMENT"]
        self.assertEqual(len(pays), 300)                       # amortisation from the first payment
        self.assertEqual(pays[0]["amount"], Decimal("2882.31"))
        self.assertLess(pays[-1]["amount"], Decimal("2883"))  # no balloon
        adj = next(x for x in r["ledger"] if x["kind"] == "INTEREST_ADJUSTMENT")
        interest = [x["amount"] for x in r["ledger"]
                    if x["kind"] == "LOAN_INTEREST" and x["month"] < "2027-07"]
        self.assertEqual(adj["amount"], sum(interest))
        self.assertEqual(adj["from"], "cash")


class PhaseZeroAccountOpening(unittest.TestCase):
    """C-M4 (ADR-0057): an account opened inside the horizon states its balance's source."""

    def scenario(self, source):
        return plain(items=[account("tfsa", balance="50000", ret="0",
                                    openedDate="2030-01-01", openingFrom=source)])

    def test_source_required(self):
        with self.assertRaisesRegex(ValueError, "set openingFrom: cash"):
            engine.run(self.scenario(""))
        with self.assertRaisesRegex(ValueError, "openingFrom must be cash or outside"):
            engine.run(self.scenario("bank"))

    def test_from_cash_moves_cash(self):
        rows = engine.run(self.scenario("cash"))
        k = 36                                                 # 2030-01
        self.assertEqual(rows[k]["investments"], Decimal("50000.00"))
        self.assertEqual(rows[k]["netWorth"] - rows[k - 1]["netWorth"],
                         rows[1]["netWorth"] - rows[0]["netWorth"])   # no jump

    def test_from_outside_adds_to_net_worth(self):
        r = engine.run_detailed(self.scenario("outside"))
        k = 36
        jump = r["rows"][k]["netWorth"] - r["rows"][k - 1]["netWorth"]
        self.assertEqual(jump - (r["rows"][1]["netWorth"] - r["rows"][0]["netWorth"]),
                         Decimal("50000.00"))
        self.assertTrue([x for x in r["ledger"] if x["kind"] == "OPENING_BALANCE"])

    def test_not_needed_at_the_horizon_start(self):
        engine.run(plain(items=[account("tfsa", balance="50000")]))


class PhaseZeroRenewalAndSale(unittest.TestCase):
    """C-M10: a renewal in or after the month of the sale is rejected."""

    def scenario(self, renew):
        return with_items({"type": "sale", "id": "sell", "property": "house",
                           "saleDate": "2032-01-01", "salePenalty": "5000"},
                          {"type": "renewal", "id": "rn", "mortgage": "mtg", "startDate": renew,
                           "annualRate": "0.05", "penalty": "3000"})

    def test_same_month_rejected(self):
        with self.assertRaisesRegex(ValueError, "House mortgage on 2032-01 is in the same month "
                                                "as the sale of House; remove the renewal"):
            engine.run(self.scenario("2032-01-01"))

    def test_after_the_sale_rejected(self):
        with self.assertRaisesRegex(ValueError, "is after the sale of House"):
            engine.run(self.scenario("2033-01-01"))

    def test_before_the_sale_allowed(self):
        engine.run(self.scenario("2031-01-01"))


class PhaseZeroAmortization(unittest.TestCase):
    """C-M11: amortization must be a whole number of months, at least 1."""

    def test_mortgage_and_renewal(self):
        for bad in ("0", "0.05", "1.01", "-1"):
            s = house()
            s["items"][1]["amortizationYears"] = bad
            with self.assertRaisesRegex(ValueError, "whole number of months", msg=bad):
                engine.run(s)
            s = with_items({"type": "renewal", "id": "rn", "mortgage": "mtg",
                            "startDate": "2032-01-01", "annualRate": "0.05",
                            "amortizationYears": bad})
            with self.assertRaisesRegex(ValueError, "whole number of months", msg=bad):
                engine.run(s)
        s = house()
        s["items"][1]["amortizationYears"] = "2.5"             # 30 months is fine
        engine.run(s)


class Pensions(unittest.TestCase):
    def scenario(self, inflation="0.02", **pension):
        p = {"type": "pension", "id": "db", "name": "DB pension", "amount": "3000",
             "indexing": "inflation"}
        p.update(pension)
        s = plain(effectiveTaxRate="0.30", annualInflation=inflation,
                  retirementDate="2030-01-01")
        s["items"].append(p)
        return s

    def test_value_is_remaining_payments_in_base_date_dollars(self):
        rows = engine.run(self.scenario())
        months = 12 * 7                                        # 2030-01 .. 2036-12
        real_value = rows[0]["realNetWorth"] - money(rows[0]["cash"])
        self.assertAlmostEqual(float(real_value), 3000 * months, delta=1)
        self.assertEqual(rows[-1]["investments"], Decimal("0.00"))  # nothing left at the end

    def test_payments_start_at_retirement_indexed_and_taxed(self):
        r = engine.run_detailed(self.scenario())
        pay = [x for x in r["ledger"] if x["kind"] == "PENSION_PAYMENT"]
        self.assertEqual(pay[0]["month"], "2030-01")
        self.assertEqual(pay[0]["amount"], money(Decimal(3000) * Decimal("1.02") ** 3))
        rows = r["rows"]
        # Job salary 6000 + pension, both taxed at 30%.
        k = 36
        self.assertEqual(rows[k]["cash"] - rows[k - 1]["cash"],
                         money((Decimal(6000) + pay[0]["amount"]) * Decimal("0.7")))

    def test_own_start_and_end_dates(self):
        r = engine.run_detailed(self.scenario(startDate="2032-01-01", endDate="2033-12-01"))
        pay = [x["month"] for x in r["ledger"] if x["kind"] == "PENSION_PAYMENT"]
        self.assertEqual((pay[0], pay[-1], len(pay)), ("2032-01", "2033-12", 24))

    def test_payments_continue_in_income_less_mode(self):
        s = self.scenario()
        s["incomeMode"] = "expensesCovered"
        rows = engine.run(s)
        self.assertGreater(rows[36]["cash"], rows[35]["cash"])

    def test_member_contribution_is_deducted_value_unchanged(self):
        s = self.scenario()
        base = engine.run(s)
        s["items"].append({"type": "contribution", "id": "c", "account": "db",
                           "startDate": "2027-01-01", "amount": "500", "endsAtRetirement": True})
        rows = engine.run(s)
        self.assertEqual(base[0]["cash"] - rows[0]["cash"], Decimal("350.00"))   # 500 less 30%
        self.assertEqual(rows[0]["investments"], base[0]["investments"])
        # Booked cash -> outside, with no revaluation pair on the pension (C-M14).
        r = engine.run_detailed(s)
        jan = [x for x in r["ledger"] if x["month"] == "2027-01"]
        paid = [x for x in jan if x["kind"] == "PENSION_CONTRIBUTION"]
        self.assertEqual([(x["from"], x["to"], x["amount"]) for x in paid],
                         [("cash", None, Decimal("500.00"))])
        self.assertFalse([x for x in jan if x["to"] == "db" and x["kind"] == "CONTRIBUTION"])

    def test_end_before_effective_start_rejected(self):
        with self.assertRaisesRegex(ValueError, r"ends 2029-12, before its effective start "
                                                r"2030-01 \(retirement date\)"):
            engine.run(self.scenario(endDate="2029-12-01"))
        with self.assertRaisesRegex(ValueError, "endDate is before startDate"):
            engine.run(self.scenario(startDate="2032-01-01", endDate="2031-01-01"))

    def test_needs_a_start(self):
        s = self.scenario()
        s["retirementDate"] = ""
        with self.assertRaisesRegex(ValueError, "startDate or a retirement event"):
            engine.run(s)


class DetailPages(unittest.TestCase):
    def test_mortgage_detail_splits_interest_and_principal(self):
        r = engine.run_detailed(house())
        mtg = next(h for h in r["holdings"] if h["id"] == "mtg")
        p = mtg["points"][1]                                   # 2027-02, first payment
        self.assertEqual(p["paid"], Decimal("2882.31"))
        self.assertEqual(p["interest"] + p["principalPaid"], p["paid"])
        self.assertEqual(p["opening"] - p["closing"], p["principalPaid"])

    def test_pages(self):
        client = Browser()
        client.get("/")
        client.scenario = copy.deepcopy(HOUSE)
        page = client.get("/run/holdings?id=mtg").data
        self.assertIn(b"<th>Principal paid</th>", page)
        self.assertIn(b"2,882.31", page)
        page = client.get("/run/ledger?month=2027-02").data
        self.assertIn(b"LOAN_PAYMENT", page)
        self.assertIn(b"Holdings at the end of 2027-02", page)
        house_value = engine.run(HOUSE)[1]["assets"]           # value after appreciation
        self.assertIn(f"<b>{house_value:,.2f}</b>".encode(), page)
        self.assertIn(b"House mortgage", page)
        self.assertIn(b"/run/ledger?month=2027-01", client.get("/run").data)


class SaleItem(unittest.TestCase):
    def sale(self, **fields):
        item = {"type": "sale", "id": "sell", "name": "Sell", "property": "house",
                "saleDate": "2037-01-01", "sellingCostRate": "0.05"}
        item.update(fields)
        return with_items(item, end="2040-12-01")

    def test_same_result_as_the_property_fields(self):
        old = house(end="2040-12-01")
        old["items"][0].update(saleDate="2037-01-01", sellingCostRate="0.05")
        self.assertEqual(engine.run(self.sale()), engine.run(old))

    def test_sale_pays_off_the_mortgage_and_penalty(self):
        rows = engine.run(self.sale(salePenalty="7000"))
        base = engine.run(self.sale())
        self.assertEqual((rows[120]["assets"], rows[120]["debts"]), (Decimal("0.00"), Decimal("0.00")))
        self.assertEqual(base[120]["cash"] - rows[120]["cash"], Decimal("7000.00"))
        ledger = engine.run_detailed(self.sale())["ledger"]
        self.assertEqual({x["source"] for x in ledger if x["kind"] in ("SALE", "LOAN_PAYOFF")},
                         {"sell"})

    def test_validation(self):
        with self.assertRaisesRegex(ValueError, "unknown property"):
            engine.run(self.sale(property="nope"))
        with self.assertRaisesRegex(ValueError, "saleDate must be after the purchase|"
                                                "starts after its property is sold"):
            engine.run(self.sale(saleDate="2027-01-01"))
        twice = self.sale()
        twice["items"][0]["saleDate"] = "2038-01-01"
        with self.assertRaisesRegex(ValueError, "sold more than once"):
            engine.run(twice)
        late = self.sale(saleDate="2030-01-01")
        late["items"].append({"type": "improvement", "property": "house",
                              "improvementDate": "2031-01-01", "cost": "1000"})
        with self.assertRaisesRegex(ValueError, "before the sale"):
            engine.run(late)

    def test_form_and_cascade(self):
        client = Browser()
        client.get("/")
        client.scenario = copy.deepcopy(HOUSE)
        page = client.get("/").data
        self.assertIn(b"Sale (property or vehicle)", page)
        self.assertNotIn(b"salePenalty (optional, $ on that date) (%)", page)
        self.assertNotIn(b'name="sellingCostRate"', page)     # an associated cost (ADR-0067)
        client.post("/items/add", data={"type": "sale", "name": "Sell", "property": "house",
                                         "saleDate": "2040-01-01", "salePenalty": ""})
        client.post("/items/add", data={"type": "associatedCost", "name": "Agent",
                                         "parent": "house", "at": "end", "costDate": "",
                                         "amount": "", "rate": "5", "basis": "value"})
        item = client.scenario["items"][-1]
        self.assertEqual((item["type"], Decimal(item["rate"])), ("associatedCost", Decimal("0.05")))
        self.assertNotIn("enabled", item)
        self.assertEqual(engine.run(client.scenario)[-1]["assets"], Decimal("0.00"))
        client.post("/items/house/delete")          # takes its sale and its cost along
        self.assertEqual([i["type"] for i in client.scenario["items"]], ["income"])


class MarketAdjustment(unittest.TestCase):
    def adjust(self, **fields):
        item = {"type": "marketAdjustment", "id": "adj", "name": "Crash", "property": "house",
                "adjustmentDate": "2030-01-01"}
        item.update(fields)
        return with_items(item)

    def test_percent_drop_then_normal_growth(self):
        base, rows = engine.run(house()), engine.run(self.adjust(percent="-0.15"))
        self.assertEqual(rows[35], base[35])
        opening = base[35]["assets"]
        growth = base[36]["assets"] - opening
        self.assertEqual(rows[36]["assets"], opening + money(opening * Decimal("-0.15")) + growth)
        # Afterwards it appreciates at the usual 5% from the lower value.
        self.assertAlmostEqual(float(rows[48]["assets"] / rows[36]["assets"]), 1.05, places=3)

    def test_set_value_is_the_closing_value(self):
        rows = engine.run(self.adjust(newValue="820000"))
        self.assertEqual(rows[36]["assets"], Decimal("820000.00"))
        self.assertGreater(rows[37]["assets"], Decimal("820000.00"))

    def test_value_only_cash_and_debt_unchanged(self):
        base, rows = engine.run(house()), engine.run(self.adjust(percent="0.08"))
        self.assertEqual([r["cash"] for r in rows], [r["cash"] for r in base])
        self.assertEqual([r["debts"] for r in rows], [r["debts"] for r in base])

    def test_validation_and_form(self):
        with self.assertRaisesRegex(ValueError, "either percent or newValue"):
            engine.run(self.adjust(percent="-0.1", newValue="500000"))
        with self.assertRaisesRegex(ValueError, "either percent or newValue"):
            engine.run(self.adjust())
        with self.assertRaisesRegex(ValueError, "percent must be a fraction"):
            engine.run(self.adjust(percent="-15"))
        client = Browser()
        client.get("/")
        client.scenario = copy.deepcopy(HOUSE)
        client.post("/items/add", data={"type": "marketAdjustment", "name": "Crash",
                                         "property": "house", "adjustmentDate": "2030-01-01",
                                         "percent": "-15", "newValue": ""})
        item = client.scenario["items"][-1]
        self.assertEqual(Decimal(item["percent"]), Decimal("-0.15"))
        ledger = client.get("/run/ledger?month=2030-01").data
        self.assertIn(b"MARKET_ADJUSTMENT", ledger)


class ExpensesTiedToRetirement(unittest.TestCase):
    def scenario(self, retire="2040-01-01"):
        s = house()
        s["retirementDate"] = retire
        s["items"] += [
            {"type": "expense", "id": "before", "name": "Living (working)",
             "startDate": "2027-01-01", "amount": "3000", "endsAtRetirement": True},
            {"type": "expense", "id": "after", "name": "Living (retired)",
             "startDate": "", "amount": "2000", "startsAtRetirement": True}]
        return s

    def spent(self, rows_detail, month):
        return {x["source"]: x["amount"] for x in rows_detail["ledger"]
                if x["kind"] == "EXPENSE" and x["month"] == month}

    def test_switches_at_the_retirement_date(self):
        r = engine.run_detailed(self.scenario())
        self.assertEqual(self.spent(r, "2039-12"), {"before": Decimal("3000.00")})
        self.assertEqual(self.spent(r, "2040-01"), {"after": Decimal("2000.00")})

    def test_moving_retirement_moves_the_switch(self):
        r = engine.run_detailed(self.scenario("2045-01-01"))
        self.assertEqual(self.spent(r, "2044-12"), {"before": Decimal("3000.00")})
        self.assertEqual(self.spent(r, "2045-01"), {"after": Decimal("2000.00")})

    def test_indexing_counts_from_retirement(self):
        s = self.scenario()
        s["annualInflation"] = "0.02"
        s["items"][-1]["indexing"] = "inflation"
        r = engine.run_detailed(s)
        self.assertEqual(self.spent(r, "2040-12")["after"], Decimal("2000.00"))
        self.assertEqual(self.spent(r, "2041-01")["after"], Decimal("2040.00"))

    def test_validation(self):
        s = self.scenario("")
        with self.assertRaisesRegex(ValueError, "no retirement event"):
            engine.run(s)
        s = self.scenario()
        s["items"][-1]["endsAtRetirement"] = True
        with self.assertRaisesRegex(ValueError, "both start and end"):
            engine.run(s)

    def test_form(self):
        client = Browser()
        client.get("/")
        client.scenario = engine.upgrade(self.scenario())     # as loaded: an event
        client.post("/items/add", data={"type": "expense", "name": "Travel", "startDate": "",
                                         "amount": "500", "per": "month", "indexing": "none"})
        item = client.scenario["items"][-1]
        self.assertIs(item["enabled"], False)             # waits for a trigger (ADR-0065)
        ret = next(i["id"] for i in client.scenario["items"] if i["type"] == "retirement")
        client.post("/items/add", data={"type": "trigger", "name": "Starts at retirement",
                                         "event": ret, "target": item["id"], "action": "start"})
        self.assertNotIn("enabled", client.scenario["items"][-2])


class WithdrawalMethodMessages(unittest.TestCase):
    def test_method_and_fields_must_agree(self):
        w = {"type": "withdrawal", "id": "w", "name": "Pension draw", "account": "acct",
             "startDate": "2030-01-01", "amount": "", "annualRate": "0.04", "method": "amount"}
        with self.assertRaisesRegex(ValueError, "choose method 'percent'"):
            engine.run(plain(items=[account(), w]))
        w.update(method="percent", amount="1000", annualRate="")
        with self.assertRaisesRegex(ValueError, "choose method 'amount'"):
            engine.run(plain(items=[account(), w]))

    def test_percent_from_the_form(self):
        client = Browser()
        client.get("/")
        client.scenario = plain(items=[account()])
        client.post("/items/add", data={"type": "withdrawal", "name": "Pension draw",
                                         "account": "acct", "method": "percent",
                                         "startDate": "2030-01-01", "endDate": "", "amount": "",
                                         "per": "month", "annualRate": "4", "indexing": "none",
                                         "indexRate": ""})
        item = client.scenario["items"][-1]
        self.assertEqual((item["method"], Decimal(item["annualRate"])), ("percent", Decimal("0.04")))


class VehicleMaintenance(unittest.TestCase):
    def car(self, **fields):
        v = {"type": "vehicle", "id": "car", "name": "Car", "purchaseDate": "2027-03-01",
             "price": "30000", "annualDepreciation": "0.15", "annualMaintenance": "2400"}
        v.update(fields)
        r = engine.run_detailed(with_items(v))
        # An associated expense of the vehicle (ADR-0067; converted on load).
        return {x["month"]: x["amount"] for x in r["ledger"] if x["source"] == "car-maintenance"}

    def test_flat_without_increase(self):
        m = self.car()
        self.assertEqual(set(m.values()), {Decimal("200.00")})

    def test_rises_yearly_on_the_purchase_anniversary(self):
        m = self.car(maintenanceIncrease="0.08")
        self.assertEqual(m["2027-03"], Decimal("200.00"))
        self.assertEqual(m["2028-02"], Decimal("200.00"))
        self.assertEqual(m["2028-03"], Decimal("216.00"))
        self.assertEqual(m["2029-03"], money(Decimal(2400) * Decimal("1.08") ** 2 / 12))

    def test_validation_and_form(self):
        with self.assertRaisesRegex(ValueError, "Car maintenance: indexRate must be a fraction"):
            self.car(maintenanceIncrease="8")
        client = Browser()
        client.get("/")
        client.scenario = copy.deepcopy(HOUSE)
        page = client.get("/").data.decode()
        self.assertNotIn('name="annualMaintenance"', page)
        client.post("/items/add", data={"type": "vehicle", "name": "Car", "purchaseDate": "2027-03-01",
                                         "price": "30000", "annualDepreciation": "15"})
        car = client.scenario["items"][-1]["id"]
        # Maintenance: an associated expense with its own form (ADR-0067).
        client.post("/items/add", data={"type": "associatedExpense", "name": "Upkeep",
                                         "parent": car, "amount": "2400", "per": "year",
                                         "indexing": "custom", "indexRate": "8",
                                         "annualRate": "", "basis": ""})
        item = client.scenario["items"][-1]
        self.assertEqual((item["type"], Decimal(item["indexRate"])),
                         ("associatedExpense", Decimal("0.08")))
        months = {x["month"]: x["amount"] for x in engine.run_detailed(client.scenario)["ledger"]
                  if x["source"] == item["id"]}
        self.assertEqual((months["2027-03"], months["2028-03"]),
                         (Decimal("200.00"), Decimal("216.00")))
        page = client.get("/").data.decode()
        self.assertIn(f"parent=Car (vehicle)", page)


class LedgerCashEffect(unittest.TestCase):
    def test_net_cash_flow_equals_change_in_cash(self):
        client = Browser()
        client.get("/")
        client.scenario = json.loads((HERE / "samples" / "household-baseline.json").read_text())
        rows = engine.run(client.scenario)
        for k in (1, 53, 54, 200):
            month = rows[k]["month"]
            change = rows[k]["cash"] - rows[k - 1]["cash"]
            page = client.get(f"/run/ledger?month={month}").data.decode()
            sign = "+" if change > 0 else ""
            self.assertIn(f"<b>{sign}{change:,.2f}</b>", page, month)
        page = client.get("/run/ledger?month=2019-09").data.decode()
        self.assertIn("Net cash flow this month", page)
        self.assertIn('class="num neg">-', page)               # expenses shown negative in red


class RenewalAttribution(unittest.TestCase):
    def test_interest_and_payments_are_caused_by_the_term_in_effect(self):
        s = with_items({"type": "renewal", "id": "renew", "name": "Renewal with another lender",
                        "mortgage": "mtg", "startDate": "2030-01-01", "annualRate": "0.0429"})
        ledger = engine.run_detailed(s)["ledger"]
        cause = {(x["month"], x["kind"]): x["source"] for x in ledger
                 if x["kind"] in ("LOAN_INTEREST", "LOAN_PAYMENT")}
        self.assertEqual(cause[("2029-12", "LOAN_PAYMENT")], "mtg")
        self.assertEqual(cause[("2030-01", "LOAN_INTEREST")], "renew")
        self.assertEqual(cause[("2035-06", "LOAN_PAYMENT")], "renew")
        # From/To still name the mortgage: it is the same debt (ADR-0043).
        self.assertTrue(all(x["to"] == "mtg" for x in ledger if x["kind"] == "LOAN_PAYMENT"))


class BoughtBeforeHorizon(unittest.TestCase):
    def car(self, **fields):
        v = {"type": "vehicle", "id": "car", "name": "Car", "purchaseDate": "2024-01-01",
             "price": "30000", "annualDepreciation": "0.15", "annualMaintenance": "2400",
             "maintenanceIncrease": "0.10"}
        v.update(fields)
        return engine.run_detailed(with_items(v))

    def test_vehicle_carried_in_at_depreciated_value_without_cash(self):
        r = self.car()
        car = next(h for h in r["holdings"] if h["id"] == "car")
        start_value = car["points"][0]["opening"]
        self.assertAlmostEqual(float(start_value), 30000 * 0.85 ** 3, delta=1)  # 3 years old
        self.assertLess(car["points"][0]["closing"], start_value)               # depreciates in month 1
        self.assertFalse([x for x in r["ledger"] if x["kind"] == "PURCHASE" and x["to"] == "car"])
        # Only the month's maintenance leaves cash; nothing is paid for the car.
        base = engine.run(house())
        maintenance = money(Decimal(2400) * Decimal("1.1") ** 3 / 12)
        self.assertEqual(r["rows"][0]["cash"], base[0]["cash"] - maintenance)

    def test_maintenance_counts_age_from_the_real_purchase(self):
        r = self.car()
        m = {x["month"]: x["amount"] for x in r["ledger"] if x["source"].endswith("-maintenance")}
        self.assertEqual(m["2027-01"], money(Decimal(2400) * Decimal("1.1") ** 3 / 12))
        self.assertEqual(m["2027-01"], m["2027-12"])

    def test_property_bought_before_the_horizon(self):
        s = house()
        s["items"].append({"type": "property", "id": "cottage", "name": "Cottage",
                           "purchaseDate": "2017-01-01", "price": "200000",
                           "annualAppreciation": "0.05"})
        rows, base = engine.run(s), engine.run(house())
        self.assertEqual(rows[0]["cash"], base[0]["cash"])
        extra = rows[0]["assets"] - base[0]["assets"]
        self.assertAlmostEqual(float(extra), 200000 * 1.05 ** 10 * 1.05 ** (1 / 12), delta=2)

    def test_still_rejected(self):
        with self.assertRaisesRegex(ValueError, "after the horizon end"):
            self.car(purchaseDate="2060-01-01")
        s = house()
        s["items"][1]["startDate"] = "2020-01-01"
        with self.assertRaisesRegex(ValueError, "outside the horizon"):
            engine.run(s)


class VehicleSale(unittest.TestCase):
    def scenario(self, **sale):
        s = with_items(
            {"type": "vehicle", "id": "car", "name": "Car", "purchaseDate": "2027-01-01",
             "price": "30000", "annualDepreciation": "0.15", "annualMaintenance": "2400"},
            {"type": "sale", "id": "sell-car", "name": "Trade in", "property": "car",
             "saleDate": "2032-01-01", "sellingCostRate": "0.10"})
        s["items"][-1].update(sale)
        return s

    def test_proceeds_less_selling_cost_then_nothing(self):
        r = engine.run_detailed(self.scenario())
        rows = r["rows"]
        k = 60                                                  # 2032-01
        car_value = rows[k - 1]["assets"] - engine.run(house())[k - 1]["assets"]
        sale = next(x for x in r["ledger"] if x["kind"] == "SALE")
        self.assertEqual(sale["amount"], car_value)
        cost = next(x for x in r["ledger"] if x["kind"] == "COST")       # ADR-0067
        self.assertEqual(cost["amount"], money(car_value * Decimal("0.10")))
        maint = [x["month"] for x in r["ledger"] if x["source"].endswith("-maintenance")]
        self.assertEqual(maint[-1], "2031-12")                 # maintenance stops at the sale
        self.assertEqual(rows[k]["assets"], engine.run(house())[k]["assets"])

    def test_trade_in_and_replace_in_the_same_month(self):
        s = self.scenario()
        s["items"].append({"type": "vehicle", "id": "car2", "name": "Next car",
                           "purchaseDate": "2032-01-01", "price": "35000",
                           "annualDepreciation": "0.15", "annualMaintenance": "1800"})
        r = engine.run_detailed(s)
        kinds = [(x["kind"], x["source"]) for x in r["ledger"] if x["month"] == "2032-01"]
        self.assertIn(("SALE", "sell-car"), kinds)
        self.assertIn(("PURCHASE", "car2"), kinds)

    def test_validation_and_form(self):
        with self.assertRaisesRegex(ValueError, "saleDate must be after the purchase"):
            engine.run(self.scenario(saleDate="2027-01-01"))
        client = Browser()
        client.get("/")
        client.scenario = self.scenario()
        client.scenario["items"].pop()
        page = client.get("/").data.decode()
        self.assertIn('<option value="car">Car</option>', page)
        client.post("/items/add", data={"type": "sale", "name": "Sell car", "property": "car",
                                         "saleDate": "2033-01-01", "sellingCostRate": "",
                                         "salePenalty": ""})
        self.assertEqual(engine.run(client.scenario)[-1]["assets"],
                         engine.run(house())[-1]["assets"])
        client.post("/items/car/delete")
        self.assertNotIn("sale", [i["type"] for i in client.scenario["items"]])


class SalePrice(unittest.TestCase):
    def sold(self, **sale):
        item = {"type": "sale", "id": "sell", "name": "Sell", "property": "house",
                "saleDate": "2037-01-01", "sellingCostRate": "0.05"}
        item.update(sale)
        return engine.run_detailed(with_items(item, end="2040-12-01"))

    def test_price_replaces_the_value(self):
        at_value, at_price = self.sold(), self.sold(salePrice="1000000")
        k = 120
        value = at_value["rows"][k - 1]["assets"]
        cash_gap = at_price["rows"][k]["cash"] - at_value["rows"][k]["cash"]
        # Proceeds and selling costs both follow the price.
        self.assertEqual(cash_gap, (Decimal("1000000") - value)
                         - (money(Decimal("1000000") * Decimal("0.05")) - money(value * Decimal("0.05"))))
        sale = next(x for x in at_price["ledger"] if x["kind"] == "SALE")
        self.assertEqual(sale["amount"], Decimal("1000000.00"))
        diff = next(x for x in at_price["ledger"] if x["kind"] == "SALE_PRICE_DIFFERENCE")
        self.assertEqual(diff["amount"], Decimal("1000000.00") - value)

    def test_blank_price_sells_at_value(self):
        r = self.sold(salePrice="")
        self.assertFalse([x for x in r["ledger"] if x["kind"] == "SALE_PRICE_DIFFERENCE"])

    def test_form(self):
        client = Browser()
        client.get("/")
        client.scenario = copy.deepcopy(HOUSE)
        self.assertIn(b"salePrice (optional, blank = its value that month)", client.get("/").data)


class ItemsTableOrder(unittest.TestCase):
    def test_sorted_by_effective_start(self):
        client = Browser()
        client.get("/")
        s = json.loads((HERE / "samples" / "household-baseline.json").read_text())
        s["retirementDate"] = "2045-01-01"
        s["items"].insert(0, {"type": "expense", "id": "retired", "name": "Retired living",
                              "startDate": "", "amount": "3000", "startsAtRetirement": True})
        client.scenario = s
        from state_machine import views
        from state_machine.cards import cards
        client.get("/")
        starts = views.starts(client.scenario)
        expenses = next(c for c in cards(client.scenario)["sections"][-1]["categories"]
                        if c["key"] == "expenses")
        order = [starts[c["id"]] or "9999-99" for c in expenses["cards"]]
        self.assertEqual(order, sorted(order))                  # cards by start (ADR-0070)
        self.assertEqual(order[-1], "2045-01")                  # starts at retirement
        # The mortgage tied to the Maple Street house shows its own start, 2021-06.
        self.assertIn("2021-06", starts.values())
        # The saved file keeps its order.
        self.assertEqual(client.scenario["items"][0]["id"], "retired")


if __name__ == "__main__":
    unittest.main()


class DeleteCascade(unittest.TestCase):
    """Deleting an item takes its dependents along and never leaves an invalid scenario."""

    def setup(self, *items):
        client = Browser()
        client.get("/")
        s = plain()
        s["items"] += list(items)
        client.scenario = s
        return client, None

    def test_attached_expense_and_its_adjustment_go_with_the_property(self):
        client, sid = self.setup(
            {"type": "property", "id": "h", "name": "House", "purchaseDate": "2020-01-01",
             "price": "500000", "annualAppreciation": "0", "sellingCostRate": "0"},
            {"type": "expense", "id": "ptax", "name": "Tax", "amount": "100"},
            {"type": "adjustment", "id": "a", "name": "Reassessed", "flow": "ptax",
             "adjustmentDate": "2028-01-01", "amount": "150"},
            {"type": "trigger", "id": "t", "event": "h", "target": "ptax", "action": "start"})
        client.post("/items/h/delete")
        self.assertEqual([i["id"] for i in client.scenario["items"]], ["job"])

    def test_person_takes_retirement_and_room_and_owners_fall_back(self):
        client, sid = self.setup(
            {"type": "person", "id": "a", "name": "A"}, {"type": "person", "id": "b", "name": "B"},
            {"type": "retirement", "id": "rb", "owner": "b", "retirementDate": "2030-01-01"},
            {"type": "contributionRoom", "id": "room", "owner": "b", "accountType": "tfsa",
             "room": "0", "roomAsOfDate": "2027-01-01", "yearlyMax": "7000"},
            {"type": "income", "id": "jb", "name": "B job", "owner": "b",
             "startDate": "2027-01-01", "amount": "100"})
        client.post("/items/b/delete")
        items = {i["id"]: i for i in client.scenario["items"]}
        self.assertEqual(sorted(items), ["a", "jb", "job"])
        self.assertNotIn("owner", items["jb"])

    def test_delete_that_would_break_the_scenario_is_refused(self):
        client, sid = self.setup(
            {"type": "retirement", "id": "r", "name": "Retire", "retirementDate": "2030-01-01"},
            {"type": "pension", "id": "p", "name": "P", "amount": "100", "per": "month"})
        page = client.post("/items/r/delete", follow_redirects=True).data.decode()
        self.assertIn("needs a startDate or a retirement event", page)
        self.assertIn("r", [i["id"] for i in client.scenario["items"]])


class CashBalanceInTheApp(unittest.TestCase):
    """ADR-0063: the cash balance form."""

    def test_add_cash_balance(self):
        client = Browser()
        client.get("/")
        client.scenario = plain()
        self.assertIn('value="cashBalance"', client.get("/").data.decode())
        client.post("/items/add", data={"type": "cashBalance", "name": "Bank statement",
                                         "balanceDate": "2028-01-01", "balance": "12345"})
        item = client.scenario["items"][-1]
        self.assertEqual(item["type"], "cashBalance")
        rows = engine.run(client.scenario)
        self.assertEqual(next(r["cash"] for r in rows if r["month"] == "2028-01"),
                         Decimal("12345.00"))
        self.assertIn("2028-01", client.get("/").data.decode())       # its start column


class AdjustmentInTheApp(unittest.TestCase):
    """ADR-0062: the adjustment form; ADR-0033 amendment: vehicles in market adjustments."""

    def test_add_adjustment_to_an_expense(self):
        client = Browser()
        client.get("/")
        s = plain()
        s["items"] += [{"type": "expense", "id": "ptax", "name": "Property tax",
                        "startDate": "2027-01-01", "amount": "4800", "per": "year"},
                       {"type": "vehicle", "id": "car", "name": "Car", "purchaseDate": "2025-01-01",
                        "price": "30000", "annualDepreciation": "0.1", "annualMaintenance": "0"}]
        client.scenario = s
        page = client.get("/").data.decode()
        # Added on the expense's card (ADR-0070), or with the flow chosen in the form.
        self.assertRegex(page, r'data-kind="adjustment" data-fixed="\{&#34;flow&#34;: &#34;ptax&#34;\}"')
        self.assertIn('<option value="ptax">Property tax (expense)</option>', page)
        client.post("/items/add", data={"type": "adjustment", "name": "New assessment",
                                         "flow": "ptax", "adjustmentDate": "2029-01-01",
                                         "amount": "6000", "per": "year"})
        item = client.scenario["items"][-1]
        self.assertEqual((item["type"], item["flow"]), ("adjustment", "ptax"))
        ledger = engine.run_detailed(client.scenario)["ledger"]
        paid = {x["month"]: x["amount"] for x in ledger if x["source"] == "ptax"}
        self.assertEqual(paid["2029-01"], Decimal("500.00"))
        client.post("/items/add", data={"type": "marketAdjustment", "name": "Car revalued",
                                         "property": "car", "adjustmentDate": "2028-01-01",
                                         "percent": "", "newValue": "12000"})
        self.assertEqual(client.scenario["items"][-1]["type"], "marketAdjustment")
        client.post("/items/ptax/delete")
        self.assertFalse(any(i.get("flow") == "ptax" for i in client.scenario["items"]))
        # A percent withdrawal takes a new rate (ADR-0062 amendment).
        client.scenario["items"] += [
            {"type": "account", "id": "acc", "name": "TFSA", "accountType": "tfsa",
             "openingBalance": "120000", "annualReturn": "0"},
            {"type": "withdrawal", "id": "w", "name": "Draw", "account": "acc",
             "method": "percent", "startDate": "2027-01-01", "annualRate": "0.04"}]
        self.assertIn('<option value="w">Draw (withdrawal)</option>', client.get("/").data.decode())
        client.post("/items/add", data={"type": "adjustment", "name": "Slower", "flow": "w",
                                         "adjustmentDate": "2028-01-01", "amount": "",
                                         "per": "month", "annualRate": "3"})
        item = client.scenario["items"][-1]
        self.assertEqual((item["type"], item["annualRate"]), ("adjustment", "0.03"))


class AttachedExpenseInTheApp(unittest.TestCase):
    """An expense tied to a property by triggers (ADR-0065 amendment; formerly attachedTo):
    added without a date (kept off), started with the purchase, ended at the sale."""

    def test_property_tax_stops_at_sale(self):
        client = Browser()
        client.get("/")
        s = plain()
        s["items"] += [{"type": "property", "id": "h", "name": "House", "purchaseDate": "2020-01-01",
                        "price": "500000", "annualAppreciation": "0", "sellingCostRate": "0"},
                       {"type": "sale", "id": "s", "name": "Sell", "property": "h",
                        "saleDate": "2028-06-01"}]
        client.scenario = s
        page = client.get("/").data.decode()
        self.assertNotIn('name="attachedTo"', page)
        self.assertIn('<select name="on">', page)
        client.post("/items/add", data={"type": "expense", "name": "Property tax",
                                         "startDate": "", "amount": "4800", "per": "year",
                                         "amountIn": "start", "indexing": "none"})
        item = client.scenario["items"][-1]
        self.assertIs(item["enabled"], False)               # waits for its start trigger
        for on, action in (("start", "start"), ("end", "end")):
            client.post("/items/add", data={"type": "trigger", "name": f"{action} with House",
                                             "event": "h", "on": on, "target": item["id"],
                                             "action": action})
        items = client.scenario["items"]
        item = next(i for i in items if i["id"] == item["id"])
        self.assertNotIn("enabled", item)
        self.assertEqual([t.get("on") for t in items if t["type"] == "trigger"], [None, "end"])
        page = client.get("/").data.decode()
        self.assertIn("on=its end", page)
        # Details: dates set by a trigger name it, empty fields are left out.
        self.assertIn("startDate=&#9889; start with House, endDate=&#9889; end with House, "
                      "amount=4800", page)
        self.assertNotIn("indexRate=", page)
        self.assertNotIn("=-", page)
        months = [x["month"] for x in engine.run_detailed(client.scenario)["ledger"]
                  if x["source"] == item["id"]]
        self.assertEqual((months[0], months[-1]), ("2027-01", "2028-05"))
        # The end trigger is listed in the sale month.
        from state_machine import views
        starts = views.starts(client.scenario)
        end_trigger = next(t for t in items if t.get("on") == "end")
        self.assertEqual(starts[end_trigger["id"]], "2028-06")


class TimelinePage(unittest.TestCase):
    """The Timeline tab: lanes branch off their host, triggers as links and arrows."""

    def scenario(self):
        s = plain()
        s["items"] += [
            {"type": "property", "id": "h", "name": "House", "purchaseDate": "2027-03-01",
             "price": "500000", "annualAppreciation": "0", "sellingCostRate": "0"},
            {"type": "sale", "id": "s", "name": "Sell", "property": "h", "saleDate": "2029-06-01"},
            {"type": "expense", "id": "ptax", "name": "Property tax", "amount": "100"},
            {"type": "trigger", "id": "t1", "name": "With House", "event": "h",
             "target": "ptax", "action": "start"},
            {"type": "trigger", "id": "t2", "name": "Ends with House", "event": "h", "on": "end",
             "target": "ptax", "action": "end"},
            {"type": "retirement", "id": "r", "name": "Retire", "retirementDate": "2029-01-01"},
            {"type": "trigger", "id": "t3", "name": "Ends at Retire", "event": "r",
             "target": "job", "action": "end"},
            {"type": "expense", "id": "boat", "name": "Boat", "startDate": "2028-01-01",
             "amount": "10", "enabled": False}]
        return s

    def test_layout(self):
        import timeline
        from web import timeline_draw
        m = timeline.layout(self.scenario())
        lanes = {ln["id"]: ln for ln in m["lanes"]}
        from state_machine.dates import month_label as label
        # Property tax branches off the house at its purchase and merges back at the sale.
        tax = lanes["ptax"]
        self.assertEqual((tax["parent"], tax["by_trigger"], label(tax["first"]), label(tax["last"])),
                         ("h", True, "2027-03", "2029-05"))
        links = {(k["kind"], k["from"], k["to"]): (label(k["month"]), k["trigger"])
                 for k in m["links"]}
        self.assertEqual(links[("branch", "h", "ptax")], ("2027-03", True))
        self.assertEqual(links[("merge", "ptax", "h")], ("2029-06", True))
        self.assertEqual(links[("merge", "h", None)], ("2029-06", False))
        # The sale is a dot on the house lane; the retirement a dot on the trunk.
        dots = {d["id"]: (label(d["month"]), d["row"]) for d in m["dots"]}
        self.assertEqual(dots["s"], ("2029-06", lanes["h"]["row"]))
        self.assertEqual(dots["r"], ("2029-01", 0))
        # Only the retirement trigger needs an arrow: trunk -> end of the job.
        self.assertEqual([(a["id"], label(a["month"]), a["from_row"], a["to_row"])
                          for a in m["arrows"]], [("t3", "2029-01", 0, lanes["job"]["row"])])
        self.assertEqual(label(lanes["job"]["last"]), "2028-12")
        self.assertEqual([g["name"] for g in m["guides"]], ["Retire"])
        # An off item is drawn, greyed.
        self.assertTrue(lanes["boat"]["off"])

    def test_graph_rows_and_columns(self):
        import timeline
        from web import timeline_draw
        m = timeline.layout(self.scenario())
        rows = timeline_draw.graph_rows(m)
        from state_machine.dates import month_label as label
        text = [(label(mo), kind, thing["id"]) for mo, kind, thing in rows]
        # In time order; in the sale month the sale, then the tax ends before its house.
        self.assertEqual(text[-3:], [("2029-06", "dot", "s"), ("2029-06", "end", "ptax"),
                                     ("2029-06", "end", "h")])
        self.assertLess(text.index(("2027-03", "start", "h")), text.index(("2027-03", "start", "ptax")))
        col = timeline_draw.columns(m, rows)
        self.assertGreater(col["ptax"], col["h"])
        self.assertEqual(m["set_by"]["ptax:start"], "With House")
        self.assertIn("timeline-graph", timeline_draw.graph(m, newest_first=True))

    def test_associated_items(self):
        import timeline
        from web import timeline_draw
        from state_machine.dates import month_label as label
        s = self.scenario()
        s["items"] += [
            {"type": "associatedExpense", "id": "ins", "name": "Insurance", "parent": "h",
             "amount": "50", "per": "month"},
            {"type": "associatedCost", "id": "close", "name": "Closing", "parent": "h",
             "at": "start", "amount": "100"},
            {"type": "associatedCost", "id": "agent", "name": "Agent", "parent": "h",
             "at": "end", "rate": "0.05", "basis": "value"}]
        m = timeline.layout(s)
        lanes = {ln["id"]: ln for ln in m["lanes"]}
        ins = lanes["ins"]
        self.assertEqual((ins["parent"], ins["by_trigger"], label(ins["first"]), label(ins["last"])),
                         ("h", False, "2027-03", "2029-05"))
        dots = {d["id"]: (label(d["month"]), d["row"]) for d in m["dots"]}
        self.assertEqual(dots["close"], ("2027-03", lanes["h"]["row"]))
        self.assertEqual(dots["agent"], ("2029-06", lanes["h"]["row"]))

    def test_associated_income(self):
        import timeline
        from web import timeline_draw
        from state_machine.dates import month_label as label
        s = self.scenario()
        job = next(i for i in s["items"] if i["id"] == "job")
        s["items"] += [
            {"type": "associatedIncome", "id": "bonus", "name": "Bonus", "parent": "job",
             "annualRate": "0.1", "per": "year", "paid": "lump"},
            {"type": "associatedOneOff", "id": "sign", "name": "Signing", "parent": "job",
             "at": "start", "amount": "5000"}]
        m = timeline.layout(s)
        lanes = {ln["id"]: ln for ln in m["lanes"]}
        self.assertEqual((lanes["bonus"]["parent"], lanes["bonus"]["first"],
                          lanes["bonus"]["last"]),
                         ("job", lanes["job"]["first"], lanes["job"]["last"]))
        dots = {d["id"]: (label(d["month"]), d["row"]) for d in m["dots"]}
        self.assertEqual(dots["sign"], (job["startDate"][:7], lanes["job"]["row"]))

    def test_graph_one_row_per_month(self):
        import timeline
        from web import timeline_draw
        graph = timeline_draw.graph(timeline.layout(self.scenario()))
        dates = re.findall(r'fill="#b58900">([\d-]+)</tspan>', graph)
        self.assertEqual(len(dates), len(set(dates)))
        # The sale month: the sale, then the ends, comma-separated, on one line.
        line = re.search(r'fill="#b58900">2029-06</tspan></text>\s*<text [^>]*>(.*?)</text>',
                         graph).group(1)
        self.assertEqual(re.sub(r"<title>.*?</title>|<[^>]+>", "", line).strip(),
                         "Sell · ends: Property tax ⚡, House")
        # Its nodes share one height.
        ys = {re.search(r'<title>([^<]*)</title><circle cx="[\d.]+" cy="([\d.]+)"', g).groups()
              for g in re.findall(r"<g><title>[^<]*</title><circle[^>]*/>", graph)}
        sale_month = {y for t, y in ys if t.startswith(("Sell (sale", "End of Property tax",
                                                         "End of House"))}
        self.assertEqual(len(sale_month), 1)

    def test_graph_links_reach_their_parent(self):
        import timeline
        from web import timeline_draw
        graph = timeline_draw.graph(timeline.layout(self.scenario()))
        paths = {t: (d, s) for t, d, s in re.findall(
            r'<g><title>([^<]*)</title><path d="([^"]*)" fill="none" stroke="([^"]*)"', graph)}
        # Property tax starts and ends with House: straight across to House's own nodes,
        # not curving to a row where House is not drawn.
        start = paths["Property tax starts in 2027-03, branching off House "
                      "(⚡ trigger With House)."][0]
        end = paths["Property tax ends after 2029-05, merging back into House "
                    "(⚡ trigger Ends with House)."][0]
        self.assertRegex(start, r"^M[\d.]+,([\d.]+) L[\d.]+,\1$")
        self.assertRegex(end, r"^M[\d.]+,([\d.]+) L[\d.]+,\1$")
        # House's own branch is not drawn as a trigger link because its child's is.
        self.assertEqual(paths["House starts in 2027-03, branching off the household."][1],
                         "#ccc")

    def test_mouse_over_tips(self):
        import timeline
        from web import timeline_draw
        m = timeline.layout(self.scenario())
        for picture in (timeline_draw.graph(m), timeline_draw.svg(m)):
            self.assertIn("<title>Property tax (expense): runs 2027-03 to 2029-05; belongs to "
                          "House.</title>", picture)
            self.assertIn("<title>Property tax ends after 2029-05, merging back into House "
                          "(\u26a1 trigger Ends with House).</title>", picture)
            self.assertIn("<title>Sell (sale, one-off) in 2029-06, on House.</title>", picture)
            self.assertIn("Switched off: not in the run.", picture)
            self.assertIn('stroke="transparent" stroke-width="10"', picture)   # easy to hover
        graph = timeline_draw.graph(m)
        self.assertIn("<title>Start of Property tax (expense) in 2027-03 "
                      "(\u26a1 trigger With House).</title>", graph)
        self.assertIn("<title>End of Job (income): last month 2028-12 "
                      "(\u26a1 trigger Ends at Retire).</title>", graph)

    def test_page(self):
        client = Browser()
        client.get("/")
        client.scenario = self.scenario()
        page = client.get("/timeline?view=axis").data.decode()
        self.assertIn('<a href="/timeline">Timeline</a>', page)
        self.assertIn('<svg xmlns="http://www.w3.org/2000/svg" class="timeline"', page)
        self.assertIn("Property tax (expense): runs 2027-03 to 2029-05", page)
        self.assertIn('<a href="/#item-ptax">', page)
        # The default: the vertical graph, oldest first; newest first on request.
        page = client.get("/timeline").data.decode()
        self.assertIn('class="timeline-graph"', page)
        rows = re.findall(r'<tspan font-family="monospace" fill="#b58900">([\d-]+)</tspan>', page)
        self.assertEqual(rows, sorted(rows))
        newest = client.get("/timeline?order=newest").data.decode()
        self.assertEqual(re.findall(r'<tspan font-family="monospace" fill="#b58900">([\d-]+)</tspan>',
                                    newest), rows[::-1])
        self.assertIn('id="item-ptax"', client.get("/").data.decode())


class PersonsInTheApp(unittest.TestCase):
    """ADR-0061: the person form, owner fields and the per-person tax table."""

    def test_add_partner_with_own_income_and_see_tax_per_person(self):
        client = Browser()
        client.get("/")
        client.scenario = plain()
        page = client.get("/").data.decode()
        self.assertNotIn('name="owner"', page)          # no persons: no owner fields
        client.post("/items/add", data={"type": "person", "name": "Dima",
                                         "effectiveTaxRate": "", "retirementTaxRate": ""})
        client.post("/items/add", data={"type": "person", "name": "Partner",
                                         "effectiveTaxRate": "20", "retirementTaxRate": ""})
        items = client.scenario["items"]
        partner = items[-1]
        self.assertEqual((partner["type"], partner["effectiveTaxRate"]), ("person", "0.2"))
        page = client.get("/").data.decode()
        self.assertIn('name="owner"', page)
        self.assertNotIn('name="retirementOf"', page)          # triggers name the event
        client.post("/items/add", data={"type": "income", "name": "Partner job",
                                         "startDate": "2027-01-01",
                                         "amount": "5000", "per": "month",
                                         "taxable": "yes", "earnedIncome": "",
                                         "indexing": "none", "owner": partner["id"]})
        job = client.scenario["items"][-1]
        self.assertEqual(job["owner"], partner["id"])
        client.post("/items/add", data={"type": "expense", "name": "Food",
                                         "startDate": "2027-01-01",
                                         "amount": "100", "per": "month", "indexing": "none"})
        page = client.get("/run/ledger?month=2027-01").data.decode()
        self.assertIn("Each person is taxed separately", page)
        self.assertIn("Partner", page)
        result = engine.run_detailed(client.scenario)
        self.assertEqual(result["tax"]["2027-01"]["total"], Decimal("2800.00"))  # 1800 + 1000


class ContributionRoomInTheApp(unittest.TestCase):
    """ADR-0060: the contributionRoom form and the room column on the run page."""

    def test_add_room_item_and_see_the_room_column(self):
        client = Browser()
        client.get("/")
        s = plain()
        s["items"] += [account(), {"type": "transfer", "id": "x", "account": "acct",
                                   "amount": "50000", "transferDate": "2027-03-01"}]
        client.scenario = s
        client.post("/items/add", data={"type": "contributionRoom", "name": "RRSP room",
                                         "accountType": "rrsp", "room": "20000",
                                         "roomAsOfDate": "2027-01-01", "yearlyMax": "33810",
                                         "maxYear": "2026", "incomeRate": "",
                                         "indexing": "none"})
        item = client.scenario["items"][-1]
        self.assertEqual(item["type"], "contributionRoom")
        page = client.get("/run").data.decode()
        self.assertIn("RRSP room left", page)
        rows = engine.run(client.scenario)
        self.assertEqual(rows[2]["rrspRoom"], Decimal("0.00"))
        self.assertEqual(rows[12]["rrspRoom"], Decimal("12960.00"))   # 72000 x 18%
        client.post("/items/add", data={"type": "income", "name": "Rental", "starts": "date",
                                         "startDate": "2027-01-01", "ends": "never",
                                         "amount": "1000", "per": "month", "taxable": "yes",
                                         "earnedIncome": "no", "indexing": "none"})
        self.assertIs(client.scenario["items"][-1]["earnedIncome"], False)


class ItemSwitchInTheApp(unittest.TestCase):
    """ADR-0064: the on/off switch in the builder."""

    def setup(self, *items):
        client = Browser()
        client.get("/")
        s = plain()
        s["items"] += list(items)
        client.scenario = s
        return client, None

    def test_switch_off_and_on_keeps_the_items_and_shows_dependents(self):
        house = {"type": "property", "id": "h", "name": "House", "purchaseDate": "2020-01-01",
                 "price": "500000", "annualAppreciation": "0", "sellingCostRate": "0"}
        ptax = {"type": "expense", "id": "ptax", "name": "Property tax", "amount": "100"}
        start = {"type": "trigger", "id": "t", "name": "With House", "event": "h",
                 "target": "ptax", "action": "start"}
        client, sid = self.setup(house, ptax, start)
        rows_on = engine.run(client.scenario)
        client.post("/items/h/toggle")
        items = {i["id"]: i for i in client.scenario["items"]}
        self.assertIs(items["h"]["enabled"], False)
        self.assertNotIn("enabled", items["ptax"])
        page = client.get("/").data.decode()
        self.assertIn("(off via House)", page)
        self.assertRegex(page, r'<input type="checkbox" class="check" aria-label="House on"[^>]*onchange="this.form.requestSubmit\(\)">')
        # Sent in the background by web.js (the page is swapped in place, keeping its
        # scroll position, ADR-0069).
        self.assertIn('<form class="keep-scroll inline switch" method="post" action="/items/h/toggle">', page)
        self.assertIn('/web/static/web.js', page)
        self.assertNotEqual(engine.run(client.scenario), rows_on)
        client.post("/items/h/toggle")
        self.assertNotIn("enabled", next(i for i in client.scenario["items"]
                                         if i["id"] == "h"))
        self.assertEqual(engine.run(client.scenario), rows_on)

    def test_switch_that_would_break_the_scenario_is_refused(self):
        client, sid = self.setup(
            {"type": "retirement", "id": "r", "name": "Retire", "retirementDate": "2030-01-01"},
            {"type": "expense", "id": "e", "name": "After", "amount": "100"},
            {"type": "trigger", "id": "t", "name": "At Retire", "event": "r", "target": "e",
             "action": "start"})
        # The trigger alone off: the expense has no start date.
        page = client.post("/items/t/toggle", follow_redirects=True).data.decode()
        self.assertIn("item After: missing field &#39;startDate&#39;", page)
        self.assertNotIn("enabled", client.scenario["items"][-1])
        # Its event off: the expense never starts, so it is off too.
        page = client.post("/items/r/toggle", follow_redirects=True).data.decode()
        self.assertIn("(off via Retire)", page)
        self.assertNotIn("missing field", page)


class TriggersInTheApp(unittest.TestCase):
    """ADR-0065: trigger form, listing under the target, older files converted on load."""

    def test_loaded_at_retirement_fields_become_triggers_listed_under_their_target(self):
        s = plain()
        s["items"] += [
            {"type": "retirement", "id": "ret", "name": "Retirement",
             "retirementDate": "2030-01-01"},
            {"type": "vehicle", "id": "car", "name": "Car", "purchaseDate": "2020-01-01",
             "price": "30000", "annualDepreciation": "0.1", "annualMaintenance": "0"},
            {"type": "sale", "id": "sell", "name": "Sell car", "property": "car",
             "atRetirement": True}]
        s["items"][0]["endsAtRetirement"] = True
        client = Browser()
        client.get("/")
        client.post("/load", data={"file": (io.BytesIO(json.dumps(s).encode()), "s.json")},
                    content_type="multipart/form-data")
        items = client.scenario["items"]
        self.assertFalse(any("atRetirement" in i or "endsAtRetirement" in i for i in items))
        self.assertEqual(sorted((t["target"], t["action"]) for t in items
                                if t["type"] == "trigger"), [("job", "end"), ("sell", "start")])
        page = client.get("/").data.decode()
        # On the car's card, the sale's row is followed by its trigger, one level deeper.
        car = page[page.index('id="item-car"'):]
        car = car[:car.index("</details>")]
        rows = re.findall(r'<tr id="item-[^"]*" class="depth(\d)[^"]*">\s*<td>.*?</td>\s*'
                          r'<td class="name">(?:&#9889; )?([^<]+)', car, re.S)
        names = [name for _, name in rows]
        sale = names.index("Sell car")
        self.assertEqual(rows[sale + 1], (str(int(rows[sale][0]) + 1), "At Retirement"))
        self.assertEqual(engine.run(client.scenario), engine.run(s))
