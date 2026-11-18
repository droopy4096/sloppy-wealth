"""Cash flow adjustments (ADR-0062) and market adjustments of vehicles (ADR-0033 amendment).

    cd webapp && .venv/bin/python -m unittest state_machine.tests.test_adjustment
"""
import copy
import unittest
from decimal import Decimal

from state_machine import engine


def scenario(*items):
    return {"schemaVersion": 1, "name": "adjust",
            "horizon": {"start": "2027-01-01", "end": "2031-12-01"},
            "openingCash": "1000000", "effectiveTaxRate": "0.3", "annualInflation": "0.02",
            "items": list(items)}


def flow(kind="expense", **kw):
    return dict({"type": kind, "id": "f", "name": "Flow", "startDate": "2027-01-01",
                 "amount": "1200", "per": "year", "indexing": "inflation"}, **kw)


def adj(date, amount, id="a", **kw):
    return dict({"type": "adjustment", "id": id, "flow": "f", "adjustmentDate": date,
                 "amount": amount}, **kw)


def amounts(result, source="f"):
    return {x["month"]: x["amount"] for x in result["ledger"] if x["source"] == source}


def run(s):
    return engine.run_detailed(copy.deepcopy(s))


class FlowAdjustment(unittest.TestCase):
    def test_resets_and_indexes_from_the_adjustment_date(self):
        r = amounts(run(scenario(flow(), adj("2028-07-01", "2400"))))
        self.assertEqual(r["2028-01"], Decimal("102.00"))       # 100 x 1.02
        self.assertEqual(r["2028-06"], Decimal("102.00"))
        self.assertEqual(r["2028-07"], Decimal("200.00"))       # new amount, per year
        self.assertEqual(r["2029-06"], Decimal("200.00"))       # steps from 2028-07
        self.assertEqual(r["2029-07"], Decimal("204.00"))

    def test_several_steps_and_last_in_a_month_wins(self):
        r = amounts(run(scenario(flow(indexing="none"), adj("2028-01-01", "2400"),
                                 adj("2029-01-01", "3000", id="b"),
                                 adj("2029-01-01", "3600", id="c"))))
        self.assertEqual((r["2027-12"], r["2028-01"], r["2029-01"]),
                         (Decimal("100.00"), Decimal("200.00"), Decimal("300.00")))

    def test_per_defaults_to_the_flows_and_can_be_given(self):
        r = amounts(run(scenario(flow(indexing="none"), adj("2028-01-01", "150", per="month"))))
        self.assertEqual(r["2028-01"], Decimal("150.00"))

    def test_income_contribution_and_withdrawal(self):
        s = scenario({"type": "account", "id": "acc", "name": "TFSA", "accountType": "tfsa",
                      "openingBalance": "100000", "annualReturn": "0"},
                     flow("income", taxable=True), adj("2028-01-01", "2400"),
                     {"type": "contribution", "id": "c", "account": "acc",
                      "startDate": "2027-01-01", "amount": "100"},
                     adj("2028-01-01", "50", id="ac", flow="c"),
                     {"type": "withdrawal", "id": "w", "account": "acc", "method": "amount",
                      "startDate": "2027-01-01", "amount": "300"},
                     adj("2029-01-01", "10", id="aw", flow="w"))
        r = run(s)
        self.assertEqual(amounts(r)["2028-01"], Decimal("200.00"))
        self.assertEqual(amounts(r, "c")["2028-01"], Decimal("50.00"))
        self.assertEqual(amounts(r, "w")["2029-01"], Decimal("10.00"))

    def test_logged_in_its_month(self):
        r = run(scenario(flow(), adj("2028-07-01", "2400")))
        log = [(e["month"], e["detail"]) for e in r["events"] if e["event"] == "FlowAdjusted"]
        self.assertEqual(log, [("2028-07", "f amount set to 2400.00 per year")])

    def test_validation(self):
        def bad(message, *items):
            with self.assertRaisesRegex(ValueError, message):
                engine.validate(scenario(*items))
        bad("refers to unknown income, expense", flow(), adj("2028-01-01", "1", flow="x"))
        acc = {"type": "account", "id": "acc", "accountType": "tfsa", "annualReturn": "0"}
        pct = {"type": "withdrawal", "id": "f", "account": "acc", "method": "percent",
               "startDate": "2027-01-01", "annualRate": "0.04"}
        bad("an annuity withdrawal cannot be adjusted", acc,
            dict(pct, method="annuity", annualRate=""), adj("2028-01-01", "1"))
        bad("takes a new annualRate, not an amount", acc, pct, adj("2028-01-01", "1"))
        bad("annualRate must be a fraction", acc, pct,
            {"type": "adjustment", "flow": "f", "adjustmentDate": "2028-01-01",
             "annualRate": "5"})
        bad("annualRate applies only to percent withdrawals", flow(),
            {"type": "adjustment", "flow": "f", "adjustmentDate": "2028-01-01",
             "annualRate": "0.05"})
        bad("amount must not be negative", flow(), adj("2028-01-01", "-1"))
        bad("adjustmentDate must be within the horizon", flow(), adj("2035-01-01", "1"))
        engine.validate(scenario(flow(), adj("2028-01-01", "0")))

    def test_custom_indexing_needs_a_rate_on_contributions_and_withdrawals(self):
        acc = {"type": "account", "id": "acc", "accountType": "tfsa", "annualReturn": "0"}
        for kind in ("contribution", "withdrawal"):
            item = {"type": kind, "id": "f", "account": "acc", "startDate": "2027-01-01",
                    "amount": "10", "method": "amount", "indexing": "custom", "indexRate": ""}
            with self.assertRaisesRegex(ValueError, "'indexRate' is not a number"):
                engine.validate(scenario(acc, item))


class PercentRateAdjustment(unittest.TestCase):
    def test_new_rate_resets_in_its_month_and_on_its_anniversaries(self):
        s = scenario({"type": "account", "id": "acc", "name": "RRSP", "accountType": "tfsa",
                      "openingBalance": "120000", "annualReturn": "0"},
                     {"type": "withdrawal", "id": "f", "account": "acc", "method": "percent",
                      "startDate": "2027-01-01", "annualRate": "0.04"},
                     {"type": "adjustment", "id": "a", "flow": "f",
                      "adjustmentDate": "2027-07-01", "annualRate": "0.06"})
        r = run(s)
        paid = amounts(r)
        self.assertEqual(paid["2027-06"], Decimal("400.00"))       # 120000 x 4% / 12
        # 2027-07: balance 117600 x 6% / 12; kept until 2028-07 (its anniversary).
        self.assertEqual(paid["2027-07"], Decimal("588.00"))
        self.assertEqual(paid["2028-01"], Decimal("588.00"))
        self.assertEqual(paid["2028-07"], Decimal("552.72"))       # 110544 x 6% / 12
        log = [e["detail"] for e in r["events"] if e["event"] == "FlowAdjusted"]
        self.assertEqual(log, ["f annual rate set to 6.00%"])


class VehicleMarketAdjustment(unittest.TestCase):
    def test_new_value_and_depreciation_continues(self):
        s = scenario({"type": "vehicle", "id": "car", "name": "Car", "purchaseDate": "2025-01-01",
                      "price": "30000", "annualDepreciation": "0.1", "annualMaintenance": "0"},
                     {"type": "marketAdjustment", "id": "m", "property": "car",
                      "adjustmentDate": "2028-03-01", "newValue": "10000"})
        r = run(s)
        car = next(h for h in r["holdings"] if h["id"] == "car")
        points = {p["month"]: p["closing"] for p in car["points"]}
        self.assertEqual(points["2028-03"], Decimal("10000.00"))
        self.assertLess(points["2028-04"], Decimal("10000.00"))


if __name__ == "__main__":
    unittest.main()
