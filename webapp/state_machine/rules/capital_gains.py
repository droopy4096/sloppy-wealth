"""CapitalGainsRule (OBJECTS §5): a deliberate no-op.

The reference engine taxes no gain on the sale of a property or vehicle (C-M8 gap): the
sale moves the value into cash and nothing reaches the tax step. The rule exists so the
aggregates that would be subject to it (RealEstate, Vehicle; later InvestmentAccount)
reference one place where a future capital-gains treatment plugs in.
"""
from ..base import Rule


class CapitalGainsRule(Rule):
    def on_sale(self, household, asset, proceeds, source):
        """Called by the Sale after the SALE movement. Records nothing, adds no taxable
        income (reference parity, C-M8)."""
        return None


NO_CAPITAL_GAINS = CapitalGainsRule()
