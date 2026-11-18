"""Conformance of every registered jurisdiction (ADR-0071 decision 6). A new jurisdiction
package must pass this suite unchanged; see the CONTRIBUTING section of
state_machine/README.md.

    cd webapp && .venv/bin/python -m unittest state_machine.tests.test_conformance
"""
import json
import unittest
from pathlib import Path

from state_machine import compiler, engine, jurisdictions
from state_machine.jurisdictions import AccountType, ContributionLimits, Jurisdiction, Treatment
from state_machine.tools import update_golden as golden

PACKAGE = Path(jurisdictions.__file__).resolve().parent


class Conformance(unittest.TestCase):
    def each(self):
        """Every registered jurisdiction; use each pair inside self.subTest."""
        found = jurisdictions.registered()
        self.assertIn("CA", found)
        return list(found.items())

    def test_declarations(self):
        for code, rules in self.each():
            with self.subTest(jurisdiction=code):
                self.assertIsInstance(rules, Jurisdiction)
                self.assertEqual(rules.code, code)
                self.assertTrue(code.isupper() and code.isalpha() and len(code) == 2,
                                "an ISO 3166 alpha-2 code")
                self.assertTrue(rules.name)
                self.assertTrue(rules.account_types, "at least one account type")
                for key, kind in rules.account_types.items():
                    self.assertIsInstance(kind, AccountType)
                    self.assertEqual(kind.code, key)
                    self.assertTrue(kind.label)
                    self.assertIsInstance(kind.treatment, Treatment)
                    import schema
                    self.assertLessEqual(set(kind.fields),
                                         set(schema.describe(code)["fields"]["account"]),
                                         "an account type's own fields are on the account form")
                self.assertIsInstance(rules.limits, ContributionLimits)
                for column in rules.limits.columns:
                    self.assertTrue(column.endswith(("Room", "Limit")),
                                    f"limit column {column!r}: name it ...Room or ...Limit")

    def test_own_item_types_are_complete(self):
        registered = compiler.registered_types()
        own_elsewhere = {}
        for code, rules in self.each():
            with self.subTest(jurisdiction=code):
                for kind in rules.item_types:
                    self.assertIn(kind, registered, f"{kind}: no @item_type factory")
                    self.assertIn(kind, rules.required, f"{kind}: no required fields")
                    self.assertIn(kind, rules.form_fields, f"{kind}: no form fields")
                    self.assertIn(kind, rules.legends, f"{kind}: no legend")
                    self.assertNotIn(kind, own_elsewhere, f"{kind}: also {own_elsewhere.get(kind)}'s")
                    own_elsewhere[kind] = code
                own = set(rules.item_types)
                self.assertLessEqual(set(rules.owned_types), own)
                self.assertLessEqual({k for kinds in rules.add_groups.values() for k in kinds}, own)
                self.assertLessEqual({k for kinds in rules.head_adds.values() for k in kinds}, own)
                for field in rules.choice_fields:
                    self.assertTrue(any(field in f for f in rules.required.values()))

    def test_forms_build(self):
        import schema
        for code, rules in self.each():
            with self.subTest(jurisdiction=code):
                described = schema.describe(code)
                self.assertEqual(described["jurisdiction"]["code"], code)
                listed = sorted(k for g in described["addGroups"] for k in g["types"])
                self.assertEqual(listed, sorted(described["fields"]),
                                 "every item type is in exactly one add group")
                self.assertEqual([o["value"] for o in described["selects"]["accountType"]],
                                 list(rules.account_types))
                for other, them in jurisdictions.registered().items():
                    if other != code:
                        for kind in set(them.item_types) - set(rules.item_types):
                            self.assertNotIn(kind, described["fields"])

    def test_sample_validates_runs_and_is_golden(self):
        for code, rules in self.each():
            with self.subTest(jurisdiction=code):
                path = PACKAGE / code.lower() / "sample.json"
                self.assertTrue(path.exists(), f"{path}: every jurisdiction ships a sample")
                sample = json.loads(path.read_text())
                self.assertEqual(sample.get("jurisdiction"), code)
                used = {i.get("accountType") for i in sample["items"] if i["type"] == "account"}
                self.assertEqual(used, set(rules.account_types), "the sample uses every account type")
                kinds = {i["type"] for i in sample["items"]}
                self.assertLessEqual(set(rules.item_types), kinds, "and every own item type")
                engine.validate(sample)
                rows = engine.run_detailed(sample)["rows"]
                self.assertTrue(rows)
                for column in rules.limits.columns:
                    if any(column in row for row in rows):
                        break
                else:
                    if rules.limits.columns:
                        self.fail("the sample shows none of the limit columns")
                key = f"jurisdictions/{code.lower()}/sample.json"
                self.assertIn(code, golden.golden_sets(), "a golden set (tests/golden/<code>/)")
                self.assertEqual(golden.load_scenarios(code).get(key), sample,
                                 "the sample is in its golden set, as it is now "
                                 "(update_golden.py --jurisdiction XX --add <sample>)")


if __name__ == "__main__":
    unittest.main()
