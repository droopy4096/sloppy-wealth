"""Market adjustment of a property's value (OBJECTS §3.5, WP3; emitters E1).

``MarketAdjustmentEmitter``: a modifier of the property (D-E1) at Order.ADJUST (after the
month's improvements), placed at its *own* item index (``AT_HOST = False``). Either a
percentage of the current balance, applied before the month's growth, or a new value that
is the month's closing value: the property's ``fixed_at`` is set to the month, which
suppresses that month's APPRECIATION (reference L862-870). One
``MARKET_ADJUSTMENT None->property``, its amount resolved from the balance in ``apply``.
"""
from decimal import Decimal

from ..arith import money
from ..clock import Order
from ..compiler import item_type
from ..dates import month_index
from ..emitters import ModifierEmitter, Once, ValuationEvent


class MarketAdjustment(ValuationEvent):
    def __init__(self, month, property, percent, new_value):
        self.month, self.property = month, property
        self.percent, self.new_value = percent, new_value

    def apply(self, household):
        asset = household[self.property]
        if self.percent is not None:
            change = asset.balance * self.percent
        else:
            change = self.new_value - asset.balance
            asset.fixed_at = self.month
        household.move("MARKET_ADJUSTMENT", None, asset.id, change, self.source)

    def describe(self):
        if self.percent is not None:
            return f"{self.property} value changed by {self.percent * 100}%"
        return f"{self.property} value set to {self.new_value} (no growth this month)"


class MarketAdjustmentEmitter(ModifierEmitter):
    ORDER = Order.ADJUST
    AT_HOST = False

    def __init__(self, month, property, percent, new_value, **kw):
        super().__init__(property, Once(month), **kw)
        self.percent, self.new_value = percent, new_value

    def emit(self, month, household):
        return (MarketAdjustment(month, self.host, self.percent, self.new_value),)


@item_type("marketAdjustment")
def compile_market_adjustment(item, ctx):
    yield MarketAdjustmentEmitter(
        month_index(item["adjustmentDate"], "adjustmentDate"), item["property"],
        Decimal(str(item["percent"])) if item.get("percent") else None,
        money(Decimal(str(item["newValue"]))) if item.get("newValue") else None)
