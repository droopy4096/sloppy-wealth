"""Renewal keepPayment (ADR-0043 amendment, C-M7) in the engine and the builder
form: the payment is kept and the remaining amortization derived; fallback to a
recomputed payment when the payment cannot repay the balance in the remaining term."""
import copy
import unittest
from decimal import Decimal

import app
from browser import Browser
from state_machine import engine
from state_machine.arith import keep_payment_months


def scenario(renewal=None, extras=(), first_payment=None, end="2056-12-01"):
    mtg = {"type": "mortgage", "id": "mtg", "name": "M", "startDate": "2027-01-01",
           "principal": "400000", "annualRate": "0.05", "amortizationYears": "25"}
    if first_payment:
        mtg["firstPaymentDate"] = first_payment
    items = [mtg]
    for n, (start, stop, amount) in enumerate(extras):
        items.append({"type": "extraPayment", "id": f"x{n}", "name": "X", "mortgage": "mtg",
                      "startDate": start, "endDate": stop, "monthlyAmount": amount})
    if renewal is not None:
        items.append(dict({"type": "renewal", "id": "ren", "name": "R", "mortgage": "mtg",
                           "startDate": "2032-01-01", "annualRate": "0.04"}, **renewal))
    return {"schemaVersion": 1, "name": "kp", "openingCash": "100000",
            "horizon": {"start": "2027-01-01", "end": end}, "items": items}


def without_events(s):
    """run_detailed without the event log (whose entries note the keepPayment fallback)."""
    return {k: v for k, v in engine.run_detailed(copy.deepcopy(s)).items() if k != "events"}


def payments(s):
    """Scheduled loan payments by month."""
    return {x["month"]: x["amount"] for x in engine.run_detailed(copy.deepcopy(s))["ledger"]
            if x["kind"] == "LOAN_PAYMENT"}


def opening(s, month):
    detail = engine.run_detailed(copy.deepcopy(s))["holdings"]
    mtg = next(h for h in detail if h["id"] == "mtg")
    return next(p["opening"] for p in mtg["points"] if p["month"] == month)


EXTRAS = [("2027-02-01", "2031-12-01", "500")]


class KeepPayment(unittest.TestCase):
    def test_default_false_is_unchanged(self):
        absent, false = scenario({}), scenario({"keepPayment": False})
        self.assertEqual(engine.run_detailed(absent), engine.run_detailed(false))

    def test_payment_unchanged_across_renewal(self):
        p = payments(scenario({"keepPayment": True}))
        self.assertEqual(p["2032-01"], p["2031-12"])
        self.assertEqual(p["2040-06"], p["2031-12"])
        # Default: lower rate, lower payment.
        self.assertLess(payments(scenario({}))["2032-01"], p["2031-12"])

    def test_earlier_payoff_than_default(self):
        keep, default = payments(scenario({"keepPayment": True})), payments(scenario({}))
        self.assertLess(max(keep), max(default))
        self.assertEqual(max(default), "2052-01")      # the original 300 months from 2027-02
        last = keep[max(keep)]
        self.assertLessEqual(last, keep["2032-01"])     # smaller final payment

    def test_derived_months(self):
        s = scenario({"keepPayment": True}, extras=EXTRAS)
        p = payments(s)
        B, P, r = opening(s, "2032-01"), p["2031-12"], engine.monthly_rate("0.04")
        n = len([m for m in p if m >= "2032-01"])
        self.assertLessEqual(engine.annuity(B, r, n), P)
        self.assertGreater(engine.annuity(B, r, n - 1), P)
        self.assertEqual(n, keep_payment_months(B, r, P, 240))
        # Closed form: n = ceil(-ln(1 - rB/P) / ln(1 + r)).
        x = -(1 - r * B / P).ln() / (1 + r).ln()
        self.assertEqual(n, int(x.to_integral_value(rounding="ROUND_CEILING")))

    def test_prepayments_shorten_with_keep_lower_payment_without(self):
        keep_x = payments(scenario({"keepPayment": True}, extras=EXTRAS))
        keep = payments(scenario({"keepPayment": True}))
        self.assertLess(max(keep_x), max(keep))
        self.assertEqual(keep_x["2032-01"], keep["2032-01"])
        lower_x, lower = payments(scenario({}, extras=EXTRAS)), payments(scenario({}))
        self.assertLess(lower_x["2032-01"], lower["2032-01"])
        self.assertEqual(max(lower_x), max(lower))

    def test_fallback_when_payment_cannot_cover_interest(self):
        # 20%: the monthly interest exceeds the kept payment.
        keep = scenario({"keepPayment": True, "annualRate": "0.2"})
        self.assertEqual(without_events(keep), without_events(scenario({"annualRate": "0.2"})))
        p = payments(keep)
        self.assertGreater(p["2032-01"], p["2031-12"])

    def test_fallback_when_derived_term_exceeds_remaining(self):
        # 6%: the payment covers the interest but needs more than the 240 months left.
        keep = scenario({"keepPayment": True, "annualRate": "0.06"})
        self.assertEqual(without_events(keep), without_events(scenario({"annualRate": "0.06"})))

    def test_zero_rate(self):
        s = scenario({"keepPayment": True, "annualRate": "0"})
        p = payments(s)
        B, P = opening(s, "2032-01"), p["2031-12"]
        n = len([m for m in p if m >= "2032-01"])
        self.assertEqual(n, int((B / P).to_integral_value(rounding="ROUND_CEILING")))
        self.assertEqual(p["2032-01"], P)

    def test_renewal_in_accruing_month_keeps_scheduled_payment(self):
        s = scenario({"keepPayment": True, "startDate": "2027-03-01"},
                     first_payment="2027-06-01")
        original = engine.mortgage_terms(s["items"][0])[1]
        p = payments(s)
        self.assertEqual(p["2027-06"], original)
        self.assertLess(max(p), max(payments(scenario({"startDate": "2027-03-01"},
                                                      first_payment="2027-06-01"))))

    def test_validation(self):
        with self.assertRaisesRegex(ValueError, "keepPayment and amortizationYears are "
                                                "mutually exclusive"):
            engine.validate(scenario({"keepPayment": True, "amortizationYears": "20"}))
        for bad in ("true", "yes", 1, 0, None):
            with self.assertRaisesRegex(ValueError, "keepPayment must be true or false"):
                engine.validate(scenario({"keepPayment": bad}))
        engine.validate(scenario({"keepPayment": False, "amortizationYears": "20"}))


class Form(unittest.TestCase):
    def test_form_stores_bool_and_table_shows_it(self):
        client = Browser()
        client.get("/")
        client.post("/items/add", data={"type": "mortgage", "name": "M",
                                         "startDate": "2027-01-01", "principal": "400000",
                                         "annualRate": "5", "amortizationYears": "25"})
        mtg = client.scenario["items"][-1]["id"]
        page = client.get("/").data
        self.assertIn(b"yes: keep the payment, shorten the amortization", page)
        self.assertIn(b"no: lower the payment", page)
        for choice, stored in (("yes", True), ("no", False)):
            client.post("/items/add", data={"type": "renewal", "name": f"R{choice}",
                                             "mortgage": mtg, "startDate": "2032-01-01",
                                             "annualRate": "4", "keepPayment": choice,
                                             "amortizationYears": ""})
            item = client.scenario["items"][-1]
            self.assertIs(item["keepPayment"], stored)
            self.assertIn(f"keepPayment={choice}".encode(), client.get("/").data)
            client.scenario["items"].pop()
        # Exclusive with amortizationYears: rejected, not added.
        client.post("/items/add", data={"type": "renewal", "name": "Rx", "mortgage": mtg,
                                         "startDate": "2032-01-01", "annualRate": "4",
                                         "keepPayment": "yes", "amortizationYears": "20"})
        self.assertNotEqual(client.scenario["items"][-1]["type"], "renewal")


if __name__ == "__main__":
    unittest.main()
