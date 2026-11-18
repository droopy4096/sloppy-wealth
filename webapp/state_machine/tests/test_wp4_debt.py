"""WP4 debt: ledger, balances and loan state for mortgages and their items, golden values
frozen from the iteration-1 engine (support.assert_golden).

Run from webapp/:
    .venv/bin/python -m unittest state_machine.tests.test_wp4_debt

The engine runs with an isolated registry holding only WP4's factories plus small test
stand-ins for item types owned by other WPs (property purchase/sale: WP3; retirement:
WP7). Scenarios are income-free with a 0 tax rate, so there are no TAX lines and no
growth lines (property appreciation 0).
"""
import unittest
from decimal import Decimal

from state_machine import api, compiler
from state_machine.base import Aggregate
from state_machine.clock import Order
from state_machine.dates import month_index
from state_machine.emitters import FlowEvent, LifecycleEvent, OneShotEmitter, sub_order
from state_machine.events import loan
from state_machine.holdings.mortgage import ACCRUING, AMORTIZING, PAID_OFF

from .support import assert_golden, balances, scenario, without_tax


# ---------------------------------------------------------------- stand-ins (tests only)
class FakeProperty(Aggregate):
    kind = "property"


class FakePurchaseEvent(LifecycleEvent):
    def __init__(self, ctx):
        self.ctx = ctx

    def apply(self, hh):
        c = self.ctx
        hh.add(FakeProperty(c.id, c.name, c.ordinal, Decimal("0.00")))
        hh.move("PURCHASE", "cash", c.id, Decimal(str(c.item["price"])), c.id)


class FakePurchase(OneShotEmitter):
    """WP3 stand-in: PURCHASE in the purchase month (appreciation 0, no marketValue)."""
    ORDER = Order.ACQUIRE

    def __init__(self, ctx):
        super().__init__(month_index(ctx.item["purchaseDate"], ""))
        self.ctx = ctx

    def emit(self, month, hh):
        return (FakePurchaseEvent(self.ctx),)


class FakeLoanPayoff(LifecycleEvent):
    """D-E3 follow-up: the loan settles itself (Mortgage.pay_off)."""

    def __init__(self, loan_id):
        self.loan_id = loan_id

    def apply(self, hh):
        hh[self.loan_id].pay_off(hh, self.source)


class FakeSalePenalty(FlowEvent):
    def __init__(self, amount):
        self.amount = amount

    def apply(self, hh):
        hh.move("PENALTY", "cash", None, self.amount, self.source)


class FakeSaleEvent(LifecycleEvent):
    def __init__(self, pid, item):
        self.pid, self.item = pid, item

    def apply(self, hh):
        pid = self.pid
        hh.move("SALE", pid, "cash", hh[pid].balance, pid)
        return ([FakeLoanPayoff(debt.id) for debt in hh.loans_secured_by(pid)]
                + [FakeSalePenalty(Decimal(str(self.item.get("salePenalty") or "0")))])


class FakeSale(OneShotEmitter):
    """WP3 stand-in for a sale (no salePrice, no selling cost): SALE, then a LoanPayoff
    follow-up per secured loan (household.loans_secured_by), then PENALTY. Older files'
    property saleDate arrives as a sale item (upgrade.py)."""
    ORDER = Order.SELL

    def __init__(self, item):
        # Source as the real SaleEmitter: the sale id, else the asset id.
        super().__init__(month_index(item["saleDate"], ""),
                         source=item.get("id") or item["property"])
        self.item = item

    def emit(self, month, hh):
        return (FakeSaleEvent(self.item["property"], self.item),)


def fake_property(item, ctx):
    yield FakePurchase(ctx)


def fake_sale(item, ctx):
    if item.get("saleDate"):
        yield FakeSale(item)


def nothing(item, ctx):
    return []


def run_new(s):
    with compiler.isolated_registry():
        compiler.item_type("mortgage")(loan.compile_mortgage)
        compiler.item_type("renewal")(loan.compile_renewal)
        compiler.item_type("extraPayment")(loan.compile_extra_payment)
        compiler.item_type("lumpSum")(loan.compile_lump_sum)
        compiler.item_type("property")(fake_property)
        compiler.item_type("sale")(fake_sale)
        compiler.item_type("retirement")(nothing)
        compiler.item_type("trigger")(nothing)      # dates resolved before compiling (ADR-0065)
        return api.simulate(s)


# ---------------------------------------------------------------- scenario builders
def mortgage(id="m1", principal="300000", rate="0.05", years=2, start="2026-02-01", **kw):
    item = {"type": "mortgage", "id": id, "name": id.upper(), "principal": principal,
            "annualRate": rate, "amortizationYears": years}
    if start:
        item["startDate"] = start
    item.update(kw)
    return item


def house(id="h1", price="500000", date="2026-02-01", **kw):
    return dict({"type": "property", "id": id, "name": "House", "price": price,
                 "annualAppreciation": 0, "purchaseDate": date}, **kw)


def renewal(id, date, rate, **kw):
    return dict({"type": "renewal", "id": id, "mortgage": "m1", "startDate": date,
                 "annualRate": rate}, **kw)


def extra(id, start, amount, **kw):
    return dict({"type": "extraPayment", "id": id, "mortgage": "m1", "startDate": start,
                 "monthlyAmount": amount}, **kw)


def lump(id, **kw):
    return dict({"type": "lumpSum", "id": id, "mortgage": "m1"}, **kw)


class DebtParity(unittest.TestCase):
    def check(self, items, end="2028-12-01", validate=True, **settings):
        s = scenario(items, start="2026-01-01", end=end, cash="10000", **settings)
        if validate:
            api.validate(s)               # the scenario is a valid one
        hh = run_new(s)
        self.assertEqual(hh.ledger.entries, without_tax(hh.ledger.entries),
                         "test scenarios must be tax-free")
        assert_golden(self, "ledger, balances, loan state", (
            hh.ledger.entries, balances(hh),
            [(a.id, a.report_rate, a.payment, a.left, a.term, a.accrued, a.secured_by, a.name)
             for a in hh.aggregates("mortgage")]))
        return hh, None

    def kinds(self, hh):
        return [e["kind"] for e in hh.ledger.entries]

    # ---------- advance and amortization ----------
    def test_plain_amortization_to_payoff(self):
        hh, _ = self.check([mortgage()])
        e = hh.ledger.entries
        self.assertEqual(e[0]["kind"], "LOAN_ADVANCE")
        self.assertEqual(e[1]["month"], "2026-03")            # no service in advance month
        self.assertEqual(hh["m1"].balance, Decimal("0.00"))
        self.assertEqual(hh["m1"].status(hh.end), PAID_OFF)
        self.assertEqual(self.kinds(hh).count("LOAN_PAYMENT"), 24)

    def test_odd_principal_float_rate_fractional_years(self):
        # unrounded principal for the payment, rounded for the advance; 2.5 years
        self.check([mortgage(principal="123456.789", rate=0.0379, years=2.5)], end="2029-06-01")

    def test_zero_rate(self):
        self.check([mortgage(principal="10000", rate=0, years=1)])

    def test_horizon_ends_before_payoff(self):
        self.check([mortgage(years=25)], end="2027-06-01")

    def test_two_mortgages_holdings_order(self):
        self.check([mortgage("m2", principal="50000", start="2026-03-01"),
                    mortgage("m1", principal="80000", start="2026-01-01")])

    # ---------- late first payment ----------
    def test_first_payment_date_accrual(self):
        hh, _ = self.check([mortgage(firstPaymentDate="2026-06-01")])
        k = self.kinds(hh)
        self.assertEqual(k[1:4], ["LOAN_INTEREST"] * 3)        # Mar-May accrue
        self.assertEqual(k[4:7], ["INTEREST_ADJUSTMENT", "LOAN_INTEREST", "LOAN_PAYMENT"])
        self.assertEqual(hh.ledger.entries[4]["from"], "cash")

    def test_first_payment_date_accrual_covered(self):
        hh, _ = self.check([mortgage(firstPaymentDate="2026-06-01")],
                           incomeMode="expensesCovered")
        self.assertEqual(hh.ledger.entries[4]["kind"], "INTEREST_ADJUSTMENT")
        self.assertIsNone(hh.ledger.entries[4]["from"])

    def test_accrual_zero_rate_no_adjustment(self):
        hh, _ = self.check([mortgage(rate=0, firstPaymentDate="2026-05-01")])
        self.assertNotIn("INTEREST_ADJUSTMENT", self.kinds(hh))

    def test_status(self):
        hh = run_new(scenario([mortgage(firstPaymentDate="2026-06-01")], end="2026-04-01"))
        self.assertEqual(hh["m1"].status(month_index("2026-04-01", "")), ACCRUING)
        self.assertEqual(hh["m1"].status(month_index("2026-06-01", "")), AMORTIZING)

    def test_renewal_inside_accrual_window(self):
        # annuitises principal + accrued; later accrual uses the new rate and attribution
        self.check([mortgage(firstPaymentDate="2026-07-01"),
                    renewal("r1", "2026-04-01", "0.07", penalty="1500")])

    def test_renewal_in_first_payment_month(self):
        self.check([mortgage(firstPaymentDate="2026-07-01"),
                    renewal("r1", "2026-07-01", "0.03", amortizationYears=3)])

    def test_extras_and_lump_sum_dropped_while_accruing(self):
        hh, _ = self.check([mortgage(firstPaymentDate="2026-07-01"),
                            extra("x1", "2026-04-01", "1000"),
                            lump("l1", paymentDate="2026-05-01", amount="5000", penalty="250")])
        self.assertNotIn("l1", [e["source"] for e in hh.ledger.entries])
        x1 = [e["month"] for e in hh.ledger.entries if e["source"] == "x1"]
        self.assertEqual(x1[0], "2026-07")                     # first amortizing month

    # ---------- renewals ----------
    def test_renewal_with_amortization_and_penalty(self):
        hh, _ = self.check([mortgage(years=3),
                            renewal("r1", "2026-08-01", "0.06", amortizationYears=4,
                                    penalty="2000.555")], end="2031-12-01")
        pen = [e for e in hh.ledger.entries if e["kind"] == "PENALTY"]
        self.assertEqual(pen[0]["source"], "r1")
        later = [e for e in hh.ledger.entries if e["month"] > "2026-08"]
        self.assertTrue(all(e["source"] == "r1" for e in later))

    def test_renewal_without_amortization_keeps_term(self):
        self.check([mortgage(years=3), renewal("r1", "2026-08-01", "0.04"),
                    renewal("r2", "2027-08-01", "0.045", penalty="0")], end="2029-06-01")

    def test_renewal_numeric_zero_amortization_keeps_term(self):
        # raw truthiness: amortizationYears 0 (number) -> keep remaining months
        self.check([mortgage(years=3), renewal("r1", "2026-08-01", "0.04",
                                               amortizationYears=0)],
                   end="2029-06-01", validate=False)

    def test_lender_switch_mid_term_listed_before_mortgage(self):
        self.check([renewal("sw", "2027-01-01", "0.039", amortizationYears=20,
                            penalty="4500"),
                    mortgage(years=25)], end="2029-12-01")

    def test_two_renewals_same_month_last_wins(self):
        # validation rejects this; unvalidated, the last renewal of the month wins
        hh, _ = self.check([mortgage(years=3),
                            renewal("r1", "2026-08-01", "0.04", penalty="100"),
                            renewal("r2", "2026-08-01", "0.06", penalty="200")],
                           validate=False)
        self.assertNotIn("r1", [e["source"] for e in hh.ledger.entries])

    def test_renewal_after_payoff_is_lost(self):
        hh, _ = self.check([mortgage(years=1),
                            renewal("r1", "2027-06-01", "0.06", penalty="900")])
        self.assertNotIn("r1", [e["source"] for e in hh.ledger.entries])

    # ---------- extra payments ----------
    def test_extra_payments_date_range(self):
        self.check([mortgage(years=5), extra("x1", "2026-05-01", "750.505",
                                             endDate="2027-04-01")], end="2031-06-01")

    def test_extra_payments_until_payoff(self):
        self.check([mortgage(years=5), extra("x1", "2026-03-01", "20000")], end="2028-06-01")

    def test_extra_payment_ends_at_legacy_retirement(self):
        self.check([mortgage(years=5),
                    extra("x1", "2026-05-01", "1000", endsAtRetirement=True)],
                   retirementDate="2027-03-01")

    def test_extra_payment_ends_at_retirement_item(self):
        self.check([mortgage(years=5),
                    extra("x1", "2026-05-01", "1000", endsAtRetirement=True,
                          endDate="2028-01-01"),
                    {"type": "retirement", "retirementDate": "2027-09-01"}])

    def test_extra_payment_covered(self):
        hh, _ = self.check([mortgage(years=5), extra("x1", "2026-05-01", "1000")],
                           incomeMode="expensesCovered")
        pre = [e for e in hh.ledger.entries if e["kind"] == "PREPAYMENT"]
        self.assertTrue(pre and all(e["from"] is None for e in pre))

    # ---------- lump sums ----------
    def test_lump_sum_amount_cash_with_penalty(self):
        self.check([mortgage(years=5),
                    lump("l1", paymentDate="2026-09-01", amount="25000", penalty="333.333")])

    def test_lump_sum_outside_and_payoff(self):
        hh, _ = self.check([mortgage(years=5),
                            lump("l1", paymentDate="2026-09-01", amount="10000",
                                 paidFrom="outside"),
                            lump("l2", paymentDate="2027-03-01", payOff=True, penalty="100")])
        self.assertEqual(hh["m1"].balance, Decimal("0.00"))
        self.assertIsNone([e for e in hh.ledger.entries if e["source"] == "l1"][0]["from"])

    def test_lump_sum_cash_even_when_covered(self):
        hh, _ = self.check([mortgage(years=5),
                            lump("l1", paymentDate="2026-09-01", amount="10000")],
                           incomeMode="expensesCovered")
        self.assertEqual([e for e in hh.ledger.entries if e["source"] == "l1"][0]["from"],
                         "cash")

    def test_lump_sum_penalty_when_prepayment_rounds_to_zero(self):
        # last scheduled payment clears the loan; the lump sum moves 0 but the penalty stays
        hh, _ = self.check([mortgage(years=1),
                            lump("l1", paymentDate="2027-02-01", amount="5000",
                                 penalty="125")])
        l1 = [e["kind"] for e in hh.ledger.entries if e["source"] == "l1"]
        self.assertEqual(l1, ["PENALTY"])

    def test_lump_sum_after_payoff_is_lost(self):
        hh, _ = self.check([mortgage(years=5),
                            lump("l1", paymentDate="2026-09-01", payOff=True),
                            lump("l2", paymentDate="2027-01-01", amount="100", penalty="50")])
        self.assertNotIn("l2", [e["source"] for e in hh.ledger.entries])

    def test_lump_sum_at_legacy_retirement(self):
        self.check([mortgage(years=5),
                    lump("l1", atRetirement=True, payOff=True, penalty="700")],
                   retirementDate="2027-05-01")

    def test_lump_sum_at_retirement_item(self):
        self.check([{"type": "retirement", "retirementDate": "2027-05-01"},
                    mortgage(years=5),
                    lump("l1", atRetirement=True, amount="40000", paidFrom="outside")])

    def test_extras_same_month_item_order(self):
        self.check([mortgage(years=5),
                    lump("l1", paymentDate="2026-06-01", amount="1000", penalty="10"),
                    extra("x1", "2026-04-01", "500"),
                    lump("l2", paymentDate="2026-06-01", amount="2000")])

    def test_extras_of_other_mortgage_ignored(self):
        self.check([mortgage("m1", years=5), mortgage("m2", principal="40000", years=3),
                    dict(extra("x2", "2026-04-01", "500"), mortgage="m2"),
                    lump("l1", paymentDate="2026-06-01", amount="1000")])

    # ---------- property link and sale (WP3 stand-ins) ----------
    def test_start_from_linked_property_listed_before_it(self):
        hh, _ = self.check([mortgage(start=None, property="h1"), house()])
        self.assertEqual([e["kind"] for e in hh.ledger.entries[:2]],
                         ["LOAN_ADVANCE", "PURCHASE"])
        self.assertEqual(hh["m1"].secured_by, "h1")

    def test_sale_pays_off_secured_loan_including_accrued(self):
        hh, _ = self.check([house(saleDate="2026-05-01", salePenalty="3000"),
                            mortgage(property="h1", firstPaymentDate="2026-08-01")])
        self.assertIn("LOAN_PAYOFF", self.kinds(hh))
        self.assertNotIn("INTEREST_ADJUSTMENT", self.kinds(hh))
        self.assertEqual(hh.ledger.entries[-1]["month"], "2026-05")   # not serviced after

    def test_sale_after_payoff_no_payoff_line(self):
        hh, _ = self.check([house(saleDate="2027-06-01"), mortgage(property="h1", years=1)])
        self.assertNotIn("LOAN_PAYOFF", self.kinds(hh))


class DebtUnit(unittest.TestCase):
    def test_registration(self):
        types = compiler.registered_types()
        for t in ("mortgage", "renewal", "extraPayment", "lumpSum"):
            self.assertIs(types[t].__module__, loan.__name__)

    def compile(self, items):
        s = scenario(items)
        with compiler.isolated_registry():
            for t, f in (("mortgage", loan.compile_mortgage),
                         ("renewal", loan.compile_renewal),
                         ("extraPayment", loan.compile_extra_payment),
                         ("lumpSum", loan.compile_lump_sum)):
                compiler.item_type(t)(f)
            return compiler.compile_scenario(s)

    def test_emitter_keys(self):
        # every mortgage emitter sits at the mortgage slot (1); renewal stage 0, service
        # stage 1, extras stage 2 in item order
        _hh, runner = self.compile([extra("x1", "2026-04-01", "5"), mortgage(),
                                    renewal("r1", "2026-08-01", "0.04"),
                                    lump("l1", paymentDate="2026-06-01", amount="10")])
        svc = int(Order.SERVICE_DEBT)
        self.assertEqual(
            [(type(e).__name__, e.key) for e in runner.emitters()],
            [("LoanAdvanceEmitter", (int(Order.ACQUIRE), 1, 0)),
             ("RenewalEmitter", (svc, 1, sub_order(0, 2))),
             ("LoanServiceEmitter", (svc, 1, sub_order(1))),
             ("ExtraPaymentEmitter", (svc, 1, sub_order(2, 0))),
             ("LumpSumEmitter", (svc, 1, sub_order(2, 3)))])

    def test_last_renewal_in_month_wins(self):
        _hh, runner = self.compile([mortgage(), renewal("r1", "2026-08-01", "0.04"),
                                    renewal("r2", "2026-08-01", "0.06"),
                                    renewal("r3", "2026-09-01", "0.07")])
        m = month_index("2026-08-01", "")
        due = {e.source: e.due(m) or e.due(m + 1) for e in runner.emitters()
               if isinstance(e, loan.RenewalEmitter)}
        self.assertEqual(due, {"r1": False, "r2": True, "r3": True})

    def test_event_log(self):
        hh = run_new(scenario([mortgage(firstPaymentDate="2026-04-01"),
                               renewal("r1", "2026-03-01", "0.04", penalty="10"),
                               lump("l1", paymentDate="2026-04-01", amount="10")],
                              end="2026-04-01"))
        log = [(r["month"], r["event"], r["kind"], r["source"],
                [e["kind"] for e in hh.ledger.entries[slice(*r["ledger"])]])
               for r in hh.events.records if r["source"] in ("m1", "r1", "l1")]
        self.assertEqual(log, [
            ("2026-02", "LoanAdvance", "lifecycle", "m1", ["LOAN_ADVANCE"]),
            ("2026-03", "Renew", "state", "r1", []),
            ("2026-03", "RenewalPenalty", "flow", "r1", ["PENALTY"]),
            ("2026-03", "AccrueInterest", "valuation", "m1", ["LOAN_INTEREST"]),
            ("2026-04", "InterestAdjustment", "flow", "m1", ["INTEREST_ADJUSTMENT"]),
            ("2026-04", "LoanInterest", "valuation", "m1", ["LOAN_INTEREST"]),
            ("2026-04", "ScheduledPayment", "flow", "m1", ["LOAN_PAYMENT"]),
            ("2026-04", "LumpSumPrepayment", "flow", "l1", ["PREPAYMENT"])])

    def test_emitter_categories(self):
        _hh, runner = self.compile([mortgage(), renewal("r1", "2026-08-01", "0.04"),
                                    extra("x1", "2026-04-01", "5"),
                                    lump("l1", paymentDate="2026-06-01", amount="10")])
        self.assertLessEqual({e.CATEGORY for e in runner.emitters()},
                             {"initial", "one-shot", "recurring", "modifier", "scenario"})

if __name__ == "__main__":
    unittest.main()
