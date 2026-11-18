"""Cash balance reconciliation (``type: "cashBalance"``) — ADR-0063.

``CashBalanceEmitter`` (order CASH_BALANCE: after the tax step, before the results row;
at its own item index) fires once, in the month of ``balanceDate``, and emits a
``CashReconciled`` event that sets cash to ``balance``: the difference is one
``CASH_RECONCILIATION`` movement from outside (cash was low) or to outside (cash was
high). Not income, not taxable. Several in one month: each sets the balance again, so the
last in item order wins.
"""
from decimal import Decimal

from ..arith import money
from ..clock import Order
from ..compiler import item_type
from ..dates import month_index
from ..emitters import OneShotEmitter, ValuationEvent

ORDER_CASH_BALANCE = Order.TAX + 50


class CashReconciled(ValuationEvent):
    def __init__(self, balance):
        self.balance = balance
        self.before = None

    def apply(self, household):
        self.before = household.cash.balance
        diff = self.balance - self.before
        if diff > 0:
            household.move("CASH_RECONCILIATION", None, "cash", diff, self.source)
        elif diff < 0:
            household.move("CASH_RECONCILIATION", "cash", None, -diff, self.source)

    def describe(self):
        diff = self.balance - self.before
        sign = "+" if diff >= 0 else "-"
        return f"cash set to {self.balance} (was {self.before}, {sign}{abs(diff)})"


class CashBalanceEmitter(OneShotEmitter):
    ORDER = ORDER_CASH_BALANCE

    def __init__(self, month, balance, **kw):
        super().__init__(month, **kw)
        self.balance = balance

    def emit(self, month, household):
        return (CashReconciled(self.balance),)


@item_type("cashBalance")
def compile_cash_balance(item, ctx):
    yield CashBalanceEmitter(month_index(item["balanceDate"], "balanceDate"),
                             money(Decimal(str(item["balance"]))))
