"""WP8 results: rows, holdings points, loan flows, real net worth, tax passthrough.

The results of the real engine (``results.assemble`` after ``api.simulate``) on the samples,
a kitchen-sink scenario and cash-only scenarios are golden values frozen from the
iteration-1 engine (support.assert_golden; the WP8 replay of the reference trace is gone
with the reference). Hand-built pieces are checked directly.

Run from webapp/:  .venv/bin/python -m unittest state_machine.tests.test_wp8_results
"""
import copy
import unittest
from decimal import Decimal

from state_machine import api, results
from state_machine.base import Aggregate
from state_machine.household import Household

from .support import assert_golden, sample, scenario

SAMPLES = ["single-house.json", "single-house-prepay.json", "single-house-renewals.json",
           "single-house-sold.json", "rent.json", "household-baseline.json"]


# ---------- fakes ----------
class Fake(Aggregate):
    """A holding of any kind with a settable reported rate."""

    def __init__(self, id, name, slot, kind, balance, rate):
        self.kind = kind
        self.rate = rate
        super().__init__(id, name, slot, balance)

    @property
    def report_rate(self):
        return self.rate


def kitchen_sink():
    """Invented figures covering the results hazards: pre-horizon property, property
    bought in the horizon with an accruing mortgage (firstPaymentDate) and a sale, a
    renewal, a lump-sum payoff, a vehicle bought after the horizon (never created) with
    its never-created mortgage, an account opened later from cash, an account at the
    start, a duplicate holding id (first slot, last name), an item without id, a pension
    indexed with inflation, retirement with a tax rate switch, inflation with dollarsOf."""
    items = [
        {"type": "property", "id": "cottage", "name": "Cottage", "purchaseDate": "2020-05-01",
         "price": "300000", "marketValue": "350000", "annualAppreciation": "0.03"},
        {"type": "account", "id": "dup", "name": "First name", "accountType": "tfsa",
         "openingBalance": "1000", "annualReturn": "0.04"},
        {"type": "mortgage", "id": "mtg", "name": "House loan", "property": "house",
         "principal": "400000", "annualRate": "0.05", "amortizationYears": "25",
         "firstPaymentDate": "2026-06-01"},
        {"type": "property", "id": "house", "name": "House", "purchaseDate": "2026-03-01",
         "price": "500000", "annualAppreciation": "0.04"},
        {"type": "income", "id": "job", "name": "Job", "startDate": "2026-01-01",
         "amount": "9000", "per": "month", "taxable": True, "endsAtRetirement": True},
        {"type": "expense", "id": "life", "name": "Living", "startDate": "2026-01-01",
         "amount": "2500", "per": "month", "indexing": "inflation"},
        {"type": "renewal", "id": "ren", "mortgage": "mtg", "startDate": "2026-09-01",
         "annualRate": "0.045", "penalty": "1500"},
        {"type": "account", "id": "rrsp", "name": "RRSP", "accountType": "rrsp",
         "openingBalance": "20000", "annualReturn": "0.06", "openedDate": "2026-04-01",
         "openingFrom": "cash"},
        {"type": "contribution", "id": "c1", "account": "rrsp", "startDate": "2026-05-01",
         "amount": "500", "per": "month", "employerMatch": "0.5"},
        {"type": "account", "id": "dup", "name": "Last name", "accountType": "nonRegistered",
         "openingBalance": "5000", "annualReturn": "0.05"},
        {"type": "vehicle", "id": "car", "name": "Future car", "purchaseDate": "2031-01-01",
         "price": "40000", "annualDepreciation": "0.15", "annualMaintenance": "2000"},
        {"type": "mortgage", "id": "carloan", "name": "Car loan", "startDate": "2031-01-01",
         "principal": "20000", "annualRate": "0.07", "amortizationYears": "5"},
        {"type": "pension", "id": "db", "name": "DB", "amount": "1500",
         "indexing": "inflation"},
        {"type": "retirement", "id": "ret", "name": "Retire", "retirementDate": "2027-07-01"},
        {"type": "sale", "id": "sell-house", "name": "Sell", "property": "house",
         "saleDate": "2027-03-01", "sellingCostRate": "0.04", "salePenalty": "2000"},
        {"type": "lumpSum", "mortgage": "mtg", "paymentDate": "2027-01-01", "amount": "10000"},
        {"type": "vehicle", "name": "No id", "purchaseDate": "2026-02-01", "price": "15000",
         "annualDepreciation": "0.2", "annualMaintenance": "600"},
        {"type": "withdrawal", "id": "w", "account": "rrsp", "method": "percent",
         "annualRate": "0.04", "startDate": "2027-08-01"},
    ]
    return scenario(items, start="2026-01-01", end="2027-12-01", cash="150000",
                    annualInflation="0.025", dollarsOf="2025-07-01", effectiveTaxRate="0.3",
                    retirementTaxRate="0.2")


class ResultsGolden(unittest.TestCase):
    def assertParity(self, s):
        new = results.assemble(api.simulate(copy.deepcopy(s)))
        self.assertEqual(list(new), ["rows", "holdings", "ledger", "tax"])
        assert_golden(self, "rows, holdings, ledger, tax", new)
        return new

    def test_samples(self):
        for name in SAMPLES:
            with self.subTest(name):
                self.assertParity(sample(name))

    def test_kitchen_sink(self):
        r = self.assertParity(kitchen_sink())
        by_id = {h["id"]: h for h in r["holdings"]}
        # Slot order incl. never-created holdings; duplicate id: first slot, last name.
        self.assertEqual([h["id"] for h in r["holdings"]],
                         ["cash", "cottage", "dup", "mtg", "house", "rrsp", "car",
                          "carloan", "db", "item16"])
        self.assertEqual(by_id["dup"]["name"], "Last name")
        self.assertEqual(by_id["car"]["points"], [])
        self.assertEqual(by_id["carloan"]["points"], [])
        self.assertEqual(by_id["carloan"]["group"], "debts")
        # Creation month: opening None.
        self.assertIsNone(by_id["house"]["points"][0]["opening"])
        self.assertEqual(by_id["house"]["points"][0]["month"], "2026-03")
        # Sold house keeps emitting 0.00 points.
        last = by_id["house"]["points"][-1]
        self.assertEqual((last["month"], repr(last["closing"])), ("2027-12", "Decimal('0.00')"))
        # Loan flows: Decimal('0') defaults with no flows, key order.
        mtg = by_id["mtg"]["points"]
        self.assertEqual(list(mtg[0]), ["month", "opening", "closing", "rate", "interest",
                                        "paid", "principalPaid"])
        self.assertEqual(repr(mtg[0]["interest"]), "Decimal('0')")
        self.assertEqual(list(r["rows"][0]), ["month", "cash", "investments", "assets", "debts",
                                              "assetsNetWorth", "netWorth", "realNetWorth",
                                              "realAssetsNetWorth"])

    def test_cash_only_and_dollars_of(self):
        for extra in ({}, {"annualInflation": "0.02"},
                      {"annualInflation": 0.03, "dollarsOf": "2024-03-01"},
                      {"annualInflation": "0.03", "dollarsOf": "2027-06-01"},
                      {"annualInflation": 0, "dollarsOf": "2030-01-01"}):
            with self.subTest(extra):
                self.assertParity(scenario([], cash="1234.5", **extra))


class RealEngineCashOnly(unittest.TestCase):
    """No fakes: the real registry (results hook discovered) on an item-less scenario."""

    def test_assemble_after_simulate(self):
        s = scenario([], cash="5000", annualInflation="0.02", dollarsOf="2025-01-01")
        new = results.assemble(api.simulate(copy.deepcopy(s)))
        # The whole result, tax detail included, equals api.run_detailed's.
        detailed = api.run_detailed(copy.deepcopy(s))
        for key in ("rows", "holdings", "ledger", "tax"):
            self.assertEqual(repr(new[key]), repr(detailed[key]), key)
        assert_golden(self, "rows, holdings, ledger, tax", new)
        self.assertEqual(new["holdings"][0]["points"][0]["opening"], Decimal("5000.00"))


class HandBuilt(unittest.TestCase):
    """Direct checks of the pieces (golden values frozen from the iteration-1 functions)."""

    def test_row_golden(self):
        s = scenario([], cash="100")
        hh = Household(copy.deepcopy(s))
        specs = [("a", "account", Decimal("10.5")), ("p", "pension", Decimal("1E+2")),
                 ("h", "property", Decimal("300000.00")), ("v", "vehicle", Decimal("0.00")),
                 ("m", "mortgage", Decimal("-0.01")), ("m2", "mortgage", Decimal("250000.00"))]
        for n, (hid, kind, bal) in enumerate(specs):
            hh.add(Fake(hid, hid, n, kind, bal, None))
        assert_golden(self, "row", results.row(hh, hh.start))

    def test_loan_flows_and_add_real_net_worth(self):
        ledger = [
            {"month": "2026-01", "kind": "LOAN_INTEREST", "from": "m", "to": None,
             "amount": Decimal("10.00"), "source": "m"},
            {"month": "2026-01", "kind": "LOAN_PAYMENT", "from": "cash", "to": "m",
             "amount": Decimal("100.00"), "source": "m"},
            {"month": "2026-01", "kind": "PREPAYMENT", "from": None, "to": "m",
             "amount": Decimal("5.00"), "source": "x"},
            {"month": "2026-02", "kind": "INTEREST_ADJUSTMENT", "from": "cash", "to": "m",
             "amount": Decimal("3.33"), "source": "m"},
            {"month": "2026-02", "kind": "LOAN_PAYOFF", "from": "cash", "to": "m",
             "amount": Decimal("7.00"), "source": "h"},
            {"month": "2026-02", "kind": "LOAN_INTEREST", "from": "m", "to": None,
             "amount": Decimal("1.50"), "source": "m"},
        ]
        flows = results.loan_flows(ledger)
        self.assertEqual(repr(flows), repr({("2026-01", "m"): [Decimal("10.00"),
                                                               Decimal("105.00")],
                                            ("2026-02", "m"): [Decimal("1.50"),
                                                               Decimal("10.33")]}))
        for s in (scenario([], annualInflation="0.021", dollarsOf="2023-02-01"),
                  scenario([], annualInflation="0.021"), scenario([])):
            rows = [{"netWorth": Decimal(k * 1000) + Decimal("0.07"),
                     "assetsNetWorth": Decimal("-12.34") * k} for k in range(30)]
            assert_golden(self, "add_real_net_worth",
                          results.add_real_net_worth(copy.deepcopy(rows), s))

    def test_assemble_requires_recorder(self):
        with self.assertRaises(RuntimeError):
            results.assemble(Household(scenario([])))


if __name__ == "__main__":
    unittest.main()
