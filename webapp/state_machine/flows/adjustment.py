"""Adjustment of a cash flow's amount (``type: "adjustment"``) — ADR-0062.

An adjustment names a flow (income, expense, contribution, or a withdrawal with method
amount), an ``adjustmentDate`` and a new ``amount`` (``per``: default the flow's). From
that month the flow's amount is the new amount, in dollars of the adjustment date, indexed
with the flow's own rate in yearly steps counted from the adjustment date. Several
adjustments follow each other; in one month the last in item order wins.

An adjustment of a percent withdrawal, or of an associated expense stated as a
percentage (ADR-0067), gives a new ``annualRate`` instead (amendment 2026-11-11): the withdrawal re-sets its monthly amount from the balance in the
adjustment month and on each anniversary of it (``rate_steps_for``, PercentStrategy).

The steps are known at compile time: the flow's factory asks ``steps_for`` and passes
them to its ``IndexingRule`` (rules/indexing.py), which computes each month's amount.
``AdjustmentEmitter`` only records the change in the event log in its month (a state
event that changes nothing else).
"""
from ..arith import D, PER, flow_amount, money
from ..clock import Order
from ..compiler import item_type
from ..dates import month_index
from ..emitters import OneShotEmitter, StateEvent

ADJUSTABLE = ("income", "expense", "contribution", "withdrawal", "associatedExpense",
              "associatedIncome")
ORDER_ADJUST_FLOW = Order.OPEN + 60       # before income (log only)


def target_of(item, items):
    """The cash flow an adjustment names, or None."""
    return next((i for i in items if i.get("id") == item.get("flow")
                 and i.get("type") in ADJUSTABLE), None)


def new_amount(item, flow, where=""):
    """(amount, per) of an adjustment; ``per`` defaults to its flow's."""
    return flow_amount(dict(item, per=item.get("per") or (flow or {}).get("per")), where)


def steps_for(item, env):
    """Adjustments of the flow ``item`` as [(month, amount, divisor)] in month order (the
    last item in a month wins); None when there are none (or the flow has no id)."""
    if not item.get("id"):
        return None
    by_month = {}
    for adj in env.items:
        if adj.get("type") == "adjustment" and adj.get("flow") == item["id"]:
            amount, per = new_amount(adj, item)
            by_month[month_index(adj["adjustmentDate"], "adjustmentDate")] = (amount, PER[per])
    return [(m, a, d) for m, (a, d) in sorted(by_month.items())] or None


def is_percent(flow):
    """A flow whose adjustments give a new annualRate: a percent withdrawal, or an
    associated expense or income stated as a percentage (ADR-0067, ADR-0068)."""
    return bool(flow) and (
        (flow.get("type") == "withdrawal" and flow.get("method") == "percent")
        or (flow.get("type") in ("associatedExpense", "associatedIncome")
            and bool(flow.get("annualRate"))))


def rate_steps_for(item, env):
    """New annual rates of the percent withdrawal ``item`` as [(month, rate)] in month
    order (the last item in a month wins); None when there are none."""
    if not item.get("id"):
        return None
    by_month = {month_index(adj["adjustmentDate"], "adjustmentDate"): D(adj["annualRate"])
                for adj in env.items
                if adj.get("type") == "adjustment" and adj.get("flow") == item["id"]}
    return sorted(by_month.items()) or None


class FlowAdjusted(StateEvent):
    def __init__(self, flow, amount, per):
        self.flow, self.amount, self.per = flow, amount, per

    def apply(self, household):
        pass        # the new amount is resolved by the flow (compile-time steps)

    def describe(self):
        if self.per is None:
            return f"{self.flow} annual rate set to {self.amount * 100}%"
        return f"{self.flow} amount set to {money(self.amount)} per {self.per}"


class AdjustmentEmitter(OneShotEmitter):
    ORDER = ORDER_ADJUST_FLOW

    def __init__(self, month, flow, amount, per, **kw):
        super().__init__(month, **kw)
        self.flow, self.amount, self.per = flow, amount, per

    def emit(self, month, household):
        return (FlowAdjusted(self.flow, self.amount, self.per),)


@item_type("adjustment")
def compile_adjustment(item, ctx):
    flow = target_of(item, ctx.env.items)
    if is_percent(flow):
        amount, per = D(item["annualRate"]), None        # a new rate (amendment)
    else:
        amount, per = new_amount(item, flow)
    yield AdjustmentEmitter(month_index(item["adjustmentDate"], "adjustmentDate"),
                            item["flow"], amount, per)
