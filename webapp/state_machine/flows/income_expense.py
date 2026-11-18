"""Income and Expense flows (E5, OBJECTS §4.1; reference prepare L711-731, income L829,
debits L902) as recurring emitters (INTERFACES §10).

- ``IncomeEmitter`` (Order.INCOME, item index) emits an ``Income`` flow event,
  ``ExpenseEmitter`` (Order.EXPENSE, item index) an ``Expense`` flow event, every month
  of ``first <= m <= last``. Retirement anchors are resolved at compile time from the
  look-ahead retirement month (D2).
- The month's amount comes from the item's ``IndexingRule`` (rules/indexing.py); it does
  not depend on balances, so the emitter resolves it and the event carries it.
- An expense tied to an asset or an income (formerly ``attachedTo``, ADR-0040
  amendments) gets its dates from triggers (ADR-0065), resolved before compiling.
- In income-less mode (``household.covered``) income is ignored and expenses are paid
  from outside, i.e. both emit nothing.
- Nothing is emitted in a month whose amount rounds to 0 (``move`` would record nothing),
  except for taxable income: the reference still adds the rounded ``0.00`` to the month's
  taxable sum, which can change the exponent of the tax pool (kept exact).
"""
from decimal import Decimal

from ..arith import ONE, PER, flow_amount, power
from ..clock import Order
from ..compiler import item_type
from ..dates import flow_window, month_index
from ..emitters import FlowEvent, RecurringEmitter
from ..rules.indexing import IndexingRule
from .adjustment import steps_for


def flow_terms(item, env):
    """(first, last, base amount, IndexingRule) exactly as the reference prepare()."""
    hh = env.household
    first = month_index(item["startDate"], "startDate")
    first, last = flow_window(item, env, first)
    amount, per = flow_amount(item)
    rule = IndexingRule.for_item(item, hh.inflation, first, PER[per],
                                 steps_for(item, env))      # adjustments (ADR-0062)
    if item.get("amountIn") == "base" and hh.inflation:
        # Stated in base-date dollars: inflated to the item's start (unrounded), then
        # indexed from there as usual.
        amount = amount * power(ONE + hh.inflation, Decimal(first - hh.base) / 12)
    return first, last, amount, rule


# ---------------------------------------------------------------- events
class Income(FlowEvent):
    """INCOME None -> cash; taxable income adds the rounded amount to the month's tax."""

    def __init__(self, amount, taxable, earned=False, owner=None):
        self.amount = amount
        self.taxable = taxable
        self.earned = earned
        self.owner = owner          # person id (ADR-0061); None = the first person

    def apply(self, household):
        gross = household.move("INCOME", None, "cash", self.amount, self.source)
        if self.taxable:
            household.tax_of(self.owner).add_taxable(gross)
        if self.earned:
            household.jurisdiction.limits.note_earned(household, gross, self.owner)  # ADR-0060

    def describe(self):
        return f"income {self.amount}" + (" taxable" if self.taxable else "")


class Expense(FlowEvent):
    """EXPENSE cash -> None."""

    def __init__(self, amount):
        self.amount = amount

    def apply(self, household):
        household.move("EXPENSE", "cash", None, self.amount, self.source)

    def describe(self):
        return f"expense {self.amount}"


# ---------------------------------------------------------------- emitters
class _FlowEmitter(RecurringEmitter):
    def __init__(self, first, last, base, rule, **kw):
        super().__init__(first, last, **kw)
        self.base = base
        self.rule = rule

    @property
    def first(self):
        return self.schedule.first

    @property
    def last(self):
        return self.schedule.last

    def amount(self, month):
        """The month's indexed amount (rounded to cents)."""
        return self.rule.amount(self.base, month)

    def __repr__(self):
        return (f"<{self.name} {self.source!r} {self.first}..{self.last} "
                f"base={self.base!r} {self.rule!r}>")


class IncomeEmitter(_FlowEmitter):
    ORDER = Order.INCOME

    def __init__(self, first, last, base, rule, taxable, earned=False, owner=None, **kw):
        super().__init__(first, last, base, rule, **kw)
        self.taxable = taxable
        self.earned = earned
        self.owner = owner

    def emit(self, month, household):
        if household.covered:
            return None
        amount = self.amount(month)
        if amount == 0 and not self.taxable:
            return None
        return (Income(amount, self.taxable, self.earned, self.owner),)


class ExpenseEmitter(_FlowEmitter):
    ORDER = Order.EXPENSE

    def emit(self, month, household):
        if household.covered:
            return None
        amount = self.amount(month)
        if amount == 0:
            return None
        return (Expense(amount),)


@item_type("income")
def compile_income(item, ctx):
    first, last, base, rule = flow_terms(item, ctx.env)
    taxable = item.get("taxable", False)
    # Earned income for RRSP room (ADR-0060): default = taxable.
    earned = item.get("earnedIncome", taxable)
    yield IncomeEmitter(first, last, base, rule, taxable, bool(earned), ctx.env.person_of(item))


@item_type("expense")
def compile_expense(item, ctx):
    first, last, base, rule = flow_terms(item, ctx.env)
    yield ExpenseEmitter(first, last, base, rule)
