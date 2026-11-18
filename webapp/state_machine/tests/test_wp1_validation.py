"""WP1: validation outcomes equal to the iteration-1 ``validate`` (D3), frozen.

Every case checks the outcome: None, or (exception type, message). Sources of scenarios:
  1. webapp/samples/*.json (all must be valid);
  2. a mutation table over a valid kitchen-sink scenario, at least one case per check of
     OBJECTS §8, including the KeyError cases (OBJECTS §9.2): the expected exception type
     is in the table, the message is a golden value frozen from iteration 1.
The scenarios the reference test suite (webapp/test_engine.py) passes to ``validate`` are in
the golden suite (tests/golden, test_golden.py) with their validation messages.
"""
import copy
import json
import unittest

from state_machine import validation
from state_machine.tests.support import SAMPLES, assert_golden


def outcome(fn, scenario):
    try:
        fn(copy.deepcopy(scenario))
    except Exception as e:      # noqa: BLE001 -- the type is part of the outcome
        return type(e).__name__, str(e)
    return None


# --- kitchen-sink base scenario (valid) -------------------------------------------------

def base():
    return {
        "horizon": {"start": "2026-01-01", "end": "2040-12-01"},
        "openingCash": "50000",
        "annualInflation": 0.02,
        "effectiveTaxRate": 0.25,
        "retirementTaxRate": 0.15,
        "incomeMode": "modelled",
        "dollarsOf": "2026-01-01",
        "items": [
            {"type": "retirement", "id": "ret", "retirementDate": "2035-01-01"},
            {"type": "property", "id": "house", "name": "House", "purchaseDate": "2020-01-01",
             "price": 500000, "annualAppreciation": 0.03, "marketValue": 600000},
            {"type": "mortgage", "id": "mtg", "name": "House mortgage", "property": "house",
             "startDate": "2026-01-01", "principal": 400000, "annualRate": 0.04,
             "amortizationYears": 25, "firstPaymentDate": "2026-03-01"},
            {"type": "vehicle", "id": "car", "name": "Car", "purchaseDate": "2027-01-01",
             "price": 30000, "annualDepreciation": 0.15, "annualMaintenance": 1200,
             "maintenanceIncrease": 0.02},
            {"type": "property", "id": "cottage", "purchaseDate": "2028-01-01",
             "price": 200000, "annualAppreciation": 0.02},
            {"type": "mortgage", "id": "mtg2", "property": "cottage", "principal": 100000,
             "annualRate": 0.05, "amortizationYears": 20},
            {"type": "sale", "id": "sell-house", "property": "house", "saleDate": "2038-01-01",
             "salePrice": 900000, "sellingCostRate": 0.05, "salePenalty": 1000},
            {"type": "sale", "id": "sell-car", "property": "car", "atRetirement": True},
            {"type": "improvement", "id": "reno", "property": "house",
             "improvementDate": "2027-06-01", "cost": 20000, "valueAdded": 15000},
            {"type": "marketAdjustment", "id": "adj", "property": "house",
             "adjustmentDate": "2028-01-01", "percent": -0.1},
            {"type": "renewal", "id": "ren", "mortgage": "mtg", "startDate": "2031-01-01",
             "annualRate": 0.05, "amortizationYears": 20, "penalty": 500},
            {"type": "extraPayment", "id": "xp", "mortgage": "mtg", "startDate": "2027-01-01",
             "monthlyAmount": 100, "endsAtRetirement": True},
            {"type": "lumpSum", "id": "ls", "mortgage": "mtg", "paymentDate": "2029-01-01",
             "amount": 10000, "paidFrom": "cash", "penalty": 0},
            {"type": "income", "id": "salary", "name": "Salary", "amount": 5000, "per": "month",
             "startDate": "2026-01-01", "endsAtRetirement": True, "taxable": True,
             "indexing": "custom", "indexRate": 0.02, "amountIn": "start"},
            {"type": "expense", "id": "living", "monthlyAmount": 3000,
             "startDate": "2026-01-01", "endDate": "2040-01-01", "indexing": "inflation"},
            {"type": "account", "id": "tfsa", "name": "TFSA", "accountType": "tfsa",
             "annualReturn": 0.05, "openingBalance": 10000},
            {"type": "account", "id": "rrsp", "name": "RRSP", "accountType": "rrsp",
             "annualReturn": 0.05, "openedDate": "2027-01-01", "openingBalance": 5000,
             "openingFrom": "cash", "withdrawalTaxRate": 0.2},
            {"type": "pension", "id": "pen", "amount": 2000, "per": "month",
             "indexing": "custom", "indexRate": 0.01, "taxable": True},
            {"type": "contribution", "id": "c-rrsp", "account": "rrsp",
             "startDate": "2027-01-01", "amount": 500, "employerMatch": 0.5,
             "endsAtRetirement": True, "indexing": "inflation"},
            {"type": "contribution", "id": "c-pen", "account": "pen",
             "startDate": "2026-01-01", "amount": 100, "per": "month"},
            {"type": "withdrawal", "id": "w-rrsp", "account": "rrsp", "method": "percent",
             "annualRate": 0.04},
            {"type": "withdrawal", "id": "w-tfsa", "account": "tfsa", "method": "amount",
             "amount": 1000, "startDate": "2036-01-01", "indexing": "inflation"},
            {"type": "withdrawal", "id": "w-even", "account": "tfsa", "method": "even",
             "startDate": "2036-01-01", "endDate": "2040-01-01"},
            {"type": "transfer", "id": "tr", "account": "tfsa", "amount": 5000,
             "transferDate": "2026-06-01"},
            {"type": "transfer", "id": "tr-ret", "account": "tfsa", "amount": 5000,
             "atRetirement": True},
        ],
    }


def it(s, id_):
    return next(i for i in s["items"] if i.get("id") == id_)


def setv(id_, **fields):
    """Mutation: update item ``id_`` (None value = delete the field)."""
    def mutate(s):
        item = it(s, id_)
        for k, v in fields.items():
            if v is None:
                item.pop(k, None)
            else:
                item[k] = v
    return mutate


def top(**fields):
    def mutate(s):
        for k, v in fields.items():
            if v is None:
                s.pop(k, None)
            else:
                s[k] = v
    return mutate


def add(item, at=None):
    def mutate(s):
        s["items"].insert(len(s["items"]) if at is None else at, copy.deepcopy(item))
    return mutate


def drop(*ids):
    def mutate(s):
        s["items"] = [i for i in s["items"] if i.get("id") not in ids]
    return mutate


def chain(*fns):
    def mutate(s):
        for fn in fns:
            fn(s)
    return mutate


HOUSE_UNLINKED = drop("mtg", "ren", "xp", "ls", "reno", "adj")
NO_RET = drop("ret", "sell-car", "tr-ret", "w-rrsp", "pen", "c-pen")

# (label, mutation, expected exception type name). One row per check (OBJECTS §8).
MUTATIONS = [
    # scenario level
    ("missing horizon", top(horizon=None), "ValueError"),
    ("missing openingCash", top(openingCash=None), "ValueError"),
    ("missing items", top(items=None), "ValueError"),
    ("bad horizon.start", lambda s: s["horizon"].update(start="2026-13-01"), "ValueError"),
    ("missing horizon.start", lambda s: s["horizon"].pop("start"), "ValueError"),
    ("bad horizon.end", lambda s: s["horizon"].update(end="soon"), "ValueError"),
    ("end before start", lambda s: s["horizon"].update(end="2025-12-01"), "ValueError"),
    ("openingCash not a number", top(openingCash="lots"), "ValueError"),
    ("annualInflation too big", top(annualInflation=1), "ValueError"),
    ("annualInflation not a number", top(annualInflation="x"), "ValueError"),
    ("annualInflation zero ok", top(annualInflation=0), None),
    ("dollarsOf bad", top(dollarsOf="2026/01/01"), "ValueError"),
    ("two retirement events", add({"type": "retirement", "retirementDate": "2036-01-01"}),
     "ValueError"),
    ("event and retirementDate", top(retirementDate="2035-01-01"), "ValueError"),
    ("legacy retirementDate bad", chain(drop("ret"), top(retirementDate="2035-1")), "ValueError"),
    ("legacy retirementDate before start ok",
     chain(drop("ret"), top(retirementDate="2020-01-01"),
           drop("sell-car", "tr-ret", "c-pen", "pen", "w-rrsp")), None),
    ("retirementTaxRate 1", top(retirementTaxRate=1), "ValueError"),
    ("retirementTaxRate negative", top(retirementTaxRate=-0.1), "ValueError"),
    ("incomeMode bad", top(incomeMode="other"), "ValueError"),
    ("incomeMode covered ok", top(incomeMode="expensesCovered"), None),
    ("effectiveTaxRate 1.5", top(effectiveTaxRate=1.5), "ValueError"),
    ("sold more than once", add({"type": "sale", "property": "house", "saleDate": "2039-01-01"}),
     "ValueError"),
    ("legacy property saleDate and sale item",
     setv("house", saleDate="2037-01-01"), "ValueError"),
    # 1. type, REQUIRED
    ("unknown type", add({"type": "boat", "id": "b"}), "ValueError"),
    ("missing type", add({"id": "b"}), "ValueError"),
    ("where = index", add({"type": "boat"}), "ValueError"),
    ("contribution unknown account", setv("c-rrsp", account="nope"), "ValueError"),
    ("withdrawal to pension unknown account", setv("w-tfsa", account="pen"), "ValueError"),
    ("transfer missing account", setv("tr", account=None), "ValueError"),
    ("unknown mortgage", setv("xp", mortgage="nope"), "ValueError"),
    ("missing date field", setv("car", purchaseDate=None), "ValueError"),
    ("bad date field", setv("car", purchaseDate="2027-00-01"), "ValueError"),
    ("vehicle purchase after horizon", setv("car", purchaseDate="2041-01-01"), "ValueError"),
    ("property purchase after horizon", setv("cottage", purchaseDate="2041-01-01"), "ValueError"),
    ("mortgage startDate outside horizon (REQUIRED loop does not include it)",
     setv("mtg", startDate="2025-12-01"), "ValueError"),
    ("missing number", setv("house", price=None), "ValueError"),
    ("not a number", setv("house", price="1,000"), "ValueError"),
    ("missing annualRate on renewal", setv("ren", annualRate=None), "ValueError"),
    # 2. mortgage
    ("mortgage unknown property", setv("mtg", property="nope"), "ValueError"),
    ("mortgage no start no property", setv("mtg2", property=None), "ValueError"),
    ("mortgage start before horizon via property",
     chain(setv("cottage", purchaseDate="2020-01-01")), "ValueError"),
    ("mortgage after horizon", setv("mtg", startDate="2041-01-01"), "ValueError"),
    ("mortgage before property purchase", setv("mtg2", startDate="2027-01-01"), "ValueError"),
    ("mortgage after property sold", setv("mtg", startDate="2038-01-01"), "ValueError"),
    ("mortgage bad startDate", setv("mtg", startDate="x"), "ValueError"),
    # 3. marketValue, salePrice
    ("marketValue negative", setv("house", marketValue=-1), "ValueError"),
    ("marketValue not a number", setv("house", marketValue="abc"), "ValueError"),
    ("marketValue 0 ok", setv("house", marketValue=0), None),
    ("salePrice negative", setv("sell-house", salePrice=-5), "ValueError"),
    # 4. property / sale
    ("property sellingCostRate 1", setv("cottage", sellingCostRate=1), "ValueError"),
    ("sale sellingCostRate negative", setv("sell-house", sellingCostRate=-0.01), "ValueError"),
    ("sale unknown property", setv("sell-house", property="nope"), "ValueError"),
    ("sale missing property (KeyError)", setv("sell-house", property=None), "KeyError"),
    ("sale atRetirement not bool", setv("sell-car", atRetirement="yes"), "ValueError"),
    ("sale date and atRetirement", setv("sell-car", saleDate="2036-01-01"), "ValueError"),
    ("sale at retirement without event", chain(NO_RET, add(
        {"type": "sale", "id": "s2", "property": "car", "atRetirement": True})), "ValueError"),
    ("sale missing saleDate", setv("sell-house", saleDate=None), "ValueError"),
    # The house mortgage reads the sale first: its item reports these two (quirk kept).
    ("sale bad saleDate (reported on the mortgage)", setv("sell-house", saleDate="2038"),
     "ValueError"),
    ("sale before horizon start (reported on the mortgage)",
     setv("sell-house", saleDate="2018-05-01"), "ValueError"),
    ("sale bad saleDate", chain(HOUSE_UNLINKED, setv("sell-house", saleDate="2038")),
     "ValueError"),
    ("sale before horizon start", chain(HOUSE_UNLINKED, setv("sell-house",
                                                           saleDate="2018-05-01")),
     "ValueError"),
    ("sale before purchase", setv("sell-car", atRetirement=None, saleDate="2026-06-01"),
     "ValueError"),
    ("sale in purchase month", setv("sell-car", atRetirement=None, saleDate="2027-01-15"),
     "ValueError"),
    ("sale after horizon", setv("sell-house", saleDate="2041-01-01"), "ValueError"),
    ("legacy property saleDate before horizon",
     chain(drop("sell-house"), HOUSE_UNLINKED, setv("house", saleDate="2018-05-01")),
     "ValueError"),
    ("legacy property saleDate ok",
     chain(drop("sell-house"), setv("house", saleDate="2038-01-01")), None),
    # 5. income / expense
    ("income per bad", setv("salary", per="week"), "ValueError"),
    ("income missing amount", setv("salary", amount=None), "ValueError"),
    ("income amount not a number", setv("salary", amount="lots"), "ValueError"),
    ("expense monthlyAmount not a number", setv("living", monthlyAmount="x"), "ValueError"),
    ("income taxable not bool", setv("salary", taxable="true"), "ValueError"),
    ("income endsAtRetirement not bool", setv("salary", endsAtRetirement=1.5), "ValueError"),
    ("expense startsAtRetirement not bool", setv("living", startsAtRetirement="no"),
     "ValueError"),
    ("both start and end at retirement", setv("salary", startsAtRetirement=True), "ValueError"),
    ("starts at retirement without event", chain(NO_RET, setv(
        "living", startsAtRetirement=True, startDate=None)), "ValueError"),
    ("starts at retirement with startDate, no event ok", chain(NO_RET, setv(
        "living", startsAtRetirement=True)), None),
    ("starts at retirement with event ok", setv("living", startsAtRetirement=True,
                                                 startDate=None, endDate=None), None),
    ("income missing startDate", setv("salary", startDate=None), "ValueError"),
    ("income bad startDate", setv("salary", startDate="2026-1"), "ValueError"),
    ("income indexing bad", setv("salary", indexing="cpi"), "ValueError"),
    ("income amountIn bad", setv("salary", amountIn="end"), "ValueError"),
    ("income custom indexRate 1", setv("salary", indexRate=1), "ValueError"),
    ("income custom indexRate missing", setv("salary", indexRate=None), "ValueError"),
    # 6. endDate before startDate
    ("expense endDate before startDate", setv("living", endDate="2025-01-01"), "ValueError"),
    ("expense bad endDate", setv("living", endDate="bad"), "ValueError"),
    ("contribution endDate before startDate", setv("c-rrsp", endDate="2026-01-01"),
     "ValueError"),
    # 7. rate ranges
    ("annualAppreciation 1", setv("house", annualAppreciation=1), "ValueError"),
    ("annualAppreciation -1", setv("house", annualAppreciation=-1), "ValueError"),
    ("annualDepreciation 2", setv("car", annualDepreciation=2), "ValueError"),
    ("mortgage annualRate negative", setv("mtg", annualRate=-0.01), "ValueError"),
    ("mortgage annualRate 3.79", setv("mtg", annualRate=3.79), "ValueError"),
    ("renewal annualRate 1", setv("ren", annualRate=1), "ValueError"),
    # 8. penalties
    ("salePenalty negative", setv("sell-house", salePenalty=-1), "ValueError"),
    ("penalty negative", setv("ren", penalty=-1), "ValueError"),
    ("penalty not a number", setv("ls", penalty="x"), "ValueError"),
    ("property salePenalty negative", setv("cottage", salePenalty=-2), "ValueError"),
    # 9. renewal
    ("renewal before mortgage start", setv("ren", startDate="2026-01-01"), "ValueError"),
    ("renewal amortization 0.01", setv("ren", amortizationYears=0.01), "ValueError"),
    ("renewal amortization 0 ok (falsy)", setv("ren", amortizationYears=0), None),
    ("renewal amortization not a number", setv("ren", amortizationYears="x"), "ValueError"),
    ("renewal same month as sale", setv("ren", startDate="2038-01-01"), "ValueError"),
    ("renewal after sale", setv("ren", startDate="2039-05-01"), "ValueError"),
    ("two renewals same month", add({"type": "renewal", "mortgage": "mtg",
                                     "startDate": "2031-01-15", "annualRate": 0.04}),
     "ValueError"),
    ("renewal of mortgage without property start", chain(
        setv("mtg2", startDate="2028-02-01"),
        add({"type": "renewal", "mortgage": "mtg2", "startDate": "2028-02-01",
             "annualRate": 0.04})), "ValueError"),
    # 10. lumpSum
    ("lumpSum atRetirement not bool", setv("ls", atRetirement="y"), "ValueError"),
    ("lumpSum payOff not bool", setv("ls", payOff=0.5), "ValueError"),
    ("lumpSum date and atRetirement", setv("ls", atRetirement=True), "ValueError"),
    ("lumpSum at retirement without event", chain(NO_RET, setv(
        "ls", paymentDate=None, atRetirement=True)), "ValueError"),
    ("lumpSum missing paymentDate", setv("ls", paymentDate=None), "ValueError"),
    ("lumpSum amount and payOff", setv("ls", payOff=True), "ValueError"),
    ("lumpSum before mortgage start", setv("ls", paymentDate="2026-01-01"), "ValueError"),
    ("lumpSum bad paymentDate", setv("ls", paymentDate="2029"), "ValueError"),
    ("lumpSum at retirement ok", setv("ls", paymentDate=None, atRetirement=True), None),
    ("lumpSum payOff ok", setv("ls", amount=None, payOff=True), None),
    ("lumpSum paidFrom bad", setv("ls", paidFrom="bank"), "ValueError"),
    # 11. amounts positive
    ("extraPayment amount 0", setv("xp", monthlyAmount=0), "ValueError"),
    ("lumpSum amount negative", setv("ls", amount=-1), "ValueError"),
    ("lumpSum amount missing", setv("ls", amount=None), "ValueError"),
    # 12. account
    ("accountType bad", setv("tfsa", accountType="rasp"), "ValueError"),
    ("accountType missing (KeyError)", setv("tfsa", accountType=None), "KeyError"),
    ("annualReturn 1", setv("tfsa", annualReturn=1), "ValueError"),
    ("annualReturn missing", setv("tfsa", annualReturn=None), "ValueError"),
    ("withdrawalTaxRate 1", setv("rrsp", withdrawalTaxRate=1), "ValueError"),
    ("openingBalance negative", setv("tfsa", openingBalance=-1), "ValueError"),
    ("openedDate after horizon", setv("rrsp", openedDate="2041-01-01"), "ValueError"),
    ("openedDate bad", setv("rrsp", openedDate="2027"), "ValueError"),
    ("openingFrom bad", setv("rrsp", openingFrom="bank"), "ValueError"),
    ("opened inside horizon with balance, no openingFrom", setv("rrsp", openingFrom=None),
     "ValueError"),
    ("opened at start with balance, no openingFrom ok",
     setv("rrsp", openingFrom=None, openedDate="2026-01-01"), None),
    # 13. pension
    ("pension missing amount", setv("pen", amount=None), "ValueError"),
    ("pension no start no retirement", chain(NO_RET, add(
        {"type": "pension", "id": "p2", "amount": 100})), "ValueError"),
    ("pension bad startDate", setv("pen", startDate="2036"), "ValueError"),
    ("pension bad endDate", setv("pen", endDate="x"), "ValueError"),
    ("pension ends before effective start (retirement)", setv("pen", endDate="2030-01-01"),
     "ValueError"),
    ("pension ends before own start (generic endDate check first)", setv("pen", startDate="2036-01-01",
                                           endDate="2035-06-01"), "ValueError"),
    ("pension ends at retirement but starts at it", setv("pen", endsAtRetirement=True),
     "ValueError"),
    # Triggers (ADR-0065): ended before its own start, the item never runs (as income did).
    ("pension ends at retirement, starts later", setv("pen", endsAtRetirement=True,
                                                     startDate="2037-01-01"), None),
    ("pension ends at retirement ok", setv("pen", endsAtRetirement=True,
                                           startDate="2030-01-01"), None),
    ("pension taxable not bool", setv("pen", taxable="no"), "ValueError"),
    ("pension indexing bad", setv("pen", indexing="cpi"), "ValueError"),
    ("pension indexRate 1", setv("pen", indexRate=1), "ValueError"),
    # 14. contribution
    ("contribution missing amount", setv("c-rrsp", amount=None), "ValueError"),
    ("contribution per bad", setv("c-rrsp", per="day"), "ValueError"),
    ("employerMatch 1.5", setv("c-rrsp", employerMatch=1.5), "ValueError"),
    ("employerMatch 1 ok", setv("c-rrsp", employerMatch=1), None),
    ("contribution missing startDate", setv("c-rrsp", startDate=None), "ValueError"),
    # 15. endsAtRetirement bool
    ("contribution endsAtRetirement not bool", setv("c-rrsp", endsAtRetirement="y"),
     "ValueError"),
    ("withdrawal endsAtRetirement not bool", setv("w-tfsa", endsAtRetirement=2), "ValueError"),
    ("extraPayment endsAtRetirement not bool", setv("xp", endsAtRetirement="y"), "ValueError"),
    ("pension endsAtRetirement not bool", setv("pen", endsAtRetirement="y",
                                               startDate="2030-01-01"), "ValueError"),
    # 16. indexing
    ("contribution indexing bad", setv("c-rrsp", indexing="cpi"), "ValueError"),
    ("withdrawal indexing bad", setv("w-tfsa", indexing="cpi"), "ValueError"),
    # 17. withdrawal
    ("withdrawal no start no retirement", chain(NO_RET, add(
        {"type": "withdrawal", "id": "w2", "account": "tfsa", "method": "amount",
         "amount": 5})), "ValueError"),
    ("withdrawal bad startDate", setv("w-tfsa", startDate="2036"), "ValueError"),
    ("percent withdrawal before account opens", setv("w-rrsp", startDate="2026-06-01"),
     "ValueError"),
    ("even withdrawal before account opens", chain(
        setv("w-even", account="rrsp", startDate="2026-06-01")), "ValueError"),
    ("amount withdrawal before account opens ok", setv("w-tfsa", account="rrsp",
                                                       startDate="2026-06-01"), None),
    ("method bad", setv("w-tfsa", method="all"), "ValueError"),
    ("method missing (KeyError)", setv("w-tfsa", method=None), "KeyError"),
    ("indexing on percent", setv("w-rrsp", indexing="inflation"), "ValueError"),
    ("amount method without amount", setv("w-tfsa", amount=None), "ValueError"),
    ("amount method without amount, with annualRate (hint)",
     setv("w-tfsa", amount=None, annualRate=0.04), "ValueError"),
    ("percent without annualRate", setv("w-rrsp", annualRate=None), "ValueError"),
    ("percent without annualRate, with amount (hint)",
     setv("w-rrsp", annualRate=None, amount=100), "ValueError"),
    ("amount withdrawal per bad", setv("w-tfsa", per="week"), "ValueError"),
    ("percent annualRate 1", setv("w-rrsp", annualRate=1), "ValueError"),
    ("percent annualRate negative", setv("w-rrsp", annualRate=-0.04), "ValueError"),
    ("percent annualRate not a number", setv("w-rrsp", annualRate="x"), "ValueError"),
    # 18. transfer
    ("transfer amount 0", setv("tr", amount=0), "ValueError"),
    ("transfer amount missing", setv("tr", amount=None), "ValueError"),
    ("transfer atRetirement not bool", setv("tr", atRetirement="y"), "ValueError"),
    ("transfer date and atRetirement", setv("tr", atRetirement=True), "ValueError"),
    ("transfer at retirement without event", chain(NO_RET, add(
        {"type": "transfer", "id": "t2", "account": "tfsa", "amount": 1,
         "atRetirement": True})), "ValueError"),
    ("transfer missing date", setv("tr", transferDate=None), "ValueError"),
    ("transfer bad date", setv("tr", transferDate="x"), "ValueError"),
    ("transfer outside horizon", setv("tr", transferDate="2041-01-01"), "ValueError"),
    ("transfer before account opens", setv("tr", account="rrsp"), "ValueError"),
    # 19. retirement
    ("retirement outside horizon", setv("ret", retirementDate="2041-01-01"), "ValueError"),
    ("retirement bad date", setv("ret", retirementDate="2035"), "ValueError"),
    ("retirement missing date", setv("ret", retirementDate=None), "ValueError"),
    # 20. marketAdjustment
    ("adjustment unknown property", setv("adj", property="nope"), "ValueError"),
    # A vehicle may be adjusted too (ADR-0033 amendment 2026-11-11).
    ("adjustment on vehicle ok", setv("adj", property="car"), None),
    ("adjustment missing property (KeyError)", setv("adj", property=None), "KeyError"),
    ("adjustment before horizon", setv("adj", adjustmentDate="2025-01-01"), "ValueError"),
    ("adjustment before purchase", setv("adj", property="cottage",
                                         adjustmentDate="2027-06-01"), "ValueError"),
    ("adjustment after horizon", setv("adj", adjustmentDate="2041-01-01"), "ValueError"),
    ("adjustment at sale", setv("adj", adjustmentDate="2038-01-01"), "ValueError"),
    ("adjustment neither", setv("adj", percent=None), "ValueError"),
    ("adjustment both", setv("adj", newValue=700000), "ValueError"),
    ("adjustment percent -1", setv("adj", percent=-1), "ValueError"),
    ("adjustment newValue negative", setv("adj", percent=None, newValue=-1), "ValueError"),
    ("adjustment newValue ok", setv("adj", percent=None, newValue=1), None),
    # 21. improvement
    ("improvement unknown property", setv("reno", property="car"), "ValueError"),
    ("improvement missing property (KeyError)", setv("reno", property=None), "KeyError"),
    ("improvement before horizon", setv("reno", improvementDate="2025-01-01"), "ValueError"),
    ("improvement before purchase", setv("reno", property="cottage"), "ValueError"),
    ("improvement after horizon", setv("reno", improvementDate="2041-01-01"), "ValueError"),
    ("improvement at sale", setv("reno", improvementDate="2038-01-01"), "ValueError"),
    ("improvement cost negative", setv("reno", cost=-1), "ValueError"),
    ("improvement valueAdded negative", setv("reno", valueAdded=-1), "ValueError"),
    ("improvement cost missing", setv("reno", cost=None), "ValueError"),
    # 22. vehicle
    ("maintenanceIncrease 1", setv("car", maintenanceIncrease=1), "ValueError"),
    # Maintenance is an associated expense (ADR-0067): none without annualMaintenance.
    ("annualMaintenance missing ok", setv("car", annualMaintenance=None), None),
    # 23. mortgage firstPaymentDate, amortization
    ("firstPaymentDate at start", setv("mtg", firstPaymentDate="2026-01-01"), "ValueError"),
    ("firstPaymentDate bad", setv("mtg", firstPaymentDate="2026"), "ValueError"),
    ("amortization 0", setv("mtg", amortizationYears=0), "ValueError"),
    ("amortization 25.01", setv("mtg", amortizationYears=25.01), "ValueError"),
    ("amortization 2.5 ok", setv("mtg", amortizationYears=2.5), None),
    ("amortization missing", setv("mtg", amortizationYears=None), "ValueError"),
    # first error wins: two errors, earlier item reported
    ("first error wins", chain(setv("tr", amount=0), setv("house", price="x")), "ValueError"),
]


class Mutations(unittest.TestCase):
    def test_base_is_valid(self):
        self.assertIsNone(outcome(validation.validate, base()))

    def test_mutation_table(self):
        for label, mutate, expected in MUTATIONS:
            with self.subTest(label):
                s = base()
                mutate(s)
                new = outcome(validation.validate, s)
                self.assertEqual(new[0] if new else None, expected, f"outcome {new}")
                assert_golden(self, label, new)

    def test_check_amortization_direct(self):
        for value in (25, 2.5, "30", 1 / 12, 0, 0.05, -1, 25.01, "x", None):
            item = {} if value is None else {"amortizationYears": value}
            with self.subTest(value=value):
                assert_golden(self, repr(value),
                              outcome(lambda i: validation.check_amortization(i, "item X"), item))

    def test_constants(self):
        # Canada's (ADR-0071): the core's item types plus its own, its account types.
        from state_machine import jurisdictions
        canada = jurisdictions.get("CA")
        assert_golden(self, "REQUIRED", list(validation.required_fields(canada).items()))
        assert_golden(self, "ACCOUNT_TYPES", tuple(canada.account_types))
        assert_golden(self, "WITHDRAWAL_METHODS", validation.WITHDRAWAL_METHODS)

    def test_shared_helpers_not_redefined(self):
        from state_machine import arith, dates
        for name in ("month_index", "month_label", "base_month", "retirement_date",
                     "property_sales", "mortgage_start"):
            self.assertIs(getattr(validation, name), getattr(dates, name))
        for name in ("dec", "flow_amount"):
            self.assertIs(getattr(validation, name), getattr(arith, name))


class Samples(unittest.TestCase):
    def test_samples_valid(self):
        paths = sorted(SAMPLES.glob("*.json"))
        self.assertTrue(paths)
        for path in paths:
            with self.subTest(path.name):
                self.assertIsNone(outcome(validation.validate, json.loads(path.read_text())))


if __name__ == "__main__":
    unittest.main()
