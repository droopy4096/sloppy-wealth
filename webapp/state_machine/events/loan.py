"""Debt emitters and events (WP4, converted in E2: INTERFACES §10, DECISIONS D-E1/D-E2).

Emitters (key ``(order, ordinal, sub)``; every mortgage emitter sits at the mortgage's
holding slot):

| item | emitter | order | sub | events |
|---|---|---|---|---|
| mortgage | LoanAdvanceEmitter (one-shot, ``at``) | ACQUIRE | 0 | LoanAdvance |
| mortgage | LoanServiceEmitter (recurring from ``at + 1``) | SERVICE_DEBT | sub_order(1) | AccrueInterest, or InterestAdjustment? + LoanInterest + ScheduledPayment |
| renewal | RenewalEmitter (modifier, once) | SERVICE_DEBT | sub_order(0, index) | Renew, RenewalPenalty? |

A renewal with ``keepPayment`` (ADR-0043 amendment, C-M7) keeps the scheduled payment and
derives the remaining amortization (``arith.keep_payment_months``); when the payment cannot
repay the balance within the remaining amortization it falls back to recomputing the
payment, and the Renew event's log ``detail`` says so (the PoC has no warnings output).
| extraPayment | ExtraPaymentEmitter (modifier, window) | SERVICE_DEBT | sub_order(2, index) | ExtraPrepayment |
| lumpSum | LumpSumEmitter (modifier, once) | SERVICE_DEBT | sub_order(2, index) | LumpSumPrepayment, LumpSumPenalty? |

The gate is the service's (reference ``debits`` L899-901): a loan is serviced in a month
only if it is in the window, existed and was opened at the start of the month, and is
still owed when its service starts (not paid off, e.g. by a sale earlier this month).
- A renewal (stage 0, before the service) tests that same gate itself
  (``LoanServiceEmitter.serviceable``); a renewal of a paid-off loan is lost, penalty
  included. Last renewal of a mortgage in a month wins (``prepare``).
- Extras (stage 2, after the service) run only in a month the service *paid* (not while
  accruing: extras in the accrual window are dropped). They do not re-test
  ``balance > 0``: a lump sum after the last scheduled payment moves 0.00 but its penalty
  is still charged.

Amounts are resolved in ``apply`` (§10.6): the payment is annuitised on the *unrounded*
principal at compile time, the advance and accrual base are the rounded one; interest and
payments are attributed to the renewal in effect (``Mortgage.source_term``); the loan
payment, interest adjustment and extra payment come from outside when expenses are
covered (``household.recurring_source``), a lump sum from cash or outside per paidFrom.

Reference: ``prepare`` (engine.py L687-743), ``events`` (L850), ``debits`` (L899-901),
``pay_mortgage`` (L969-1005); OBJECTS §2.3, §3.2, §3.7, §3.8, §4.2, §4.3, §9 hazards 4-6.
"""
from decimal import Decimal

from ..arith import D, money, monthly_rate, mortgage_terms
from ..clock import Order
from ..compiler import item_type
from ..dates import flow_window, month_index, mortgage_start
from ..emitters import (NEVER, FlowEvent, LifecycleEvent, ModifierEmitter, Once,
                        OneShotEmitter, RecurringEmitter, StateEvent, ValuationEvent,
                        Window, sub_order)
from ..holdings.mortgage import ClosureTerm, LoanTerms, Mortgage

STAGE_RENEWAL, STAGE_SERVICE, STAGE_EXTRAS = 0, 1, 2


# ---------------------------------------------------------------- events
class LoanAdvance(LifecycleEvent):
    """Creates the Mortgage and advances the principal to cash."""

    def __init__(self, id, name, item_index, terms):
        self.id = id
        self.loan_name = name
        self.item_index = item_index
        self.terms = terms

    def apply(self, household):
        loan = household.add(Mortgage(self.id, self.loan_name, self.item_index, self.terms))
        loan.advance(household)

    def describe(self):
        return f"LoanAdvance {self.id} {self.terms.amount}"


class _LoanEvent:
    """Mixin: an event acting on mortgage ``loan_id``."""

    def __init__(self, loan_id):
        self.loan_id = loan_id

    def describe(self):
        return f"{self.name} {self.loan_id}"


class AccrueInterest(_LoanEvent, ValuationEvent):
    """ACCRUING month: simple interest on the rounded principal, raises the balance."""

    def apply(self, household):
        household[self.loan_id].accrue(household)


class InterestAdjustment(_LoanEvent, FlowEvent):
    """First amortizing month: the accrued interest is paid."""

    def apply(self, household):
        household[self.loan_id].settle_accrued(household)


class LoanInterest(_LoanEvent, ValuationEvent):
    """AMORTIZING month: interest on the current balance."""

    def apply(self, household):
        household[self.loan_id].charge_interest(household)


class ScheduledPayment(_LoanEvent, FlowEvent):
    """AMORTIZING month: the scheduled payment (the last one clears the remainder)."""

    def apply(self, household):
        household[self.loan_id].pay_scheduled(household)


class Renew(_LoanEvent, StateEvent):
    """Renewal or lender switch: new rate, optional amortization reset, payment
    recomputed from the current balance -- or, with ``keep``, the payment kept and the
    amortization derived (C-M7); the renewal id becomes the source term."""

    def __init__(self, loan_id, rate, reset, rid, keep=False):
        super().__init__(loan_id)
        self.rate = rate
        self.reset = reset
        self.rid = rid
        self.keep = keep
        self.outcome = None             # keepPayment outcome for the log, set by apply

    def apply(self, household):
        self.outcome = household[self.loan_id].renew(self.rate, self.reset, self.rid,
                                                     self.keep)

    def describe(self):
        base = super().describe()
        return f"{base} {self.outcome}" if self.outcome else base


class Penalty(FlowEvent):
    """A prepayment / renewal penalty from cash (unrounded until ``move``)."""

    def __init__(self, amount):
        self.amount = amount

    def apply(self, household):
        household.move("PENALTY", "cash", None, self.amount, self.source)

    def describe(self):
        return f"{self.name} {self.amount}"


class RenewalPenalty(Penalty):
    pass


class ClosurePenalty(_LoanEvent, FlowEvent):
    """The early-closure penalty by the formula of the loan's term (ADR-0073), before
    the payoff (it depends on the balance); nothing after the term or without one."""

    def apply(self, household):
        loan = household.get(self.loan_id)
        self.amount = loan.penalty_at(household.month) if loan is not None else Decimal(0)
        if self.amount:
            household.move("PENALTY", "cash", None, self.amount, self.source)

    def describe(self):
        return f"closure penalty {money(getattr(self, 'amount', 0))}"


class LumpSumPenalty(Penalty):
    pass


class Prepayment(_LoanEvent, FlowEvent):
    """Extra principal capped at the balance (``amount`` None = the whole balance) from
    ``src``; ``recurring`` sources follow the income mode at apply time."""

    def __init__(self, loan_id, amount, from_cash=None):
        super().__init__(loan_id)
        self.amount = amount
        self.from_cash = from_cash      # None: household.recurring_source

    def apply(self, household):
        if self.from_cash is None:
            src = household.recurring_source
        else:
            src = "cash" if self.from_cash else None
        household[self.loan_id].prepay(household, src, self.amount, self.source)


class ExtraPrepayment(Prepayment):
    pass


class LumpSumPrepayment(Prepayment):
    pass


# ---------------------------------------------------------------- emitters
class LoanAdvanceEmitter(OneShotEmitter):
    """Mortgage start month: the LoanAdvance lifecycle event."""
    ORDER = Order.ACQUIRE

    def __init__(self, id, name, item_index, terms):
        super().__init__(terms.at)
        self.loan = (id, name, item_index, terms)

    def emit(self, month, household):
        return (LoanAdvance(*self.loan),)


class LoanServiceEmitter(RecurringEmitter):
    """Monthly service of one mortgage from the month after the advance: accrue while
    ``month < first_pay``, else interest adjustment (if accrued), interest, payment.
    Records the months it paid in (``paid_month``) for its stage-2 modifiers."""
    ORDER = Order.SERVICE_DEBT
    SUB = sub_order(STAGE_SERVICE)

    def __init__(self, loan_id, first):
        super().__init__(first)
        self.loan_id = loan_id
        self.paid_month = None

    def serviceable(self, month, household):
        """The service gate: due, existed and opened at the start of the month, still owed."""
        if not self.due(month):
            return False
        loan = household.get(self.loan_id)
        return (loan is not None and household.is_opened(self.loan_id)
                and loan.balance > 0)

    def emit(self, month, household):
        if not self.serviceable(month, household):
            return
        loan = household[self.loan_id]
        if month < loan.first_pay:
            yield AccrueInterest(self.loan_id)
            return                      # no payment; extras in this window are dropped
        self.paid_month = month
        if loan.accrued:
            yield InterestAdjustment(self.loan_id)
        yield LoanInterest(self.loan_id)
        yield ScheduledPayment(self.loan_id)


def _service_of(env, host):
    for e in env.emitters_for(host):
        if isinstance(e, LoanServiceEmitter):
            return e
    return None


class _DebtModifier(ModifierEmitter):
    """A modifier of mortgage ``host`` at its service position (D-E1)."""
    ORDER = Order.SERVICE_DEBT

    def __init__(self, host, schedule):
        super().__init__(host, schedule)
        self.service = None

    def prepare(self, env):
        self.service = _service_of(env, self.host)
        if self.service is None:
            self.schedule = NEVER


class RenewalEmitter(_DebtModifier):
    """Renewal or lender switch in ``month`` (stage 0, before the service). Lost (penalty
    included) when the loan is not serviced that month; the last renewal of a mortgage
    in a month wins."""
    STAGE = STAGE_RENEWAL

    def __init__(self, host, month, rate, reset, penalty, keep=False):
        super().__init__(host, Once(month))
        self.month = month
        self.rate = rate
        self.reset = reset              # months, or None = keep the remaining term
        self.penalty = penalty          # unrounded
        self.keep = keep                # keepPayment: keep the payment, derive the term

    def prepare(self, env):
        super().prepare(env)
        if any(r.index > self.index and r.month == self.month
               for r in env.modifiers_of(self.host, RenewalEmitter)):
            self.schedule = NEVER       # reference dict keyed (mortgage, month)

    def emit(self, month, household):
        if not self.service.serviceable(month, household):
            return ()
        events = [Renew(self.host, self.rate, self.reset, self.source, self.keep)]
        if self.penalty:
            events.append(RenewalPenalty(self.penalty))
        return events


class ExtraPaymentEmitter(_DebtModifier):
    """Monthly extra principal (stage 2) from cash, or from outside when expenses are
    covered; does not change the scheduled payment or term."""
    STAGE = STAGE_EXTRAS

    def __init__(self, host, first, last, amount):
        super().__init__(host, Window(first, last) if first is not None else NEVER)
        self.amount = amount

    def emit(self, month, household):
        if self.service.paid_month != month:
            return ()
        return (ExtraPrepayment(self.host, self.amount),)


class LumpSumEmitter(_DebtModifier):
    """One-off prepayment (stage 2; amount or the whole balance) from cash or outside
    (independent of the income mode), then its penalty from cash -- charged even when the
    prepayment rounds to 0."""
    STAGE = STAGE_EXTRAS

    def __init__(self, host, month, amount, from_cash, penalty):
        super().__init__(host, Once(month))
        self.amount = amount            # money, or None = payOff
        self.from_cash = from_cash
        self.penalty = penalty

    def emit(self, month, household):
        if self.service.paid_month != month:
            return ()
        if self.penalty is None:            # payoff without a manual penalty: the formula
            return [ClosurePenalty(self.host),
                    LumpSumPrepayment(self.host, self.amount, self.from_cash)]
        events = [LumpSumPrepayment(self.host, self.amount, self.from_cash)]
        if self.penalty:
            events.append(LumpSumPenalty(self.penalty))
        return events


# ---------------------------------------------------------------- factories
@item_type("mortgage")
def compile_mortgage(item, ctx):
    env = ctx.env
    r, payment, n = mortgage_terms(item)
    at = mortgage_start(item, env.properties)
    first_pay = item.get("firstPaymentDate")
    # Terms with an early-closure penalty (ADR-0073): its own, and each renewal's.
    closure = {ctx.id: ClosureTerm.of(at, item)}
    for renewal in env.items:
        if renewal.get("type") == "renewal" and renewal.get("mortgage") == ctx.id \
                and renewal.get("startDate"):
            closure[renewal.get("id")] = ClosureTerm.of(
                month_index(renewal["startDate"], "startDate"), renewal)
    terms = LoanTerms(
        secured_by=item.get("property") or None,
        at=at,
        first_pay=month_index(first_pay, "firstPaymentDate") if first_pay else at + 1,
        amount=money(D(item["principal"])),
        rate=r, payment=payment, left=n,
        closure={k: v for k, v in closure.items() if v is not None})
    return [LoanAdvanceEmitter(ctx.id, ctx.name, ctx.ordinal, terms),
            LoanServiceEmitter(ctx.id, at + 1)]


@item_type("renewal")
def compile_renewal(item, ctx):
    amort = item.get("amortizationYears")
    return [RenewalEmitter(
        item["mortgage"], month_index(item["startDate"], "startDate"),
        monthly_rate(item["annualRate"]),
        int(Decimal(str(amort)) * 12) if amort else None,
        Decimal(str(item.get("penalty") or "0")),
        bool(item.get("keepPayment")))]


@item_type("extraPayment")
def compile_extra_payment(item, ctx):
    env = ctx.env
    first, last = flow_window(item, env)          # retirementOf (ADR-0061)
    return [ExtraPaymentEmitter(item["mortgage"], first, last,
                                money(Decimal(str(item["monthlyAmount"]))))]


@item_type("lumpSum")
def compile_lump_sum(item, ctx):
    env = ctx.env
    at = month_index(item["paymentDate"], "paymentDate")     # may come from a trigger
    return [LumpSumEmitter(
        item["mortgage"], at,
        None if item.get("payOff") else money(Decimal(str(item["amount"]))),
        (item.get("paidFrom") or "cash") == "cash",
        # A payoff without a manual penalty uses its term's formula (ADR-0073).
        None if item.get("payOff") and item.get("penalty") in (None, "")
        else Decimal(str(item.get("penalty") or "0")))]
