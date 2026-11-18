"""Sale of a property or vehicle (OBJECTS §3.6, WP3; emitters E1, D-E1, D-E3).

The sale comes from a ``sale`` item (``property`` = asset id; ``saleDate``, its own or
set by a trigger, ADR-0065) or, in older files, from the property's own ``saleDate``.
``SaleEmitter`` is a modifier of the asset (D-E1, ``AT_HOST``): Order.SELL at the asset's
slot, as the reference loops over holdings. The sale item's factory yields it; a legacy
property ``saleDate`` is yielded by the property's own factory (holdings/real_estate.py).
``env.sales`` (exactly one sale per asset, else ValueError) decides which one exists.

Events (reference L871-887), source = the sale id (sale item id, else the asset id):

- ``Sale`` (lifecycle): [SALE_PRICE_DIFFERENCE None->asset, salePrice - balance],
  SALE asset->cash (the balance), the CapitalGainsRule (no-op); the price is kept on the
  asset (``sale_price``) for associated costs at its sale (selling costs, ADR-0067; older
  files' ``sellingCostRate`` is converted to one by upgrade.py). Follow-ups (D-E3),
  applied immediately in this order:
- ``LoanPayoff`` (lifecycle), one per existing loan secured by the asset with a truthy
  balance (holdings order): the loan settles itself (``Mortgage.pay_off``, LOAN_PAYOFF).
- ``SalePenalty`` (flow): PENALTY cash->None.
"""
from decimal import Decimal

from ..arith import money
from ..clock import Order
from ..compiler import item_type
from ..dates import month_index
from ..emitters import FlowEvent, LifecycleEvent, ModifierEmitter, Once

REAL_ASSET_TYPES = ("property", "vehicle")


# ---------------------------------------------------------------- events
class Sale(LifecycleEvent):
    def __init__(self, asset_id, sale_price, penalty):
        self.asset_id = asset_id
        self.sale_price = sale_price        # money or None (sell at the current value)
        self.penalty = penalty              # unrounded; None: by the loans' terms
        self.price = None

    def apply(self, household):
        asset = household[self.asset_id]
        penalty = self.penalty
        if penalty is None:                 # no manual penalty: the loans' terms (ADR-0073)
            penalty = sum((loan.penalty_at(household.month)
                           for loan in household.loans_secured_by(asset.id)
                           if loan.balance and hasattr(loan, "penalty_at")), Decimal(0))
        if self.sale_price is not None:
            household.move("SALE_PRICE_DIFFERENCE", None, asset.id,
                           self.sale_price - asset.balance, self.source)
        price = self.price = asset.sale_price = asset.balance
        asset.sold = True
        household.move("SALE", asset.id, "cash", price, self.source)
        asset.capital_gains.on_sale(household, asset, price, self.source)
        return ([LoanPayoff(loan.id) for loan in household.loans_secured_by(asset.id)
                 if loan.balance]
                + [SalePenalty(penalty)])

    def describe(self):
        return f"{self.asset_id} sold for {self.price}"


class LoanPayoff(LifecycleEvent):
    """A loan secured by the sold asset settles itself from cash."""

    def __init__(self, loan_id):
        self.loan_id = loan_id
        self.amount = None

    def apply(self, household):
        self.amount = household[self.loan_id].pay_off(household, self.source)

    def describe(self):
        return f"{self.loan_id} paid off ({self.amount})"


class SalePenalty(FlowEvent):
    def __init__(self, penalty):
        self.penalty = penalty

    def apply(self, household):
        household.move("PENALTY", "cash", None, self.penalty, self.source)

    def describe(self):
        return f"sale penalty {money(self.penalty)}"


# ---------------------------------------------------------------- emitter
class SaleEmitter(ModifierEmitter):
    """The sale of an asset: Order.SELL at the asset's slot."""
    ORDER = Order.SELL

    def __init__(self, month, asset_id, sale_price, penalty, **kw):
        super().__init__(asset_id, Once(month), **kw)
        self.sale_price, self.penalty = sale_price, penalty

    @classmethod
    def from_item(cls, sale, asset_id):
        """Verbatim reference ``prepare`` (L760-765) for the sale attached to an asset;
        source = the sale id (sale item id, else the asset id)."""
        return cls(month_index(sale["saleDate"], "saleDate"), asset_id,
                   money(Decimal(str(sale["salePrice"]))) if sale.get("salePrice") else None,
                   # Blank: the penalty of the loans' terms (ADR-0073), 0 without one.
                   None if sale.get("salePenalty") in (None, "")
                   else Decimal(str(sale["salePenalty"])),
                   source=sale.get("id") or asset_id)

    def emit(self, month, household):
        return (Sale(self.host, self.sale_price, self.penalty),)


def sells_real_asset(env, asset_id):
    """True if ``asset_id``'s compiled (owner) item is a property or vehicle: the
    reference sold only holdings it looped over."""
    owner = env.owner.get(asset_id)
    return owner is not None and env.items[owner]["type"] in REAL_ASSET_TYPES


@item_type("sale")
def compile_sale(item, ctx):
    """The sale of an asset (a modifier placed at the asset's slot). A sale item without
    a date never fires. A dated one (its date may come from a trigger, ADR-0065) is the
    asset's only sale: ``dates.property_sales`` raised on a second one."""
    asset_id = item.get("property")
    if item.get("saleDate") and sells_real_asset(ctx.env, asset_id):
        yield SaleEmitter.from_item(item, asset_id)
