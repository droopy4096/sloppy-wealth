"""Improvement of a property (OBJECTS §3.4, WP3; emitters E1): construction or renovation.

``ImprovementEmitter``: a modifier of the property (D-E1) at Order.IMPROVE, placed at its
*own* item index (``AT_HOST = False``: the reference loops improvement items there, not
holdings). ``Improvement`` records ``IMPROVEMENT cash->property, cost``; its follow-up
``Revaluation`` records ``REVALUATION None->property, valueAdded - cost`` (reference
L856-859). Amounts are prepared verbatim (L680-686): ``valueAdded`` falls back to the
cost on a falsy raw value (numeric 0 included).
"""
from decimal import Decimal

from ..arith import money
from ..clock import Order
from ..compiler import item_type
from ..dates import month_index
from ..emitters import FlowEvent, ModifierEmitter, Once
from .purchase import Revaluation


class Improvement(FlowEvent):
    """Pays the cost of an improvement from cash into the property."""

    def __init__(self, property, cost, value_added):
        self.property, self.cost, self.value_added = property, cost, value_added

    def apply(self, household):
        household.move("IMPROVEMENT", "cash", self.property, self.cost, self.source)
        return [Revaluation(self.property, self.value_added - self.cost)]

    def describe(self):
        return f"{self.property} improved: cost {self.cost}, value added {self.value_added}"


class ImprovementEmitter(ModifierEmitter):
    ORDER = Order.IMPROVE
    AT_HOST = False

    def __init__(self, month, property, cost, value_added, **kw):
        super().__init__(property, Once(month), **kw)
        self.cost, self.value_added = cost, value_added

    def emit(self, month, household):
        return (Improvement(self.host, self.cost, self.value_added),)


@item_type("improvement")
def compile_improvement(item, ctx):
    cost = money(Decimal(str(item["cost"])))
    added = item.get("valueAdded")
    yield ImprovementEmitter(month_index(item["improvementDate"], "improvementDate"),
                             item["property"], cost,
                             money(Decimal(str(added))) if added else cost)
