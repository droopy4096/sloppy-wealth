"""Pension (WP6): a guaranteed (defined-benefit) pension, OBJECTS §2.5 / reference
``prepare`` L639-655, ``pension_payment`` L795, ``pension_value`` L801, ``pensions`` L811,
``revalue_pensions`` L823 and the pension branch of ``contribute`` L924.

The pension exists from the horizon start (created at INITIAL with its value at
``start - 1``). Each month it pays ``pension_payment`` into cash while active (PENSION_PAY,
covered mode included) and is then revalued to ``pension_value`` (REVALUE_PENSIONS, every
month, negative movements allowed). Its anchors (``first``, ``last``) are resolved at
compile time from the look-ahead retirement month (D2).

Emitters (INTERFACES §10): PensionCreation (InitialEmitter, INITIAL) -> PensionCreated
(lifecycle); PensionPayment (RecurringEmitter, PENSION_PAY, window first..last) ->
PensionPaid (flow); PensionRevaluation (RecurringEmitter, REVALUE_PENSIONS, every month)
-> PensionRevalued (valuation). Months in which nothing moves emit nothing.
"""
from decimal import Decimal

from ..arith import ONE, PER, flow_amount, indexing_rate, money, power
from ..base import Aggregate
from ..clock import Order
from ..compiler import item_type
from ..dates import flow_window, month_index
from ..emitters import (FlowEvent, InitialEmitter, LifecycleEvent, RecurringEmitter,
                        ValuationEvent)


class Pension(Aggregate):
    kind = "pension"

    def __init__(self, id, name, item_index, base, divisor, first, last, rate, taxable,
                 owner=None):
        self.owner = owner          # person id (ADR-0061); None = the first person
        self.base = base            # amount in base-date dollars (per ``per``)
        self.divisor = divisor      # PER[per]
        self.first = first          # first payment month (startDate or retirement)
        self.last = last            # last payment month (<= horizon end)
        self.rate = rate            # annual indexing rate
        self.taxable = taxable      # raw item.get("taxable", True)
        super().__init__(id, name, item_index, Decimal(0))

    @property
    def report_rate(self):
        # Reference points show h["rate"]: the pension's annual indexing rate.
        return self.rate

    # Verbatim reference expressions; ``household.base`` is the base date (dollarsOf).
    def payment(self, household, m):
        years = (m - household.base) // 12
        return money(self.base * (ONE + self.rate) ** years / self.divisor)

    def value(self, household, m):
        real = Decimal(0)
        for k in range(max(m + 1, self.first), self.last + 1):
            years = (k - household.base) // 12
            real += self.base * ((ONE + self.rate) / (ONE + household.inflation)) ** years / self.divisor
        factor = (power(ONE + household.inflation, Decimal(m - household.base) / 12)
                  if household.inflation else ONE)
        return money(real * factor)

    def accept_contribution(self, household, amount, source, match):
        """Paid to the plan, outside the model; the value is unchanged. Deducted; covered
        from outside (nothing recorded) in income-less mode. ``match`` is ignored."""
        if not household.covered:
            amount = household.move("PENSION_CONTRIBUTION", "cash", None, amount, source)
            household.tax_of(self.owner).add_deduction(amount)


# ---------------------------------------------------------------- events
class PensionCreated(LifecycleEvent):
    """The pension exists from month 1 with its value at ``start - 1`` (no movement)."""

    def __init__(self, pension):
        self.pension = pension

    def apply(self, household):
        p = self.pension
        p.balance = p.value(household, household.start - 1)
        household.add(p)

    def describe(self):
        return f"{self.name} {self.pension.id} value={self.pension.balance}"


class PensionPaid(FlowEvent):
    """PENSION_PAYMENT pension -> cash; taxable income if the pension is flagged."""

    def __init__(self, pension_id, amount):
        self.pension_id, self.amount = pension_id, amount

    def apply(self, household):
        p = household[self.pension_id]
        paid = household.move("PENSION_PAYMENT", p.id, "cash", self.amount, p.id)
        if p.taxable:
            household.tax_of(p.owner).add_taxable(paid)

    def describe(self):
        return f"{self.name} {self.pension_id} {self.amount}"


class PensionRevalued(ValuationEvent):
    """REVALUATION outside -> pension of ``value - balance`` (negative allowed); the
    difference is resolved against the balance at apply time."""

    def __init__(self, pension_id, value):
        self.pension_id, self.value = pension_id, value

    def apply(self, household):
        p = household[self.pension_id]
        household.move("REVALUATION", None, p.id, self.value - p.balance, p.id)

    def describe(self):
        return f"{self.name} {self.pension_id} to {self.value}"


# ---------------------------------------------------------------- emitters
class PensionCreation(InitialEmitter):
    """INITIAL step (reference ``prepare``): creates the pension."""
    ORDER = Order.INITIAL

    def __init__(self, pension, **kw):
        super().__init__(**kw)
        self.pension = pension

    def emit(self, month, household):
        return (PensionCreated(self.pension),)


class PensionPayment(RecurringEmitter):
    """PENSION_PAY while ``first <= m <= last`` (covered mode included). The payment
    depends only on the month (years from the base date), so it is computed here; a
    payment that rounds to 0 emits nothing (the move would record nothing)."""
    ORDER = Order.PENSION_PAY

    def __init__(self, pension_id, first, last, **kw):
        super().__init__(first, last, **kw)
        self.pension_id = pension_id

    def emit(self, month, household):
        amount = money(household[self.pension_id].payment(household, month))
        if amount:
            yield PensionPaid(self.pension_id, amount)


class PensionRevaluation(RecurringEmitter):
    """REVALUE_PENSIONS every month: to ``value(m)``. Emits nothing when the balance
    already equals the value (e.g. no inflation and no indexing: the value falls exactly
    by each payment)."""
    ORDER = Order.REVALUE_PENSIONS

    def __init__(self, pension_id, **kw):
        super().__init__(**kw)
        self.pension_id = pension_id

    def emit(self, month, household):
        p = household[self.pension_id]
        value = p.value(household, month)
        if value != p.balance:
            yield PensionRevalued(self.pension_id, value)


@item_type("pension")
def compile_pension(item, ctx):
    env = ctx.env
    amount, per = flow_amount(item)
    first, last = flow_window(item, env)          # its owner's retirement (ADR-0061)
    last = min(last, env.end)                     # value counts payments up to the end
    pension = Pension(ctx.id, ctx.name, ctx.ordinal, amount, PER[per], first, last,
                      indexing_rate(item, ctx.household.inflation),
                      item.get("taxable", True), ctx.env.person_of(item))
    return [PensionCreation(pension),
            PensionPayment(ctx.id, first, last),
            PensionRevaluation(ctx.id)]
