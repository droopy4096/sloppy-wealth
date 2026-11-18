"""Cash (WP0): the household's own money. May go negative; no rate, no return."""
from ..arith import D, money
from ..base import Aggregate


class Cash(Aggregate):
    kind = "cash"

    def __init__(self, opening_cash):
        # Reference: {"id": "cash", "name": "Cash", "kind": "cash",
        #             "balance": money(Decimal(str(scenario["openingCash"])))}
        super().__init__("cash", "Cash", -1, money(D(opening_cash)))
