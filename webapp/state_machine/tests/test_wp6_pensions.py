"""WP6 pensions: ledger, balances, holdings points and tax inputs, golden values frozen from
the iteration-1 engine (support.assert_golden).
Run from webapp/:
    .venv/bin/python -m unittest state_machine.tests.test_wp6_pensions

Item types owned by other WPs that may be missing on this branch (``retirement``,
``contribution``) are stood in for by small fakes registered only when absent; the fake
contribution calls ``Pension.accept_contribution`` exactly as E3's flow does. A CLOSE
recorder (sub 50) captures per-month points and the month's taxable/deductions, which
were compared with the reference ``tax_detail`` (scenarios have no tax rate, so no TAX lines).
"""
import unittest
from decimal import Decimal

from state_machine import api, compiler
from state_machine.arith import flow_amount, indexed, indexing_rate, money
from state_machine.clock import Order
from state_machine.dates import month_index, month_label
from state_machine.emitters import FlowEvent, RecurringEmitter, ScenarioEmitter, StateEvent
from state_machine.holdings.pension import Pension

from .support import assert_golden, balances, scenario


class _Snapshot(StateEvent):
    def __init__(self, out):
        self.out = out

    def apply(self, household):
        label = month_label(household.month)
        self.out["tax"][label] = (money(household.first.tax.taxable),
                                  money(household.first.tax.deductions))
        for a in household.aggregates():
            self.out["points"].setdefault(a.id, []).append(
                {"month": label, "opening": household.points_opening.get(a.id),
                 "closing": a.balance, "rate": a.report_rate})


class _Recorder(ScenarioEmitter):
    ORDER = Order.CLOSE
    SUB = 50

    def __init__(self, out):
        super().__init__()
        self.out = out

    def emit(self, month, household):
        return (_Snapshot(self.out),)


class _Contributed(FlowEvent):
    def __init__(self, target, amount, match):
        self.target, self.amount, self.match = target, amount, match

    def apply(self, household):
        household[self.target].accept_contribution(household, self.amount, self.source,
                                                   self.match)


class _FakeContribution(RecurringEmitter):
    """Stand-in for E3's contribution flow (reference ``contribute`` L915-936)."""
    ORDER = Order.CONTRIBUTE

    def __init__(self, item, ctx):
        env = ctx.env
        first = month_index(item["startDate"], "startDate")
        last = month_index(item["endDate"], "endDate") if item.get("endDate") else env.end
        super().__init__(first, last)
        self.first, self.target = first, item["account"]
        self.base, per = flow_amount(item)
        self.divisor = {"month": 1, "quarter": 3, "year": 12}[per]
        self.rate = indexing_rate(item, ctx.household.inflation)
        self.match = Decimal(str(item.get("employerMatch") or "0"))

    def emit(self, month, household):
        if household.get(self.target) is None:
            return
        amount = indexed(self.base, self.rate, month - self.first, self.divisor)
        yield _Contributed(self.target, amount, self.match)


def run_new(s):
    """Compile and run the new engine with the fakes and the recorder; returns
    (household, recorded)."""
    out = {"tax": {}, "points": {}}
    with compiler.isolated_registry(empty=False):
        types = compiler.registered_types()
        if "retirement" not in types:
            compiler.item_type("retirement")(lambda item, ctx: [])
        if "contribution" not in types:
            compiler.item_type("contribution")(lambda item, ctx: [_FakeContribution(item, ctx)])
        compiler.scenario_setup("wp6test.recorder", order=999)(lambda env: [_Recorder(out)])
        hh = api.simulate(s)
    return hh, out


PENSION = {"type": "pension", "id": "db", "name": "DB plan", "amount": "1200",
           "per": "month", "startDate": "2026-06-01"}


def pension(**kw):
    return dict(PENSION, **kw)


class PensionParity(unittest.TestCase):
    def check(self, s):
        api.validate(s)           # every scenario here is valid
        hh, out = run_new(s)
        assert_golden(self, "ledger, balances, points, tax",
                      (hh.ledger.entries, balances(hh), out["points"], out["tax"]))
        return hh, hh.ledger.entries

    # ---- value at start-1, payment, revaluation ----
    def test_basic_no_inflation(self):
        hh, ledger = self.check(scenario([pension()]))
        # Without inflation the value falls exactly by each payment: no REVALUATION line.
        self.assertEqual({e["kind"] for e in ledger}, {"PENSION_PAYMENT"})

    def test_value_at_start_minus_one(self):
        s = scenario([pension(startDate="2025-01-01", endDate="2030-12-01")],
                     annualInflation="0.025")
        hh, out = run_new(s)
        assert_golden(self, "opening value", out["points"]["db"][0]["opening"])
        self.check(s)

    def test_inflation_indexing_none(self):
        hh, ledger = self.check(scenario([pension()], annualInflation="0.03"))
        # Revaluation goes both ways (negative amounts are recorded).
        signs = {e["amount"] < 0 for e in ledger if e["kind"] == "REVALUATION"}
        self.assertEqual(signs, {True, False})

    def test_inflation_indexing_inflation(self):
        self.check(scenario([pension(indexing="inflation")], annualInflation="0.03"))

    def test_custom_indexing_with_inflation(self):
        self.check(scenario([pension(indexing="custom", indexRate="0.015")],
                            annualInflation=0.021))

    def test_custom_indexing_no_inflation(self):
        self.check(scenario([pension(indexing="custom", indexRate=0.02)]))

    def test_dollars_of_before_start(self):
        # Payment indexing counts years from the base date, not from the pension start.
        s = scenario([pension(indexing="custom", indexRate="0.02", startDate="2026-03-01")],
                     start="2026-01-01", end="2029-12-01", annualInflation="0.02",
                     dollarsOf="2024-07-01")
        self.check(s)

    def test_dollars_of_after_start(self):
        s = scenario([pension(indexing="inflation", startDate="2026-01-01")],
                     start="2026-01-01", end="2028-06-01", annualInflation="0.019",
                     dollarsOf="2027-05-01")
        self.check(s)

    def test_quarter_year_and_legacy_monthly(self):
        items = [pension(id="q", amount="3000", per="quarter"),
                 pension(id="y", amount="12345.67", per="year", indexing="inflation"),
                 {"type": "pension", "id": "legacy", "monthlyAmount": 800,
                  "startDate": "2026-02-01"}]
        self.check(scenario(items, annualInflation="0.02"))

    # ---- start/end ----
    def test_started_before_horizon(self):
        self.check(scenario([pension(startDate="2020-01-01")], annualInflation="0.02"))

    def test_own_end_inside_horizon(self):
        self.check(scenario([pension(startDate="2026-02-01", endDate="2027-03-01",
                                     indexing="inflation")], annualInflation="0.02"))

    def test_end_after_horizon(self):
        self.check(scenario([pension(endDate="2040-12-01")], annualInflation="0.02"))

    def test_starts_after_horizon(self):
        # Valued but never paid within the horizon; still revalued every month.
        self.check(scenario([pension(startDate="2030-01-01", endDate="2035-01-01")],
                            annualInflation="0.02"))

    def test_ended_before_horizon(self):
        # Value 0: no payment and no ledger line.
        hh, ledger = self.check(scenario([pension(startDate="2020-01-01",
                                               endDate="2021-01-01")]))
        self.assertEqual(ledger, [])
        self.assertEqual(repr(hh["db"].balance), "Decimal('0.00')")

    # ---- retirement (compile-time look-ahead) ----
    def test_blank_start_retirement_item(self):
        items = [{"type": "retirement", "retirementDate": "2026-09-01"},
                 pension(startDate="", indexing="inflation")]
        self.check(scenario(items, annualInflation="0.02"))

    def test_blank_start_legacy_retirement_date(self):
        self.check(scenario([{k: v for k, v in PENSION.items() if k != "startDate"}],
                            annualInflation="0.02", retirementDate="2027-02-01"))

    def test_ends_at_retirement(self):
        items = [pension(startDate="2025-06-01", endsAtRetirement=True, indexing="inflation"),
                 {"type": "retirement", "retirementDate": "2027-04-01"}]
        self.check(scenario(items, annualInflation="0.02"))

    def test_ends_at_retirement_with_earlier_own_end(self):
        items = [pension(startDate="2026-01-01", endDate="2026-08-01", endsAtRetirement=True),
                 {"type": "retirement", "retirementDate": "2027-04-01"}]
        self.check(scenario(items))

    def test_ends_at_retirement_without_retirement(self):
        self.check(scenario([pension(endsAtRetirement=True)], annualInflation="0.02"))

    def test_legacy_retirement_before_start(self):
        s = scenario([pension(startDate="", endDate="2027-01-01")],
                     annualInflation="0.02", retirementDate="2024-01-01")
        self.check(s)

    # ---- tax flag, covered mode ----
    def test_not_taxable(self):
        items = [pension(id="a", taxable=False), pension(id="b", amount="500")]
        self.check(scenario(items))

    def test_covered_mode_pays(self):
        hh, ledger = self.check(scenario([pension(indexing="inflation")], annualInflation="0.02",
                                      incomeMode="expensesCovered"))
        self.assertTrue(any(e["kind"] == "PENSION_PAYMENT" for e in ledger))

    # ---- holdings order, duplicate ids, no id ----
    def test_order_and_duplicates(self):
        items = [pension(id="b", amount="100"),
                 {"type": "pension", "amount": "250", "startDate": "2026-01-01"},
                 pension(id="a", amount="300"),
                 pension(id="b", amount="400", indexing="custom", indexRate="0.01")]
        hh, ledger = self.check(scenario(items, annualInflation="0.01"))
        self.assertEqual([a.id for a in hh.aggregates()], ["cash", "b", "item1", "a"])
        self.assertEqual(hh["b"].item_index, 0)

    # ---- contributions (accept_contribution) ----
    def test_contribution_to_pension(self):
        items = [pension(startDate="2027-06-01"),
                 {"type": "contribution", "id": "c1", "account": "db",
                  "startDate": "2026-02-01", "endDate": "2027-05-01", "amount": "350.555",
                  "indexing": "inflation", "employerMatch": "0.5"}]
        hh, ledger = self.check(scenario(items, annualInflation="0.02"))
        self.assertTrue(any(e["kind"] == "PENSION_CONTRIBUTION" for e in ledger))

    def test_contribution_to_pension_covered(self):
        items = [pension(startDate="2027-06-01"),
                 {"type": "contribution", "id": "c1", "account": "db",
                  "startDate": "2026-02-01", "amount": "1200", "per": "year"}]
        hh, ledger = self.check(scenario(items, incomeMode="expensesCovered"))
        self.assertFalse(any(e["kind"] == "PENSION_CONTRIBUTION" for e in ledger))

    def test_contribution_before_pension_in_item_order(self):
        items = [{"type": "contribution", "id": "c1", "account": "db",
                  "startDate": "2026-01-01", "amount": "100"},
                 pension(startDate="2026-03-01", endDate="2026-12-01")]
        self.check(scenario(items))


class PensionUnit(unittest.TestCase):
    def test_accept_contribution_direct(self):
        hh, _ = run_new(scenario([pension()]))
        hh.month = hh.end
        hh.first.tax.reset_month()
        before = hh["db"].balance
        hh["db"].accept_contribution(hh, Decimal("100.005"), "cX", Decimal("1"))
        e = hh.ledger.entries[-1]
        self.assertEqual(repr(e), repr({"month": "2027-12", "kind": "PENSION_CONTRIBUTION",
                                        "from": "cash", "to": None,
                                        "amount": Decimal("100.00"), "source": "cX"}))
        self.assertEqual(repr(hh.first.tax.deductions), "Decimal('100.00')")
        self.assertEqual(hh["db"].balance, before)

    def test_accept_contribution_covered_does_nothing(self):
        hh, _ = run_new(scenario([pension()], incomeMode="expensesCovered"))
        n = len(hh.ledger)
        hh.first.tax.reset_month()
        hh["db"].accept_contribution(hh, Decimal("100"), "cX", Decimal(0))
        self.assertEqual(len(hh.ledger), n)
        self.assertEqual(hh.first.tax.deductions, 0)

    def test_report_rate_and_group(self):
        hh, _ = run_new(scenario([pension(indexing="inflation")], annualInflation="0.025"))
        p = hh["db"]
        self.assertIsInstance(p, Pension)
        self.assertEqual(repr(p.report_rate), "Decimal('0.025')")
        self.assertEqual(p.group, "investments")


if __name__ == "__main__":
    unittest.main()
