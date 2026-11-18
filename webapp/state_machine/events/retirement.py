"""Retirement (E5, D2): a scenario-level emitter at the start of the retirement month
(Order.OPEN, ordinal SCENARIO, sub 0, after the core ``begin_month``) emits one
``Retirement`` state event per person that sets the person's ``retired``, which switches
their tax rate.

Retirement-anchored dates of other items are resolved at compile time from
``env.retirement_for(item)`` (look-ahead), so this event changes only the runtime state. The
``retirement`` item type itself compiles to nothing: the scenario setup hook below
handles both the event item and the legacy scenario ``retirementDate``, and also
registers the tax step (rules/tax.py).
"""
from ..clock import Order
from ..compiler import item_type, scenario_setup
from ..emitters import Once, ScenarioEmitter, StateEvent
from ..rules.tax import TaxEmitter


class Retirement(StateEvent):
    """A person retires (ADR-0061): their ``retired`` flag, which switches their tax
    rate. Without ``person`` the first person (older callers)."""

    def __init__(self, person=None, label=""):
        self.person = person
        self.label = label

    def apply(self, household):
        household.person(self.person).retired = True

    def describe(self):
        return f"{self.label} retired" if self.label else "retired"


class RetirementEmitter(ScenarioEmitter):
    """Due once, in month ``max(retirement, start)``: a legacy retirementDate may lie
    before the horizon start, and the reference then counts every month as retired
    (``month >= retirement``). A retirement after the horizon end never fires."""
    ORDER = Order.OPEN
    SUB = 0

    def __init__(self, retirement, start, person=None, label="", **kw):
        super().__init__(Once(max(retirement, start)), **kw)
        self.retirement = retirement
        self.person = person
        self.label = label

    @property
    def month(self):
        return self.schedule.month

    def emit(self, month, household):
        return (Retirement(self.person, self.label),)

    def __repr__(self):
        return f"<RetirementEmitter retirement={self.retirement} fires={self.month}>"


@item_type("retirement")
def compile_retirement(item, ctx):
    return []       # handled by setup_retirement_and_tax (reference: skipped in prepare)


@scenario_setup("wp7.retirement_tax", order=50)
def setup_retirement_and_tax(env):
    persons = list(env.household.persons.values())
    for n, person in enumerate(persons):
        if person.retirement is not None:
            # One per person (ADR-0061); distinct subs at Order.OPEN, names only when
            # there is more than one person (single-person logs unchanged).
            label = person.name if len(persons) > 1 else ""
            yield RetirementEmitter(person.retirement, env.start, person.id, label, sub=n)
    yield TaxEmitter()
