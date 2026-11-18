"""Expenses attached to an asset or an income (ADR-0040 amendments), now triggers
(ADR-0065 amendment): older ``attachedTo`` files are converted by ``upgrade``.

    cd webapp && .venv/bin/python -m unittest state_machine.tests.test_attached_cost
"""
import copy
import unittest
from decimal import Decimal

from state_machine import engine
from state_machine.upgrade import upgrade


def scenario(*items):
    return {"schemaVersion": 1, "name": "attached",
            "horizon": {"start": "2027-01-01", "end": "2030-12-01"},
            "openingCash": "1000000", "effectiveTaxRate": "0.3", "annualInflation": "0.02",
            "items": [{"type": "property", "id": "h", "name": "House",
                       "purchaseDate": "2020-01-01", "price": "500000",
                       "annualAppreciation": "0.03", "sellingCostRate": "0"}, *items]}


def tax(**kw):
    return dict({"type": "expense", "id": "ptax", "name": "Property tax", "attachedTo": "h",
                 "amount": "4800", "per": "year"}, **kw)


def paid(result):
    return [x["month"] for x in result["ledger"] if x["source"] == "ptax"]


def run(s):
    return engine.run_detailed(copy.deepcopy(s))


class AttachedExpense(unittest.TestCase):
    def test_stops_in_the_sale_month(self):
        r = run(scenario(tax(), {"type": "sale", "id": "s", "property": "h",
                                 "saleDate": "2028-06-01"}))
        months = paid(r)
        self.assertEqual((months[0], months[-1]), ("2027-01", "2028-05"))

    def test_follows_a_sale_at_retirement(self):
        s = scenario(tax(), {"type": "sale", "id": "s", "property": "h", "atRetirement": True},
                     {"type": "retirement", "retirementDate": "2029-03-01"})
        self.assertEqual(paid(run(s))[-1], "2029-02")

    def test_starts_with_a_purchase_inside_the_horizon(self):
        s = scenario({"type": "property", "id": "n", "name": "New", "purchaseDate": "2028-04-01",
                      "price": "300000", "annualAppreciation": "0", "sellingCostRate": "0"},
                     tax(attachedTo="n", startDate="2027-01-01"))
        self.assertEqual(paid(run(s))[0], "2028-04")

    def test_blank_start_is_the_purchase_date_for_indexing(self):
        r = run(scenario(tax(indexing="inflation")))
        first = next(x["amount"] for x in r["ledger"] if x["source"] == "ptax")
        # Indexed yearly from the 2020-01 purchase: 400 x 1.02^7 in 2027.
        self.assertEqual(first, Decimal("459.47"))

    def test_attached_to_a_vehicle_and_unattached_unchanged(self):
        car = {"type": "vehicle", "id": "c", "name": "Car", "purchaseDate": "2026-01-01",
               "price": "20000", "annualDepreciation": "0.1", "annualMaintenance": "0"}
        r = run(scenario(car, tax(attachedTo="c", amount="100", per="month"),
                         {"type": "sale", "id": "s", "property": "c", "saleDate": "2027-03-01"}))
        self.assertEqual(paid(r), ["2027-01", "2027-02"])

    def test_validation(self):
        with self.assertRaisesRegex(ValueError, "attachedTo refers to unknown property, vehicle or income"):
            engine.validate(scenario(tax(attachedTo="zz")))
        with self.assertRaisesRegex(ValueError, "attachedTo applies only to expenses"):
            engine.validate(scenario({"type": "income", "attachedTo": "h", "amount": "1",
                                      "startDate": "2027-01-01"}))
        with self.assertRaisesRegex(ValueError, "missing field 'startDate'"):
            engine.validate(scenario(tax(attachedTo="")))
        engine.validate(scenario(tax()))


class AttachedToIncome(unittest.TestCase):
    def job_scenario(self, **job):
        return scenario(dict({"type": "income", "id": "job", "name": "Job",
                              "startDate": "2027-04-01", "endDate": "2029-09-01",
                              "amount": "5000", "taxable": True}, **job),
                        tax(attachedTo="job", amount="100", per="month"))

    def test_runs_only_while_the_income_runs(self):
        months = paid(run(self.job_scenario()))
        self.assertEqual((months[0], months[-1], len(months)), ("2027-04", "2029-09", 30))

    def test_follows_the_income_ending_at_retirement(self):
        s = self.job_scenario(endDate="", endsAtRetirement=True)
        s["items"].append({"type": "retirement", "retirementDate": "2028-07-01"})
        self.assertEqual(paid(run(s))[-1], "2028-06")

    def test_own_dates_are_cut_to_the_income(self):
        s = self.job_scenario()
        s["items"][-1].update(startDate="2028-01-01", endDate="2030-12-01")
        months = paid(run(s))
        self.assertEqual((months[0], months[-1]), ("2028-01", "2029-09"))


def trig(event, action, on="start", target="ptax"):
    t = {"type": "trigger", "id": f"{target}-{action}-{on}", "event": event,
         "target": target, "action": action}
    if on != "start":
        t["on"] = on
    return t


class AttachedToConverted(unittest.TestCase):
    def converted(self, *items):
        s = upgrade(scenario(*items))
        return ([i for i in s["items"] if i.get("type") == "trigger"],
                next(i for i in s["items"] if i.get("id") == "ptax"))

    def test_without_own_dates_an_associated_expense(self):
        triggers, ptax = self.converted(tax())
        self.assertNotIn("attachedTo", ptax)
        self.assertEqual(triggers, [])
        self.assertEqual((ptax["type"], ptax["parent"]), ("associatedExpense", "h"))

    def test_own_dates_give_start_and_end_triggers(self):
        triggers, ptax = self.converted(tax(endDate="2030-01-01"))
        self.assertEqual([(t["event"], t["action"], t.get("on", "start")) for t in triggers],
                         [("h", "start", "start"), ("h", "end", "end")])

    def test_own_later_start_is_kept_without_a_start_trigger(self):
        triggers, ptax = self.converted(tax(startDate="2027-01-01"))
        self.assertEqual([t["action"] for t in triggers], ["end"])
        self.assertEqual(ptax["startDate"], "2027-01-01")

    def test_blank_attached_to_is_dropped(self):
        triggers, ptax = self.converted(tax(attachedTo="", startDate="2027-01-01"))
        self.assertEqual((triggers, "attachedTo" in ptax), ([], False))

    def test_converted_twice_is_unchanged(self):
        once = upgrade(scenario(tax()))
        self.assertIs(upgrade(once), once)


class TriggerOnEnd(unittest.TestCase):
    def test_end_on_a_sale_follows_the_sale_at_retirement(self):
        plain = {k: v for k, v in tax().items() if k != "attachedTo"}
        s = scenario(plain, trig("h", "start"), trig("h", "end", "end"),
                     {"type": "sale", "id": "s", "property": "h"},
                     {"type": "retirement", "id": "r", "retirementDate": "2029-03-01"},
                     trig("r", "start", target="s"))
        self.assertEqual(paid(run(s))[-1], "2029-02")

    def test_asset_never_sold_runs_to_the_end(self):
        s = scenario(tax())
        self.assertEqual(paid(run(s))[-1], "2030-12")

    def test_start_on_the_end_of_an_income(self):
        job = {"type": "income", "id": "job", "name": "Job", "startDate": "2027-01-01",
               "endDate": "2028-03-01", "amount": "5000"}
        cobra = {"type": "expense", "id": "ptax", "name": "Insurance", "amount": "100"}
        months = paid(run(scenario(job, cobra, trig("job", "startAndEnd", "end"))))
        self.assertEqual(months, ["2028-04"])

    def test_start_on_an_end_that_never_comes_never_runs(self):
        job = {"type": "income", "id": "job", "name": "Job", "startDate": "2027-01-01",
               "amount": "5000"}
        cobra = {"type": "expense", "id": "ptax", "name": "Insurance", "amount": "100"}
        self.assertEqual(paid(run(scenario(job, cobra, trig("job", "start", "end")))), [])

    def test_on_end_needs_an_event_with_an_end(self):
        r = {"type": "retirement", "id": "r", "retirementDate": "2029-03-01"}
        with self.assertRaisesRegex(ValueError, "on end applies only to recurring events"):
            engine.validate(scenario(r, tax(), trig("r", "end", "end")))
        with self.assertRaisesRegex(ValueError, "on must be start or end"):
            engine.validate(scenario(tax(), trig("h", "end", "later")))


class StartedByAnOffEvent(unittest.TestCase):
    def test_asset_off_takes_its_attached_expense(self):
        s = scenario(tax())
        s["items"][0]["enabled"] = False
        self.assertEqual(paid(run(s)), [])

    def test_end_trigger_event_off_leaves_the_target_running(self):
        s = scenario(tax(startDate="2027-01-01"),
                     {"type": "sale", "id": "s", "property": "h", "saleDate": "2028-06-01",
                      "enabled": False})
        self.assertEqual(paid(run(s))[-1], "2030-12")


if __name__ == "__main__":
    unittest.main()
