"""Early-closure penalty by the term's formula (ADR-0073 decision 4, ADR-0047 amendment).

    cd webapp && .venv/bin/python -m unittest state_machine.tests.test_closure_penalty
"""
import unittest
from decimal import Decimal

from state_machine import engine, validation

D = Decimal


def scenario(*items):
    return {"schemaVersion": 1, "name": "closure", "jurisdiction": "CA",
            "horizon": {"start": "2027-01-01", "end": "2033-12-01"},
            "openingCash": "300000", "effectiveTaxRate": "0.3", "items": list(items)}


HOUSE = {"type": "property", "id": "h", "name": "House", "purchaseDate": "2027-01-01",
         "price": "500000", "annualAppreciation": "0"}
LOAN = {"type": "mortgage", "id": "m", "name": "Loan", "property": "h", "principal": "400000",
        "annualRate": "0.06", "amortizationYears": "25"}
SALE = {"type": "sale", "id": "s", "property": "h", "saleDate": "2029-01-01"}


def penalties(result):
    return [(x["month"], x["amount"], x["source"]) for x in result["ledger"]
            if x["kind"] == "PENALTY"]


def points(result, hid):
    return next(h for h in result["holdings"] if h["id"] == hid)["points"]


def refusal(s):
    try:
        validation.validate(s)
    except ValueError as e:
        return str(e)
    return ""


class Formula(unittest.TestCase):
    def test_flat_inside_the_term_none_after(self):
        loan = dict(LOAN, termMonths="60", penaltyMethod="flat", penaltyAmount="4000")
        r = engine.run_detailed(scenario(HOUSE, loan, SALE))
        self.assertEqual(penalties(r), [("2029-01", D("4000.00"), "s")])
        late = dict(SALE, saleDate="2032-02-01")              # the term ended 2032-01
        self.assertEqual(penalties(engine.run_detailed(scenario(HOUSE, loan, late))), [])

    def test_months_of_interest(self):
        loan = dict(LOAN, termMonths="60", penaltyMethod="monthsInterest", penaltyMonths="3")
        r = engine.run_detailed(scenario(HOUSE, loan, SALE))
        before = next(p for p in points(r, "m") if p["month"] == "2028-12")
        rate = before["rate"]
        (month, amount, _), = penalties(r)
        self.assertEqual(amount, (3 * before["closing"] * rate).quantize(D("0.01")))

    def test_share_of_the_interest_left_in_the_term(self):
        loan = dict(LOAN, termMonths="60", penaltyMethod="interestLeft", penaltyRate="0.5")
        r = engine.run_detailed(scenario(HOUSE, loan, SALE))
        (month, amount, _), = penalties(r)
        # 36 months left (2029-01 .. 2031-12) at ~6%/12 on ~385k: about half of ~67k.
        self.assertTrue(D(30000) < amount < D(36000), amount)

    def test_manual_penalty_wins_and_no_term_no_penalty(self):
        loan = dict(LOAN, termMonths="60", penaltyMethod="flat", penaltyAmount="4000")
        manual = dict(SALE, salePenalty="1000")
        self.assertEqual(penalties(engine.run_detailed(scenario(HOUSE, loan, manual))),
                         [("2029-01", D("1000.00"), "s")])
        self.assertEqual(penalties(engine.run_detailed(scenario(HOUSE, LOAN, SALE))), [])

    def test_a_renewal_starts_its_own_term(self):
        loan = dict(LOAN, termMonths="12", penaltyMethod="flat", penaltyAmount="4000")
        renewal = {"type": "renewal", "id": "r", "mortgage": "m", "startDate": "2028-01-01",
                   "annualRate": "0.05", "termMonths": "36", "penaltyMethod": "flat",
                   "penaltyAmount": "2500"}
        r = engine.run_detailed(scenario(HOUSE, loan, renewal, SALE))
        self.assertEqual(penalties(r), [("2029-01", D("2500.00"), "s")])

    def test_lump_sum_payoff_uses_the_formula(self):
        loan = dict(LOAN, termMonths="60", penaltyMethod="flat", penaltyAmount="4000")
        payoff = {"type": "lumpSum", "id": "l", "mortgage": "m", "paymentDate": "2028-06-01",
                  "payOff": True}
        r = engine.run_detailed(scenario(HOUSE, loan, payoff))
        self.assertEqual(penalties(r), [("2028-06", D("4000.00"), "l")])

    def test_points_carry_the_penalty_only_with_a_term(self):
        loan = dict(LOAN, termMonths="60", penaltyMethod="flat", penaltyAmount="4000")
        r = engine.run_detailed(scenario(HOUSE, loan))
        pts = points(r, "m")
        self.assertEqual(pts[0]["closingPenalty"], D("4000.00"))
        self.assertEqual(next(p for p in pts if p["month"] == "2031-12")["closingPenalty"], D("0.00"))
        plain = points(engine.run_detailed(scenario(HOUSE, LOAN)), "m")
        self.assertNotIn("closingPenalty", plain[0])


class Validation(unittest.TestCase):
    def test_fields(self):
        ok = dict(LOAN, termMonths="60", penaltyMethod="interestLeft", penaltyRate="0.5")
        self.assertEqual(refusal(scenario(HOUSE, ok)), "")
        self.assertIn("give termMonths and penaltyMethod together",
                      refusal(scenario(HOUSE, dict(LOAN, termMonths="60"))))
        self.assertIn("penaltyMethod interestLeft needs penaltyRate",
                      refusal(scenario(HOUSE, dict(ok, penaltyRate=""))))
        self.assertIn("whole number of months",
                      refusal(scenario(HOUSE, dict(ok, termMonths="2.5"))))
        self.assertIn("penaltyMethod must be one of",
                      refusal(scenario(HOUSE, dict(ok, penaltyMethod="ird"))))


if __name__ == "__main__":
    unittest.main()
