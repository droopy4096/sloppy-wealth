"""InvestmentAccount (``type: "account"``) — WP5/E3, OBJECTS §2.4 and §3.3.

An account is created by an event (D1): in the INITIAL step when it is opened on or
before the horizon start (``AccountAtStartEmitter`` -> ``AccountAtStart``: statement
balance, no ledger line), else in its opening month (``AccountOpeningEmitter``, order
ACQUIRE -> ``AccountOpening``: OPENING_TRANSFER from cash or OPENING_BALANCE from
outside). Every month it existed at the start of, ``AccountReturnEmitter`` (order GROW)
emits ``AccountReturn``: RETURN on its opening balance, taxed as the scenario's
jurisdiction says (``on_return``, ADR-0071).
"""
from decimal import Decimal

from ..arith import D, ONE, money, power
from ..base import Aggregate
from ..clock import Order
from ..compiler import item_type
from ..dates import month_index
from ..emitters import (InitialEmitter, LifecycleEvent, OneShotEmitter, RecurringEmitter,
                        ValuationEvent)
from ..jurisdictions import capped_note


class AccountSpec:
    """The compiled account item (reference prepare(), L624-638), verbatim expressions."""

    def __init__(self, item, ctx):
        opened = item.get("openedDate")
        start = ctx.env.start
        at = month_index(opened, "openedDate") if opened else start
        wrate = item.get("withdrawalTaxRate")
        self.id = ctx.id
        self.name = ctx.name
        self.item_index = ctx.ordinal
        self.account_type = item["accountType"]
        self.owner = ctx.env.person_of(item)                 # ADR-0061
        self.contributor = ctx.env.contributor_of(item)     # spousal RRSP: room and deduction
        self.rate = power(ONE + D(item["annualReturn"]), ONE / 12) - 1
        # Raw truthiness: a JSON number 0 means "no own rate" (taxed as income).
        self.withdrawal_tax_rate = D(wrate) if wrate else None
        self.opening_balance = money(D(item.get("openingBalance") or "0"))
        self.opening_from = item.get("openingFrom") or "outside"
        # Opened inside the horizon: an AccountOpening in month ``at``; else it exists
        # before the first month (``at`` None, like the reference holding).
        self.at = at if at > start else None
        # Fields only its account type takes (e.g. an RESP's grant history, ADR-0072).
        kind = ctx.env.household.jurisdiction.account_types.get(self.account_type)
        self.extra = {f: item.get(f) for f in (kind.fields if kind else ())}


class InvestmentAccount(Aggregate):
    """An account of one of the jurisdiction's account types (ADR-0071)."""
    kind = "account"

    def __init__(self, spec, balance):
        super().__init__(spec.id, spec.name, spec.item_index, balance)
        self.spec = spec
        self.account_type = spec.account_type
        self.owner = spec.owner
        self.contributor = spec.contributor
        self.rate = spec.rate
        self.withdrawal_tax_rate = spec.withdrawal_tax_rate
        self.extra = spec.extra

    @property
    def report_rate(self):
        return self.rate

    def accept_contribution(self, household, amount, source, match):
        """Reference contribute(), account branch (L928-932): the member's share from
        cash (from outside when expenses are covered), a deduction if the jurisdiction
        says so (``on_contribute``), then the employer match from outside (neither income
        nor a deduction). Both are capped at the jurisdiction's limits (ADR-0060,
        ADR-0071): the member's share first,
        the match on the share actually paid; returns a note when capped."""
        rules = household.jurisdiction
        own = rules.limits.cap(household, self, amount)
        household.move("CONTRIBUTION", household.recurring_source, self.id, own, source)
        rules.on_contribute(household, self, own, source)
        wanted = amount * match if own == amount else money(own) * match
        paid = rules.limits.cap(household, self, wanted, match=True)
        household.move("EMPLOYER_MATCH", None, self.id, paid, source)
        return capped_note(amount, own) + ("" if paid == wanted else
                                            f" (match capped at room: {money(paid)})")


# ---------------------------------------------------------------- events
class AccountAtStart(LifecycleEvent):
    """Opened on or before the horizon start: exists from month 1 with its statement
    balance, no ledger line."""

    def __init__(self, spec):
        self.spec = spec

    def apply(self, household):
        household.add(InvestmentAccount(self.spec, self.spec.opening_balance))

    def describe(self):
        return f"{self.spec.account_type} {self.spec.id} at start: {self.spec.opening_balance}"


class AccountOpening(LifecycleEvent):
    """Opened inside the horizon: balance 0.00, then the opening balance from cash or
    from outside. A zero balance records no line but the account exists (and is not in
    ``opened`` until next month)."""

    def __init__(self, spec):
        self.spec = spec
        self.note = ""

    def apply(self, household):
        spec = self.spec
        household.add(InvestmentAccount(spec, Decimal("0.00")))
        if spec.opening_from == "cash":
            account = household[spec.id]
            amount = household.jurisdiction.limits.cap(household, account,
                                                       spec.opening_balance)
            self.note = capped_note(spec.opening_balance, amount)
            household.move("OPENING_TRANSFER", "cash", spec.id, amount, spec.id)
        else:
            household.move("OPENING_BALANCE", None, spec.id, spec.opening_balance, spec.id)

    def describe(self):
        return (f"open {self.spec.account_type} {self.spec.id}: {self.spec.opening_balance}"
                f" from {self.spec.opening_from}{self.note}")


class AccountReturn(ValuationEvent):
    """RETURN on the month's opening balance (no balance check, reference growth
    L1014-1019), taxed as the jurisdiction says (``on_return``)."""

    def __init__(self, account_id):
        self.account_id = account_id

    def apply(self, household):
        hid = self.account_id
        account = household[hid]
        ret = household.move("RETURN", None, hid, household.opening[hid] * account.rate, hid)
        household.jurisdiction.on_return(household, account, ret)

    def describe(self):
        return f"return on {self.account_id}"


# ---------------------------------------------------------------- emitters
class AccountAtStartEmitter(InitialEmitter):
    ORDER = Order.INITIAL

    def __init__(self, spec, **kw):
        super().__init__(**kw)
        self.spec = spec

    def emit(self, month, household):
        return (AccountAtStart(self.spec),)


class AccountOpeningEmitter(OneShotEmitter):
    ORDER = Order.ACQUIRE

    def __init__(self, spec, **kw):
        super().__init__(spec.at, **kw)
        self.spec = spec

    def emit(self, month, household):
        return (AccountOpening(self.spec),)


class AccountReturnEmitter(RecurringEmitter):
    """Every month, for an account in ``opened`` (it existed at the start of the month);
    nothing otherwise."""
    ORDER = Order.GROW

    def __init__(self, spec, **kw):
        super().__init__(**kw)
        self.spec = spec

    def emit(self, month, household):
        if household.is_opened(self.spec.id):
            yield AccountReturn(self.spec.id)


@item_type("account")
def compile_account(item, ctx):
    spec = AccountSpec(item, ctx)
    if spec.at is None:
        yield AccountAtStartEmitter(spec)
    else:
        yield AccountOpeningEmitter(spec)
    yield AccountReturnEmitter(spec)
