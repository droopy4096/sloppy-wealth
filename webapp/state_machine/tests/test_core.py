"""WP0 core: arith/dates equal to the frozen iteration-1 results (golden values), move semantics, clock ordering,
compiler registry. Run from webapp/:
    .venv/bin/python -m unittest state_machine.tests.test_core
"""
import random
import unittest
from decimal import Decimal

from state_machine.upgrade import upgrade
from state_machine import api, arith, compiler, dates
from state_machine.base import Aggregate
from state_machine.clock import ORDER_STEP, SCENARIO, Order
from state_machine.emitters import INITIAL, Emitter, Once, StateEvent, Window
from state_machine.runner import ScenarioRunner as Clock
from state_machine.household import Household

from .support import assert_golden, sample, scenario


def outcome(fn, *args):
    """(result repr) or (exception type, message): compares behaviour incl. errors."""
    try:
        return ("ok", repr(fn(*args)))
    except Exception as e:  # noqa: BLE001 - the type is part of the comparison
        return (type(e).__name__, str(e))


class ArithParity(unittest.TestCase):
    """arith results over many inputs, frozen from iteration 1 (golden values)."""

    def setUp(self):
        rnd = random.Random(7)
        self.decimals = [Decimal(s) for s in (
            "0", "0.005", "0.015", "0.025", "-0.005", "-0.015", "1.005", "2.675", "1e-30",
            "123456789.125", "-123456789.135", "0.0049999", "999999999999.995")]
        self.decimals += [Decimal(rnd.randint(-10**9, 10**9)) / Decimal(10**rnd.randint(0, 8))
                          for _ in range(200)]

    def test_constants(self):
        self.assertEqual([repr(getattr(arith, n)) for n in ("CENT", "ONE", "PER")],
                         ["Decimal('0.01')", "Decimal('1')",
                          "{'month': 1, 'quarter': 3, 'year': 12}"])

    def test_money(self):
        assert_golden(self, "money", [arith.money(x) for x in self.decimals])
        self.assertEqual(repr(arith.money(Decimal("2.675"))), "Decimal('2.68')")
        self.assertEqual(repr(arith.money(Decimal("-0.015"))), "Decimal('-0.02')")

    def test_power(self):
        assert_golden(self, "power", [
            arith.power(Decimal(b), e)
            for b in ("1.02", "0.97", "1.0379", "1.5", "0.01", "1")
            for e in (Decimal(1) / 12, Decimal(1) / 6, Decimal(-7) / 12, Decimal(25) / 12,
                      Decimal(0), Decimal("0.5"))])

    def test_monthly_rate_annuity_terms(self):
        assert_golden(self, "monthly_rate", [
            arith.monthly_rate(a) for a in ("0.0379", 0.0379, "0", 0, "0.05", "0.999", 0.12)])
        assert_golden(self, "annuity", [
            arith.annuity(Decimal(bal), arith.monthly_rate(annual), n)
            for bal in ("560000", "560000.004", "1", "0", "-100")
            for annual in ("0.0379", "0", "0.07") for n in (1, 12, 300, 360)])
        items = [i for i in sample("single-house.json")["items"] if i["type"] == "mortgage"]
        items += [{"principal": 100000, "annualRate": 0.05, "amortizationYears": 2.5},
                  {"principal": "1", "annualRate": "0", "amortizationYears": "1"}]
        assert_golden(self, "mortgage_terms", [arith.mortgage_terms(i) for i in items])

    def test_indexed(self):
        assert_golden(self, "indexed", [
            arith.indexed(Decimal(base), Decimal(rate), k, div)
            for base in ("1000", "1000.333", "0.01", "-50")
            for rate in ("0", "0.02", "-0.03", "0.0379")
            for k in (0, 1, 11, 12, 13, 120, 599) for div in (1, 3, 12)])

    def test_dec_and_flow_amount(self):
        items = [{"amount": "12"}, {"amount": 12.5, "per": "year"}, {"amount": "x"},
                 {"amount": 1, "per": "week"}, {"monthlyAmount": "3"}, {}, {"amount": None},
                 {"amount": "1", "per": ""}, {"monthlyAmount": "abc"}]
        assert_golden(self, "flow_amount", [outcome(arith.flow_amount, i, "item x") for i in items])
        assert_golden(self, "dec", [outcome(arith.dec, i, "amount", "w") for i in items])

    def test_indexing_rate(self):
        infl = Decimal("0.02")
        self.assertEqual(repr(arith.indexing_rate({}, infl)), "Decimal('0')")
        self.assertIs(arith.indexing_rate({"indexing": "inflation"}, infl), infl)
        self.assertEqual(repr(arith.indexing_rate({"indexing": "custom", "indexRate": 0.03}, infl)),
                         "Decimal('0.03')")


class DatesParity(unittest.TestCase):
    """dates results, frozen from iteration 1 (golden values)."""

    def test_month_index_and_label(self):
        assert_golden(self, "month_index", [
            outcome(dates.month_index, v, "where")
            for v in ("2026-01-01", "2026-12-31", "0001-01-01", "2026-13-01", "2026-00-01",
                      "2026-1", "", None, "abc", "2026-02-xx", 20260101, "2026-1-1")])
        assert_golden(self, "month_label", [dates.month_label(i) for i in range(0, 30000, 7)])
        self.assertEqual(dates.month_label(dates.month_index("2026-03-01", "")), "2026-03")

    def test_scenario_lookups(self):
        scenarios = [sample(n) for n in ("single-house.json", "household-baseline.json", "rent.json",
                                          "single-house-sold.json")]
        scenarios += [
            {"horizon": {"start": "2026-01-01"}, "dollarsOf": "2020-05-01", "items": []},
            {"horizon": {"start": "2026-01-01"}, "retirementDate": "2040-01-01", "items": []},
            {"horizon": {"start": "2026-01-01"}, "dollarsOf": "bad", "items": [
                {"type": "retirement", "retirementDate": ""}]},
        ]
        assert_golden(self, "base_month", [outcome(dates.base_month, s) for s in scenarios])
        assert_golden(self, "retirement_date", [dates.retirement_date(s) for s in scenarios])
        # Older files' property saleDate arrives as a sale item (upgrade.py).
        items = upgrade({"items": [
            {"type": "property", "id": "p", "purchaseDate": "2026-01-01", "saleDate": "2030-01-01"},
            {"type": "sale", "property": "v", "saleDate": "2035-06-01"},
            {"type": "sale", "property": "w"},
            {"type": "vehicle", "id": "v", "purchaseDate": "2026-01-01"}]})["items"]
        twice = items + [{"type": "sale", "property": "p", "saleDate": "2031-01-01", "name": "S"}]
        assert_golden(self, "property_sales", [outcome(dates.property_sales, items),
                                               outcome(dates.property_sales, twice)])
        props = {"p": items[0]}
        assert_golden(self, "mortgage_start", [
            outcome(dates.mortgage_start, m, props, "item m")
            for m in ({"startDate": "2026-03-01"}, {"property": "p"}, {}, {"startDate": "x"})])


class Loan(Aggregate):
    kind = "mortgage"

    def __init__(self, id, item_index, secured_by=None):
        super().__init__(id, id, item_index, Decimal("0.00"))
        self.secured_by = secured_by


class Asset(Aggregate):
    kind = "property"

    def __init__(self, id, item_index, balance=Decimal("0.00")):
        super().__init__(id, id, item_index, balance)


SETTINGS = [
    {},
    {"annualInflation": 0.02, "effectiveTaxRate": "0.3", "retirementTaxRate": 0,
     "incomeMode": "expensesCovered", "dollarsOf": "2020-01-01"},
    {"annualInflation": "0", "retirementTaxRate": "0", "retirementDate": "2026-06-01"},
    {"retirementTaxRate": 0.15, "effectiveTaxRate": 0.25,
     "items": [{"type": "retirement", "retirementDate": "2027-01-01"}]},
]


PERSON_ATTRS = ("tax_rate", "retirement", "retirement_tax_rate")   # on the person (ADR-0061)


class HouseholdCore(unittest.TestCase):
    def test_settings_golden(self):
        attrs = ("start", "end", "inflation", "tax_rate", "retirement", "retirement_tax_rate",
                 "base", "covered")
        for extra in SETTINGS:
            extra = dict(extra)
            s = scenario(extra.pop("items", []), cash="150000.005", **extra)
            hh = Household(s)
            assert_golden(self, "settings", [repr(getattr(hh.first if a in PERSON_ATTRS else hh, a)) for a in attrs])
            self.assertEqual(repr(hh.cash.balance), "Decimal('150000.00')")  # ROUND_HALF_EVEN
            self.assertFalse(hh.first.retired)
            self.assertEqual(hh.first.current_tax_rate, hh.first.tax_rate)
            hh.first.retired = True
            self.assertEqual(hh.first.current_tax_rate, hh.first.retirement_tax_rate)
            self.assertEqual(hh.recurring_source, None if hh.covered else "cash")

    def test_move_golden(self):
        s = scenario([{"type": "mortgage", "id": "m", "principal": 1000, "annualRate": 0.05,
                       "amortizationYears": 1, "startDate": "2026-01-01"}])
        hh = Household(s)
        hh.month = hh.start
        hh.add(Loan("m", 0))
        moves = [("LOAN_ADVANCE", "m", "cash", Decimal("1000"), "m"),
                 ("LOAN_INTEREST", "m", None, Decimal("4.123456"), "m"),
                 ("LOAN_PAYMENT", "cash", "m", Decimal("85.605"), "m"),
                 ("NOTHING", "cash", None, Decimal("0.004"), "x"),
                 ("NEG", None, "cash", Decimal("-12.345"), None),
                 ("PREPAYMENT", None, "m", Decimal("0.015"), "e")]
        assert_golden(self, "moves", [hh.move(*mv) for mv in moves])
        assert_golden(self, "ledger and balances",
                      (hh.ledger.entries, hh["m"].balance, hh.cash.balance))
        self.assertEqual(list(hh.ledger.entries[0]), ["month", "kind", "from", "to", "amount", "source"])

    def test_zero_move_records_nothing(self):
        hh = Household(scenario([]))
        hh.month = hh.start
        self.assertEqual(repr(hh.move("X", "cash", None, Decimal("0.0049"))), "Decimal('0.00')")
        self.assertEqual(len(hh.ledger), 0)
        self.assertEqual(hh.cash.balance, Decimal("10000.00"))
        with self.assertRaises(KeyError):
            hh.move("X", "missing", None, Decimal(1))

    def test_slot_order_and_lookups(self):
        hh = Household(scenario([]))
        hh.add(Asset("p2", 5))
        hh.add(Loan("m1", 1, secured_by="p2"))
        hh.add(Asset("p1", 3))
        hh.add(Loan("m2", 4, secured_by="p2"))
        hh.add(Loan("m3", 2, secured_by="p1"))
        self.assertEqual([a.id for a in hh.aggregates()], ["cash", "m1", "m3", "p1", "m2", "p2"])
        self.assertEqual([a.id for a in hh.aggregates("property")], ["p1", "p2"])
        self.assertEqual([a.id for a in hh.loans_secured_by("p2")], ["m1", "m2"])
        replacement = Asset("p2", 0)            # same id: replaces, keeps the first slot
        hh.add(replacement)
        self.assertIs(hh.get("p2"), replacement)
        self.assertEqual([a.id for a in hh.aggregates()][-1], "p2")
        self.assertIsNone(hh.get("nope"))
        self.assertEqual(hh.cash.group, "cash")
        self.assertEqual(hh["m1"].group, "debts")
        self.assertIsNone(hh.cash.report_rate)

    def test_begin_month_snapshot(self):
        hh = Household(scenario([]))
        hh.add(Asset("p", 2, Decimal("500.00")))
        hh.first.tax.add_taxable(Decimal("5"))
        hh.first.tax.add_deduction(Decimal("1"))
        hh.first.tax.add_own_rate_tax(Decimal("0.123"))
        hh.first.tax.pool = Decimal("7")
        hh.begin_month(hh.start)
        self.assertEqual(hh.month, hh.start)
        self.assertEqual((repr(hh.first.tax.taxable), repr(hh.first.tax.deductions), repr(hh.first.tax.extra_tax)),
                         ("Decimal('0')",) * 3)
        self.assertEqual(hh.first.tax.pool, Decimal("7"))
        self.assertEqual([a.id for a in hh.opened], ["p"])
        self.assertEqual(hh.opening, {"p": Decimal("500.00")})
        self.assertEqual(hh.points_opening, {"cash": Decimal("10000.00"), "p": Decimal("500.00")})
        hh.add(Loan("m", 1))                    # created this month: not opened
        hh.move("LOAN_ADVANCE", "m", "cash", Decimal(100), "m")
        self.assertFalse(hh.is_opened("m"))
        self.assertTrue(hh.is_opened("p"))
        self.assertEqual(hh.opened_aggregates("mortgage"), [])
        hh.begin_month(hh.start + 1)
        self.assertEqual([a.id for a in hh.opened_aggregates()], ["m", "p"])
        self.assertEqual(hh.ledger.entries[0]["month"], "2026-01")


class Log:
    def __init__(self):
        self.calls = []


class Logged(StateEvent):
    """Appends (month, label) to the log; in the INITIAL step also the opening points."""

    def __init__(self, log, label):
        self.log, self.label = log, label

    def apply(self, household):
        if household.month is None:
            self.log.calls.append((None, self.label, household.points_opening))
        else:
            self.log.calls.append((household.month, self.label))


class LogEmitter(Emitter):
    def __init__(self, log, label, order, schedule, sub=0):
        super().__init__(schedule, order=order, sub=sub)
        self.log, self.label = log, label

    def emit(self, month, household):
        return [Logged(self.log, self.label)]


def LogOnce(log, label, order, month, sub=0):
    """One-shot emitter (month None = never)."""
    return LogEmitter(log, label, order, Once(month), sub)


def LogRecurring(log, label, order, first=None, last=None, sub=0):
    """Recurring emitter, active first <= m <= last (None = unbounded)."""
    return LogEmitter(log, label, order, Window(first, last), sub)


def LogInitial(log, label):
    return LogEmitter(log, label, Order.INITIAL, INITIAL)


class ClockOrdering(unittest.TestCase):
    def test_order_table_is_the_reference_step_order(self):
        self.assertEqual([o.name for o in Order], [
            "INITIAL", "OPEN", "INCOME", "PENSION_PAY", "ACQUIRE", "IMPROVE", "ADJUST", "SELL",
            "TRANSFER", "SERVICE_DEBT", "EXPENSE", "MAINTAIN", "CONTRIBUTE", "WITHDRAW", "GROW",
            "REVALUE_PENSIONS", "TAX", "CLOSE"])
        # Default emitter order numbers: ORDER_STEP apart, INITIAL negative (D-E2).
        self.assertEqual(ORDER_STEP, 100)
        self.assertEqual([int(o) for o in Order], [n * 100 for n in range(-1, 17)])

    def test_fires_by_order_then_ordinal_then_sub(self):
        log = Log()
        hh = Household(scenario([], start="2026-01-01", end="2026-03-01"))
        start = hh.start
        specs = [
            (LogRecurring(log, "tax", Order.TAX), SCENARIO),
            (LogRecurring(log, "grow#2", Order.GROW), 2),
            (LogRecurring(log, "grow#0", Order.GROW), 0),
            (LogOnce(log, "buy#4", Order.ACQUIRE, start + 1), 4),
            (LogOnce(log, "advance#1", Order.ACQUIRE, start + 1), 1),
            (LogRecurring(log, "income#3", Order.INCOME, first=start + 1, last=start + 1), 3),
            (LogOnce(log, "retire", Order.OPEN, start + 1), SCENARIO),
            (LogRecurring(log, "service#1.1", Order.SERVICE_DEBT, sub=1), 1),
            (LogRecurring(log, "service#1.0", Order.SERVICE_DEBT), 1),
            (LogOnce(log, "never", Order.SELL, None), 6),
            (LogRecurring(log, "close", Order.CLOSE), SCENARIO),
            (LogInitial(log, "init#5"), 5),
            (LogInitial(log, "init#0"), 0),
        ]
        random.Random(3).shuffle(specs)
        clock = Clock()
        for h, ordinal in specs:
            clock.register(h, ordinal)
        clock.run(hh)
        per_month = ["service#1.0", "service#1.1", "grow#0", "grow#2", "tax", "close"]
        expected = [(None, "init#0", {}), (None, "init#5", {})]
        expected += [(start, n) for n in per_month]
        expected += [(start + 1, n) for n in
                     ["retire", "income#3", "advance#1", "buy#4"] + per_month]
        expected += [(start + 2, n) for n in per_month]
        self.assertEqual(log.calls, expected)
        self.assertEqual(clock.schedule()[:2], [(-100, 0, 0), (-100, 5, 0)])
        acquire = dict(clock.steps())[int(Order.ACQUIRE)]
        self.assertEqual([e.label for e in acquire], ["advance#1", "buy#4"])
        self.assertEqual([r["event"] for r in hh.events][:2], ["Logged", "Logged"])
        self.assertEqual({r["kind"] for r in hh.events}, {"state"})

    def test_duplicate_key_and_non_emitter_rejected(self):
        log, clock = Log(), Clock()
        clock.register(LogRecurring(log, "a", Order.GROW), 3)
        with self.assertRaises(ValueError):
            clock.register(LogRecurring(log, "b", Order.GROW), 3)
        clock.register(LogRecurring(log, "c", Order.GROW, sub=1), 3)
        clock.register(LogRecurring(log, "d", Order.GROW + 50), 3)   # any int is an order
        with self.assertRaises(TypeError) as cm:
            clock.register(object(), 4)                            # not an Emitter
        self.assertIn("not an emitters.Emitter", str(cm.exception))
        with self.assertRaises(TypeError):
            clock.register(LogRecurring(log, "e", None), 4)          # no order


class CompilerRegistry(unittest.TestCase):
    def test_discover_and_facade(self):
        compiler.discover()
        self.assertIsInstance(compiler.registered_types(), dict)
        from state_machine import engine
        for name in ("validate", "run", "run_detailed", "retirement_date", "month_label",
                     "month_index", "base_month", "annuity", "monthly_rate", "mortgage_terms",
                     "money"):
            self.assertTrue(callable(getattr(engine, name)), name)
        self.assertIs(engine.money, arith.money)
        self.assertIs(api.month_label, dates.month_label)

    def test_factories_ordinals_and_setup(self):
        log = Log()
        seen = []
        with compiler.isolated_registry():
            @compiler.item_type("property")
            def prop(item, ctx):
                seen.append((ctx.index, ctx.id, ctx.ordinal, ctx.name))
                ctx.env.bucket("test.extras", ctx.id)       # same list as the flow's
                return [LogRecurring(log, f"grow:{ctx.id}", Order.GROW)]

            @compiler.item_type("income")
            def income(item, ctx):
                seen.append((ctx.index, ctx.id, ctx.ordinal, ctx.name))
                ctx.env.bucket("test.extras", "p").append(ctx.id)
                yield LogRecurring(log, f"income:{ctx.id}", Order.INCOME)

            @compiler.scenario_setup("b-late", order=20)
            def late(env):
                yield LogRecurring(log, "tax", Order.TAX)

            @compiler.scenario_setup("a-early", order=10)
            def early(env):
                self.assertIs(env.household.scenario, s)
                self.assertEqual(env.household.first.retirement, None)
                return [LogRecurring(log, "close", Order.CLOSE)]

            with self.assertRaises(ValueError):
                compiler.item_type("property")(lambda item, ctx: None)

            s = scenario([{"type": "income", "id": "p"},
                          {"type": "property", "id": "p", "name": "First"},
                          {"type": "income"},
                          {"type": "property", "id": "q"},
                          {"type": "property", "id": "p"}],
                         start="2026-01-01", end="2026-01-01")
            s["jurisdiction"] = "CA"                    # current form (ADR-0071)
            hh, clock = compiler.compile_scenario(s)
            clock.run(hh)
        self.assertEqual(seen, [(0, "p", 0, "p"), (2, "item2", 2, "item2"),
                                (3, "q", 3, "q"), (4, "p", 1, "p")])
        self.assertEqual(clock.schedule(), [(100, 0, 0), (100, 2, 0), (1300, 1, 0), (1300, 3, 0),
                                            (1500, -1, 0), (1600, -1, 0)])
        self.assertEqual([c[1] for c in log.calls],
                         ["income:p", "income:item2", "grow:p", "grow:q", "tax", "close"])

    def test_unknown_type(self):
        with compiler.isolated_registry():
            with self.assertRaises(NotImplementedError):
                compiler.compile_scenario(scenario([{"type": "mystery"}]))


if __name__ == "__main__":
    unittest.main()
