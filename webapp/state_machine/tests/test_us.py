"""United States (ADR-0071): account tax treatments and yearly contribution limits.

    cd webapp && .venv/bin/python -m unittest state_machine.tests.test_us
"""
import unittest
from decimal import Decimal

from state_machine import engine, validation

D = Decimal


def scenario(*items, **over):
    s = {"schemaVersion": 1, "name": "us", "jurisdiction": "US",
         "horizon": {"start": "2027-01-01", "end": "2028-12-01"},
         "openingCash": "500000", "effectiveTaxRate": "0.25", "items": list(items)}
    s.update(over)
    return s


PAT = {"type": "person", "id": "pat", "name": "Pat", "birthDate": "1975-06-01"}


def account(kind, **over):
    return dict({"type": "account", "id": "acc", "name": kind, "accountType": kind,
                 "annualReturn": "0"}, **over)


def contribution(amount="2500", **over):
    return dict({"type": "contribution", "id": "c", "account": "acc",
                 "startDate": "2027-01-01", "amount": amount, "per": "month"}, **over)


def limit(**over):
    return dict({"type": "contributionLimit", "id": "l", "limitType": "401k",
                 "yearlyLimit": "23500", "limitYear": "2027"}, **over)


def refusal(s):
    try:
        validation.validate(s)
    except ValueError as e:
        return str(e)
    return ""


def moved(result, kind, year=None, source=None):
    return sum((x["amount"] for x in result["ledger"] if x["kind"] == kind
                and (year is None or x["month"].startswith(str(year)))
                and (source is None or x["source"] == source)), D(0))


class Treatments(unittest.TestCase):
    def month_tax(self, result, month):
        return result["tax"][month] if "tax" in result else None

    def test_traditional_is_deducted_and_its_withdrawals_taxed(self):
        draw = {"type": "withdrawal", "id": "w", "account": "acc", "method": "amount",
                "amount": "1000", "per": "month", "startDate": "2027-01-01"}
        r = engine.run_detailed(scenario(account("traditional401k", openingBalance="100000"),
                                         contribution("500"), draw))
        jan = r["tax"]["2027-01"]
        self.assertEqual((jan["deductions"], jan["taxable"]), (D("500.00"), D("1000.00")))

    def test_roth_is_neither_deducted_nor_taxed(self):
        draw = {"type": "withdrawal", "id": "w", "account": "acc", "method": "amount",
                "amount": "1000", "per": "month", "startDate": "2027-01-01"}
        r = engine.run_detailed(scenario(account("rothIra", openingBalance="100000"),
                                         contribution("500"), draw))
        jan = r["tax"]["2027-01"]
        self.assertEqual((jan["deductions"], jan["taxable"]), (D("0.00"), D("0.00")))

    def test_hsa_deducted_withdrawals_free_and_brokerage_returns_taxed(self):
        r = engine.run_detailed(scenario(account("hsa", openingBalance="10000"),
                                         contribution("300")))
        self.assertEqual(r["tax"]["2027-01"]["deductions"], D("300.00"))
        b = engine.run_detailed(scenario(account("brokerage", openingBalance="120000",
                                                 annualReturn="0.12")))
        self.assertGreater(b["tax"]["2027-02"]["taxable"], D(0))


class Limits(unittest.TestCase):
    def test_capped_at_the_yearly_limit_and_reset_each_january(self):
        r = engine.run_detailed(scenario(PAT | {"birthDate": ""}, account("traditional401k", owner="pat"),
                                         contribution(owner=None), limit(owner="pat")))
        self.assertEqual(moved(r, "CONTRIBUTION", 2027), D("23500.00"))
        self.assertEqual(moved(r, "CONTRIBUTION", 2028), D("23500.00"))
        rows = {row["month"]: row for row in r["rows"]}
        self.assertEqual(rows["2027-09"]["k401Limit"], D("1000.00"))   # 9 x 2500 = 22500
        self.assertEqual(rows["2027-12"]["k401Limit"], D("0.00"))
        self.assertEqual(rows["2028-01"]["k401Limit"], D("21000.00"))

    def test_catch_up_from_the_year_the_person_turns_50(self):
        # Born 1975: 52 in 2027, so 23500 + 7500 = 31000 >= 12 x 2500.
        r = engine.run_detailed(scenario(PAT, account("roth401k", owner="pat"),
                                         contribution(), limit(owner="pat", catchUp="7500")))
        self.assertEqual(moved(r, "CONTRIBUTION", 2027), D("30000.00"))
        young = dict(PAT, birthDate="1990-01-01")
        r = engine.run_detailed(scenario(young, account("roth401k", owner="pat"),
                                         contribution(), limit(owner="pat", catchUp="7500")))
        self.assertEqual(moved(r, "CONTRIBUTION", 2027), D("23500.00"))

    def test_traditional_and_roth_share_the_group_limit(self):
        roth = account("roth401k", id="roth", name="Roth")
        r = engine.run_detailed(scenario(account("traditional401k"), roth, contribution("1500"),
                                         contribution("1500", id="c2", account="roth"),
                                         limit()))
        self.assertEqual(moved(r, "CONTRIBUTION", 2027), D("23500.00"))

    def test_match_is_outside_the_limit(self):
        r = engine.run_detailed(scenario(account("traditional401k"),
                                         contribution(employerMatch="0.5"), limit()))
        self.assertEqual(moved(r, "CONTRIBUTION", 2027), D("23500.00"))
        # Half of what was actually contributed, not reduced by the used-up limit.
        self.assertEqual(moved(r, "EMPLOYER_MATCH", 2027), D("11750.00"))

    def test_indexing_rounds_down_and_contributed_so_far(self):
        r = engine.run_detailed(scenario(account("traditionalIra"), contribution("1000"),
                                         limit(limitType="ira", yearlyLimit="7000",
                                               indexing="custom", indexRate="0.03",
                                               contributedSoFar="2000")))
        self.assertEqual(moved(r, "CONTRIBUTION", 2027), D("5000.00"))
        self.assertEqual(moved(r, "CONTRIBUTION", 2028), D("7000.00"))   # 7210 -> 7000

    def test_brokerage_is_not_limited(self):
        r = engine.run_detailed(scenario(account("brokerage"), contribution(), limit()))
        self.assertEqual(moved(r, "CONTRIBUTION", 2027), D("30000.00"))


class Validation(unittest.TestCase):
    def test_canadian_types_are_refused(self):
        self.assertIn("accountType must be one of traditional401k, roth401k",
                      refusal(scenario(account("rrsp"))))
        room = {"type": "contributionRoom", "id": "r", "accountType": "rrsp", "room": "0",
                "roomAsOfDate": "2027-01-01", "yearlyMax": "0"}
        self.assertIn("contributionRoom is not available in United States (it belongs to "
                      "Canada)", refusal(scenario(room)))

    def test_limit_items(self):
        self.assertEqual(refusal(scenario(limit())), "")
        self.assertIn("limitType must be one of 401k, ira, hsa",
                      refusal(scenario(limit(limitType="tfsa"))))
        self.assertIn("only one contributionLimit item per limit type",
                      refusal(scenario(limit(), limit(id="l2"))))
        self.assertIn("is not available in Canada",
                      refusal(scenario(limit(), jurisdiction="CA")))
        self.assertIn("contributor applies only to no accounts",
                      refusal(scenario(PAT, dict(PAT, id="sam"),
                                       account("traditionalIra", owner="pat", contributor="sam"))))


if __name__ == "__main__":
    unittest.main()
