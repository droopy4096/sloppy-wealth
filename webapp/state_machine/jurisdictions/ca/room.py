"""Canada: contribution room (``type: "contributionRoom"``) — ADR-0060; Canada's
``ContributionLimits`` (ADR-0071).

One item per account type (rrsp | tfsa) holds the room available in the month of
``roomAsOfDate`` and the yearly rules. All accounts of that type share the room.

- ``RoomStartEmitter`` (order ROOM, in the as-of month): the room becomes ``room``.
  Before that month nothing is checked.
- ``RoomYearEmitter`` (order ROOM, every January after the as-of month): adds the new
  room. RRSP: min(incomeRate x the previous calendar year's earned income, the year's
  maximum). TFSA: the year's maximum plus the previous year's TFSA withdrawals.
  The year's maximum is ``yearlyMax`` indexed from ``maxYear`` (indexing field) and
  rounded as CRA does: TFSA to the nearest $500, RRSP to the nearest $10.
- ``RoomLimits.cap`` (through ``household.jurisdiction.limits``) is called by every movement that uses room (contribution
  incl. employer match, transfer, opening balance moved from cash): it returns the part
  within the room and uses it up; the excess stays where it was (cash, or not paid for a
  match).
- Earned income (income items with ``earnedIncome``, default = taxable) and TFSA
  withdrawals are counted per calendar year by ``note_earned`` / ``note_withdrawal``.

Per person (ADR-0061): the room is keyed by (person, account type). A room item
belongs to its ``owner``; a movement into an account uses its contributor's room (the
owner, or a spousal RRSP's contributor); earned income counts for the income's owner,
TFSA withdrawals for the account owner. ``remaining`` reports the household total per
type.

State lives in ``household.ext["contribution_room"]`` (only when the scenario has a
contributionRoom item); without it nothing is capped and results are unchanged.
"""
from decimal import ROUND_HALF_UP, Decimal

from ...arith import D, ONE, indexing_rate, money
from ...clock import Order
from ...compiler import item_type
from ...dates import month_index
from ...emitters import OneShotEmitter, RecurringEmitter, StateEvent
from .. import ContributionLimits

KEY = "contribution_room"
ROOM_TYPES = ("rrsp", "tfsa")
ROUNDING = {"rrsp": Decimal(10), "tfsa": Decimal(500)}
DEFAULT_INCOME_RATE = Decimal("0.18")
# After the core OPEN step and the retirement event, before income (order 100).
ORDER_ROOM = Order.OPEN + 50


def year_of(month):
    return month // 12


class RoomType:
    """The room of one account type of one person."""

    def __init__(self, account_type, item, inflation, person=None, label=""):
        self.account_type = account_type
        self.person = person
        self.label = label              # the person's name with several persons, else ""
        self.start_room = money(D(item["room"]))
        self.as_of = month_index(item["roomAsOfDate"], "roomAsOfDate")
        self.yearly_max = D(item["yearlyMax"])
        self.max_year = int(item.get("maxYear") or year_of(self.as_of))
        self.income_rate = D(item.get("incomeRate") or DEFAULT_INCOME_RATE)
        self.rate = indexing_rate(item, inflation)
        self.available = None           # None until the as-of month: nothing is checked
        self.earned = {}                # calendar year -> earned income
        self.withdrawn = {}             # calendar year -> TFSA withdrawals

    def maximum(self, year):
        """The year's dollar maximum, indexed from max_year and rounded as CRA does."""
        step = ROUNDING[self.account_type]
        value = self.yearly_max * (ONE + self.rate) ** (year - self.max_year)
        return (value / step).quantize(ONE, rounding=ROUND_HALF_UP) * step

    def new_room(self, year):
        """Room added on January 1 of ``year``."""
        if self.account_type == "rrsp":
            earned = self.earned.get(year - 1, Decimal(0))
            return min(money(earned * self.income_rate), self.maximum(year))
        return self.maximum(year) + self.withdrawn.get(year - 1, Decimal(0))


class RoomState:
    def __init__(self):
        self.types = {}                 # (person id, account type) -> RoomType

    def get(self, person, account_type):
        return self.types.get((person, account_type))


def state(household):
    return household.ext.get(KEY)


def person_id(household, pid):
    return pid or household.first.id


class RoomLimits(ContributionLimits):
    """Caps movements into RRSP/TFSA accounts at the available room (ADR-0060)."""

    columns = {"rrspRoom": "RRSP room left", "tfsaRoom": "TFSA room left"}

    def cap(self, household, account, amount, match=False):
        if getattr(account, "account_type", None) == "resp":      # lifetime limit, ADR-0072
            from . import resp
            return resp.cap(household, account, amount)
        """The part of ``amount`` within the room of ``account``'s type; uses it up.
        Unchanged when the type has no room item or before its as-of month."""
        st = state(household)
        pid = person_id(household, getattr(account, "contributor", None))
        room = st and st.get(pid, getattr(account, "account_type", None))
        if room is None or room.available is None:
            return amount
        allowed = max(Decimal(0), min(amount, room.available))
        room.available -= money(allowed)
        return allowed

    def note_earned(self, household, amount, person=None):
        st = state(household)
        room = st and st.get(person_id(household, person), "rrsp")
        if room is not None:
            year = year_of(household.month)
            room.earned[year] = room.earned.get(year, Decimal(0)) + amount

    def note_withdrawal(self, household, account, amount):
        st = state(household)
        pid = person_id(household, getattr(account, "owner", None))
        room = st and st.get(pid, getattr(account, "account_type", None))
        if room is not None and room.account_type == "tfsa":
            year = year_of(household.month)
            room.withdrawn[year] = room.withdrawn.get(year, Decimal(0)) + amount

    def remaining(self, household):
        """{"<type>Room": available room or None} for the result rows: the household
        total over persons (None while no person's room of that type is known yet)."""
        st = state(household)
        if st is None:
            return {}
        out = {}
        for (_pid, kind), room in st.types.items():
            column = f"{kind}Room"
            if room.available is not None:
                out[column] = (out.get(column) or Decimal(0)) + room.available
            else:
                out.setdefault(column, None)
        return out


# ---------------------------------------------------------------- events
def who(label):
    return f"{label}: " if label else ""


class RoomStart(StateEvent):
    def __init__(self, room_key):
        self.room_key = room_key
        self.account_type = room_key[1]
        self.room = None
        self.label = ""

    def apply(self, household):
        room = state(household).types[self.room_key]
        room.available = room.start_room
        self.room = room.available
        self.label = room.label

    def describe(self):
        return f"{who(self.label)}{self.account_type} contribution room set to {self.room}"


class RoomYear(StateEvent):
    def __init__(self, room_key):
        self.room_key = room_key
        self.account_type = room_key[1]
        self.before = self.added = None
        self.label = ""

    def apply(self, household):
        room = state(household).types[self.room_key]
        self.label = room.label
        self.before = room.available
        self.added = room.new_room(year_of(household.month))
        room.available += self.added

    def describe(self):
        return (f"{who(self.label)}{self.account_type} contribution room {self.before} + "
                f"{self.added} = "
                f"{None if self.before is None else self.before + self.added}")


# ---------------------------------------------------------------- emitters
class RoomStartEmitter(OneShotEmitter):
    ORDER = ORDER_ROOM

    def __init__(self, room_key, month, **kw):
        super().__init__(month, **kw)
        self.room_key = room_key

    def emit(self, month, household):
        return (RoomStart(self.room_key),)


class RoomYearEmitter(RecurringEmitter):
    ORDER = ORDER_ROOM
    SUB = 1

    def __init__(self, room_key, after, **kw):
        super().__init__(**kw)
        self.room_key = room_key
        self.after = after

    def emit(self, month, household):
        if month > self.after and month % 12 == 0:
            yield RoomYear(self.room_key)


@item_type("contributionRoom")
def compile_contribution_room(item, ctx):
    hh = ctx.env.household
    st = hh.ext.setdefault(KEY, RoomState())
    pid = ctx.env.person_of(item)                    # the room's owner (ADR-0061)
    label = hh.person(pid).name if len(hh.persons) > 1 else ""
    room = RoomType(item["accountType"], item, hh.inflation, pid, label)
    key = (pid, room.account_type)
    st.types[key] = room
    yield RoomStartEmitter(key, room.as_of)
    yield RoomYearEmitter(key, room.as_of)
