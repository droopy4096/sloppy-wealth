"""WP7: income/expense flows, TaxRule, RetirementEvent, IndexingRule; ledger incl. TAX,
cash, tax detail and pool are golden values frozen from the iteration-1 engine
(support.assert_golden). Run from webapp/:
    .venv/bin/python -m unittest state_machine.tests.test_wp7_flows_tax
"""
import copy
import unittest
from decimal import Decimal

from state_machine import api, arith, compiler
from state_machine.clock import Order
from state_machine.emitters import RecurringEmitter, StateEvent
from state_machine.events.retirement import RetirementEmitter
from state_machine.rules.indexing import IndexingRule

from .support import assert_golden, scenario


def inc(id, amount="1000", **kw):
    return dict({"type": "income", "id": id, "amount": amount, "startDate": "2026-01-01"}, **kw)


def exp(id, amount="400", **kw):
    return dict({"type": "expense", "id": id, "amount": amount, "startDate": "2026-01-01"}, **kw)


def retire(date):
    return {"type": "retirement", "retirementDate": date}


class Parity(unittest.TestCase):
    """Each case: validate, run the engine, check the golden values."""

    def check(self, s, extra_handlers=()):
        api.validate(copy.deepcopy(s))
        household, clock = compiler.compile_scenario(copy.deepcopy(s))
        for handler, ordinal in extra_handlers:
            clock.register(handler, ordinal)
        clock.run(household)
        assert_golden(self, "ledger, cash, tax detail, pool",
                      (household.ledger.entries, household.cash.balance, household.first.tax.detail,
                       household.first.tax.pool))
        self.assertTrue(household.ledger.entries, "scenario should produce movements")
        return household, household.first.tax


class FlowParity(Parity):
    def test_untaxed_and_taxed_income_and_expense(self):
        self.check(scenario([inc("job", "5000", taxable=True), inc("gift", "300"),
                             exp("rent", "1800")], effectiveTaxRate=0.3))

    def test_taxable_string_rate_and_no_rate(self):
        self.check(scenario([inc("job", "4321.17", taxable=True)], effectiveTaxRate="0.255"))
        self.check(scenario([inc("job", "4321.17", taxable=True)]))

    def test_quarter_year_and_legacy_monthly(self):
        self.check(scenario([inc("bonus", "10000", per="year", taxable=True),
                             exp("ins", "1000", per="quarter"),
                             {"type": "expense", "id": "old", "monthlyAmount": "123.45",
                              "startDate": "2026-03-01"},
                             exp("odd", "100.01", per="quarter")], effectiveTaxRate=0.2))

    def test_indexing_inflation_custom_none(self):
        self.check(scenario([inc("a", "3000", indexing="inflation", taxable=True),
                             exp("b", "1000", indexing="custom", indexRate=0.035,
                                 startDate="2026-05-01"),
                             exp("c", "777", indexing="none", per="year"),
                             exp("d", "500", indexing="custom", indexRate=-0.02)],
                            end="2029-12-01", annualInflation=0.021, effectiveTaxRate=0.25))

    def test_start_before_horizon_counts_from_own_start(self):
        self.check(scenario([inc("a", "2000", startDate="2023-07-01", indexing="inflation"),
                             exp("b", "900", startDate="2024-11-01", indexing="custom",
                                 indexRate=0.05, endDate="2027-03-01")],
                            annualInflation=0.03))

    def test_end_date_and_late_start(self):
        self.check(scenario([inc("a", "100", startDate="2026-06-01", endDate="2026-09-01"),
                             exp("b", "50", startDate="2027-02-01", endDate="2030-01-01")]))

    def test_amount_in_base_before_and_after_base_date(self):
        items = [exp("later", "1000", amountIn="base", startDate="2027-04-01",
                     indexing="inflation"),
                 exp("earlier", "1000", amountIn="base", startDate="2024-02-01"),
                 inc("start", "1000", amountIn="start", indexing="inflation"),
                 inc("same", "2500", amountIn="base", per="quarter", taxable=True)]
        self.check(scenario(items, end="2029-06-01", annualInflation=0.027,
                            effectiveTaxRate=0.3, dollarsOf="2026-09-01"))
        # No inflation: amountIn base leaves the amount as stated.
        self.check(scenario(items, end="2029-06-01", dollarsOf="2026-09-01"))

    def test_covered_mode_skips_income_and_expense(self):
        s = scenario([inc("job", "5000", taxable=True), exp("rent", "1800"),
                      inc("x", "1", startDate="2026-02-01")],
                     effectiveTaxRate=0.3, incomeMode="expensesCovered")
        hh = api.simulate(copy.deepcopy(s))
        self.assertEqual(hh.ledger.entries, [])
        assert_golden(self, "tax detail", hh.first.tax.detail)
        self.assertEqual(repr(hh.cash.balance), "Decimal('10000.00')")
        api.validate(s)

    def test_id_defaults_to_item_index(self):
        self.check(scenario([{"type": "income", "amount": "10", "startDate": "2026-01-01"},
                             {"type": "expense", "amount": "3", "startDate": "2026-01-01"}]))

    def test_tiny_amounts_dropped(self):
        self.check(scenario([inc("a", "0.004"), inc("b", "0.05", per="year", taxable=True),
                             exp("c", "1")], effectiveTaxRate=0.1))


class RetirementParity(Parity):
    def test_starts_and_ends_at_retirement(self):
        self.check(scenario([retire("2026-09-01"),
                             inc("job", "6000", endsAtRetirement=True, taxable=True,
                                 indexing="inflation"),
                             inc("annuity", "1500", startsAtRetirement=True, taxable=True,
                                 indexing="inflation", amountIn="base"),
                             exp("commute", "200", endsAtRetirement=True,
                                 endDate="2026-05-01"),
                             exp("travel", "800", startsAtRetirement=True, startDate="",
                                 per="quarter")],
                            end="2028-12-01", annualInflation=0.02, effectiveTaxRate=0.3,
                            retirementTaxRate=0.15))

    def test_starts_at_retirement_without_retirement_uses_start_date(self):
        self.check(scenario([inc("a", "100", startsAtRetirement=True),
                             exp("b", "40", endsAtRetirement=True)]))

    def test_retirement_tax_rate_switch(self):
        h, _ = self.check(scenario([retire("2026-07-01"), inc("job", "5000", taxable=True)],
                                   effectiveTaxRate=0.3, retirementTaxRate=0.1))
        self.assertTrue(h.first.retired)

    def test_retirement_tax_rate_number_zero_means_no_switch(self):
        self.check(scenario([retire("2026-07-01"), inc("job", "5000", taxable=True)],
                            effectiveTaxRate=0.3, retirementTaxRate=0))

    def test_retirement_tax_rate_string_zero_switches_to_zero(self):
        self.check(scenario([retire("2026-07-01"), inc("job", "5000", taxable=True)],
                            effectiveTaxRate=0.3, retirementTaxRate="0"))

    def test_retirement_without_rate_keeps_rate(self):
        self.check(scenario([retire("2026-07-01"), inc("job", "5000", taxable=True)],
                            effectiveTaxRate=0.3))

    def test_retirement_in_first_and_last_month(self):
        for date in ("2026-01-01", "2027-12-01"):
            with self.subTest(date=date):
                self.check(scenario([retire(date), inc("job", "5000", taxable=True,
                                                       endsAtRetirement=True),
                                     inc("p", "700", taxable=True, startsAtRetirement=True)],
                                    effectiveTaxRate=0.3, retirementTaxRate=0.2))

    def test_legacy_retirement_date(self):
        self.check(scenario([inc("job", "5000", taxable=True, endsAtRetirement=True),
                             inc("p", "900", taxable=True, startsAtRetirement=True)],
                            effectiveTaxRate=0.3, retirementTaxRate=0.12,
                            retirementDate="2027-03-01"))

    def test_legacy_retirement_date_before_horizon(self):
        # Every month counts as retired; startsAtRetirement flows count from the
        # pre-horizon retirement month (indexing anniversaries), endsAtRetirement never run.
        h, tax = self.check(scenario([inc("job", "5000", taxable=True, endsAtRetirement=True),
                                      inc("p", "900", taxable=True, startsAtRetirement=True,
                                          indexing="inflation"),
                                      exp("e", "100", startsAtRetirement=True,
                                          amountIn="base")],
                                     effectiveTaxRate=0.3, retirementTaxRate=0.12,
                                     annualInflation=0.02, retirementDate="2024-08-01"))
        self.assertTrue(all(d["retired"] for d in tax.detail.values()))

    def test_legacy_retirement_date_after_horizon(self):
        self.check(scenario([inc("job", "5000", taxable=True, endsAtRetirement=True)],
                            effectiveTaxRate=0.3, retirementTaxRate=0.12,
                            retirementDate="2031-03-01"))

    def test_event_fires_at_max_of_retirement_and_start(self):
        e = RetirementEmitter(100, 120)
        self.assertEqual(e.month, 120)
        self.assertEqual(RetirementEmitter(130, 120).month, 130)
        self.assertEqual([m for m in range(110, 140) if e.due(m)], [120])

    def test_schedule_keys(self):
        _, clock = compiler.compile_scenario(scenario(
            [inc("a"), retire("2026-05-01"), exp("b")]))
        # After integration the WP8 results recorder also sits at CLOSE/-1/0.
        # Order numbers = former phase x 100 (OPEN 0, INCOME 100, EXPENSE 900, TAX 1500, CLOSE 1600).
        self.assertEqual(clock.schedule(), [(0, -1, 0), (100, 0, 0), (900, 2, 0), (1500, -1, 0),
                                            (1600, -1, 0)])


class _TaxInputs(StateEvent):
    def __init__(self, ded, own):
        self.ded, self.own = ded, own

    def apply(self, household):
        if self.ded:
            household.first.tax.add_deduction(self.ded)
        if self.own:
            household.first.tax.add_own_rate_tax(self.own)


class _AddTax(RecurringEmitter):
    """Stands in for WP5/WP6: deductions / own-rate tax through the accumulator API."""
    ORDER = Order.TRANSFER

    def __init__(self, plan):
        super().__init__()
        self.plan = plan

    def emit(self, month, household):
        ded, own = self.plan(month)
        if ded or own:
            yield _TaxInputs(ded, own)


class DeductionPoolParity(Parity):
    def run_case(self, plan, s):
        return self.check(s, extra_handlers=[(_AddTax(plan), 99)])

    def test_pool_carries_forward(self):
        start = 2026 * 12
        big = {start + 1: Decimal("12000.004"), start + 5: Decimal("333.333")}

        def plan(m):
            return big.get(m), (Decimal("17.123456") if m % 3 == 0 else None)

        h, tax = self.run_case(plan, scenario(
            [inc("job", "5000", taxable=True), exp("rent", "100"), retire("2026-09-01")],
            effectiveTaxRate=0.3, retirementTaxRate=0.2))
        self.assertTrue(any(d["poolOut"] for d in tax.detail.values()))
        self.assertTrue(any(d["used"] for d in tax.detail.values()))

    def test_negative_taxable_and_covered(self):
        def plan(m):
            return Decimal("50"), Decimal("1.005")       # own-rate tax rounds half-even

        self.run_case(plan, scenario([inc("job", "20", taxable=True)], end="2026-06-01",
                                     effectiveTaxRate=0.4))
        self.run_case(plan, scenario([inc("job", "20", taxable=True)], end="2026-06-01",
                                     effectiveTaxRate=0.4, incomeMode="expensesCovered",
                                     cash="5"))


class IndexingRuleTests(unittest.TestCase):
    def test_matches_indexed(self):
        item = {"indexing": "custom", "indexRate": 0.031}
        r = IndexingRule.for_item(item, Decimal("0.02"), 100, 3)
        for m in (100, 111, 112, 150):
            self.assertEqual(repr(r.amount(Decimal("1234.5678"), m)),
                             repr(arith.indexed(Decimal("1234.5678"), Decimal("0.031"),
                                                m - 100, 3)))
        self.assertEqual(IndexingRule.for_item({}, Decimal("0.02"), 0).rate, Decimal(0))
        self.assertEqual(IndexingRule.for_item({"indexing": "inflation"}, Decimal("0.02"),
                                               0).rate, Decimal("0.02"))


if __name__ == "__main__":
    unittest.main()
