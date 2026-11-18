"""Withdrawal (``type: "withdrawal"``) — WP5/E3, OBJECTS §4.5, reference withdraw()
L938-967.

Order WITHDRAW, item order. One ``WithdrawalEmitter`` per item; the strategy for its
method (and its state: the percent anniversary amount, the annuity amount) lives on the
emitter:
- amount: the indexed amount (anniversary steps from ``first``);
- percent: on the start and each anniversary, ``annualRate / 12`` of the account's
  opening balance of that month, falling back to its *current* balance when it was not
  in ``opened`` (its opening month) and to 0 when it does not exist; re-based every
  active anniversary, even when the account is empty or missing;
- annuity (ADR-0039 amendment 2026-11-11): spends the account down by ``min(last, end)``.
  Set at the first active month with a non-zero balance and re-set on every anniversary of
  ``first`` from the *current* balance (after same-month transfers) and the months left,
  using the account's own return; with ``indexing`` the payment grows by the indexing
  rate each year (an indexed annuity, constant purchasing power), without it the payment
  is level. The final month requests the whole balance. (Older files' ``even`` is
  converted to ``annuity`` by upgrade.py.)
Nothing is emitted while the balance is None or 0; otherwise a ``Withdrawal`` of the
requested amount, which ``apply`` caps at the balance. Its tax is the
jurisdiction's ``on_withdraw`` (ADR-0071).
"""
from decimal import Decimal

from ..arith import D, ONE, PER, flow_amount, indexing_rate, money
from ..clock import Order
from ..compiler import item_type
from ..emitters import FlowEvent
from ..rules.indexing import IndexingRule
from .adjustment import rate_steps_for, steps_for
from .contribution import FlowWindowEmitter, flow_window


class AmountStrategy:
    def __init__(self, base, divisor, steps=None):
        self.base = base
        self.divisor = divisor
        self.steps = steps          # cash flow adjustments (ADR-0062)

    def anniversary(self, flow, household, month, acct):
        pass

    def amount(self, flow, household, month, acct):
        rule = IndexingRule(flow.rate, flow.first, self.divisor, self.steps)
        return rule.amount(self.base, month)


class PercentStrategy:
    def __init__(self, annual_rate, steps=None):
        self.annual_rate = annual_rate
        self.steps = steps          # new rates [(month, rate)] (ADR-0062 amendment)
        self.monthly = None         # reference f.get("monthly") absent

    def anniversary(self, flow, household, month, acct):
        rate, anchor = self.annual_rate, flow.first
        for at, new_rate in self.steps or ():
            if at <= month:         # re-set in its month and on its anniversaries
                rate, anchor = new_rate, max(at, flow.first)
        if (month - anchor) % 12 == 0:
            current = acct.balance if acct is not None else None
            balance = household.opening.get(flow.account, current) or Decimal(0)
            self.monthly = money(balance * rate / 12)

    def amount(self, flow, household, month, acct):
        # Started before the horizon and not on an anniversary yet: Decimal(0).
        return Decimal(0) if self.monthly is None else self.monthly


def annuity_factor(r, g, n):
    """Present value at monthly rate ``r`` of n end-of-month payments of 1 that grow by
    ``g`` after every 12 payments (a growing annuity; g = 0 is the level annuity):
    v = 1/(1+r), a12 = (1-v^12)/r, q = (1+g)v^12, n = 12Y + s,
    F = a12 (1-q^Y)/(1-q) + q^Y (1-v^s)/r; r = 0 and q = 1 are the limits."""
    years, stub = divmod(n, 12)
    if r == 0:
        a12, tail = Decimal(12), Decimal(stub)
        q = ONE + g
    else:
        v = ONE / (ONE + r)
        a12 = (ONE - v ** 12) / r
        tail = (ONE - v ** stub) / r
        q = (ONE + g) * v ** 12
    geometric = Decimal(years) if q == 1 else (ONE - q ** years) / (ONE - q)
    return a12 * geometric + q ** years * tail


class AnnuityStrategy:
    def __init__(self):
        self.monthly = None         # set at the first month with a balance, then yearly

    def anniversary(self, flow, household, month, acct):
        pass

    def amount(self, flow, household, month, acct):
        final = min(flow.last, household.end)
        if month >= final:
            return acct.balance                 # the final month empties the account
        if self.monthly is None or (month - flow.first) % 12 == 0:
            factor = annuity_factor(acct.rate, flow.rate, final - month + 1)
            self.monthly = money(acct.balance / factor)
        return self.monthly


class Withdrawal(FlowEvent):
    """WITHDRAWAL of ``requested``, capped at the account's balance when applied."""

    def __init__(self, account, requested):
        self.account = account
        self.requested = requested

    def apply(self, household):
        acct = household.get(self.account)
        if acct is None or not acct.balance:
            return
        amt = household.move("WITHDRAWAL", acct.id, "cash", min(self.requested, acct.balance),
                             self.source)
        household.jurisdiction.on_withdraw(household, acct, amt)       # ADR-0071
        household.jurisdiction.limits.note_withdrawal(household, acct, amt)   # ADR-0060

    def describe(self):
        return f"withdraw {self.requested} (capped at balance) {self.account} -> cash"


class WithdrawalEmitter(FlowWindowEmitter):
    ORDER = Order.WITHDRAW

    def __init__(self, account, first, last, rate, strategy, **kw):
        super().__init__(first, last, **kw)
        self.account = account
        self.rate = rate
        self.strategy = strategy

    def emit(self, month, household):
        # Strategy decisions (anniversary re-base, annuity amount) read the state at emit
        # time, which is the state the event is applied to (the runner applies it next).
        acct = household.get(self.account)
        self.strategy.anniversary(self, household, month, acct)
        if acct is None or not acct.balance:
            return
        yield Withdrawal(self.account, self.strategy.amount(self, household, month, acct))


@item_type("withdrawal")
def compile_withdrawal(item, ctx):
    env = ctx.env
    first, last = flow_window(item, env)
    rate = indexing_rate(item, env.household.inflation)
    method = item["method"]
    if method == "amount":
        amount, per = flow_amount(item)
        strategy = AmountStrategy(amount, PER[per], steps_for(item, env))
    elif method == "percent":
        strategy = PercentStrategy(D(item["annualRate"]), rate_steps_for(item, env))
    else:                           # annuity
        strategy = AnnuityStrategy()
    yield WithdrawalEmitter(item["account"], first, last, rate, strategy)
