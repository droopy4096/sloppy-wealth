"""Transfer (``type: "transfer"``) — WP5/E3, OBJECTS §3.9: a one-off TRANSFER from cash
into an account at order TRANSFER (after the month's sales), on its transferDate or in
the retirement month (resolved at compile time). Always from cash, also when expenses
are covered; a deduction where the jurisdiction says so (``on_contribute``, ADR-0071).
"""
from ..arith import D, money
from ..clock import Order
from ..compiler import item_type
from ..dates import month_index
from ..emitters import FlowEvent, OneShotEmitter
from ..jurisdictions import capped_note


class Transfer(FlowEvent):
    def __init__(self, account, amount):
        self.account = account
        self.amount = amount
        self.note = ""

    def apply(self, household):
        acct = household[self.account]
        amount = household.jurisdiction.limits.cap(household, acct, self.amount)  # ADR-0060
        self.note = capped_note(self.amount, amount)
        household.move("TRANSFER", "cash", acct.id, amount, self.source)
        household.jurisdiction.on_contribute(household, acct, money(amount), self.source)

    def describe(self):
        return f"transfer {self.amount} cash -> {self.account}{self.note}"


class TransferEmitter(OneShotEmitter):
    ORDER = Order.TRANSFER

    def __init__(self, account, month, amount, **kw):
        super().__init__(month, **kw)
        self.account = account
        self.amount = amount

    def emit(self, month, household):
        return (Transfer(self.account, self.amount),)


@item_type("transfer")
def compile_transfer(item, ctx):
    at = month_index(item["transferDate"], "transferDate")   # may come from a trigger
    yield TransferEmitter(item["account"], at, money(D(item["amount"])))
