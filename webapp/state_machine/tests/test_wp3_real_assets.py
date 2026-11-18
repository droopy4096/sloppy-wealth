"""WP3 real assets: RealEstate, Vehicle, Purchase/CarryIn, Improvement, MarketAdjustment,
Sale (incl. LOAN_PAYOFF), growth and maintenance; ledger, balances and holdings are
golden values frozen from the iteration-1 engine (support.assert_golden).

Scenarios contain only WP3 item types (and cash). The secured-loan payoff and the
retirement item use small local test doubles registered in an isolated registry.
Run from webapp/:
    .venv/bin/python -m unittest state_machine.tests.test_wp3_real_assets
"""
import random
import unittest
from decimal import Decimal

from state_machine import api, compiler
from state_machine.arith import mortgage_terms, money
from state_machine.base import Aggregate
from state_machine.clock import Order
from state_machine.dates import month_index
from state_machine.emitters import (FlowEvent, LifecycleEvent, OneShotEmitter,
                                    RecurringEmitter)
from state_machine.holdings.real_estate import RealEstate
from state_machine.holdings.vehicle import Vehicle

from .support import assert_golden, balances, scenario, without_tax


def house(id="h", date="2026-03-01", price=500000, appr=0.03, **kw):
    return dict(type="property", id=id, name=kw.pop("name", f"House {id}"),
                purchaseDate=date, price=price, annualAppreciation=appr, **kw)


def car(id="v", date="2026-02-01", price=30000, dep=0.15, maint=1200, **kw):
    return dict(type="vehicle", id=id, purchaseDate=date, price=price,
                annualDepreciation=dep, annualMaintenance=maint, **kw)


# ---------- test doubles for item types owned by other WPs ----------

class FakeLoan(Aggregate):
    """Minimal stand-in for WP4's Mortgage: the reference's regular path only (advance,
    interest, annuity payment, last payment clears; no renewal/accrual/extras)."""
    kind = "mortgage"

    def __init__(self, id, name, item_index, balance, secured_by, rate, payment, left):
        super().__init__(id, name, item_index, balance)
        self.secured_by, self.rate, self.payment, self.left = secured_by, rate, payment, left

    @property
    def report_rate(self):
        return self.rate


    def pay_off(self, household, source, kind="LOAN_PAYOFF"):
        """Same contract as Mortgage.pay_off (the Sale's LoanPayoff follow-up calls it)."""
        if self.balance:
            return household.move(kind, "cash", self.id, self.balance, source)
        return Decimal("0.00")


class FakeAdvanceEvent(LifecycleEvent):
    def __init__(self, make, amount):
        self.make, self.amount = make, amount

    def apply(self, household):
        loan = household.add(self.make())
        household.move("LOAN_ADVANCE", loan.id, "cash", self.amount, loan.id)


class FakeAdvance(OneShotEmitter):
    ORDER = Order.ACQUIRE

    def __init__(self, month, make, amount):
        super().__init__(month)
        self.make, self.amount = make, amount

    def emit(self, month, household):
        return (FakeAdvanceEvent(self.make, self.amount),)


class FakeServiceEvent(FlowEvent):
    def __init__(self, loan_id):
        self.loan_id = loan_id

    def apply(self, household):
        h = household[self.loan_id]
        household.move("LOAN_INTEREST", h.id, None, h.balance * h.rate, h.id)
        h.left -= 1
        owed = h.balance
        payment = owed if h.left <= 0 else min(h.payment, owed)
        household.move("LOAN_PAYMENT", household.recurring_source, h.id, payment, h.id)


class FakeService(RecurringEmitter):
    ORDER = Order.SERVICE_DEBT

    def __init__(self, loan_id):
        super().__init__()
        self.loan_id = loan_id

    def emit(self, month, household):
        if household.is_opened(self.loan_id) and household[self.loan_id].balance > 0:
            return (FakeServiceEvent(self.loan_id),)
        return None


def fake_mortgage(item, ctx):
    r, payment, n = mortgage_terms(item)
    if item.get("startDate"):
        at = month_index(item["startDate"], "startDate")
    else:
        at = month_index(ctx.env.properties[item["property"]]["purchaseDate"], "")

    def make():
        return FakeLoan(ctx.id, ctx.name, ctx.ordinal, Decimal("0.00"),
                        item.get("property") or None, r, payment, n)

    yield FakeAdvance(at, make, money(Decimal(str(item["principal"]))))
    yield FakeService(ctx.id)


def fake_retirement(item, ctx):
    return []        # the compile-time retirement month comes from dates.retirement_date


def loan(id, prop=None, principal=300000, rate=0.05, years=25, **kw):
    d = dict(type="mortgage", id=id, principal=principal, annualRate=rate,
             amortizationYears=years, **kw)
    if prop:
        d["property"] = prop
    return d


class Parity(unittest.TestCase):
    def setUp(self):
        self._registry = compiler.isolated_registry(empty=False)
        self._registry.__enter__()
        compiler._ITEM_TYPES["mortgage"] = fake_mortgage
        compiler._ITEM_TYPES["retirement"] = fake_retirement

    def tearDown(self):
        self._registry.__exit__(None, None, None)

    def assertParity(self, s, validate=True):
        if validate:
            api.validate(s)                 # the scenario is a valid one
        hh = api.simulate(s)
        assert_golden(self, "ledger, balances, holdings", (
            without_tax(hh.ledger.entries), balances(hh),
            [(a.id, a.name, a.kind, repr(a.report_rate)) for a in hh.aggregates()],
            [(a.id, bool(a.sold)) for a in hh.aggregates() if a.kind in ("property", "vehicle")]))
        return hh, None

    # ---------- purchase ----------
    def test_purchase_in_horizon(self):
        hh, _ = self.assertParity(scenario([house()]))
        kinds = [e["kind"] for e in hh.ledger.entries[:2]]
        self.assertEqual(kinds, ["PURCHASE", "APPRECIATION"])
        self.assertEqual(hh.ledger.entries[1]["month"], "2026-04")   # no growth in month 1

    def test_purchase_at_horizon_start_and_end(self):
        self.assertParity(scenario([house(date="2026-01-01"), car(date="2027-12-01")]))

    def test_purchase_with_market_value(self):
        hh, _ = self.assertParity(scenario([house(marketValue=520000)]))
        self.assertEqual(hh.ledger.entries[1]["kind"], "REVALUATION")
        self.assertParity(scenario([house(marketValue="480000.555")]))

    def test_market_value_raw_truthiness(self):
        for mv in (0, "0", "", None, "0.001"):
            with self.subTest(marketValue=mv):
                self.assertParity(scenario([house(marketValue=mv)]), validate=mv not in ("",))

    def test_pre_horizon_property_and_vehicle(self):
        hh, _ = self.assertParity(scenario([
            house(date="2015-07-01", marketValue=650000), house("h2", date="2020-01-01"),
            car(date="2023-05-01", maintenanceIncrease=0.04)]))
        self.assertNotIn("PURCHASE", [e["kind"] for e in hh.ledger.entries])

    def test_negative_appreciation_and_odd_prices(self):
        self.assertParity(scenario([house(price="123456.785", appr=-0.02),
                                    house("h2", date="2026-06-01", price=1, appr=0.5)]))

    # ---------- improvement / adjustment ----------
    def test_improvement(self):
        self.assertParity(scenario([house(), dict(
            type="improvement", id="i1", property="h", improvementDate="2026-08-01",
            cost=40000, valueAdded=55000), dict(
            type="improvement", id="i2", property="h", improvementDate="2027-01-01",
            cost="12000.505")]))

    def test_improvement_value_added_zero_means_cost(self):
        for va in (0, "0", 15000):
            with self.subTest(valueAdded=va):
                self.assertParity(scenario([house(), dict(
                    type="improvement", id="i", property="h", improvementDate="2026-05-01",
                    cost=20000, valueAdded=va)]))

    def test_improvement_in_purchase_month_and_pre_horizon_property(self):
        self.assertParity(scenario([house(date="2019-01-01"), dict(
            type="improvement", property="h", improvementDate="2026-01-01", cost=1000),
            house("h2"), dict(type="improvement", id="i2", property="h2",
                              improvementDate="2026-03-01", cost=5000, valueAdded=4000)]))

    def test_improvement_then_percent_adjustment_same_month(self):
        hh, _ = self.assertParity(scenario([
            dict(type="marketAdjustment", id="a", property="h", adjustmentDate="2026-09-01",
                 percent=-0.1),
            house(),
            dict(type="improvement", id="i", property="h", improvementDate="2026-09-01",
                 cost=30000)]))
        sep = [e["kind"] for e in hh.ledger.entries if e["month"] == "2026-09"]
        self.assertEqual(sep, ["IMPROVEMENT", "MARKET_ADJUSTMENT", "APPRECIATION"])

    def test_new_value_adjustment_suppresses_growth_that_month(self):
        hh, _ = self.assertParity(scenario([house(), dict(
            type="improvement", id="i", property="h", improvementDate="2026-09-01", cost=30000),
            dict(type="marketAdjustment", id="a", property="h", adjustmentDate="2026-09-01",
                 newValue=610000)], end="2026-09-01"))
        sep = [e["kind"] for e in hh.ledger.entries if e["month"] == "2026-09"]
        self.assertEqual(sep, ["IMPROVEMENT", "MARKET_ADJUSTMENT"])
        self.assertEqual(hh["h"].balance, Decimal("610000.00"))

    def test_adjustments_both_forms_several(self):
        self.assertParity(scenario([
            house(), house("h2", date="2018-04-01"),
            dict(type="marketAdjustment", id="a1", property="h2", adjustmentDate="2026-01-01",
                 percent="0.05"),
            dict(type="marketAdjustment", id="a2", property="h", adjustmentDate="2026-03-01",
                 percent=0.123456),
            dict(type="marketAdjustment", id="a3", property="h", adjustmentDate="2027-02-01",
                 newValue="499999.995"),
            dict(type="marketAdjustment", property="h2", adjustmentDate="2027-02-01",
                 newValue=0.004),
            dict(type="marketAdjustment", id="a5", property="h", adjustmentDate="2027-05-01",
                 percent="0")]))

    # ---------- sale ----------
    def test_sale_item_plain(self):
        self.assertParity(scenario([house(), dict(type="sale", id="s", property="h",
                                                   saleDate="2027-03-01")]))

    def test_sale_with_price_cost_penalty(self):
        hh, _ = self.assertParity(scenario([house(), dict(
            type="sale", id="s", property="h", saleDate="2027-03-01", salePrice=575000,
            sellingCostRate=0.045, salePenalty="3210.555")]))
        mar = [e["kind"] for e in hh.ledger.entries if e["month"] == "2027-03"]
        # The selling cost is an associated cost (ADR-0067), at Order.EXPENSE.
        self.assertEqual(mar, ["SALE_PRICE_DIFFERENCE", "SALE", "PENALTY", "COST"])
        self.assertEqual([e["kind"] for e in hh.ledger.entries if e["month"] == "2027-04"], [])

    def test_sale_price_raw_truthiness(self):
        for price in (0, "0", "", 450000):
            with self.subTest(salePrice=price):
                self.assertParity(scenario([house(), dict(
                    type="sale", property="h", saleDate="2027-03-01", salePrice=price)]),
                    validate=False)

    def test_legacy_property_sale_date(self):
        self.assertParity(scenario([house(saleDate="2027-06-01", sellingCostRate=0.05,
                                          salePenalty=1234.567, salePrice="600000")]))
        self.assertParity(scenario([house(date="2012-01-01", saleDate="2026-01-01")]))

    def test_legacy_sale_without_id_never_fires(self):
        item = house(saleDate="2027-06-01")
        del item["id"]
        self.assertParity(scenario([item]), validate=False)

    def test_vehicle_sale(self):
        hh, _ = self.assertParity(scenario([car(maintenanceIncrease=0.05), dict(
            type="sale", id="sv", property="v", saleDate="2027-02-01", sellingCostRate=0.01)]))
        self.assertTrue(hh["v"].sold)
        self.assertEqual(hh["v"].balance, Decimal("0.00"))

    def test_sale_at_retirement(self):
        items = [house(), car(), dict(type="sale", id="s1", property="h", atRetirement=True,
                                      sellingCostRate=0.03),
                 dict(type="sale", id="s2", property="v", atRetirement=True)]
        self.assertParity(scenario(items, retirementDate="2027-04-01"))
        self.assertParity(scenario(items + [dict(type="retirement",
                                                 retirementDate="2026-11-01")]))

    def test_sold_more_than_once(self):
        s = scenario([house(saleDate="2027-01-01"),
                      dict(type="sale", id="s", property="h", saleDate="2027-02-01")])
        with self.assertRaises(ValueError) as new_err:
            api.simulate(s)
        assert_golden(self, "message", str(new_err.exception))

    # ---------- secured loans (fake WP4 aggregate) ----------
    def test_sale_pays_off_secured_loans_in_holdings_order(self):
        hh, _ = self.assertParity(scenario([
            loan("m1", "h", principal=200000),           # listed before its property
            house(),
            loan("m2", "h", principal=50000, rate=0.07, years=10, startDate="2026-06-01"),
            loan("m3", principal=10000, years=5, startDate="2026-02-01"),   # unsecured
            loan("m4", "h", principal=12000, years=1, startDate="2026-03-01"),  # paid off
            dict(type="sale", id="s", property="h", saleDate="2027-07-01",
                 sellingCostRate=0.04, salePenalty=5000)]))
        jul = [(e["kind"], e["to"]) for e in hh.ledger.entries if e["month"] == "2027-07"]
        self.assertEqual(jul[:4], [("SALE", "cash"), ("LOAN_PAYOFF", "m1"),
                                   ("LOAN_PAYOFF", "m2"), ("PENALTY", None)])
        self.assertIn(("COST", None), jul)
        self.assertEqual(hh["m4"].balance, Decimal("0.00"))

    def test_legacy_sale_pays_off_loan_covered(self):
        self.assertParity(scenario([
            house(saleDate="2027-01-01"), loan("m", "h"), car()],
            incomeMode="expensesCovered"))

    # ---------- vehicle maintenance ----------
    def test_vehicle_maintenance_increase_anniversary(self):
        hh, _ = self.assertParity(scenario([
            car(date="2024-11-01", maintenanceIncrease=0.1, maint="1000.6"),
            car("v2", date="2026-05-01", maintenanceIncrease="-0.05")],
            end="2029-12-01"))
        m = [e for e in hh.ledger.entries if e["source"] == "v-maintenance"]
        self.assertEqual(m[0]["month"], "2026-01")

    def test_vehicle_maintenance_covered_mode(self):
        hh, _ = self.assertParity(scenario([car(), car("v2", date="2020-01-01")],
                                           incomeMode="expensesCovered"))
        self.assertNotIn("EXPENSE", [e["kind"] for e in hh.ledger.entries])

    def test_vehicle_zero_maintenance_and_depreciation(self):
        self.assertParity(scenario([car(maint=0, dep=0), car("v2", dep=0.99, maint=0.01)]))

    # ---------- holdings order / ids ----------
    def test_interleaved_kinds_and_ids(self):
        items = [car("a"), house("b"), car(None, date="2026-04-01"), house(None, date="2016-01-01")]
        for i in items:
            if i["id"] is None:
                del i["id"]
        hh, _ = self.assertParity(scenario(items), validate=False)
        self.assertEqual([a.id for a in hh.aggregates()], ["cash", "a", "b", "item2", "item3"])

    def test_duplicate_id_keeps_first_slot_last_item(self):
        self.assertParity(scenario([house("x", price=100000), car("y"),
                                    car("x", date="2026-07-01", price=20000)]), validate=False)

    def test_classes(self):
        hh = api.simulate(scenario([house(), car()]))
        self.assertIsInstance(hh["h"], RealEstate)
        self.assertIsInstance(hh["v"], Vehicle)
        self.assertEqual(hh["h"].group, "property")
        self.assertEqual(hh["v"].group, "property")

    def test_assets_not_created_before_purchase(self):
        hh = api.simulate(scenario([house(date="2027-12-01")], end="2027-11-01"))
        self.assertIsNone(hh.get("h"))

    # ---------- random scenarios ----------
    def test_random_scenarios(self):
        rnd = random.Random(20261110)
        checked = 0
        for n in range(300):
            s = random_scenario(rnd)
            try:
                api.validate(s)
            except (ValueError, KeyError):
                continue
            with self.subTest(n=n):
                self.assertParity(s)
            checked += 1
        self.assertGreater(checked, 150)


def date(rnd, lo, hi):
    m = rnd.randint(lo, hi)
    return f"{m // 12:04d}-{m % 12 + 1:02d}-01"


def random_scenario(rnd):
    start, end = month_index("2026-01-01", ""), month_index("2028-12-01", "")
    items, assets = [], []
    for k in range(rnd.randint(1, 4)):
        at = rnd.randint(start - 120, end)
        kind = rnd.choice(("property", "vehicle"))
        aid = f"{kind[0]}{k}"
        if kind == "property":
            item = house(aid, date(rnd, at, at), price=rnd.choice((350000, "512345.675", 99999)),
                         appr=rnd.choice((0.03, -0.01, "0.0525", 0)))
            if rnd.random() < 0.4:
                item["marketValue"] = rnd.choice((400000, "600000.125", 0))
        else:
            item = car(aid, date(rnd, at, at), price=rnd.choice((25000, "41999.99")),
                       dep=rnd.choice((0.15, "0.2", 0)), maint=rnd.choice((900, "1500.5", 0)))
            if rnd.random() < 0.5:
                item["maintenanceIncrease"] = rnd.choice((0.03, "-0.02", 0.1))
        items.append(item)
        assets.append((aid, kind, at))
    for aid, kind, at in assets:
        lo = max(at, start)
        sold = None
        if rnd.random() < 0.5 and lo + 1 <= end:
            sold = rnd.randint(lo + 1, end)
            sale = dict(type="sale", id=f"s{aid}", property=aid, saleDate=date(rnd, sold, sold))
            if rnd.random() < 0.5:
                sale["sellingCostRate"] = rnd.choice((0.05, "0.035"))
            if rnd.random() < 0.4:
                sale["salePrice"] = rnd.choice((300000, "123456.789", 0))
            if rnd.random() < 0.3:
                sale["salePenalty"] = rnd.choice((1000, "99.995"))
            items.append(sale)
        hi = end if sold is None else sold - 1
        if kind == "property" and at >= start and rnd.random() < 0.4:
            items.append(loan(f"m{aid}", aid, principal=rnd.choice((200000, "150000.5")),
                              years=rnd.choice((1, 25))))
        if kind == "property":
            for j in range(rnd.randint(0, 2)):
                items.append(dict(type="improvement", id=f"i{aid}{j}", property=aid,
                                  improvementDate=date(rnd, lo, hi),
                                  cost=rnd.choice((10000, "2500.505")),
                                  **({"valueAdded": rnd.choice((0, 8000, 30000))}
                                     if rnd.random() < 0.5 else {})))
            for j in range(rnd.randint(0, 2)):
                adj = dict(type="marketAdjustment", id=f"a{aid}{j}", property=aid,
                           adjustmentDate=date(rnd, lo, hi))
                if rnd.random() < 0.5:
                    adj["percent"] = rnd.choice((0.05, "-0.1", 0.0333))
                else:
                    adj["newValue"] = rnd.choice((450000, "700000.5"))
                items.append(adj)
    rnd.shuffle(items)
    settings = {}
    if rnd.random() < 0.3:
        settings["incomeMode"] = "expensesCovered"
    return scenario(items, start="2026-01-01", end="2028-12-01", **settings)


if __name__ == "__main__":
    unittest.main()
