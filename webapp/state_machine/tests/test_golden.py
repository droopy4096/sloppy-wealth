"""Golden suite: every golden scenario (samples, fixtures, the test suite's scenarios) is
replayed through the current engine and compared with the hashes frozen from iteration 1
(tests/golden/golden.json; see tools/update_golden.py for an intended change). Run from webapp/:
    .venv/bin/python -m unittest state_machine.tests.test_golden
"""
import unittest

from state_machine import engine
from state_machine.tools import update_golden as golden


class Golden(unittest.TestCase):
    """Canada's set, frozen from iteration 1."""
    code = "CA"

    @classmethod
    def setUpClass(cls):
        cls.scenarios = golden.load_scenarios(cls.code)
        cls.expected = golden.load_golden(cls.code)

    def test_every_scenario_has_a_golden_result(self):
        self.assertEqual(sorted(self.scenarios), sorted(self.expected))
        if self.code == "CA":
            self.assertGreater(len(self.scenarios), 200)

    def test_current_engine_matches_golden(self):
        mismatches = []
        for key, scenario in self.scenarios.items():
            found = golden.mismatch(key, self.expected.get(key, {}),
                                    golden.fingerprint(engine, scenario))
            if found:
                mismatches.append(found)
        if mismatches:
            self.fail(f"{len(mismatches)} of {len(self.scenarios)} golden scenarios differ; "
                      f"first:\n{mismatches[0]}\n(intended change? see "
                      f"state_machine/tools/update_golden.py --check)")



class GoldenUnitedStates(Golden):
    """The US set (ADR-0071), tests/golden/us/."""
    code = "US"

    def test_the_set_is_found(self):
        self.assertIn("US", golden.golden_sets())


if __name__ == "__main__":
    unittest.main()
