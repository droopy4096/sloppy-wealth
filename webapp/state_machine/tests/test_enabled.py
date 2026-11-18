"""Item on/off switch (ADR-0064).

    cd webapp && .venv/bin/python -m unittest state_machine.tests.test_enabled
"""
import copy
import unittest

from state_machine import engine
from state_machine.dates import retirement_dates
from state_machine.enabled import active, off_reasons


def scenario(*items):
    return {"schemaVersion": 1, "name": "on/off",
            "horizon": {"start": "2027-01-01", "end": "2028-12-01"},
            "openingCash": "10000", "effectiveTaxRate": "0.3", "items": list(items)}


JOB = {"type": "income", "id": "job", "name": "Job", "startDate": "2027-01-01",
       "amount": "1000", "taxable": True}
TFSA = {"type": "account", "id": "tfsa", "name": "TFSA", "accountType": "tfsa",
        "openingBalance": "5000", "openedDate": "2027-01-01", "openingFrom": "cash",
        "annualReturn": "0.05"}
SAVE = {"type": "contribution", "id": "save", "name": "Save", "account": "tfsa",
        "startDate": "2027-01-01", "amount": "100", "per": "month"}
RAISE = {"type": "adjustment", "id": "raise", "name": "Raise", "flow": "save",
         "adjustmentDate": "2028-01-01", "amount": "200"}


def off(item):
    return dict(item, enabled=False)


def run(s):
    return engine.run_detailed(copy.deepcopy(s))


class Enabled(unittest.TestCase):
    def test_all_on_is_the_same_object(self):
        s = scenario(JOB, dict(TFSA, enabled=True))
        self.assertIs(active(s), s)

    def test_off_item_is_left_out_of_the_run(self):
        self.assertEqual(run(scenario(JOB, off(TFSA)))["rows"],
                         run(scenario(JOB))["rows"])

    def test_dependents_follow_their_target_transitively(self):
        s = scenario(JOB, off(TFSA), SAVE, RAISE)
        self.assertEqual(off_reasons(s["items"]), {1: None, 2: "tfsa", 3: "tfsa"})
        self.assertEqual(run(s)["rows"], run(scenario(JOB))["rows"])

    def test_off_dependent_alone_leaves_its_target_on(self):
        self.assertEqual(run(scenario(JOB, TFSA, off(SAVE), RAISE))["rows"],
                         run(scenario(JOB, TFSA))["rows"])

    def test_the_file_is_not_changed(self):
        s = scenario(JOB, off(TFSA), SAVE)
        before = copy.deepcopy(s)
        run(s)
        self.assertEqual(s, before)

    def test_off_items_are_not_validated(self):
        broken = {"type": "expense", "id": "x", "name": "Broken", "amount": "abc",
                  "enabled": False}
        run(scenario(JOB, broken))
        with self.assertRaises(ValueError):
            run(scenario(JOB, dict(broken, enabled=True)))

    def test_enabled_must_be_boolean(self):
        with self.assertRaisesRegex(ValueError, "enabled must be true or false"):
            engine.validate(scenario(dict(JOB, enabled="no")))

    def test_person_off_takes_their_items_and_retirement(self):
        a = {"type": "person", "id": "a", "name": "A"}
        b = {"type": "person", "id": "b", "name": "B"}
        b_job = dict(JOB, id="bjob", name="B job", owner="b")
        b_ret = {"type": "retirement", "id": "bret", "name": "B retires", "owner": "b",
                 "retirementDate": "2028-01-01"}
        s = scenario(a, off(b), JOB, b_job, b_ret)
        self.assertEqual(retirement_dates(s), {"a": ""})
        self.assertEqual(run(s)["rows"], run(scenario(a, JOB))["rows"])


if __name__ == "__main__":
    unittest.main()
