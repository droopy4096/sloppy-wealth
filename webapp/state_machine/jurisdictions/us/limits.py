"""United States: yearly contribution limits (``type: "contributionLimit"``) — ADR-0071.

One item per person and limit group holds the group's yearly limit:

- ``401k``: employee contributions to traditional and Roth 401(k) accounts together;
- ``ira``: traditional and Roth IRA contributions together;
- ``hsa``: HSA contributions.

Fields: ``limitType`` (401k | ira | hsa), ``yearlyLimit`` (the limit in ``limitYear``,
default the horizon start's year), optional ``catchUp`` (the extra amount allowed from
the year the person reaches the catch-up age: 50 for 401(k) and IRA, 55 for HSA; needs
the person's ``birthDate``), ``indexing`` / ``indexRate`` (how both grow each year,
rounded down as the IRS does: to $500 for 401(k) and IRA, $50 for HSA), and optional
``contributedSoFar`` (already contributed in the horizon start's year, before the
model starts).

Unlike Canada's room nothing carries over: each calendar year starts at the limit. A
movement into an account of a group (contribution, one-off transfer, opening balance
moved from cash) is capped at what is left this year; the excess stays where it was.
The employer match does not count against the employee limit and is not capped.
Years before ``limitYear`` are not checked; without an item a group is not checked.

State lives in ``household.ext["us_limits"]``; the result rows get ``<group>Limit``
columns (left this year, household total over persons).
"""
from decimal import ROUND_FLOOR, Decimal

from ...arith import D, ONE, indexing_rate, money
from ...compiler import item_type
from ...dates import month_index
from .. import ContributionLimits

KEY = "us_limits"
GROUPS = {"traditional401k": "401k", "roth401k": "401k", "traditionalIra": "ira",
          "rothIra": "ira", "hsa": "hsa"}
LIMIT_TYPES = ("401k", "ira", "hsa")
CATCH_UP_AGE = {"401k": 50, "ira": 50, "hsa": 55}
ROUNDING = {"401k": Decimal(500), "ira": Decimal(500), "hsa": Decimal(50)}
COLUMN = {"401k": "k401Limit", "ira": "iraLimit", "hsa": "hsaLimit"}


def year_of(month):
    return month // 12


class GroupLimit:
    """The yearly limit of one group for one person."""

    def __init__(self, group, item, inflation, first_year, birth_year):
        self.group = group
        self.yearly = D(item["yearlyLimit"])
        self.catch_up = D(item.get("catchUp") or "0")
        self.limit_year = int(item.get("limitYear") or first_year)
        self.rate = indexing_rate(item, inflation)
        self.birth_year = birth_year
        self.used = {}                       # calendar year -> contributed
        if item.get("contributedSoFar"):
            self.used[first_year] = money(D(item["contributedSoFar"]))

    def _indexed(self, amount, year):
        step = ROUNDING[self.group]
        value = amount * (ONE + self.rate) ** (year - self.limit_year)
        return (value / step).quantize(ONE, rounding=ROUND_FLOOR) * step

    def limit(self, year):
        """The year's limit, with catch-up from the year the person reaches its age."""
        total = self._indexed(self.yearly, year)
        if self.catch_up and self.birth_year is not None and \
                year - self.birth_year >= CATCH_UP_AGE[self.group]:
            total += self._indexed(self.catch_up, year)
        return total

    def left(self, year):
        """What can still go in this year, or None before limitYear (not checked)."""
        if year < self.limit_year:
            return None
        return money(max(Decimal(0), self.limit(year) - self.used.get(year, Decimal(0))))


class YearlyLimits(ContributionLimits):
    columns = {"k401Limit": "401(k) limit left this year", "iraLimit": "IRA limit left "
               "this year", "hsaLimit": "HSA limit left this year"}

    def _limit(self, household, account):
        group = GROUPS.get(getattr(account, "account_type", None))
        state = household.ext.get(KEY)
        if group is None or state is None:
            return None
        pid = getattr(account, "contributor", None) or household.first.id
        return state.get((pid, group))

    def cap(self, household, account, amount, match=False):
        if match:
            return amount                    # employer match: outside the employee limit
        limit = self._limit(household, account)
        year = year_of(household.month)
        left = limit.left(year) if limit else None
        if left is None:
            return amount
        allowed = max(Decimal(0), min(amount, left))
        limit.used[year] = limit.used.get(year, Decimal(0)) + money(allowed)
        return allowed

    def remaining(self, household):
        state = household.ext.get(KEY)
        if not state:
            return {}
        year = year_of(household.month)
        out = {}
        for (_pid, group), limit in state.items():
            column = COLUMN[group]
            left = limit.left(year)
            if left is not None:
                out[column] = (out.get(column) or Decimal(0)) + left
            else:
                out.setdefault(column, None)
        return out


def birth_year(scenario, pid):
    for item in scenario.get("items", []):
        if item.get("type") == "person" and item.get("id") == pid and item.get("birthDate"):
            return month_index(item["birthDate"], "birthDate") // 12
    return None


@item_type("contributionLimit")
def compile_contribution_limit(item, ctx):
    hh = ctx.env.household
    pid = ctx.env.person_of(item)
    state = hh.ext.setdefault(KEY, {})
    state[(pid, item["limitType"])] = GroupLimit(
        item["limitType"], item, hh.inflation, year_of(hh.start), birth_year(ctx.env.scenario, pid))
    return ()
