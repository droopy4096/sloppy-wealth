"""TaxRule and the monthly tax step (E5), reference ``Simulation.tax`` (OBJECTS §4.9).

``TaxEmitter`` is a scenario-level emitter (Order.TAX, ordinal SCENARIO, sub 0), due
every month; it emits one ``TaxStepEvent`` (a state event) whose ``apply`` runs the
``TaxRule`` on the month's accumulator: tax detail, deduction pool, TAX movement. It is
registered together with the retirement emitter (events/retirement.py) by one setup
hook. The month's inputs come from each person's ``tax`` (a TaxAccumulator filled by
income, pensions, accounts), so everything is resolved at apply time (§10.6).
"""
from decimal import Decimal

from ..arith import money
from ..base import Rule
from ..clock import Order
from ..dates import month_label
from ..emitters import ScenarioEmitter, StateEvent


SUMMED = ("taxable", "deductions", "poolIn", "used", "poolOut", "incomeTax", "ownRateTax",
          "total")


class TaxRule(Rule):
    """One flat rate on taxable income less deductions; deductions the month cannot
    absorb carry forward in ``tax.pool`` (ADR-0048). Per person (ADR-0061): each has
    their own accumulator, pool and rate (``person.current_tax_rate``: their
    retirementTaxRate once they retired, ADR-0059) and pays their own TAX movement
    (source: the person id; None with one person). ``household.tax_detail`` is the
    household view: the person's detail with one person, else the sums plus
    ``persons`` (person id -> detail)."""

    def apply(self, household):
        label = month_label(household.month)
        persons = list(household.persons.values())
        single = len(persons) == 1
        details = {}
        for person in persons:
            details[person.id] = detail = self.person_step(person, label)
            household.move("TAX", "cash", None, detail["total"], None if single else person.id)
        if single:
            household.tax_detail[label] = details[persons[0].id]
        else:
            combined = {k: sum((d[k] for d in details.values()), Decimal("0.00")) for k in SUMMED}
            combined.update(rate=None, retired=None, persons=details)
            household.tax_detail[label] = combined

    @staticmethod
    def person_step(person, label):
        tax = person.tax
        retired = person.retired
        rate = person.current_tax_rate
        # Reference L1026-1036, expression for expression.
        pool_in = tax.pool
        available = tax.deductions + tax.pool
        used = min(available, max(Decimal(0), tax.taxable))
        tax.pool = available - used
        due = money(rate * (max(Decimal(0), tax.taxable) - used))
        detail = tax.detail[label] = {
            "taxable": money(tax.taxable), "deductions": money(tax.deductions),
            "poolIn": money(pool_in), "used": money(used), "poolOut": money(tax.pool),
            "rate": rate, "retired": retired, "incomeTax": due,
            "ownRateTax": money(tax.extra_tax), "total": due + money(tax.extra_tax)}
        return detail


class TaxStepEvent(StateEvent):
    """The month's tax step: records the tax detail, carries the deduction pool and pays
    the tax (a TAX movement unless it rounds to 0). The detail is written every month."""

    def __init__(self, rule):
        self.rule = rule

    def apply(self, household):
        self.rule.apply(household)

    def describe(self):
        return "tax step"


class TaxEmitter(ScenarioEmitter):
    """Every month: one TaxStepEvent."""
    ORDER = Order.TAX
    SUB = 0

    def __init__(self, rule=None, **kw):
        super().__init__(**kw)
        self.rule = rule or TaxRule()

    def emit(self, month, household):
        return (TaxStepEvent(self.rule),)
