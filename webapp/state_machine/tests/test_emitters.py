"""E0 event-emitter core: schedules, runner order, immediate apply, follow-ups (D-E3),
modifier placement (D-E1), event log and the ``events`` output (D-E4). Run from webapp/:
    .venv/bin/python -m unittest state_machine.tests.test_emitters
"""
import unittest
from decimal import Decimal

from state_machine import api, compiler
from state_machine.clock import SCENARIO, Order
from state_machine.emitters import (INITIAL, Anniversary, Emitter, FlowEvent, InitialEmitter,
                                    ModifierEmitter, Never, OneShotEmitter, Once,
                                    RecurringEmitter, ScenarioEmitter, StateEvent, Window,
                                    sub_order)
from state_machine.household import Household
from state_machine.runner import ScenarioRunner

from .support import sample, scenario


class Pay(FlowEvent):
    """Moves ``amount`` cash -> outside; with ``fraction`` instead: that share of the cash
    balance at apply time (state-dependent amount resolved in apply)."""

    def __init__(self, amount=None, fraction=None, then=()):
        self.amount, self.fraction, self.then = amount, fraction, list(then)

    def apply(self, household):
        amount = self.amount if self.fraction is None else household.cash.balance * self.fraction
        household.move("EXPENSE", "cash", None, amount, self.source)
        return self.then


class Note(StateEvent):
    def __init__(self, log, text):
        self.log, self.text = log, text

    def apply(self, household):
        self.log.append((household.month, self.text))

    def describe(self):
        return f"note {self.text}"


class Say(RecurringEmitter):
    ORDER = Order.EXPENSE

    def __init__(self, log, text, **kw):
        super().__init__(**kw)
        self.log, self.text = log, text

    def emit(self, month, household):
        return [Note(self.log, self.text)]


class SayInitial(InitialEmitter):
    ORDER = Order.INITIAL

    def __init__(self, log, text, **kw):
        super().__init__(**kw)
        self.log, self.text = log, text

    def emit(self, month, household):
        yield Note(self.log, self.text)


def household(start="2026-01-01", end="2026-02-01", cash="1000"):
    return Household(scenario([], start=start, end=end, cash=cash))


class Schedules(unittest.TestCase):
    def test_due(self):
        self.assertTrue(INITIAL.due(None))
        self.assertFalse(INITIAL.due(5))
        self.assertFalse(Once(None).due(None))
        self.assertTrue(Once(7).due(7))
        self.assertFalse(Once(7).due(8))
        self.assertFalse(Window().due(None))
        self.assertTrue(Window().due(3))
        self.assertEqual([m for m in range(10) if Window(2, 4).due(m)], [2, 3, 4])
        self.assertEqual([m for m in range(40) if Anniversary(3, 12, 30).due(m)], [3, 15, 27])
        self.assertFalse(Never().due(1))


class Runner(unittest.TestCase):
    def test_order_override_and_inserted_number(self):
        log, hh = [], household(end="2026-01-01")
        runner = ScenarioRunner()
        runner.register(Say(log, "expense#2"), 2)
        runner.register(Say(log, "expense#0"), 0)
        runner.register(Say(log, "between", order=Order.SERVICE_DEBT + 50), 9)
        runner.register(Say(log, "expense#1"), 1)
        runner.register(Say(log, "debt", order=Order.SERVICE_DEBT), 9)
        runner.register(SayInitial(log, "init"), 4)
        runner.run(hh)
        self.assertEqual(log, [(None, "init")] + [(hh.start, t) for t in
                         ["debt", "between", "expense#0", "expense#1", "expense#2"]])
        self.assertEqual(runner.schedule(), [(-100, 4, 0), (800, 9, 0), (850, 9, 0),
                                             (900, 0, 0), (900, 1, 0), (900, 2, 0)])
        self.assertEqual([o for o, _ in runner.steps()], [-100, 800, 850, 900])

    def test_registration_errors(self):
        runner, log = ScenarioRunner(), []
        runner.register(Say(log, "a"), 3)
        with self.assertRaises(ValueError):            # same key
            runner.register(Say(log, "b"), 3)
        runner.register(Say(log, "c", sub=1), 3)

        class NoOrder(Emitter):
            def emit(self, month, household):
                return []
        with self.assertRaises(TypeError):
            runner.register(NoOrder(), 4)
        with self.assertRaises(TypeError):
            runner.register(object(), 4)

    def test_apply_immediately_and_generator_sees_state(self):
        hh = household(end="2026-01-01", cash="1000")

        class Halves(ScenarioEmitter):
            ORDER = Order.EXPENSE

            def emit(self, month, household):
                yield Pay(fraction=Decimal("0.5"))
                yield Pay(fraction=Decimal("0.5"))       # resolved after the first applied

        class Reader(RecurringEmitter):
            ORDER = Order.WITHDRAW
            seen = None

            def emit(self, month, household):
                Reader.seen = household.cash.balance     # later emitter sees earlier state
                return None

        runner = ScenarioRunner()
        runner.register(Halves(source="h"), SCENARIO)
        runner.register(Reader(), 0)
        runner.run(hh)
        self.assertEqual([e["amount"] for e in hh.ledger], [Decimal("500.00"),
                                                            Decimal("250.00")])
        self.assertEqual(Reader.seen, Decimal("250.00"))

    def test_follow_ups_depth_first_and_log(self):
        hh = household(end="2026-01-01")
        log = []

        class Sale(OneShotEmitter):
            ORDER = Order.SELL

            def emit(self, month, household):
                return [Pay(Decimal("1"), then=[Pay(Decimal("2"), then=[Note(log, "deep")]),
                                                Pay(Decimal("3"))]),
                        Pay(Decimal("4"))]

        runner = ScenarioRunner()
        runner.register(Sale(hh.start, source="s"), 5)
        runner.run(hh)
        self.assertEqual([e["amount"] for e in hh.ledger],
                         [Decimal(x) for x in ("1.00", "2.00", "3.00", "4.00")])
        recs = hh.events.records
        self.assertEqual([(r["event"], r["cause"], r["ledger"]) for r in recs],
                         [("Pay", None, (0, 1)), ("Pay", 0, (1, 2)), ("Note", 1, (2, 2)),
                          ("Pay", 0, (2, 3)), ("Pay", None, (3, 4))])
        self.assertEqual(recs[2], {"month": "2026-01", "key": (600, 5, 0), "emitter": "Sale",
                                   "event": "Note", "kind": "state", "source": "s",
                                   "cause": 1, "ledger": (2, 2), "detail": "note deep"})
        # Every movement belongs to exactly one event.
        self.assertEqual(sum(b - a for a, b in (r["ledger"] for r in recs)), len(hh.ledger))


class Compile(unittest.TestCase):
    def test_modifier_placement_and_prepare(self):
        log, prepared = [], []

        class Host(RecurringEmitter):
            ORDER = Order.SERVICE_DEBT

            def emit(self, month, household):
                return [Note(log, "service")]

        class Renewal(ModifierEmitter):
            ORDER = Order.SERVICE_DEBT
            STAGE = 0

            def emit(self, month, household):
                return [Note(log, f"renew:{self.source}")]

            def prepare(self, env):
                prepared.append(self.source)
                self.host_emitters = env.emitters_for(self.host)
                self.siblings = [e.source for e in env.modifiers_of(self.host, Renewal)]

        class Extra(Renewal):
            STAGE = 2

        class Improve(ModifierEmitter):
            ORDER = Order.IMPROVE
            AT_HOST = False

            def emit(self, month, household):
                return [Note(log, "improve")]

        with compiler.isolated_registry():
            compiler.item_type("mortgage")(lambda item, ctx: [Host(sub=sub_order(1))])
            compiler.item_type("extraPayment")(lambda item, ctx: [Extra(item["mortgage"])])
            compiler.item_type("renewal")(lambda item, ctx: [Renewal(item["mortgage"])])
            compiler.item_type("improvement")(lambda item, ctx: [Improve(item["property"])])
            s = scenario([{"type": "extraPayment", "id": "x", "mortgage": "m"},
                          {"type": "improvement", "id": "i", "property": "p"},
                          {"type": "mortgage", "id": "m"},
                          {"type": "renewal", "id": "r", "mortgage": "m"}],
                         start="2026-01-01", end="2026-01-01")
            hh, runner = compiler.compile_scenario(s)
            runner.run(hh)
            with self.assertRaises(ValueError):
                compiler.compile_scenario(scenario([{"type": "renewal", "mortgage": "zz"}]))
        self.assertEqual(runner.schedule(), [(400, 1, 1), (800, 2, 3), (800, 2, 1_000_000),
                                             (800, 2, 2_000_000)])
        self.assertEqual([t for _, t in log], ["improve", "renew:r", "service", "renew:x"])
        self.assertEqual(prepared, ["r", "x"])
        renewal = runner.emitters()[1]
        self.assertEqual([type(e).__name__ for e in renewal.host_emitters], ["Host"])
        self.assertEqual(renewal.siblings, ["x", "r"])      # item order (Extra is a Renewal)
        self.assertEqual((renewal.index, renewal.host), (3, "m"))
        self.assertEqual([r["source"] for r in hh.events.records], ["i", "r", "m", "x"])


class Output(unittest.TestCase):
    def test_run_detailed_events(self):
        for name in ("single-house-sold.json", "rent.json"):
            with self.subTest(name):
                r = api.run_detailed(sample(name))
                self.assertEqual(list(r), ["rows", "holdings", "ledger", "tax", "events"])
                ev = r["events"]
                self.assertEqual(list(ev[0]), ["month", "key", "emitter", "event", "kind",
                                               "source", "cause", "ledger", "detail"])
                pos = 0                     # ledger ranges tile the whole ledger, in order
                for rec in ev:
                    a, b = rec["ledger"]
                    self.assertEqual(a, pos)
                    pos = b
                self.assertEqual(pos, len(r["ledger"]))
                # The results recorder (CLOSE) logs nothing: the last event is the tax step.
                self.assertEqual(ev[-1]["key"], (int(Order.TAX), SCENARIO, 0))
                self.assertEqual(ev[-1]["month"], r["rows"][-1]["month"])
                self.assertLessEqual({rec["kind"] for rec in ev},
                                     {"lifecycle", "flow", "valuation", "state"})
                # The ledger's movements are attributed to the emitting item.
                for rec in ev:
                    for x in r["ledger"][slice(*rec["ledger"])]:
                        if x["kind"] != "TAX":
                            self.assertEqual(x["source"], rec["source"])


if __name__ == "__main__":
    unittest.main()
