"""Builder cards and their estimates (ADR-0070), without the web layer.

    cd webapp && .venv/bin/python -m unittest state_machine.tests.test_cards
"""
import unittest
from decimal import Decimal

from state_machine import engine
from state_machine.cards import cards


def scenario(*items, **over):
    s = {"schemaVersion": 1, "name": "cards", "dollarsOf": "2030-01-01",
         "horizon": {"start": "2027-01-01", "end": "2040-12-01"},
         "openingCash": "100000", "effectiveTaxRate": "0.3", "annualInflation": "0.02",
         "items": list(items)}
    s.update(over)
    return s


A = {"type": "person", "id": "a", "name": "Ann"}
B = {"type": "person", "id": "b", "name": "Bob"}
JOB = {"type": "income", "id": "job", "name": "Job", "owner": "b", "startDate": "2027-01-01",
       "amount": "120000", "per": "year", "taxable": True, "indexing": "inflation"}
HOUSE = {"type": "property", "id": "h", "name": "House", "purchaseDate": "2027-01-01",
         "price": "500000", "annualAppreciation": "0"}
LOAN = {"type": "mortgage", "id": "m", "name": "Loan", "property": "h", "principal": "400000",
        "annualRate": "0.05", "amortizationYears": "25"}
TAX = {"type": "associatedExpense", "id": "t", "name": "Tax", "parent": "h",
       "annualRate": "0.01", "basis": "price"}


def find(layout, iid):
    for section in layout["sections"]:
        for cat in section["categories"]:
            for card in cat["cards"]:
                if card["id"] == iid:
                    return section, cat, card
                for row in card["rows"]:
                    if row["id"] == iid:
                        return section, cat, row
    return None


class Layout(unittest.TestCase):
    def test_sections_by_person_then_household(self):
        layout = cards(scenario(A, B, JOB, HOUSE, LOAN, TAX))
        self.assertEqual(layout["base"], "2030-01")
        self.assertEqual([s["title"] for s in layout["sections"]], ["Ann", "Bob", "Household"])
        section, cat, card = find(layout, "job")
        self.assertEqual((section["title"], cat["key"]), ("Bob", "income"))
        section, cat, card = find(layout, "h")
        self.assertEqual([r["id"] for r in card["rows"]], ["m", "t"])
        self.assertEqual([c["key"] for c in section["categories"]],
                         ["properties", "vehicles", "expenses"])      # no "other" when empty

    def test_a_withdrawal_is_also_shown_under_pensions(self):
        acc = {"type": "account", "id": "acc", "name": "RRSP", "owner": "b",
               "accountType": "rrsp", "openingBalance": "100000", "annualReturn": "0"}
        draw = {"type": "withdrawal", "id": "w", "name": "Draw", "account": "acc",
                "method": "amount", "amount": "1000", "per": "month",
                "startDate": "2027-01-01"}
        bob = next(s for s in cards(scenario(A, B, acc, draw))["sections"] if s["title"] == "Bob")
        cats = {c["key"]: c for c in bob["categories"]}
        account = cats["accounts"]["cards"][0]
        self.assertEqual([r["id"] for r in account["rows"]], ["w"])
        also = cats["pensions"]["cards"]
        self.assertEqual([(c["id"], c["via"]) for c in also], [("w", "RRSP")])
        # Counted once: under the account, not again under Pensions.
        self.assertEqual(cats["accounts"]["total"], Decimal("700.00"))   # after 30% tax
        self.assertIsNone(cats["pensions"]["total"])
        self.assertEqual(bob["total"], Decimal("700.00"))

    def test_without_persons_one_section_called_you(self):
        layout = cards(scenario(JOB | {"owner": ""}))
        self.assertEqual([s["title"] for s in layout["sections"]], ["You", "Household"])


class Estimates(unittest.TestCase):
    def estimate(self, iid, *items, **over):
        return find(cards(scenario(*items, **over)), iid)[2]["estimate"]

    def test_indexed_to_the_base_month_and_after_tax(self):
        # 120000 a year from 2027-01, +2% on each anniversary: three steps by 2030-01;
        # taxable, so 30% off (ADR-0070 amendment).
        gross = (10000 * Decimal("1.02") ** 3).quantize(Decimal("0.01"))
        estimate = self.estimate("job", A, B, JOB)
        self.assertEqual(estimate["monthly"], (gross * Decimal("0.7")).quantize(Decimal("0.01")))
        self.assertEqual(estimate["tax"], Decimal("0.3"))
        untaxed = self.estimate("job", A, B, dict(JOB, taxable=False))
        self.assertEqual((untaxed["monthly"], untaxed["tax"]), (gross, None))

    def test_retirement_rate_and_rrsp_withdrawal_rate(self):
        retire = {"type": "retirement", "id": "r", "owner": "b", "retirementDate": "2029-01-01"}
        bob = dict(B, retirementTaxRate="0.2")
        pension = {"type": "pension", "id": "p", "name": "DB", "owner": "b", "amount": "1000",
                   "per": "month", "startDate": "2029-01-01"}
        self.assertEqual(self.estimate("p", A, bob, retire, pension)["monthly"],
                         Decimal("800.00"))
        rrsp = {"type": "account", "id": "acc", "name": "RRSP", "owner": "b",
                "accountType": "rrsp", "openingBalance": "100000", "annualReturn": "0",
                "withdrawalTaxRate": "0.25"}
        draw = {"type": "withdrawal", "id": "w", "account": "acc", "method": "amount",
                "amount": "1000", "per": "month", "startDate": "2029-01-01"}
        self.assertEqual(self.estimate("w", A, bob, retire, rrsp, draw)["monthly"],
                         Decimal("750.00"))

    def test_adjustment_replaces_the_amount(self):
        adj = {"type": "adjustment", "id": "x", "flow": "job", "adjustmentDate": "2029-06-01",
               "amount": "150000", "per": "year"}
        self.assertEqual(self.estimate("job", A, B, JOB, adj)["monthly"], Decimal("8750.00"))

    def test_percentage_of_the_stated_basis_and_signs(self):
        self.assertEqual(self.estimate("t", HOUSE, TAX)["monthly"], Decimal("-416.67"))

    def test_mortgage_payment_close_to_the_run(self):
        s = scenario(HOUSE, LOAN, dollarsOf="2027-06-01")
        estimate = find(cards(s), "m")[2]["estimate"]["monthly"]
        paid = next(x["amount"] for x in engine.run_detailed(s)["ledger"]
                    if x["source"] == "m" and x["kind"] == "LOAN_PAYMENT" and x["month"] == "2027-06")
        self.assertLess(abs(-estimate - paid), Decimal("1.00"))

    def test_a_pension_not_started_shows_its_first_month_in_todays_dollars(self):
        retire = {"type": "retirement", "id": "r", "owner": "b", "retirementDate": "2035-01-01"}
        bob = dict(B, retirementTaxRate="0.2")
        pension = {"type": "pension", "id": "p", "name": "DB", "owner": "b", "amount": "1200",
                   "per": "month", "indexing": "inflation"}         # starts at retirement
        estimate = self.estimate("p", A, bob, retire, pension)
        self.assertEqual((estimate["monthly"], estimate["note"]), (None, "from 2035-01"))
        later = estimate["later"]
        self.assertEqual((later["at"], later["tax"]), ("2035-01", Decimal("0.2")))
        # Stated in base-date dollars and indexed with inflation: exactly 1200 today,
        # 960 after the 20% retirement tax.
        self.assertEqual((later["monthly"], later["gross"]), (Decimal("960.00"), Decimal("1200.00")))
        card = find(cards(scenario(A, bob, retire, pension)), "p")[2]
        self.assertIsNone(card["total"])                            # not in the totals

    def test_not_running_gets_a_note(self):
        later = dict(JOB, startDate="2032-01-01")
        estimate = self.estimate("job", A, B, later)
        self.assertEqual((estimate["monthly"], estimate["note"]), (None, "from 2032-01"))
        ended = dict(JOB, endDate="2028-12-01")
        self.assertEqual(self.estimate("job", A, B, ended)["note"], "until 2028-12")

    def test_a_switched_off_sale_does_not_count_as_a_second_sale(self):
        # Owner's report 2026-11-16: the planned sale switched off, a new one added.
        old = {"type": "sale", "id": "s1", "name": "Old", "property": "h",
               "saleDate": "2040-01-01", "enabled": False}
        new = {"type": "sale", "id": "s2", "name": "New", "property": "h",
               "saleDate": "2035-01-01"}
        layout = cards(scenario(HOUSE, old, new))
        self.assertEqual(find(layout, "s2")[2]["estimate"]["at"], "2035-01")

    def test_one_offs_and_card_totals(self):
        sale = {"type": "sale", "id": "s", "name": "Sell", "property": "h",
                "saleDate": "2035-01-01", "salePrice": "600000"}
        card = find(cards(scenario(HOUSE, LOAN, TAX, sale)), "h")[2]
        sale_row = next(r for r in card["rows"] if r["id"] == "s")
        self.assertEqual((sale_row["estimate"]["oneOff"], sale_row["estimate"]["at"]),
                         (Decimal("600000.00"), "2035-01"))
        monthly = [r["estimate"]["monthly"] for r in card["rows"] if r["estimate"]["monthly"]]
        self.assertEqual(card["total"], sum(monthly))               # one-offs not included


if __name__ == "__main__":
    unittest.main()
