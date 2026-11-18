"""Canada: RESP accounts and the Canada Education Savings Grant (ADR-0072).

An ``resp`` account is one beneficiary's plan. Money put in (a contribution or a one-off
transfer) is capped at the lifetime contribution limit ($50,000, less ``contributedSoFar``)
by ``RoomLimits.cap``, and brings the CESG through ``Canada.on_contribute``: a ``GRANT``
movement from outside into the account, 20% of the amount, limited by

- the grant room: $500 for each calendar year from the horizon's first year, plus
  ``unusedGrantRoom`` (room not used before the horizon);
- $1,000 of grant in a calendar year;
- $7,200 over the account's life, less ``grantReceived``.

An opening balance from outside is the existing balance: no grant, no limit. State lives
in ``household.ext["resp"]`` (account id -> ``Plan``), made on first use.
"""
from decimal import Decimal

from ...arith import D, money

KEY = "resp"
RATE = Decimal("0.20")
YEARLY_ROOM = Decimal(500)
YEARLY_MAX = Decimal(1000)
LIFETIME_GRANT = Decimal(7200)
LIFETIME_CONTRIBUTIONS = Decimal(50000)
FIELDS = ("unusedGrantRoom", "grantReceived", "contributedSoFar")


def _amount(extra, field):
    return D(extra.get(field) or "0")


class Plan:
    """One RESP account's grant room and lifetime totals."""

    def __init__(self, extra, first_year):
        self.room = _amount(extra, "unusedGrantRoom")      # before the first year's $500
        self.granted = _amount(extra, "grantReceived")
        self.contributed = _amount(extra, "contributedSoFar")
        self.year = first_year - 1                          # last year whose room was added
        self.paid = {}                                      # calendar year -> grant paid

    def to_year(self, year):
        while self.year < year:
            self.year += 1
            self.room += YEARLY_ROOM

    def contribution_left(self):
        return max(Decimal(0), LIFETIME_CONTRIBUTIONS - self.contributed)

    def grant(self, year, amount):
        """The grant on ``amount`` contributed in ``year`` (and use it up)."""
        self.to_year(year)
        grant = min(money(amount * RATE), self.room, YEARLY_MAX - self.paid.get(year, 0),
                    LIFETIME_GRANT - self.granted)
        grant = max(Decimal(0), grant)
        self.room -= grant
        self.granted += grant
        self.paid[year] = self.paid.get(year, Decimal(0)) + grant
        return grant


def plan(household, account):
    plans = household.ext.setdefault(KEY, {})
    if account.id not in plans:
        plans[account.id] = Plan(getattr(account, "extra", {}) or {}, household.start // 12)
    return plans[account.id]


def cap(household, account, amount):
    """The part of ``amount`` within the lifetime contribution limit (and count it)."""
    p = plan(household, account)
    allowed = max(Decimal(0), min(amount, p.contribution_left()))
    p.contributed += money(allowed)
    return allowed


def pay_grant(household, account, amount, source):
    """The CESG on ``amount`` put into ``account``: a GRANT movement from outside."""
    if amount <= 0:
        return
    grant = plan(household, account).grant(household.month // 12, amount)
    if grant:
        household.move("GRANT", None, account.id, grant, source)
