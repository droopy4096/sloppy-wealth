"""Canada: RESP accounts with the CESG grant (ADR-0072).

    cd webapp && .venv/bin/python -m unittest state_machine.tests.test_resp
"""
import unittest
from decimal import Decimal

from state_machine import engine, validation

D = Decimal


def scenario(*items, **over):
    s = {"schemaVersion": 1, "name": "resp", "jurisdiction": "CA",
         "horizon": {"start": "2027-01-01", "end": "2029-12-01"},
         "openingCash": "200000", "effectiveTaxRate": "0.3", "items": list(items)}
    s.update(over)
    return s


def resp(**over):
    return dict({"type": "account", "id": "r", "name": "Kid's RESP", "accountType": "resp",
                 "annualReturn": "0"}, **over)


def monthly(amount, **over):
    return dict({"type": "contribution", "id": "c", "account": "r", "startDate": "2027-01-01",
                 "amount": amount, "per": "month"}, **over)


def total(result, kind, year=None):
    return sum((x["amount"] for x in result["ledger"] if x["kind"] == kind
                and (year is None or x["month"].startswith(str(year)))), D(0))


def refusal(s):
    try:
        validation.validate(s)
    except ValueError as e:
        return str(e)
    return ""


class Grant(unittest.TestCase):
    def test_twenty_percent_up_to_500_a_year(self):
        # 2500 a year (208.33 a month) earns exactly the $500 a year.
        r = engine.run_detailed(scenario(resp(), monthly("2500", per="year")))
        self.assertEqual([total(r, "GRANT", y) for y in (2027, 2028, 2029)], [D("500.00")] * 3)
        r = engine.run_detailed(scenario(resp(), monthly("100")))      # 1200 a year
        self.assertEqual(total(r, "GRANT", 2027), D("240.00"))
        jan = [x for x in r["ledger"] if x["kind"] == "GRANT" and x["month"] == "2027-01"]
        self.assertEqual((jan[0]["to"], jan[0]["from"], jan[0]["amount"], jan[0]["source"]),
                         ("r", None, D("20.00"), "c"))

    def test_unused_room_caught_up_at_most_1000_a_year(self):
        # 5000 each March with 1000 of unused room: room 1500 -> grant 1000 (max a year),
        # then 500 + 500 = 1000 -> 1000, then 0 + 500 -> 500.
        transfers = [{"type": "transfer", "id": f"t{y}", "account": "r",
                      "transferDate": f"{y}-03-01", "amount": "5000"} for y in (2027, 2028, 2029)]
        r = engine.run_detailed(scenario(resp(unusedGrantRoom="1000"), *transfers))
        self.assertEqual([total(r, "GRANT", y) for y in (2027, 2028, 2029)],
                         [D("1000.00"), D("1000.00"), D("500.00")])

    def test_lifetime_grant_7200(self):
        r = engine.run_detailed(scenario(resp(grantReceived="6900"), monthly("2500", per="year")))
        self.assertEqual(total(r, "GRANT"), D("300.00"))

    def test_no_deduction_and_untaxed(self):
        draw = {"type": "withdrawal", "id": "w", "account": "r", "method": "amount",
                "amount": "1000", "per": "month", "startDate": "2027-01-01"}
        r = engine.run_detailed(scenario(resp(openingBalance="20000"), monthly("500"), draw))
        jan = r["tax"]["2027-01"]
        self.assertEqual((jan["deductions"], jan["taxable"]), (D("0.00"), D("0.00")))

    def test_transfer_earns_the_grant_and_opening_balance_does_not(self):
        t = {"type": "transfer", "id": "t", "account": "r", "transferDate": "2027-05-01",
             "amount": "2000"}
        r = engine.run_detailed(scenario(resp(openingBalance="30000"), t))
        self.assertEqual(total(r, "GRANT"), D("400.00"))


class LifetimeLimit(unittest.TestCase):
    def test_contributions_capped_at_50000(self):
        r = engine.run_detailed(scenario(resp(contributedSoFar="48000"), monthly("500")))
        self.assertEqual(total(r, "CONTRIBUTION"), D("2000.00"))
        self.assertEqual(total(r, "GRANT"), D("400.00"))


class Validation(unittest.TestCase):
    def test_fields_only_on_an_resp(self):
        self.assertEqual(refusal(scenario(resp(grantReceived="100"))), "")
        tfsa = resp(accountType="tfsa", grantReceived="100")
        self.assertIn("grantReceived applies only to resp accounts", refusal(scenario(tfsa)))
        self.assertIn("must not be negative", refusal(scenario(resp(unusedGrantRoom="-1"))))

    def test_not_in_the_us(self):
        self.assertIn("accountType must be one of",
                      refusal(scenario(resp(), jurisdiction="US")))


if __name__ == "__main__":
    unittest.main()
