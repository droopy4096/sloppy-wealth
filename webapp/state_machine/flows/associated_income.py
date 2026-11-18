"""Associated income and associated one-off income — ADR-0068 (proposed).

An associated income names its ``parent``, an income or a pension, and lives exactly as
long as it (ADR-0067 for associated expenses). Taxable, earned income (RRSP room) and
owner are the parent's; like its parent it is not paid in income-less mode for an income
parent, and is paid for a pension parent (pensions are paid in that mode).

- ``associatedIncome`` (recurring, Order.INCOME): its monthly amount is either
  - ``amount`` (+ ``per``, ``indexing``, ``amountIn``), indexed from the parent's start as
    an income (adjustments: a new amount, ADR-0062); or
  - ``annualRate`` of the parent's yearly amount: on the parent's start and on each
    anniversary (an adjustment's month and its anniversaries for a new rate), yearly
    amount x rate / 12.
  ``paid``: ``monthly`` (default) pays that every month; ``lump`` pays the sum of a whole
  period's monthly amounts (``per`` quarter or year) in arrears, on each quarterly or
  yearly anniversary of the parent's start (the last full period's in the month after
  the parent's last month); never in its first month; a partial last period is forfeited.
- ``associatedOneOff`` (one-off, Order.INCOME): ``at`` the parent's start, its end (its
  last month) or a ``paymentDate`` while the parent runs; ``amount``, or ``rate`` x the
  parent's yearly amount in that month.
Ledger: ``INCOME`` None -> cash, source = the associated item.
"""
from decimal import Decimal

from ..arith import ONE, PER, D, flow_amount, indexing_rate, money, power
from ..clock import Order
from ..compiler import item_type
from ..dates import flow_window, month_index
from ..emitters import OneShotEmitter, RecurringEmitter
from ..rules.indexing import IndexingRule
from .adjustment import rate_steps_for, steps_for
from .associated import parent_of
from .income_expense import Income, flow_terms

PARENTS = ("income", "pension")
PAID = ("monthly", "lump")


def parent_window(parent, env):
    """(first, last) payment months of an income or pension parent."""
    first, last = flow_window(parent, env)
    return first, min(last, env.end)


def yearly_amount(parent, env):
    """A function month -> the parent's yearly amount that month (0 outside its window)."""
    first, last = parent_window(parent, env)
    if parent["type"] == "income":
        _, _, base, rule = flow_terms(parent, env)
        return lambda month: (rule.amount(base, month) * 12 if first <= month <= last
                              else Decimal(0))
    hh = env.household
    base, per = flow_amount(parent)
    rate, divisor = indexing_rate(parent, hh.inflation), PER[per]
    return lambda month: (money(base * (ONE + rate) ** ((month - hh.base) // 12) / divisor) * 12
                          if first <= month <= last else Decimal(0))


def tax_terms(parent, env):
    """(taxable, earned, owner) of the parent (ADR-0068 decision 5)."""
    if parent["type"] == "pension":
        return bool(parent.get("taxable", True)), False, env.person_of(parent)
    taxable = parent.get("taxable", False)
    return bool(taxable), bool(parent.get("earnedIncome", taxable)), env.person_of(parent)


def percent_of(anchor, rate, steps, yearly):
    """month -> yearly amount x rate / 12, the yearly amount taken on ``anchor`` and its
    anniversaries (a new rate from an adjustment re-anchors at its month)."""
    def monthly(month):
        r, a = rate, anchor
        for at, new_rate in steps or ():
            if at <= month:
                r, a = new_rate, max(at, anchor)
        taken = a + (month - a) // 12 * 12
        return yearly(taken) * r / 12
    return monthly


def indexed_of(rule, base):
    """month -> the fixed amount's monthly share, unrounded (IndexingRule.amount before
    rounding: a lump is the rounded sum of a period's shares, e.g. 2000 a quarter, not
    3 x 666.67)."""
    def monthly(month):
        anchor, b, divisor = rule.anchor, base, rule.divisor
        for at, new_base, new_divisor in rule.steps or ():
            if at <= month:
                anchor, b, divisor = at, new_base, new_divisor
        return b * (ONE + rule.rate) ** ((month - anchor) // 12) / divisor
    return monthly


# ---------------------------------------------------------------- recurring
class AssociatedIncomeEmitter(RecurringEmitter):
    ORDER = Order.INCOME

    def __init__(self, first, last, monthly, period, tax, covered_too, **kw):
        # A lump is paid in arrears: a period ending in the parent's last month is paid in
        # the month after it.
        super().__init__(first, last if period is None else last + 1, **kw)
        self.anchor = first
        self.monthly = monthly          # month -> that month's share (unrounded)
        self.period = period            # None: paid monthly; 3 or 12: a lump in arrears
        self.tax = tax                  # (taxable, earned, owner)
        self.covered_too = covered_too  # paid in income-less mode (pension parent)

    def amount(self, month):
        if self.period is None:
            return money(self.monthly(month))
        since = month - self.anchor
        if since <= 0 or since % self.period:
            return Decimal(0)
        return money(sum((self.monthly(m) for m in range(month - self.period, month)),
                         Decimal(0)))

    def emit(self, month, household):
        if household.covered and not self.covered_too:
            return None
        amount = self.amount(month)
        if amount == 0:
            return None
        return (Income(amount, *self.tax),)


@item_type("associatedIncome")
def compile_associated_income(item, ctx):
    env = ctx.env
    parent = parent_of(item, env.items)
    first, last = parent_window(parent, env)
    if first is None or first > last:
        return
    if item.get("annualRate"):
        monthly = percent_of(first, D(item["annualRate"]), rate_steps_for(item, env),
                             yearly_amount(parent, env))
    else:
        base, per = flow_amount(item)
        rule = IndexingRule.for_item(item, env.household.inflation, first, PER[per],
                                     steps_for(item, env))
        if item.get("amountIn") == "base" and env.household.inflation:
            base = base * power(ONE + env.household.inflation,
                                Decimal(first - env.household.base) / 12)
        monthly = indexed_of(rule, base)
    period = PER[item.get("per") or "year"] if item.get("paid") == "lump" else None
    if period is not None:
        last = min(last + 1, env.end) - 1      # the month after it, within the horizon
    yield AssociatedIncomeEmitter(first, last, monthly, period, tax_terms(parent, env),
                                  parent["type"] == "pension")


# ---------------------------------------------------------------- one-off
class AssociatedOneOffEmitter(OneShotEmitter):
    ORDER = Order.INCOME

    def __init__(self, month, amount, tax, covered_too, **kw):
        super().__init__(month, **kw)
        self.amount, self.tax, self.covered_too = amount, tax, covered_too

    def emit(self, month, household):
        if household.covered and not self.covered_too:
            return None
        return (Income(self.amount, *self.tax),)


def one_off_month(item, parent, env):
    """The month of an associated one-off income, or None (an end that never comes)."""
    at = item.get("at") or "start"
    if at == "date":
        return month_index(item["paymentDate"], "paymentDate")
    first, last = flow_window(parent, env)
    if first is None:
        return None
    if at == "end":
        return last if parent.get("endDate") else None       # after the horizon: dropped
    return first


@item_type("associatedOneOff")
def compile_associated_one_off(item, ctx):
    env = ctx.env
    parent = parent_of(item, env.items)
    month = one_off_month(item, parent, env)
    first, last = parent_window(parent, env)
    if month is None or first is None or not max(first, env.start) <= month <= min(last, env.end):
        return
    if item.get("rate"):
        amount = money(yearly_amount(parent, env)(month) * D(item["rate"]))
    else:
        amount = money(D(item["amount"]))
    if amount:
        yield AssociatedOneOffEmitter(month, amount, tax_terms(parent, env),
                                      parent["type"] == "pension")

