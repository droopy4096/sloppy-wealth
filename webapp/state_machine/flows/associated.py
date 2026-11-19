"""Associated expense and associated cost — ADR-0067 (proposed).

An associated item names its ``parent`` (any item with a lifetime) and lives exactly as
long as it; no dates of its own (an associated cost on a ``date`` excepted).

- ``associatedExpense`` (recurring, Order.EXPENSE, item order): paid every month from the
  parent's start to its end. A holding parent (property, vehicle, account, mortgage) is
  also checked each month: it must exist, not be sold, and a mortgage must still be owed.
  Not paid in income-less mode (like expenses). The amount is either
  - ``amount`` (+ ``per``, ``indexing``, ``amountIn``) as an expense, indexed from the
    parent's start (adjustments: a new amount, ADR-0062); or
  - ``annualRate`` of a ``basis`` looked up from the parent: on the first month and on
    each anniversary of the parent's start, basis x rate / 12 for the next 12 months (as
    percent withdrawals, ADR-0049); an adjustment gives a new rate from its month.
- ``associatedCost`` (one-off, Order.EXPENSE): ``at`` the parent's start, its end (an
  asset's sale month, a recurring item's last month, a mortgage's property sale) or on a
  ``costDate`` while the parent exists. ``amount``, or ``rate`` x the basis in that month
  (computed when applied: the sale price at a sale). Paid also in income-less mode (it
  belongs to a purchase or sale).

Bases per parent type (``BASES``): property / vehicle: ``value`` (its value at the start
of the month; at its sale, the sale price) or ``price``; account: ``balance``; mortgage:
``principal`` or ``balance``; income: ``amount`` (its yearly amount that month).
Ledger: ``EXPENSE`` / ``COST`` cash -> None, source = the associated item.
"""
from decimal import Decimal

from ..arith import ONE, PER, D, flow_amount, money, power
from ..clock import Order
from ..compiler import item_type
from ..dates import flow_window, month_index
from ..emitters import FlowEvent, OneShotEmitter, RecurringEmitter
from ..rules.indexing import IndexingRule
from .adjustment import rate_steps_for, steps_for
from .income_expense import Expense

ASSETS = ("property", "vehicle")
HOLDINGS = ASSETS + ("account", "mortgage")
RECURRING = ("income", "expense", "contribution", "withdrawal", "pension", "extraPayment")
PARENTS = HOLDINGS + RECURRING + ("associatedExpense",)
BASES = {"property": ("value", "price"), "vehicle": ("value", "price"),
         "account": ("balance",), "mortgage": ("principal", "balance"),
         "income": ("amount",)}
AT = ("start", "end", "date")


def parent_of(item, items):
    return next((i for i in items if i.get("id") == item.get("parent")), None)


def lifetime(parent, env):
    """(first, last) months of a parent's life (last: the horizon end if it does not end
    by date; holdings are also checked at run time), first None if it never starts."""
    kind = parent["type"]
    if kind in ASSETS:
        return month_index(parent["purchaseDate"], "purchaseDate"), env.end
    if kind == "account":
        opened = parent.get("openedDate")
        return (month_index(opened, "openedDate") if opened else env.start), env.end
    if kind == "mortgage":
        start = parent.get("startDate") or env.assets.get(parent.get("property"), {}).get(
            "purchaseDate")
        return (month_index(start, "startDate") if start else None), env.end
    if kind == "associatedExpense":
        grand = parent_of(parent, env.items)
        return lifetime(grand, env) if grand else (None, None)
    return flow_window(parent, env)


def end_month(parent, env):
    """The month a parent ends (for a cost at its end), or None if it does not end."""
    kind = parent["type"]
    if kind in ASSETS:
        sale = env.sales.get(parent.get("id"))
        return month_index(sale["saleDate"], "saleDate") if sale else None
    if kind == "mortgage":
        sale = env.sales.get(parent.get("property"))
        return month_index(sale["saleDate"], "saleDate") if sale else None
    if kind == "account":
        return None
    if kind == "associatedExpense":
        grand = parent_of(parent, env.items)
        return end_month(grand, env) if grand else None
    if not parent.get("endDate"):
        return None
    return flow_window(parent, env)[1]


def alive(parent, household):
    """A holding parent exists this month (not sold; a mortgage still owed)."""
    if parent["type"] not in HOLDINGS:
        return True
    h = household.get(parent.get("id"))
    if h is None:
        return False
    if parent["type"] in ASSETS:
        return not h.sold
    if parent["type"] == "mortgage":
        return h.balance is not None and h.balance > 0
    return h.balance is not None


def basis_reader(item, parent, env):
    """A function (household, month) -> the basis value (unrounded), for a percentage."""
    basis = item.get("basis")
    pid = parent.get("id")
    if basis == "price":
        price = D(parent["price"])
        return lambda household, month: price
    if basis == "principal":
        principal = D(parent["principal"])
        return lambda household, month: principal
    if basis == "amount":
        from .income_expense import flow_terms
        first, last, base, rule = flow_terms(parent, env)
        return lambda household, month: (rule.amount(base, month) * 12
                                         if first <= month <= last else Decimal(0))

    def current(household, month):           # value or balance
        h = household.get(pid)
        if h is None:
            return Decimal(0)
        if getattr(h, "sale_price", None) is not None and h.sold:
            return h.sale_price               # at its sale: the sale price
        opening = household.opening.get(pid)
        return opening if opening is not None else (h.balance or Decimal(0))
    return current


# ---------------------------------------------------------------- expense
class AssociatedExpenseEmitter(RecurringEmitter):
    ORDER = Order.EXPENSE

    def __init__(self, first, last, parent, amount, **kw):
        super().__init__(first, last, **kw)
        self.anchor = first
        self.parent = parent
        self.amount = amount            # (household, month) -> the month's amount

    def emit(self, month, household):
        if household.covered or not alive(self.parent, household):
            return None
        amount = self.amount(household, month)
        if amount == 0:
            return None
        return (Expense(amount),)


class YearlyPercent:
    """basis x rate / 12, re-set on the first month and each anniversary of ``anchor``;
    a new rate (adjustment) re-sets it in its month and its anniversaries."""

    def __init__(self, anchor, rate, steps, basis):
        self.anchor, self.rate, self.steps, self.basis = anchor, rate, steps, basis
        self.monthly = None

    def __call__(self, household, month):
        rate, anchor = self.rate, self.anchor
        for at, new_rate in self.steps or ():
            if at <= month:
                rate, anchor = new_rate, max(at, self.anchor)
        if self.monthly is None or (month - anchor) % 12 == 0:
            self.monthly = money(self.basis(household, month) * rate / 12)
        return self.monthly


@item_type("associatedExpense")
def compile_associated_expense(item, ctx):
    env = ctx.env
    parent = parent_of(item, env.items)
    first, last = lifetime(parent, env)
    if first is None:
        return
    if item.get("annualRate"):
        amount = YearlyPercent(first, D(item["annualRate"]), rate_steps_for(item, env),
                               basis_reader(item, parent, env))
    else:
        base, per = flow_amount(item)
        rule = IndexingRule.for_item(item, env.household.inflation, first, PER[per],
                                     steps_for(item, env))
        if item.get("amountIn") == "base" and env.household.inflation:
            base = base * power(ONE + env.household.inflation,
                                Decimal(first - env.household.base) / 12)
        amount = lambda household, month: rule.amount(base, month)
    yield AssociatedExpenseEmitter(first, last, parent, amount)


# ---------------------------------------------------------------- cost
class Cost(FlowEvent):
    """COST cash -> None: a fixed amount, or rate x the basis when applied."""

    def __init__(self, amount, rate, basis, month):
        self.fixed, self.rate, self.basis, self.month = amount, rate, basis, month
        self.amount = None

    def apply(self, household):
        value = self.fixed if self.rate is None else self.basis(household, self.month) * self.rate
        self.amount = household.move("COST", "cash", None, value, self.source)

    def describe(self):
        return f"cost {self.amount}"


class AssociatedCostEmitter(OneShotEmitter):
    ORDER = Order.EXPENSE

    def __init__(self, month, parent, cost, at, **kw):
        super().__init__(month, **kw)
        self.parent, self.cost, self.at = parent, cost, at

    def emit(self, month, household):
        h = household.get(self.parent.get("id")) if self.parent["type"] in HOLDINGS else None
        if self.at == "end" and self.parent["type"] in ASSETS:
            if h is None or not h.sold:
                return None             # sold this month (the sale runs earlier)
        elif not alive(self.parent, household):
            return None
        rate, amount, basis = self.cost
        return (Cost(amount, rate, basis, month),)


def cost_month(item, parent, env):
    at = item.get("at") or "start"
    if at == "date":
        return month_index(item["costDate"], "costDate")
    if at == "end":
        return end_month(parent, env)
    return lifetime(parent, env)[0]


@item_type("associatedCost")
def compile_associated_cost(item, ctx):
    env = ctx.env
    parent = parent_of(item, env.items)
    month = cost_month(item, parent, env)
    if month is None or not env.start <= month <= env.end:
        return
    first, last = lifetime(parent, env)
    if first is None or not first <= month <= max(last, month if item.get("at") == "end" else last):
        return
    if item.get("rate"):
        cost = (D(item["rate"]), None, basis_reader(item, parent, env))
    else:
        cost = (None, money(D(item["amount"])), None)
    yield AssociatedCostEmitter(month, parent, cost, item.get("at") or "start")
