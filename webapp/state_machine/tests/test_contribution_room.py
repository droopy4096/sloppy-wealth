"""Contribution room limits (ADR-0060).

    cd webapp && .venv/bin/python -m unittest state_machine.tests.test_contribution_room
"""
import copy
import unittest
from decimal import Decimal

from state_machine import engine


def scenario(*items, salary="6000", earned=None, **over):
    job = {"type": "income", "id": "job", "name": "Job", "startDate": "2027-01-01",
           "amount": salary, "per": "month", "taxable": True}
    if earned is not None:
        job["earnedIncome"] = earned
    s = {"schemaVersion": 1, "name": "room", "horizon": {"start": "2027-01-01",
                                                         "end": "2030-12-01"},
         "openingCash": "100000", "effectiveTaxRate": "0.3", "annualInflation": "0.022",
         "items": [job, {"type": "account", "id": "r", "name": "RRSP", "accountType": "rrsp",
                         "openingBalance": "0", "annualReturn": "0"},
                   {"type": "account", "id": "t", "name": "TFSA", "accountType": "tfsa",
                    "openingBalance": "5000", "annualReturn": "0"}, *items]}
    s.update(over)
    return s


def rrsp_room(room="10000", asof="2027-01-01", **kw):
    return dict({"type": "contributionRoom", "id": "rr", "name": "RRSP room",
                 "accountType": "rrsp", "room": room, "roomAsOfDate": asof,
                 "yearlyMax": "33810", "maxYear": "2026"}, **kw)


def tfsa_room(room="0", asof="2027-01-01", **kw):
    return dict({"type": "contributionRoom", "id": "tr", "name": "TFSA room",
                 "accountType": "tfsa", "room": room, "roomAsOfDate": asof,
                 "yearlyMax": "7000", "maxYear": "2026", "indexing": "inflation"}, **kw)


def transfer(account, amount, date, id="x"):
    return {"type": "transfer", "id": id, "account": account, "amount": amount,
            "transferDate": date}


def run(s):
    return engine.run_detailed(copy.deepcopy(s))


def moved(result, kind, month=None, to=None):
    return sum((x["amount"] for x in result["ledger"] if x["kind"] == kind
                and (month is None or x["month"] == month) and (to is None or x["to"] == to)),
               Decimal(0))


def row(result, month):
    return next(r for r in result["rows"] if r["month"] == month)


class Capping(unittest.TestCase):
    def test_transfer_capped_excess_stays_in_cash_and_only_room_is_deducted(self):
        r = run(scenario(rrsp_room(), transfer("r", "25000", "2027-03-01")))
        self.assertEqual(moved(r, "TRANSFER", "2027-03"), Decimal("10000.00"))
        self.assertEqual(row(r, "2027-03")["rrspRoom"], Decimal("0.00"))
        uncapped = run(scenario(transfer("r", "25000", "2027-03-01")))
        # Both deductions exceed March's income (no tax that month): the excess is in cash.
        self.assertEqual(row(r, "2027-03")["cash"] - row(uncapped, "2027-03")["cash"],
                         Decimal("15000.00"))
        self.assertEqual(r["tax"]["2027-03"]["deductions"], Decimal("10000.00"))
        detail = [e["detail"] for e in r["events"] if e["source"] == "x"]
        self.assertIn("capped at room: 10000.00 of 25000.00", detail[0])

    def test_without_room_item_nothing_changes(self):
        s = scenario(transfer("r", "25000", "2027-03-01"))
        r = run(s)
        self.assertEqual(moved(r, "TRANSFER"), Decimal("25000.00"))
        self.assertNotIn("rrspRoom", r["rows"][0])

    def test_before_the_as_of_month_nothing_is_checked(self):
        r = run(scenario(rrsp_room(asof="2027-06-01"), transfer("r", "25000", "2027-03-01"),
                         transfer("r", "25000", "2027-07-01", id="y")))
        self.assertEqual(moved(r, "TRANSFER", "2027-03"), Decimal("25000.00"))
        self.assertIsNone(row(r, "2027-05")["rrspRoom"])
        self.assertEqual(moved(r, "TRANSFER", "2027-07"), Decimal("10000.00"))

    def test_contribution_and_match_capped(self):
        c = {"type": "contribution", "id": "c", "account": "r", "startDate": "2027-01-01",
             "amount": "4000", "per": "month", "employerMatch": "0.5"}
        r = run(scenario(rrsp_room(room="9000"), c))
        jan, feb = "2027-01", "2027-02"
        self.assertEqual(moved(r, "CONTRIBUTION", jan), Decimal("4000.00"))
        self.assertEqual(moved(r, "EMPLOYER_MATCH", jan), Decimal("2000.00"))
        self.assertEqual(moved(r, "CONTRIBUTION", feb), Decimal("3000.00"))   # 3000 left
        self.assertEqual(moved(r, "EMPLOYER_MATCH", feb), Decimal("0"))       # no room left
        self.assertEqual(moved(r, "CONTRIBUTION", "2027-03"), Decimal("0"))

    def test_opening_from_cash_is_current_state_not_capped(self):
        """An opening balance (from cash or outside) is the account's current state, not
        a contribution: moved in full, no room used (owner 2026-11-18, ADR-0060 am.)."""
        acct = {"type": "account", "id": "n", "name": "New TFSA", "accountType": "tfsa",
                "openingBalance": "20000", "openedDate": "2027-05-01", "openingFrom": "cash",
                "annualReturn": "0"}
        later = transfer("n", "6000", "2027-06-01")
        r = run(scenario(tfsa_room(room="8000"), acct, later))
        self.assertEqual(moved(r, "OPENING_TRANSFER"), Decimal("20000.00"))
        self.assertEqual(moved(r, "TRANSFER", to="n"), Decimal("6000.00"))   # room intact

    def test_accounts_of_a_type_share_the_room(self):
        acct = {"type": "account", "id": "r2", "name": "RRSP 2", "accountType": "rrsp",
                "openingBalance": "0", "annualReturn": "0"}
        r = run(scenario(acct, rrsp_room(), transfer("r", "6000", "2027-03-01"),
                         transfer("r2", "6000", "2027-03-01", id="y")))
        self.assertEqual(moved(r, "TRANSFER", to="r"), Decimal("6000.00"))
        self.assertEqual(moved(r, "TRANSFER", to="r2"), Decimal("4000.00"))

    def test_non_registered_never_capped(self):
        acct = {"type": "account", "id": "n", "name": "Cash acct", "accountType": "nonRegistered",
                "openingBalance": "0", "annualReturn": "0"}
        r = run(scenario(acct, rrsp_room(room="0"), tfsa_room(), transfer("n", "50000", "2027-03-01")))
        self.assertEqual(moved(r, "TRANSFER"), Decimal("50000.00"))


class NewRoomEachYear(unittest.TestCase):
    def test_rrsp_18_percent_of_last_years_earned_income(self):
        r = run(scenario(rrsp_room(room="0")))
        self.assertEqual(row(r, "2027-12")["rrspRoom"], Decimal("0.00"))
        self.assertEqual(row(r, "2028-01")["rrspRoom"], Decimal("12960.00"))   # 72000 x 18%
        self.assertEqual(row(r, "2029-01")["rrspRoom"], Decimal("25920.00"))   # carried forward

    def test_rrsp_dollar_maximum_indexed_and_rounded_to_10(self):
        r = run(scenario(rrsp_room(room="0", indexing="custom", indexRate="0.03"),
                         salary="25000"))
        # 2028 maximum: 33810 x 1.03^2 = 35868.97 -> 35870.
        self.assertEqual(row(r, "2028-01")["rrspRoom"], Decimal("35870.00"))

    def test_earned_income_flag(self):
        r = run(scenario(rrsp_room(room="0"), earned=False))
        self.assertEqual(row(r, "2028-01")["rrspRoom"], Decimal("0.00"))
        untaxed = scenario(rrsp_room(room="0"))
        untaxed["items"][0]["taxable"] = False
        self.assertEqual(row(run(untaxed), "2028-01")["rrspRoom"], Decimal("0.00"))
        untaxed["items"][0]["earnedIncome"] = True
        self.assertEqual(row(run(untaxed), "2028-01")["rrspRoom"], Decimal("12960.00"))

    def test_tfsa_limit_indexed_rounded_to_500_and_withdrawals_added_back(self):
        w = {"type": "withdrawal", "id": "w", "account": "t", "method": "amount",
             "startDate": "2027-06-01", "endDate": "2027-07-01", "amount": "1000"}
        r = run(scenario(tfsa_room(room="100"), w))
        # 2028: 7000 x 1.022^2 = 7311.39 -> 7500, plus 2000 withdrawn in 2027.
        self.assertEqual(row(r, "2028-01")["tfsaRoom"], Decimal("9600.00"))
        self.assertEqual(row(r, "2029-01")["tfsaRoom"], Decimal("17100.00"))  # 7472 -> 7500
        log = [e for e in r["events"] if e["event"] == "RoomYear" and e["month"] == "2028-01"]
        self.assertEqual(log[0]["kind"], "state")
        self.assertIn("100.00 + 9500", log[0]["detail"])

    def test_as_of_in_january_already_includes_that_years_room(self):
        r = run(scenario(rrsp_room(room="5000", asof="2028-01-01")))
        self.assertEqual(row(r, "2028-01")["rrspRoom"], Decimal("5000.00"))
        self.assertEqual(row(r, "2029-01")["rrspRoom"], Decimal("17960.00"))


class Validation(unittest.TestCase):
    def check(self, item, message, *more):
        with self.assertRaisesRegex(ValueError, message):
            engine.validate(scenario(item, *more))

    def test_errors(self):
        self.check(rrsp_room(accountType="nonRegistered"), "accountType must be rrsp or tfsa")
        self.check(rrsp_room(), "only one contributionRoom item per account type",
                   rrsp_room(id="rr2"))
        self.check(rrsp_room(roomAsOfDate="2026-01-01"), "roomAsOfDate must be within")
        self.check(rrsp_room(room="-1"), "room must not be negative")
        self.check(rrsp_room(maxYear="twenty"), "maxYear must be a year")
        self.check(rrsp_room(incomeRate="18"), "incomeRate must be a fraction")
        self.check(rrsp_room(indexing="wages"), "indexing must be none, inflation or custom")
        bad = scenario()
        bad["items"][0]["earnedIncome"] = "yes"
        with self.assertRaisesRegex(ValueError, "earnedIncome must be true or false"):
            engine.validate(bad)
        engine.validate(scenario(rrsp_room(), tfsa_room()))


if __name__ == "__main__":
    unittest.main()
