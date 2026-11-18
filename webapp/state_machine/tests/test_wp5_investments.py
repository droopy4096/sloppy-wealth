"""WP5 investments: accounts, openings, transfers, contributions, withdrawals.

Every scenario is run by the state-machine engine; the ledger (TAX lines excluded), the
balances and the month's tax inputs (taxable, deductions, own-rate tax, unrounded) are
golden values frozen from the iteration-1 engine (support.assert_golden). Run from webapp/:
    .venv/bin/python -m unittest state_machine.tests.test_wp5_investments
"""
import copy
import unittest
from decimal import Decimal

from state_machine import api, compiler
from state_machine.base import Aggregate
from state_machine.clock import SCENARIO, Order
from state_machine.emitters import InitialEmitter, LifecycleEvent, ScenarioEmitter

from .support import assert_golden, balances, scenario, without_tax


class TaxProbe(ScenarioEmitter):
    """Records the month's tax inputs after every other emitter of order TAX (emits
    nothing)."""
    ORDER = Order.TAX
    SUB = 77

    def __init__(self):
        super().__init__()
        self.inputs = []

    def emit(self, month, household):
        t = household.first.tax
        self.inputs.append((month, t.taxable, t.deductions, t.extra_tax))


def new_run(s):
    household, clock = compiler.compile_scenario(copy.deepcopy(s))
    probe = clock.register(TaxProbe(), SCENARIO)
    clock.run(household)
    return household, probe


def tax_total(ledger):
    return sum((e["amount"] for e in ledger if e["kind"] == "TAX"), Decimal(0))


def acct(id, type="tfsa", ret="0.06", **kw):
    return dict({"type": "account", "id": id, "name": id.upper(), "accountType": type,
                 "annualReturn": ret}, **kw)


class Parity(unittest.TestCase):
    """Helpers: run the engine and check the golden values."""

    def check(self, items, validate=True, **settings):
        settings.setdefault("effectiveTaxRate", "0.3")
        s = scenario(items, **settings)
        if validate:
            api.validate(copy.deepcopy(s))
        hh, probe = new_run(s)
        assert_golden(self, "ledger, balances, tax inputs, account rates", (
            without_tax(hh.ledger.entries), balances(hh), tax_total(hh.ledger.entries),
            probe.inputs, [(a.id, a.report_rate) for a in hh.aggregates("account")]))
        return hh, None


class Accounts(Parity):
    def test_at_start_kinds_and_returns(self):
        hh, sim = self.check([
            acct("t", "tfsa", "0.06", openingBalance="12000"),
            acct("r", "rrsp", 0.05, openingBalance=50000.5, openedDate="2020-03-01"),
            acct("n", "nonRegistered", "0.07", openingBalance="30000"),
            acct("z", "tfsa", "0.04"),                        # no balance: never a line
        ])
        self.assertFalse([e for e in hh.ledger.entries if e["source"] == "z"])
        self.assertEqual(hh.get("z").balance, Decimal("0.00"))

    def test_non_registered_negative_return_not_taxable(self):
        hh, sim = self.check([
            acct("n", "nonRegistered", "-0.2", openingBalance="40000"),
            acct("p", "nonRegistered", "0.1", openingBalance="1000"),
        ])
        self.assertTrue(any(e["amount"] < 0 for e in hh.ledger.entries if e["kind"] == "RETURN"))

    def test_tiny_balance_return_rounds_to_zero(self):
        self.check([acct("n", "nonRegistered", "0.01", openingBalance="0.5")])

    def test_opened_inside_horizon_from_cash_outside_and_zero(self):
        hh, sim = self.check([
            acct("c", "tfsa", "0.06", openingBalance="5000", openedDate="2026-04-01",
                 openingFrom="cash"),
            acct("o", "rrsp", "0.05", openingBalance="7000", openedDate="2026-06-01",
                 openingFrom="outside"),
            acct("d", "nonRegistered", "0.05", openingBalance="2500", openedDate="2026-02-01",
                 openingFrom=""),
            acct("e", "tfsa", "0.05", openedDate="2026-05-01"),
        ], validate=False)      # blank openingFrom is rejected by validation; engine: outside
        kinds = [(e["kind"], e["source"]) for e in hh.ledger.entries if "OPENING" in e["kind"]]
        self.assertEqual(kinds, [("OPENING_BALANCE", "d"), ("OPENING_TRANSFER", "c"),
                                 ("OPENING_BALANCE", "o")])
        self.assertIn("e", hh)

    def test_opened_after_horizon_never_exists(self):
        hh, sim = self.check([acct("late", openingBalance="100", openedDate="2030-01-01")],
                             validate=False)
        self.assertIsNone(hh.get("late"))

    def test_duplicate_id_keeps_first_slot_last_definition(self):
        hh, _ = self.check([
            acct("a", "tfsa", "0.02", openingBalance="100"),
            acct("b", "rrsp", "0.03", openingBalance="200"),
            acct("a", "nonRegistered", "0.09", openingBalance="300", openedDate="2026-03-01"),
        ], validate=False)
        self.assertEqual([x.id for x in hh.aggregates()], ["cash", "a", "b"])


class Transfers(Parity):
    def test_transfer_rrsp_deduction_and_tfsa(self):
        self.check([
            acct("r", "rrsp", openingBalance="1000"),
            acct("t", "tfsa"),
            {"type": "transfer", "id": "x1", "account": "r", "amount": "2500.555",
             "transferDate": "2026-03-01"},
            {"type": "transfer", "id": "x2", "account": "t", "amount": 1000,
             "transferDate": "2026-03-01"},
        ])

    def test_transfer_covered_mode_no_deduction(self):
        self.check([
            acct("r", "rrsp", openingBalance="1000"),
            {"type": "transfer", "id": "x1", "account": "r", "amount": "2500",
             "transferDate": "2026-03-01"},
        ], incomeMode="expensesCovered")

    def test_transfer_at_retirement_and_in_opening_month(self):
        self.check([
            acct("r", "rrsp", openingBalance="100", openedDate="2026-05-01",
                 openingFrom="cash"),
            {"type": "transfer", "id": "x1", "account": "r", "amount": "300",
             "transferDate": "2026-05-01"},
            {"type": "transfer", "id": "x2", "account": "r", "amount": "400",
             "atRetirement": True},
        ], retirementDate="2027-02-01", retirementTaxRate="0.2", validate=False)


class Contributions(Parity):
    def test_match_rrsp_deduction_indexing(self):
        self.check([
            acct("r", "rrsp", openingBalance="1000"),
            acct("t", "tfsa", openingBalance="0"),
            {"type": "contribution", "id": "c1", "account": "r", "startDate": "2026-02-01",
             "amount": "500", "per": "month", "employerMatch": "0.5",
             "indexing": "inflation"},
            {"type": "contribution", "id": "c2", "account": "t", "startDate": "2026-01-01",
             "endDate": "2027-03-01", "amount": 6000, "per": "year",
             "indexing": "custom", "indexRate": "0.031"},
            {"type": "contribution", "id": "c3", "account": "t", "startDate": "2026-01-01",
             "monthlyAmount": "100.005", "employerMatch": 0.333},
        ], annualInflation="0.025", end="2028-06-01")

    def test_covered_mode_from_outside_no_deduction(self):
        self.check([
            acct("r", "rrsp", openingBalance="1000"),
            {"type": "contribution", "id": "c1", "account": "r", "startDate": "2026-02-01",
             "amount": "1500", "per": "quarter", "employerMatch": "1"},
        ], incomeMode="expensesCovered")

    def test_contribution_waits_for_account_and_ends_at_retirement(self):
        self.check([
            acct("n", "nonRegistered", openingBalance="800", openedDate="2026-06-01"),
            {"type": "contribution", "id": "c1", "account": "n", "startDate": "2026-01-01",
             "amount": "250", "endsAtRetirement": True},
        ], retirementDate="2027-03-01", validate=False)

    def test_pension_target_dispatch(self):
        calls = []

        class FakePension(Aggregate):
            kind = "pension"

            def accept_contribution(self, household, amount, source, match):
                calls.append((household.month, amount, source, match))

        class CreatePension(LifecycleEvent):
            def apply(self, household):
                household.add(FakePension("p", "P", 0, Decimal("0.00")))

        class CreatePensionEmitter(InitialEmitter):
            ORDER = Order.INITIAL

            def emit(self, month, household):
                return (CreatePension(),)

        def fake_pension(item, ctx):
            yield CreatePensionEmitter()

        with compiler.isolated_registry(empty=False):
            compiler._ITEM_TYPES["pension"] = fake_pension
            s = scenario([{"type": "pension", "id": "p"},
                          acct("t", openingBalance="10"),
                          {"type": "contribution", "id": "c", "account": "p",
                           "startDate": "2026-11-01", "amount": "120", "per": "year",
                           "employerMatch": "0.1", "indexing": "custom",
                           "indexRate": "0.1"}])
            hh, _ = new_run(s)
        self.assertEqual(len(calls), 14)
        self.assertEqual(calls[0], (2026 * 12 + 10, Decimal("10.00"), "c", Decimal("0.1")))
        self.assertEqual(calls[-1][1], Decimal("11.00"))


class Withdrawals(Parity):
    def test_amount_indexed_capped_rrsp_taxable(self):
        self.check([
            acct("r", "rrsp", "0.03", openingBalance="9000"),
            {"type": "withdrawal", "id": "w", "account": "r", "method": "amount",
             "startDate": "2026-03-01", "amount": "1000", "indexing": "custom",
             "indexRate": "0.1"},
        ], end="2027-08-01")

    def test_rrsp_own_rate_vs_number_zero_vs_string_zero(self):
        self.check([
            acct("a", "rrsp", openingBalance="5000", withdrawalTaxRate="0.25"),
            acct("b", "rrsp", openingBalance="5000", withdrawalTaxRate=0),
            acct("c", "rrsp", openingBalance="5000", withdrawalTaxRate="0"),
            acct("d", "tfsa", openingBalance="5000", withdrawalTaxRate="0.4"),
            acct("e", "nonRegistered", openingBalance="5000"),
        ] + [{"type": "withdrawal", "id": f"w{x}", "account": x, "method": "amount",
              "startDate": "2026-01-01", "amount": "333.33"} for x in "abcde"])

    def test_percent_across_anniversaries(self):
        self.check([
            acct("n", "nonRegistered", "0.08", openingBalance="100000"),
            {"type": "withdrawal", "id": "w", "account": "n", "method": "percent",
             "startDate": "2026-04-01", "annualRate": "0.04"},
        ], end="2029-06-01")

    def test_percent_opening_month_uses_current_balance(self):
        self.check([
            acct("r", "rrsp", "0.05", openingBalance="24000", openedDate="2026-07-01",
                 openingFrom="cash", withdrawalTaxRate="0.15"),
            {"type": "withdrawal", "id": "w", "account": "r", "method": "percent",
             "startDate": "2026-07-01", "annualRate": "0.05"},
        ], end="2028-01-01")

    def test_percent_empty_account_gives_zero_for_the_year(self):
        self.check([
            acct("t", "tfsa", "0.05"),
            {"type": "transfer", "id": "x", "account": "t", "amount": "5000",
             "transferDate": "2026-02-01"},
            {"type": "withdrawal", "id": "w", "account": "t", "method": "percent",
             "startDate": "2026-01-01", "annualRate": "0.06"},
        ], end="2027-06-01")

    def test_percent_started_before_horizon(self):
        self.check([
            acct("t", "tfsa", "0.05", openingBalance="10000"),
            {"type": "withdrawal", "id": "w", "account": "t", "method": "percent",
             "startDate": "2025-08-01", "annualRate": "0.06"},
        ], validate=False)

    def test_even_latches_first_non_zero_month(self):
        self.check([
            acct("t", "tfsa", "0.05"),
            acct("n", "nonRegistered", "0.05", openingBalance="12345.67"),
            {"type": "transfer", "id": "x", "account": "t", "amount": "6000",
             "transferDate": "2026-05-01"},
            {"type": "withdrawal", "id": "w1", "account": "t", "method": "even",
             "startDate": "2026-01-01", "endDate": "2027-06-01"},
            {"type": "withdrawal", "id": "w2", "account": "n", "method": "even",
             "startDate": "2026-03-01"},
        ])

    def test_blank_start_at_retirement_and_ends_at_retirement(self):
        self.check([
            acct("r", "rrsp", "0.04", openingBalance="60000"),
            acct("t", "tfsa", "0.04", openingBalance="20000"),
            {"type": "withdrawal", "id": "w1", "account": "r", "method": "even"},
            {"type": "withdrawal", "id": "w2", "account": "t", "method": "amount",
             "startDate": "2026-01-01", "endsAtRetirement": True, "amount": "1200",
             "per": "quarter"},
            {"type": "withdrawal", "id": "w3", "account": "t", "method": "percent",
             "annualRate": "0.1"},
        ], retirementDate="2026-09-01", retirementTaxRate="0.2", end="2028-12-01")

    def test_amount_withdrawal_before_account_opens(self):
        self.check([
            acct("t", "tfsa", "0.05", openingBalance="3000", openedDate="2026-06-01",
                 openingFrom="outside"),
            {"type": "withdrawal", "id": "w", "account": "t", "method": "amount",
             "startDate": "2026-01-01", "amount": "400"},
        ])


class Combined(Parity):
    def test_everything_same_month(self):
        self.check([
            acct("r", "rrsp", "0.05", openingBalance="20000", withdrawalTaxRate="0.3"),
            acct("n", "nonRegistered", "-0.03", openingBalance="15000", openedDate="2026-04-01",
                 openingFrom="cash"),
            acct("t", "tfsa", "0.06", openingBalance="9000"),
            {"type": "transfer", "id": "x", "account": "n", "amount": "1000",
             "transferDate": "2026-04-01"},
            {"type": "contribution", "id": "c", "account": "r", "startDate": "2026-04-01",
             "amount": "700", "employerMatch": "0.25"},
            {"type": "withdrawal", "id": "w1", "account": "n", "method": "percent",
             "startDate": "2026-04-01", "annualRate": "0.05"},
            {"type": "withdrawal", "id": "w2", "account": "r", "method": "amount",
             "startDate": "2026-04-01", "amount": "900"},
            {"type": "withdrawal", "id": "w3", "account": "t", "method": "even",
             "startDate": "2026-04-01", "endDate": "2027-03-01"},
        ], annualInflation="0.02", end="2028-12-01")


if __name__ == "__main__":
    unittest.main()
