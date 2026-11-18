"""Purchase of a property or vehicle (OBJECTS §3.1, WP3; emitters E1, INTERFACES §10).

D1: the purchase *creates* the asset aggregate. Two emitters, at the asset's slot:

- ``PurchaseEmitter`` (Order.ACQUIRE, one-shot) in the purchase month when it lies inside
  the horizon: ``Purchase`` creates the asset with balance 0.00, then
  ``PURCHASE cash->asset, price``; with a truthy market value its follow-up
  ``Revaluation`` records ``REVALUATION None->asset, value - price`` (reference
  ``events`` L840-854).
- ``CarryInEmitter`` (Order.INITIAL) when it was bought before the horizon start:
  ``CarryIn`` creates the asset before the first month at
  ``money(base * (ONE + rate) ** (start - at))``, base = value or price, an *integer*
  power; no movement (reference ``prepare``).

``Revaluation`` is shared with the Improvement (events/improvement.py).
"""
from decimal import Decimal

from ..arith import ONE, money
from ..clock import Order
from ..emitters import InitialEmitter, LifecycleEvent, OneShotEmitter, ValuationEvent


# ---------------------------------------------------------------- events
class Purchase(LifecycleEvent):
    """Creates the asset (balance 0.00) and pays the price from cash."""

    def __init__(self, make):
        self.make = make            # balance -> a new asset aggregate
        self.asset = None

    def apply(self, household):
        asset = self.asset = household.add(self.make(Decimal("0.00")))
        household.move("PURCHASE", "cash", asset.id, asset.amount, asset.id)
        if asset.value:
            return [Revaluation(asset.id, asset.value - asset.amount)]
        return None

    def describe(self):
        if self.asset is None:
            return self.name
        return f"{self.asset.kind} {self.asset.id} bought for {self.asset.amount}"


class Revaluation(ValuationEvent):
    """``REVALUATION None->asset, amount``: the asset's value differs from what was paid
    (market value at purchase, value added by an improvement)."""

    def __init__(self, asset_id, amount):
        self.asset_id, self.amount = asset_id, amount

    def apply(self, household):
        household.move("REVALUATION", None, self.asset_id, self.amount, self.source)

    def describe(self):
        return f"{self.asset_id} revalued by {money(self.amount)}"


class CarryIn(LifecycleEvent):
    """An asset bought before the horizon, carried in at its grown value at the start."""

    def __init__(self, start, at, base, rate, make):
        self.start, self.at, self.base, self.rate, self.make = start, at, base, rate, make
        self.asset = None

    def apply(self, household):
        self.asset = household.add(
            self.make(money(self.base * (ONE + self.rate) ** (self.start - self.at))))

    def describe(self):
        if self.asset is None:
            return self.name
        return (f"{self.asset.kind} {self.asset.id} carried in at {self.asset.balance} "
                f"({self.start - self.at} months after purchase)")


# ---------------------------------------------------------------- emitters
class PurchaseEmitter(OneShotEmitter):
    """The purchase of an asset inside the horizon (asset slot)."""
    ORDER = Order.ACQUIRE

    def __init__(self, month, make, **kw):
        super().__init__(month, **kw)
        self.make = make

    def emit(self, month, household):
        return (Purchase(self.make),)


class CarryInEmitter(InitialEmitter):
    """An asset bought before the horizon start (asset slot, INITIAL step)."""
    ORDER = Order.INITIAL

    def __init__(self, start, at, base, rate, make, **kw):
        super().__init__(**kw)
        self.start, self.at, self.base, self.rate, self.make = start, at, base, rate, make

    def emit(self, month, household):
        return (CarryIn(self.start, self.at, self.base, self.rate, self.make),)
