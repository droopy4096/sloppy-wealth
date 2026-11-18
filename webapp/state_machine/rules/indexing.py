"""IndexingRule (WP7, OBJECTS §5): a flow's yearly step-up, anchored at a start month.

A thin object over ``arith.indexed`` / ``arith.indexing_rate``; the arithmetic itself is
never re-derived here (``indexed`` is the reference expression verbatim).
"""
from ..arith import indexed, indexing_rate
from ..base import Rule


class IndexingRule(Rule):
    """Annual ``rate`` applied once a year on the anniversary of ``anchor`` (a month
    index); ``divisor`` spreads a quarterly (3) or yearly (12) amount over the months."""

    def __init__(self, rate, anchor, divisor=1, steps=None):
        self.rate = rate
        self.anchor = anchor
        self.divisor = divisor
        # Cash flow adjustments (ADR-0062): [(month, new base, divisor)] in month order,
        # from flows/adjustment.steps_for; None without adjustments.
        self.steps = steps

    @classmethod
    def for_item(cls, item, inflation, anchor, divisor=1, steps=None):
        """The rate from the item's ``indexing``/``indexRate`` (reference resolution)."""
        return cls(indexing_rate(item, inflation), anchor, divisor, steps)

    def amount(self, base, month):
        """Reference ``indexed(base, rate, m - first, divisor)`` (rounded to cents). With
        adjustments: from the last one at or before ``month``, indexed from its month."""
        anchor, divisor = self.anchor, self.divisor
        for at, new_base, new_divisor in self.steps or ():
            if at <= month:
                anchor, base, divisor = at, new_base, new_divisor
        return indexed(base, self.rate, month - anchor, divisor)

    def __repr__(self):
        return f"<IndexingRule rate={self.rate!r} anchor={self.anchor} /{self.divisor}>"
