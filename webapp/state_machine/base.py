"""Abstract building blocks: Aggregate (a holding) and Rule.

What happens to aggregates over time is written as emitters and events
(emitters.py, INTERFACES.md §4); the order table lives in clock.py.
"""
from abc import ABC

# Item types that become a holding (an Aggregate in the household). Their order key is
# the holding's *slot*: the index of the first holding item with that id (OBJECTS §1).
HOLDING_TYPES = ("account", "pension", "mortgage", "property", "vehicle")
# A liability's balance is positive when owed: money *from* it raises the balance.
LIABILITIES = ("mortgage",)
# Result group of each holding kind (reference GROUPS).
GROUPS = {"cash": "cash", "property": "property", "vehicle": "property", "mortgage": "debts",
          "account": "investments", "pension": "investments"}


class Aggregate(ABC):
    """A holding: something with a balance that ledger movements change.

    An aggregate is created by an event (D1) and added with ``household.add``; it does
    not exist before. ``item_index`` is its slot (scenario item index; cash is -1) and
    fixes its position in every holdings iteration and in the results.

    Subclasses set the class attribute ``kind`` and override ``report_rate``.
    """
    kind = None          # "cash" | "property" | "vehicle" | "mortgage" | "account" | "pension"
    secured_by = None    # id of the asset securing a loan (Mortgage sets it); see loans_secured_by

    def __init__(self, id, name, item_index, balance):
        self.id = id
        self.name = name
        self.item_index = item_index
        self.balance = balance      # Decimal; never None once the aggregate exists

    @property
    def liability(self):
        return self.kind in LIABILITIES

    @property
    def group(self):
        return GROUPS[self.kind]

    @property
    def report_rate(self):
        """The ``rate`` shown in each holdings point (reference ``h.get("rate")``):
        monthly rate for property, vehicle, mortgage (current, after renewal) and account;
        the annual indexing rate for a pension; None for cash."""
        return None

    def report_extra(self, month):
        """Extra fields of the holdings point after ``month`` (a dict), or None."""
        return None

    def accept_contribution(self, household, amount, source, match):
        """A contribution flow (WP5) paying ``amount`` (already indexed and rounded) into
        this holding; ``source`` is the contribution item id, ``match`` its employer-match
        fraction. Implemented by InvestmentAccount (WP5) and Pension (WP6)."""
        raise NotImplementedError(f"{self.kind} {self.id!r} does not take contributions")

    def _apply(self, delta):
        # Verbatim reference _apply: the sign is flipped in this single place.
        self.balance += -delta if self.liability else delta

    def __repr__(self):
        return f"<{type(self).__name__} {self.id!r} #{self.item_index} balance={self.balance!r}>"


class Rule(ABC):
    """A calculator referenced by aggregates or flows (TaxRule, IndexingRule, ...).
    Stateless, or with small state kept on the household (e.g. the tax pool lives on
    ``household.tax_of(person)``). Rules call arith.py; they never re-derive a formula."""
