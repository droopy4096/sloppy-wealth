"""Associated expense and associated cost (ADR-0067).

    cd webapp && .venv/bin/python -m unittest state_machine.tests.test_associated
"""
import copy
import unittest
from decimal import Decimal

from state_machine import engine
from state_machine.upgrade import upgrade


def scenario(*items, **over):
    s = {"schemaVersion": 1, "name": "associated",
         "horizon": {"start": "2027-01-01", "end": "2030-12-01"},
         "openingCash": "2000000", "effectiveTaxRate": "0.3", "items": list(items)}
    s.update(over)
    return s


HOUSE = {"type": "property", "id": "h", "name": "House", "purchaseDate": "2027-04-01",
         "price": "500000", "annualAppreciation": "0.12"}
SALE = {"type": "sale", "id": "s", "name": "Sell", "property": "h", "saleDate": "2029-07-01"}
JOB = {"type": "income", "id": "job", "name": "Job", "startDate": "2027-01-01",
       "endDate": "2028-06-01", "amount": "120000", "per": "year", "taxable": True}


def expense(**kw):
    return dict({"type": "associatedExpense", "id": "e", "name": "Tax", "parent": "h"}, **kw)


def cost(**kw):
    return dict({"type": "associatedCost", "id": "c", "name": "Cost", "parent": "h"}, **kw)


def run(s):
    return engine.run_detailed(copy.deepcopy(s))


def paid(result, source):
    return {x["month"]: x["amount"] for x in result["ledger"] if x["source"] == source}


class AssociatedExpense(unittest.TestCase):
    def test_lives_with_its_asset_and_is_indexed_from_its_start(self):
        r = run(scenario(HOUSE, SALE, expense(amount="1200", per="year", indexing="custom",
                                              indexRate="0.1")))
        months = paid(r, "e")
        self.assertEqual((min(months), max(months)), ("2027-04", "2029-06"))
        self.assertEqual((months["2027-04"], months["2028-03"], months["2028-04"]),
                         (Decimal("100.00"), Decimal("100.00"), Decimal("110.00")))

    def test_percentage_of_value_recomputed_on_anniversaries(self):
        r = run(scenario(HOUSE, expense(annualRate="0.012", basis="value")))
        months = paid(r, "e")
        # The purchase month: the price (no opening value yet); 12 months the same.
        self.assertEqual(months["2027-04"], Decimal("500.00"))
        self.assertEqual(months["2028-03"], Decimal("500.00"))
        # The anniversary: the value at the start of 2028-04 (12% a year later) x 1.2% / 12.
        value = next(h for h in r["holdings"] if h["id"] == "h")
        opening = next(p["opening"] for p in value["points"] if p["month"] == "2028-04")
        self.assertEqual(months["2028-04"], (opening * Decimal("0.001")).quantize(Decimal("0.01")))
        self.assertGreater(months["2028-04"], months["2027-04"])

    def test_percentage_of_price(self):
        months = paid(run(scenario(HOUSE, expense(annualRate="0.012", basis="price"))), "e")
        self.assertEqual(set(months.values()), {Decimal("500.00")})

    def test_bought_before_the_horizon_pays_from_the_first_month(self):
        old = dict(HOUSE, purchaseDate="2020-06-01")
        months = paid(run(scenario(old, expense(annualRate="0.012", basis="price"))), "e")
        self.assertEqual(min(months), "2027-01")

    def test_follows_an_income_and_a_percentage_of_it(self):
        dues = expense(parent="job", annualRate="0.01", basis="amount")
        months = paid(run(scenario(JOB, dues)), "e")
        self.assertEqual((min(months), max(months)), ("2027-01", "2028-06"))
        self.assertEqual(months["2027-01"], Decimal("100.00"))          # 1% of 120000 / 12

    def test_account_balance_basis(self):
        acct = {"type": "account", "id": "a", "name": "RRSP", "accountType": "rrsp",
                "openingBalance": "120000", "annualReturn": "0"}
        fee = expense(parent="a", annualRate="0.01", basis="balance")
        self.assertEqual(paid(run(scenario(acct, fee)), "e")["2027-01"], Decimal("100.00"))

    def test_stops_when_the_mortgage_is_paid_off(self):
        loan = {"type": "mortgage", "id": "m", "name": "Loan", "principal": "12000",
                "annualRate": "0", "amortizationYears": "1", "startDate": "2027-01-01"}
        fee = expense(parent="m", amount="10", per="month")
        months = paid(run(scenario(loan, fee)), "e")
        self.assertEqual(max(months), "2027-12")

    def test_adjustments_new_amount_and_new_rate(self):
        fixed = expense(amount="100", per="month")
        adj = {"type": "adjustment", "id": "a", "flow": "e", "adjustmentDate": "2028-01-01",
               "amount": "150"}
        months = paid(run(scenario(HOUSE, fixed, adj)), "e")
        self.assertEqual((months["2027-12"], months["2028-01"]),
                         (Decimal("100.00"), Decimal("150.00")))
        rate = expense(annualRate="0.012", basis="price")
        adj = {"type": "adjustment", "id": "a", "flow": "e", "adjustmentDate": "2028-01-01",
               "annualRate": "0.024"}
        months = paid(run(scenario(HOUSE, rate, adj)), "e")
        self.assertEqual((months["2027-12"], months["2028-01"]),
                         (Decimal("500.00"), Decimal("1000.00")))

    def test_not_paid_in_income_less_mode(self):
        r = run(scenario(HOUSE, expense(amount="100", per="month"),
                         incomeMode="expensesCovered"))
        self.assertEqual(paid(r, "e"), {})

    def test_off_with_its_parent(self):
        s = scenario(dict(HOUSE, enabled=False), expense(amount="100", per="month"))
        self.assertEqual(paid(run(s), "e"), {})


class AssociatedCost(unittest.TestCase):
    def test_closing_costs_at_the_purchase(self):
        r = run(scenario(HOUSE, cost(at="start", rate="0.015", basis="price")))
        self.assertEqual(paid(r, "c"), {"2027-04": Decimal("7500.00")})
        line = next(x for x in r["ledger"] if x["source"] == "c")
        self.assertEqual((line["kind"], line["from"], line["to"]), ("COST", "cash", None))

    def test_selling_costs_at_the_sale_price(self):
        sale = dict(SALE, salePrice="600000")
        r = run(scenario(HOUSE, sale, cost(at="end", rate="0.05", basis="value")))
        self.assertEqual(paid(r, "c"), {"2029-07": Decimal("30000.00")})

    def test_fixed_cost_on_a_date_only_while_the_parent_exists(self):
        before = cost(at="date", costDate="2028-05-01", amount="2500")
        self.assertEqual(paid(run(scenario(HOUSE, SALE, before)), "c"),
                         {"2028-05": Decimal("2500.00")})
        after = cost(at="date", costDate="2030-01-01", amount="2500")
        self.assertEqual(paid(run(scenario(HOUSE, SALE, after)), "c"), {})

    def test_at_the_end_of_an_income_and_never_without_one(self):
        bonus = cost(parent="job", at="end", amount="1000")
        self.assertEqual(paid(run(scenario(JOB, bonus)), "c"), {"2028-06": Decimal("1000.00")})
        endless = dict(JOB, endDate="")
        self.assertEqual(paid(run(scenario(endless, bonus)), "c"), {})

    def test_paid_also_in_income_less_mode(self):
        r = run(scenario(HOUSE, cost(at="start", amount="100"), incomeMode="expensesCovered"))
        self.assertEqual(paid(r, "c"), {"2027-04": Decimal("100.00")})


class Validation(unittest.TestCase):
    def check(self, item, message, *more):
        with self.assertRaisesRegex(ValueError, message):
            engine.validate(scenario(HOUSE, JOB, *more, item))

    def test_messages(self):
        self.check(expense(parent="zz", amount="1"), "parent refers to unknown item 'zz'")
        self.check(expense(amount="1", annualRate="0.01", basis="value"),
                   "give either an amount or a annualRate, not both")
        self.check(expense(), "give either an amount or a annualRate")
        self.check(expense(annualRate="0.01", basis="balance"),
                   "basis must be value or price for a property; got 'balance'")
        self.check(expense(parent="job", annualRate="2", basis="amount"),
                   "annualRate must be a fraction between 0 and 1")
        self.check(cost(at="later", amount="1"), "at must be start, end or date")
        self.check(cost(at="date", amount="1"), "missing field 'costDate'")
        self.check(cost(at="date", costDate="2040-01-01", amount="1"),
                   "costDate must be within the horizon")
        acct = {"type": "account", "id": "a", "accountType": "tfsa", "annualReturn": "0"}
        self.check(expense(parent="a", annualRate="0.01", basis="value"),
                   "basis must be balance for a account", acct)
        engine.validate(scenario(HOUSE, expense(annualRate="0.01", basis="value"),
                                 cost(at="end", rate="0.05", basis="value")))


class Upgrade(unittest.TestCase):
    CAR = {"type": "vehicle", "id": "v", "name": "Car", "purchaseDate": "2025-08-01",
           "price": "30000", "annualDepreciation": "0.15", "annualMaintenance": "1000.6",
           "maintenanceIncrease": "0.1"}

    def test_vehicle_maintenance_becomes_an_associated_expense(self):
        s = upgrade(scenario(self.CAR))
        self.assertNotIn("annualMaintenance", s["items"][0])
        self.assertEqual(s["items"][1], {
            "type": "associatedExpense", "id": "v-maintenance", "name": "Car maintenance",
            "parent": "v", "amount": "1000.6", "per": "year", "indexing": "custom",
            "indexRate": "0.1"})
        # Same amounts as the vehicle's own maintenance: steps on the purchase anniversary.
        months = paid(run(scenario(self.CAR)), "v-maintenance")
        self.assertEqual((months["2027-07"], months["2027-08"]),
                         (Decimal("91.72"), Decimal("100.89")))   # 1000.6 x 1.1^1 / 12, ^2

    def test_zero_costs_give_no_items(self):
        car = dict(self.CAR, annualMaintenance="0")
        sale = {"type": "sale", "property": "v", "saleDate": "2028-01-01", "sellingCostRate": "0"}
        s = upgrade(scenario(car, sale))
        self.assertEqual([i["type"] for i in s["items"]], ["vehicle", "sale"])
        self.assertIs(upgrade(s), s)


if __name__ == "__main__":
    unittest.main()
