"""Mortgage (WP4/E2): a liability created by its LoanAdvance event (D1), serviced monthly
by the events of its LoanServiceEmitter and modifier emitters (events/loan.py).

Reference: ``prepare`` (engine.py L732-743), ``events`` LOAN_ADVANCE (L850), ``pay_mortgage``
(L969-1005). OBJECTS §2.3, §3.2, §3.7, §3.8, §4.3.

Lifecycle (no PLANNED object, D1): created at ``at`` by LoanAdvance with balance 0.00 and
advanced the same month -> ACCRUING while ``month < first_pay`` -> AMORTIZING -> PAID_OFF
(balance 0.00, never serviced again). Balance sign: positive = owed (the sign flip lives in
``Aggregate._apply``).
"""
from decimal import Decimal

from ..arith import D, annuity, keep_payment_months, money
from ..base import Aggregate

ACCRUING, AMORTIZING, PAID_OFF = "accruing", "amortizing", "paid_off"


PENALTY_METHODS = ("flat", "interestLeft", "monthsInterest")


class ClosureTerm:
    """A term of a mortgage or renewal with its early-closure penalty (ADR-0073): from
    ``start`` for ``months``; ``method`` flat (``amount``), interestLeft (``rate`` x the
    schedule's interest left in the term) or monthsInterest (``months_interest`` months
    of interest on the balance)."""

    def __init__(self, start, item):
        self.start = start
        self.months = int(D(item.get("termMonths") or "0"))
        self.method = item.get("penaltyMethod") or None
        self.amount = D(item.get("penaltyAmount") or "0")
        self.rate = D(item.get("penaltyRate") or "0")
        self.months_interest = D(item.get("penaltyMonths") or "0")

    @classmethod
    def of(cls, start, item):
        """The term of ``item``, or None when it gives no term or no penalty method."""
        term = cls(start, item)
        return term if term.months and term.method in PENALTY_METHODS else None

    def end(self):
        return self.start + self.months


class LoanTerms:
    """The compile-time terms of a mortgage item (reference holding dict before the
    advance). ``payment`` is annuitised on the *unrounded* principal, ``amount`` (advance
    and accrual base) is the rounded one (OBJECTS §9 hazard 6)."""

    def __init__(self, secured_by, at, first_pay, amount, rate, payment, left, closure=None):
        self.closure = closure or {}     # term id (mortgage or renewal) -> ClosureTerm
        self.secured_by = secured_by
        self.at = at
        self.first_pay = first_pay
        self.amount = amount
        self.rate = rate
        self.payment = payment
        self.left = left


class Mortgage(Aggregate):
    kind = "mortgage"

    def __init__(self, id, name, item_index, terms):
        # Reference: the advance sets balance = Decimal("0.00"), then LOAN_ADVANCE raises it.
        super().__init__(id, name, item_index, Decimal("0.00"))
        self.secured_by = terms.secured_by
        self.at = terms.at
        self.first_pay = terms.first_pay
        self.amount = terms.amount
        self.rate = terms.rate
        self.payment = terms.payment
        self.left = terms.left
        self.term = None             # id of the renewal in effect (h.get("term"))
        self.closure = terms.closure     # ADR-0073: penalties per term
        self.accrued = Decimal(0)    # interest accrued before first_pay (h.get("accrued", 0))

    @property
    def report_rate(self):
        return self.rate             # current monthly rate, changes at renewal

    def status(self, month):
        if not self.balance > 0:
            return PAID_OFF
        return ACCRUING if month < self.first_pay else AMORTIZING

    @property
    def source_term(self):
        """Source of interest and payments: the renewal in effect, else the loan itself."""
        return self.term or self.id

    # ---------- early closure (ADR-0073) ----------
    def penalty_at(self, month):
        """The early-closure penalty if the loan were closed in ``month`` (unrounded):
        by the formula of the term in effect, 0 after that term's end or without one."""
        term = self.closure.get(self.source_term)
        if term is None or not self.balance > 0 or month >= term.end():
            return Decimal(0)
        if term.method == "flat":
            return term.amount
        if term.method == "monthsInterest":
            return term.months_interest * self.balance * self.rate
        return term.rate * self.interest_left(term.end() - month)

    def interest_left(self, months):
        """The schedule's interest over the next ``months`` payments from the current
        balance, payment and rate (no prepayments)."""
        balance, total = self.balance, Decimal(0)
        for _ in range(max(0, months)):
            if balance <= 0:
                break
            interest = money(balance * self.rate)
            total += interest
            balance -= min(self.payment, balance + interest) - interest
        return total

    def report_extra(self, month):
        """Extra holdings-point fields: the penalty if closed after this month, only for
        a loan with a term (ADR-0073), so other results are unchanged."""
        if not self.closure:
            return None
        return {"closingPenalty": money(self.penalty_at(month + 1))}

    # ---------- transitions (each records its movements) ----------
    def advance(self, household):
        """LoanAdvance event: the principal goes to cash (ACQUIRE)."""
        household.move("LOAN_ADVANCE", self.id, "cash", self.amount, self.id)

    def renew(self, rate, reset, rid, keep=False):
        """Renewal or lender switch: new rate from this month, optionally a new
        amortization; payment recomputed from the current balance (in an accruing month
        that includes the accrued interest). The renewal's penalty is a separate event
        (events/loan.py RenewalPenalty), charged from cash right after.

        ``keep`` (keepPayment, ADR-0043 amendment, C-M7): the current scheduled payment
        (in an accruing month the loan's original one) is kept and the remaining
        amortization derived from the same balance; if it cannot repay the balance within
        the remaining amortization, the payment is recomputed as usual. Returns a note for
        the event log when ``keep``, else None."""
        self.rate = rate
        self.term = rid
        n = keep and keep_payment_months(self.balance, self.rate, self.payment, self.left)
        if n:
            self.left = n
            return f"keepPayment: payment {self.payment} kept, {n} months left"
        self.left = reset or self.left
        self.payment = annuity(self.balance, self.rate, self.left)
        if keep:
            return ("keepPayment fell back: the payment cannot repay the balance at the new "
                    f"rate within the remaining {self.left} months; payment recomputed "
                    f"to {self.payment}")
        return None

    def accrue(self, household):
        """ACCRUING month: simple interest on the rounded principal; raises the balance."""
        interest = household.move("LOAN_INTEREST", self.id, None, self.amount * self.rate,
                                  self.source_term)
        self.accrued = self.accrued + interest

    def settle_accrued(self, household):
        """First payment month: the accrued interest is paid (interest adjustment)."""
        if self.accrued:
            household.move("INTEREST_ADJUSTMENT", household.recurring_source, self.id,
                           self.accrued, self.source_term)
            self.accrued = Decimal(0)

    def charge_interest(self, household):
        """AMORTIZING month: interest on the current balance (before the payment)."""
        return household.move("LOAN_INTEREST", self.id, None, self.balance * self.rate,
                              self.source_term)

    def pay_scheduled(self, household):
        """The scheduled payment (after ``charge_interest``); the last one clears the
        remainder."""
        self.left -= 1
        owed = self.balance
        payment = owed if self.left <= 0 else min(self.payment, owed)
        return household.move("LOAN_PAYMENT", household.recurring_source, self.id, payment,
                              self.source_term)

    def prepay(self, household, src, amount, source):
        """Extra principal capped at the balance; ``amount`` None = the whole balance.
        Returns the rounded amount moved (0.00 if nothing)."""
        amt = self.balance if amount is None else min(amount, self.balance)
        return household.move("PREPAYMENT", src, self.id, amt, source)

    def pay_off(self, household, source, kind="LOAN_PAYOFF"):
        """Settle the whole balance from cash (a sale of the securing asset, WP3).
        Reference: ``if loan["balance"]: move(LOAN_PAYOFF, cash, loan, balance, saleId)``."""
        if self.balance:
            return household.move(kind, "cash", self.id, self.balance, source)
        return Decimal("0.00")
