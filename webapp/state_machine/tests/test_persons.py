"""Persons in the household (ADR-0061).

    cd webapp && .venv/bin/python -m unittest state_machine.tests.test_persons
"""
import copy
import unittest
from decimal import Decimal

from state_machine import compiler, engine
from state_machine.dates import retirement_dates
from state_machine.household import Household
from state_machine.persons import IMPLICIT, owner_of, retirement_person


def person(pid, **kw):
    return dict({"type": "person", "id": pid, "name": pid.title()}, **kw)


def scenario(*items, **over):
    s = {"schemaVersion": 1, "name": "persons",
         "horizon": {"start": "2027-01-01", "end": "2030-12-01"},
         "openingCash": "100000", "effectiveTaxRate": "0.3", "annualInflation": "0.02",
         "items": list(items)}
    s.update(over)
    return s


def account(aid, kind="rrsp", **kw):
    return dict({"type": "account", "id": aid, "name": aid, "accountType": kind,
                 "openingBalance": "1000", "annualReturn": "0"}, **kw)


def run(s):
    return engine.run_detailed(copy.deepcopy(s))


class PersonsModel(unittest.TestCase):
    def test_implicit_person_without_person_items(self):
        hh = Household(scenario(retirementTaxRate="0.2"))
        self.assertEqual(list(hh.persons), [IMPLICIT])
        self.assertEqual(hh.first.tax_rate, Decimal("0.3"))
        self.assertEqual(hh.first.retirement_tax_rate, Decimal("0.2"))

    def test_rates_fall_back_to_the_scenario(self):
        hh = Household(scenario(person("a"), person("b", effectiveTaxRate="0.4"),
                                person("c", effectiveTaxRate="0.25", retirementTaxRate="0.1"),
                                retirementTaxRate="0.2"))
        rates = {p.id: (p.tax_rate, p.retirement_tax_rate) for p in hh.persons.values()}
        self.assertEqual(rates["a"], (Decimal("0.3"), Decimal("0.2")))
        self.assertEqual(rates["b"], (Decimal("0.4"), Decimal("0.2")))
        self.assertEqual(rates["c"], (Decimal("0.25"), Decimal("0.1")))
        self.assertIs(hh.first, hh.persons["a"])

    def test_retired_rate_falls_back_to_own_working_rate(self):
        hh = Household(scenario(person("a", effectiveTaxRate="0.4")))
        self.assertEqual(hh.persons["a"].retirement_tax_rate, Decimal("0.4"))

    def test_owners(self):
        s = scenario(person("a"), person("b"), account("r", owner="b"),
                     {"type": "contribution", "account": "r"}, {"type": "expense"},
                     {"type": "income"})
        items = s["items"]
        self.assertEqual(owner_of(items[2], s), "b")
        self.assertEqual(owner_of(items[3], s), "b")      # via its account
        self.assertEqual(owner_of(items[4], s), "a")      # household item: first person
        self.assertEqual(owner_of(items[5], s), "a")      # blank owner: first person
        self.assertEqual(retirement_person({"type": "sale", "retirementOf": "b"}, s), "b")
        self.assertEqual(retirement_person({"type": "sale"}, s), "a")
        self.assertEqual(retirement_person(items[3], s), "b")

    def test_retirement_dates(self):
        s = scenario(person("a"), person("b"),
                     {"type": "retirement", "retirementDate": "2028-01-01"},
                     {"type": "retirement", "owner": "b", "retirementDate": "2029-06-01"})
        self.assertEqual(retirement_dates(s), {"a": "2028-01-01", "b": "2029-06-01"})
        legacy = scenario(person("a"), person("b"), retirementDate="2028-01-01")
        self.assertEqual(retirement_dates(legacy), {"a": "2028-01-01", "b": ""})

    def test_owners_reach_the_aggregates(self):
        s = scenario(person("a"), person("b"), account("r", owner="b", contributor="a"),
                     account("t", kind="tfsa"))
        hh, runner = compiler.compile_scenario(copy.deepcopy(s))
        runner.run(hh)
        self.assertEqual((hh["r"].owner, hh["r"].contributor), ("b", "a"))
        self.assertEqual((hh["t"].owner, hh["t"].contributor), ("a", "a"))


class Validation(unittest.TestCase):
    def check(self, message, *items, **over):
        with self.assertRaisesRegex(ValueError, message):
            engine.validate(scenario(*items, **over))

    def test_errors(self):
        self.check("a person needs an id", {"type": "person", "name": "X"})
        self.check("another person has the id", person("a"), person("a"))
        self.check("effectiveTaxRate must be a fraction", person("a", effectiveTaxRate="30"))
        self.check("owner refers to unknown person 'z'", person("a"), account("r", owner="z"))
        self.check(r"unknown person 'a' \(add a person item first\)", account("r", owner="a"))
        self.check("owner applies only to", person("a"),
                   {"type": "expense", "owner": "a", "startDate": "2027-01-01", "amount": "1"})
        self.check("contributor applies only to rrsp", person("a"), person("b"),
                   account("t", kind="tfsa", contributor="b"))
        self.check("contributor is the owner", person("a"), person("b"),
                   account("r", owner="b", contributor="b"))
        self.check("retirementOf refers to unknown person", person("a"),
                   {"type": "expense", "retirementOf": "q", "startDate": "2027-01-01",
                    "amount": "1"})

    def test_valid(self):
        engine.validate(scenario(person("a"), person("b", retirementTaxRate="0.15"),
                                 account("r", owner="b", contributor="a"),
                                 {"type": "income", "owner": "b", "startDate": "2027-01-01",
                                  "amount": "1000"}))


def two_retirements(*items):
    return scenario(person("a"), person("b"),
                    {"type": "retirement", "id": "ra", "retirementDate": "2028-01-01"},
                    {"type": "retirement", "id": "rb", "owner": "b",
                     "retirementDate": "2029-07-01"}, *items)


def moved(result, kind, source=None):
    return [(x["month"], x["amount"]) for x in result["ledger"]
            if x["kind"] == kind and (source is None or x["source"] == source)]


class RetirementPerPerson(unittest.TestCase):
    def test_salary_ends_at_its_owners_retirement(self):
        r = run(two_retirements(
            {"type": "income", "id": "ja", "startDate": "2027-01-01", "amount": "100",
             "endsAtRetirement": True},
            {"type": "income", "id": "jb", "owner": "b", "startDate": "2027-01-01",
             "amount": "100", "endsAtRetirement": True}))
        self.assertEqual(moved(r, "INCOME", "ja")[-1][0], "2027-12")
        self.assertEqual(moved(r, "INCOME", "jb")[-1][0], "2029-06")

    def test_household_items_follow_retirement_of(self):
        prop = {"type": "property", "id": "h", "purchaseDate": "2020-01-01", "price": "100000",
                "annualAppreciation": "0", "sellingCostRate": "0"}
        r = run(two_retirements(prop, {"type": "sale", "id": "s", "property": "h",
                                       "atRetirement": True, "retirementOf": "b"}))
        self.assertEqual(moved(r, "SALE", "s")[0][0], "2029-07")
        r = run(two_retirements(
            {"type": "expense", "id": "e", "startDate": "2027-01-01", "amount": "10",
             "endsAtRetirement": True}))
        self.assertEqual(moved(r, "EXPENSE", "e")[-1][0], "2027-12")   # first person

    def test_flows_and_pensions_follow_their_account_or_owner(self):
        r = run(two_retirements(
            account("rb", owner="b", openingBalance="12000"),
            {"type": "withdrawal", "id": "w", "account": "rb", "method": "amount",
             "amount": "100"},
            {"type": "pension", "id": "p", "owner": "b", "amount": "500"}))
        self.assertEqual(moved(r, "WITHDRAWAL", "w")[0][0], "2029-07")
        self.assertEqual(moved(r, "PENSION_PAYMENT")[0][0], "2029-07")

    def test_each_person_retires_in_the_event_log(self):
        r = run(two_retirements())
        log = [(e["month"], e["detail"]) for e in r["events"] if e["event"] == "Retirement"]
        self.assertEqual(log, [("2028-01", "A retired"), ("2029-07", "B retired")])

    def test_validation(self):
        with self.assertRaisesRegex(ValueError, "person 'b' has more than one retirement"):
            engine.validate(two_retirements({"type": "retirement", "owner": "b",
                                             "retirementDate": "2030-01-01"}))
        with self.assertRaisesRegex(ValueError, "no retirement event"):
            engine.validate(scenario(person("a"), person("b"),
                                     {"type": "retirement", "retirementDate": "2028-01-01"},
                                     {"type": "income", "owner": "b", "amount": "1",
                                      "startsAtRetirement": True}))
        engine.validate(two_retirements())


def earners(*items, **over):
    return scenario(person("a"), person("b", effectiveTaxRate="0.2", retirementTaxRate="0.1"),
                    {"type": "income", "id": "ja", "startDate": "2027-01-01",
                     "amount": "10000", "taxable": True},
                    {"type": "income", "id": "jb", "owner": "b", "startDate": "2027-01-01",
                     "amount": "5000", "taxable": True}, *items, **over)


def tax_lines(result, month):
    return {x["source"]: x["amount"] for x in result["ledger"]
            if x["kind"] == "TAX" and x["month"] == month}


class TaxPerPerson(unittest.TestCase):
    def test_each_person_at_their_own_rate(self):
        r = run(earners())
        self.assertEqual(tax_lines(r, "2027-01"), {"a": Decimal("3000.00"), "b": Decimal("1000.00")})
        detail = r["tax"]["2027-01"]
        self.assertEqual(detail["total"], Decimal("4000.00"))
        self.assertEqual(detail["persons"]["b"]["rate"], Decimal("0.2"))
        self.assertIsNone(detail["rate"])

    def test_retirement_switches_only_that_persons_rate(self):
        r = run(earners({"type": "retirement", "owner": "b", "retirementDate": "2028-01-01"}))
        self.assertEqual(tax_lines(r, "2028-01"), {"a": Decimal("3000.00"), "b": Decimal("500.00")})

    def test_rrsp_deduction_reduces_only_its_owners_tax(self):
        r = run(earners(account("rb", owner="b"),
                        {"type": "transfer", "id": "x", "account": "rb", "amount": "8000",
                         "transferDate": "2027-03-01"}))
        self.assertEqual(tax_lines(r, "2027-03"), {"a": Decimal("3000.00")})   # b: 0
        self.assertEqual(r["tax"]["2027-03"]["persons"]["b"]["poolOut"], Decimal("3000.00"))
        self.assertEqual(tax_lines(r, "2027-04"), {"a": Decimal("3000.00"), "b": Decimal("400.00")})

    def test_spousal_rrsp_deducts_for_the_contributor_and_taxes_the_owner(self):
        r = run(earners(account("sp", owner="b", contributor="a", openingBalance="0"),
                        {"type": "transfer", "id": "x", "account": "sp", "amount": "10000",
                         "transferDate": "2027-03-01"},
                        {"type": "withdrawal", "id": "w", "account": "sp", "method": "amount",
                         "amount": "1000", "startDate": "2027-05-01",
                         "endDate": "2027-05-01"}))
        self.assertEqual(tax_lines(r, "2027-03"), {"b": Decimal("1000.00")})   # a: 0
        self.assertEqual(r["tax"]["2027-05"]["persons"]["b"]["taxable"], Decimal("6000.00"))

    def test_investment_income_taxed_to_the_owner(self):
        r = run(scenario(person("a"), person("b", effectiveTaxRate="0.1"),
                         account("n", kind="nonRegistered", owner="b", openingBalance="120000",
                                 annualReturn="0.1")))
        self.assertEqual(set(tax_lines(r, "2027-01")), {"b"})

    def test_single_person_detail_shape_unchanged(self):
        r = run(scenario({"type": "income", "startDate": "2027-01-01", "amount": "100",
                          "taxable": True}))
        self.assertNotIn("persons", r["tax"]["2027-01"])
        self.assertEqual(tax_lines(r, "2027-01"), {None: Decimal("30.00")})


def room(pid, kind="rrsp", amount="5000", **kw):
    return dict({"type": "contributionRoom", "id": f"{kind}-{pid}", "accountType": kind,
                 "owner": pid, "room": amount, "roomAsOfDate": "2027-01-01",
                 "yearlyMax": "33810" if kind == "rrsp" else "7000", "maxYear": "2026"}, **kw)


class RoomPerPerson(unittest.TestCase):
    def test_each_person_uses_own_room(self):
        r = run(earners(room("a"), room("b", amount="2000"), account("ra"),
                        account("rb", owner="b"),
                        {"type": "transfer", "id": "x", "account": "ra", "amount": "4000",
                         "transferDate": "2027-03-01"},
                        {"type": "transfer", "id": "y", "account": "rb", "amount": "4000",
                         "transferDate": "2027-03-01"}))
        self.assertEqual(moved(r, "TRANSFER", "x"), [("2027-03", Decimal("4000.00"))])
        self.assertEqual(moved(r, "TRANSFER", "y"), [("2027-03", Decimal("2000.00"))])
        rows = {row["month"]: row for row in r["rows"]}
        self.assertEqual(rows["2027-02"]["rrspRoom"], Decimal("7000.00"))   # household total
        self.assertEqual(rows["2027-03"]["rrspRoom"], Decimal("1000.00"))

    def test_new_room_from_own_earned_income(self):
        r = run(earners(room("a", amount="0"), room("b", amount="0")))
        log = {e["detail"] for e in r["events"] if e["event"] == "RoomYear"
               and e["month"] == "2028-01"}
        # a: 120000 x 18% = 21600; b: 60000 x 18% = 10800.
        self.assertEqual(log, {"A: rrsp contribution room 0.00 + 21600.00 = 21600.00",
                               "B: rrsp contribution room 0.00 + 10800.00 = 10800.00"})

    def test_spousal_rrsp_uses_the_contributors_room(self):
        r = run(earners(room("a", amount="3000"), room("b", amount="0"),
                        account("sp", owner="b", contributor="a", openingBalance="0"),
                        {"type": "transfer", "id": "x", "account": "sp", "amount": "5000",
                         "transferDate": "2027-03-01"}))
        self.assertEqual(moved(r, "TRANSFER", "x"), [("2027-03", Decimal("3000.00"))])

    def test_tfsa_withdrawal_adds_back_to_the_owners_room(self):
        r = run(earners(room("a", "tfsa", "0"), room("b", "tfsa", "0"),
                        account("tb", kind="tfsa", owner="b"),
                        {"type": "withdrawal", "id": "w", "account": "tb", "method": "amount",
                         "amount": "500", "startDate": "2027-06-01", "endDate": "2027-06-01"}))
        log = {e["detail"] for e in r["events"] if e["event"] == "RoomYear"
               and e["month"] == "2028-01"}
        self.assertIn("B: tfsa contribution room 0.00 + 7500.00 = 7500.00", log)  # 7000 + 500
        self.assertIn("A: tfsa contribution room 0.00 + 7000 = 7000.00", log)

    def test_validation_one_room_per_person_and_type(self):
        engine.validate(earners(room("a"), room("b")))
        with self.assertRaisesRegex(ValueError, r"per account type \(rrsp\) and person \(b\)"):
            engine.validate(earners(room("b"), room("b", id="again")))


if __name__ == "__main__":
    unittest.main()
