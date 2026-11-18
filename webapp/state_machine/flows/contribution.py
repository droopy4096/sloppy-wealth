"""Contribution (``type: "contribution"``) — WP5/E3, OBJECTS §4.4.

A recurring flow into an account or a pension (order CONTRIBUTE, item order). Nothing is
emitted while inactive or while the target does not exist yet; otherwise a
``Contribution`` hands the indexed amount to the target's ``accept_contribution``
(InvestmentAccount here, Pension in WP6/E4).
"""
from ..arith import D, PER, flow_amount, indexing_rate
from ..clock import Order
from ..compiler import item_type
from ..dates import flow_window  # noqa: F401 (withdrawal.py imports it from here)
from ..emitters import FlowEvent, RecurringEmitter
from ..rules.indexing import IndexingRule
from .adjustment import steps_for


class FlowWindowEmitter(RecurringEmitter):
    """A contribution/withdrawal emitter; ``due`` is the reference ``active`` verbatim
    (a missing ``first`` fails exactly as the reference does, unlike ``Window``)."""

    def __init__(self, first, last, **kw):
        super().__init__(first, last, **kw)
        self.first = first
        self.last = last

    def due(self, month):
        return self.first <= month <= self.last


class Contribution(FlowEvent):
    def __init__(self, account, amount, match):
        self.account = account
        self.amount = amount
        self.match = match
        self.note = ""

    def apply(self, household):
        self.note = household[self.account].accept_contribution(
            household, self.amount, self.source, self.match) or ""

    def describe(self):
        return f"contribute {self.amount} -> {self.account} (match {self.match}){self.note}"


class ContributionEmitter(FlowWindowEmitter):
    ORDER = Order.CONTRIBUTE

    def __init__(self, account, first, last, rate, base, divisor, match, **kw):
        super().__init__(first, last, **kw)
        self.account = account
        self.rate = rate
        self.base = base
        self.divisor = divisor
        self.match = match

    def emit(self, month, household):
        if household.get(self.account) is None:     # reference: acct["balance"] is None
            return
        amount = self.rule.amount(self.base, month)
        yield Contribution(self.account, amount, self.match)


@item_type("contribution")
def compile_contribution(item, ctx):
    env = ctx.env
    first, last = flow_window(item, env)
    rate = indexing_rate(item, env.household.inflation)
    amount, per = flow_amount(item)
    emitter = ContributionEmitter(item["account"], first, last, rate, amount, PER[per],
                                  D(item.get("employerMatch") or "0"))
    emitter.rule = IndexingRule(rate, first, PER[per], steps_for(item, env))   # ADR-0062
    yield emitter
