"""The jurisdiction seam (ADR-0071): registry, Canada as the default, hooks that follow
the treatment flags, and validation by jurisdiction.

    cd webapp && .venv/bin/python -m unittest state_machine.tests.test_jurisdictions
"""
import unittest
from decimal import Decimal

from state_machine import engine, jurisdictions, validation
from state_machine.jurisdictions import (DEFERRED, EXEMPT, TAXABLE, AccountType,
                                         Jurisdiction)


def scenario(*items, **over):
    s = {"schemaVersion": 1, "name": "j", "horizon": {"start": "2027-01-01", "end": "2027-12-01"},
         "openingCash": "100000", "effectiveTaxRate": "0.3", "items": list(items)}
    s.update(over)
    return s


class FakeHousehold:
    covered = False

    def __init__(self):
        from state_machine.household import TaxAccumulator
        self.tax = TaxAccumulator()

    def tax_of(self, person):
        return self.tax


class FakeAccount:
    def __init__(self, account_type, rate=None):
        self.account_type = account_type
        self.owner = self.contributor = None
        self.withdrawal_tax_rate = rate


class Registry(unittest.TestCase):
    def test_canada_is_registered_and_the_default(self):
        self.assertIn("CA", jurisdictions.registered())
        self.assertEqual(jurisdictions.of({}).name, "Canada")
        self.assertEqual(jurisdictions.of({"jurisdiction": "CA"}).code, "CA")
        self.assertEqual(list(jurisdictions.get("CA").account_types),
                         ["tfsa", "rrsp", "nonRegistered", "resp"])

    def test_an_unknown_jurisdiction_is_refused(self):
        self.assertIn("jurisdiction must be one of", _refusal(scenario(jurisdiction="XX")))
        with self.assertRaisesRegex(ValueError, "jurisdiction must be one of"):
            engine.run_detailed(scenario(jurisdiction="XX"))


def _refusal(s):
    try:
        validation.validate(s)
    except ValueError as e:
        return str(e)
    return ""


class Hooks(unittest.TestCase):
    """The default hooks do what the flags say."""

    class Test(Jurisdiction):
        account_types = {"d": AccountType("d", "deferred", DEFERRED),
                         "e": AccountType("e", "exempt", EXEMPT),
                         "t": AccountType("t", "taxable", TAXABLE)}

    def run_hooks(self, kind, rate=None):
        hh, acct, rules = FakeHousehold(), FakeAccount(kind, rate), self.Test()
        rules.on_contribute(hh, acct, Decimal("100"))
        rules.on_return(hh, acct, Decimal("10"))
        rules.on_return(hh, acct, Decimal("-5"))            # a loss: no credit
        rules.on_withdraw(hh, acct, Decimal("50"))
        t = hh.tax
        return t.deductions, t.taxable, t.extra_tax

    def test_flags(self):
        self.assertEqual(self.run_hooks("d"), (Decimal("100"), Decimal("50"), Decimal("0")))
        self.assertEqual(self.run_hooks("e"), (Decimal("0"), Decimal("0"), Decimal("0")))
        self.assertEqual(self.run_hooks("t"), (Decimal("0"), Decimal("10"), Decimal("0")))

    def test_own_withdrawal_rate(self):
        self.assertEqual(self.run_hooks("d", Decimal("0.25")),
                         (Decimal("100"), Decimal("0"), Decimal("12.50")))

    def test_income_less_mode_has_no_deduction(self):
        hh, rules = FakeHousehold(), self.Test()
        hh.covered = True
        rules.on_contribute(hh, FakeAccount("d"), Decimal("100"))
        self.assertEqual(hh.tax.deductions, Decimal("0"))


class Validation(unittest.TestCase):
    def test_account_types_come_from_the_jurisdiction(self):
        acc = {"type": "account", "id": "a", "accountType": "roth401k", "annualReturn": "0"}
        self.assertIn("accountType must be one of tfsa, rrsp, nonRegistered, resp",
                      _refusal(scenario(acc)))

    def test_contributor_only_on_types_that_take_it(self):
        persons = [{"type": "person", "id": "p1"}, {"type": "person", "id": "p2"}]
        tfsa = {"type": "account", "id": "a", "accountType": "tfsa", "annualReturn": "0",
                "owner": "p1", "contributor": "p2"}
        self.assertIn("contributor applies only to rrsp accounts (spousal RRSP)",
                      _refusal(scenario(*persons, tfsa)))
        self.assertEqual(_refusal(scenario(*persons, dict(tfsa, accountType="rrsp"))), "")


class Fake(Jurisdiction):
    """A second jurisdiction for the tests: one exempt account type, no own items."""
    name = "Fakeland"
    account_types = {"fakeSaver": AccountType("fakeSaver", "Fake saver", EXEMPT)}


class Switching(unittest.TestCase):
    """ADR-0071 decision 2: the jurisdiction changes only when no item needs the old one."""

    def setUp(self):
        jurisdictions.discover()
        Fake.code = "XX"
        jurisdictions.REGISTRY["XX"] = Fake()

    def tearDown(self):
        del jurisdictions.REGISTRY["XX"]

    def settings(self, s, code):
        from state_machine import ops
        return ops.settings(s, {"name": "j", "horizon": s["horizon"], "openingCash": "1",
                                "jurisdiction": code})

    def test_switch_refused_naming_the_items(self):
        rrsp = {"type": "account", "id": "a", "name": "My RRSP", "accountType": "rrsp",
                "annualReturn": "0"}
        room = {"type": "contributionRoom", "id": "r", "name": "Room", "accountType": "rrsp",
                "room": "0", "roomAsOfDate": "2027-01-01", "yearlyMax": "0"}
        out = self.settings(scenario(rrsp, room), "XX")
        self.assertFalse(out["ok"])
        self.assertIn("My RRSP (rrsp account), Room (contributionRoom)", out["messages"][0])

    def test_switch_allowed_without_country_items(self):
        job = {"type": "income", "id": "j", "startDate": "2027-01-01", "amount": "1",
               "per": "month"}
        out = self.settings(scenario(job), "XX")
        self.assertTrue(out["ok"], out["messages"])
        self.assertEqual(out["scenario"]["jurisdiction"], "XX")
        # Canada's own item type is refused in Fakeland, by name.
        room = {"type": "contributionRoom", "id": "r", "accountType": "rrsp", "room": "0",
                "roomAsOfDate": "2027-01-01", "yearlyMax": "0"}
        self.assertIn("contributionRoom is not available in Fakeland (it belongs to Canada)",
                      _refusal(dict(out["scenario"], items=[room])))

    def test_unknown_code(self):
        self.assertIn("unknown jurisdiction 'ZZ'", self.settings(scenario(), "ZZ")["messages"][0])

    def test_schema_follows_the_jurisdiction(self):
        import schema
        fake = schema.describe("XX")
        self.assertNotIn("contributionRoom", fake["fields"])
        self.assertNotIn("contributor", fake["fields"]["account"])
        self.assertEqual(fake["selects"]["accountType"], [{"value": "fakeSaver",
                                                           "label": "Fake saver"}])
        canada = schema.describe()
        self.assertIn("contributionRoom", canada["fields"])
        self.assertIn("contributor", canada["fields"]["account"])
        self.assertEqual({j["code"] for j in canada["jurisdictions"]} >= {"CA", "XX"}, True)


class Persons(unittest.TestCase):
    def test_birth_date_is_optional_and_checked(self):
        p = {"type": "person", "id": "p", "name": "Pat"}
        self.assertEqual(_refusal(scenario(p)), "")
        self.assertEqual(_refusal(scenario(dict(p, birthDate="1986-02-01"))), "")
        self.assertIn("birthDate", _refusal(scenario(dict(p, birthDate="February 1986"))))


if __name__ == "__main__":
    unittest.main()
