"""Real assets (OBJECTS §2.1, §2.2, §4.7, WP3): RealEstate (``property``) and the shared
RealAsset base that Vehicle (holdings/vehicle.py) extends.

Emitters of one asset item (E1, INTERFACES §10), all at the asset's slot:

- Lifecycle (D1): the aggregate does not exist until its ``PurchaseEmitter``
  (Order.ACQUIRE of the purchase month) or, if bought before the horizon, its
  ``CarryInEmitter`` (Order.INITIAL) creates it (events/purchase.py).
- Its sale is a ``sale`` item (events/sale.py; older files' property ``saleDate`` is
  converted to one by upgrade.py). A Sale sets ``sold`` and leaves the balance at 0.00: the asset
  stays in ``opened`` and keeps emitting points; its growth is suppressed only by the zero
  balance.
- ``AppreciationEmitter`` (Order.GROW, every month): only an asset that existed at the
  start of the month (``is_opened``), with a truthy current balance and no newValue
  adjustment this month, emits ``Appreciation``:
  ``APPRECIATION None->asset, opening * monthly rate`` (negative for a vehicle).
"""
from decimal import Decimal

from ..arith import ONE, money, power
from ..base import Aggregate
from ..clock import Order
from ..compiler import item_type
from ..dates import month_index
from ..emitters import RecurringEmitter, ValuationEvent
from ..events.purchase import CarryInEmitter, PurchaseEmitter
from ..rules.capital_gains import NO_CAPITAL_GAINS


class RealAsset(Aggregate):
    """A property or vehicle. Terms are prepared verbatim (reference ``prepare``)."""
    capital_gains = NO_CAPITAL_GAINS     # CapitalGainsRule: no-op (C-M8)

    def __init__(self, id, name, item_index, balance, *, at, amount, value, rate):
        super().__init__(id, name, item_index, balance)
        self.at = at                    # purchase month (kept even if before the start)
        self.amount = amount            # money(price)
        self.value = value              # money(marketValue) or None
        self.rate = rate                # monthly appreciation (negative: depreciation)
        self.sold = False
        self.sale_price = None          # set by its Sale (associated costs, ADR-0067)
        self.fixed_at = None            # month of a newValue market adjustment

    @property
    def report_rate(self):
        return self.rate

    @classmethod
    def terms(cls, item):
        """Reference ``prepare`` for property/vehicle (L744-765), without the sale."""
        if cls.kind == "property":
            rate = power(ONE + Decimal(str(item["annualAppreciation"])), ONE / 12) - 1
        else:
            rate = power(ONE - Decimal(str(item["annualDepreciation"])), ONE / 12) - 1
        worth = item.get("marketValue") if cls.kind == "property" else None
        return {"at": month_index(item["purchaseDate"], ""),
                "amount": money(Decimal(str(item["price"]))),
                "value": money(Decimal(str(worth))) if worth else None,
                "rate": rate}


class RealEstate(RealAsset):
    kind = "property"


class Appreciation(ValuationEvent):
    """Monthly growth of one asset on its opening balance (reference ``growth``)."""

    def __init__(self, asset_id):
        self.asset_id = asset_id
        self.amount = None

    def apply(self, household):
        asset = household[self.asset_id]
        self.amount = household.move("APPRECIATION", None, asset.id,
                                     household.opening[asset.id] * asset.rate, asset.id)

    def describe(self):
        return f"{self.asset_id} grew by {self.amount}"


class AppreciationEmitter(RecurringEmitter):
    """Growth of one asset, every month it existed at the start of the month."""
    ORDER = Order.GROW

    def __init__(self, asset_id, **kw):
        super().__init__(**kw)
        self.asset_id = asset_id

    def emit(self, month, household):
        if not household.is_opened(self.asset_id):
            return None
        asset = household[self.asset_id]
        # A holding sold this month (balance now 0) no longer grows; a newValue market
        # adjustment fixed this month's closing value.
        if asset.balance and asset.fixed_at != month:
            return (Appreciation(asset.id),)
        return None


def compile_real_asset(cls, item, ctx):
    """Emitters of one property/vehicle item: its creation (CarryIn or Purchase) and its
    growth (its sale is a sale item, events/sale.py)."""
    env = ctx.env
    terms = cls.terms(item)

    def make(balance):
        return cls(ctx.id, ctx.name, ctx.ordinal, balance, **terms)

    if terms["at"] < env.start:
        yield CarryInEmitter(env.start, terms["at"], terms["value"] or terms["amount"],
                             terms["rate"], make)
    else:
        yield PurchaseEmitter(terms["at"], make)
    yield AppreciationEmitter(ctx.id)


@item_type("property")
def compile_property(item, ctx):
    return compile_real_asset(RealEstate, item, ctx)
