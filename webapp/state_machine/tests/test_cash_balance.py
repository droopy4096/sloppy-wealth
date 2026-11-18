"""Cash balance reconciliation (ADR-0063).

    cd webapp && .venv/bin/python -m unittest state_machine.tests.test_cash_balance
"""
import copy
import unittest
from decimal import Decimal

from state_machine import engine


def scenario(*items, **over):
    s = {"schemaVersion": 1, "name": "cash", "horizon": {"start": "2027-01-01", "end": "2028-12-01"},
         "openingCash": "10000", "effectiveTaxRate": "0.3",
         "items": [{"type": "income", "id": "job", "startDate": "2027-01-01", "amount": "1000",
                    "taxable": True}, *items]}
    s.update(over)
    return s


def bal(date, amount, id="b"):
    return {"type": "cashBalance", "id": id, "name": "Statement", "balanceDate": date,
            "balance": amount}


def run(s):
    return engine.run_detailed(copy.deepcopy(s))


def cash(r, month):
    return next(x["cash"] for x in r["rows"] if x["month"] == month)


class CashBalance(unittest.TestCase):
    def test_sets_the_month_end_balance_and_records_the_difference(self):
        r = run(scenario(bal("2027-06-01", "20000")))
        self.assertEqual(cash(r, "2027-05"), Decimal("13500.00"))   # 10000 + 5 x 700
        self.assertEqual(cash(r, "2027-06"), Decimal("20000.00"))
        self.assertEqual(cash(r, "2027-07"), Decimal("20700.00"))
        line = [x for x in r["ledger"] if x["kind"] == "CASH_RECONCILIATION"]
        self.assertEqual([(x["from"], x["to"], x["amount"]) for x in line],
                         [(None, "cash", Decimal("5800.00"))])
        self.assertEqual(r["tax"]["2027-06"]["taxable"], Decimal("1000.00"))   # not taxed

    def test_lower_balance_moves_cash_out(self):
        r = run(scenario(bal("2027-06-01", "1000")))
        line = [x for x in r["ledger"] if x["kind"] == "CASH_RECONCILIATION"][0]
        self.assertEqual((line["from"], line["to"], line["amount"]), ("cash", None, Decimal("13200.00")))
        log = [e["detail"] for e in r["events"] if e["event"] == "CashReconciled"]
        self.assertEqual(log, ["cash set to 1000.00 (was 14200.00, -13200.00)"])

    def test_several_and_last_in_a_month_wins(self):
        r = run(scenario(bal("2027-06-01", "1000"), bal("2027-06-01", "5000", id="c"),
                         bal("2028-01-01", "0", id="d")))
        self.assertEqual(cash(r, "2027-06"), Decimal("5000.00"))
        self.assertEqual(cash(r, "2028-01"), Decimal("0.00"))

    def test_equal_balance_records_nothing(self):
        r = run(scenario(bal("2027-01-01", "10700")))
        self.assertFalse([x for x in r["ledger"] if x["kind"] == "CASH_RECONCILIATION"])

    def test_validation(self):
        with self.assertRaisesRegex(ValueError, "balanceDate must be within the horizon"):
            engine.validate(scenario(bal("2030-01-01", "1")))
        with self.assertRaisesRegex(ValueError, "missing field 'balanceDate'"):
            engine.validate(scenario({"type": "cashBalance", "balance": "1"}))


if __name__ == "__main__":
    unittest.main()
