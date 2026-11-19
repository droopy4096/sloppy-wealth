"""Scenario validation (WP1): a verbatim port of the reference ``validate`` (D3).

Same checks, same order, same exception types (including the KeyError cases, OBJECTS
§9.2) and byte-identical messages as iteration 1's ``validate`` / ``check_amortization``
(engine.py, tag poc-iteration-1).
Shared helpers come from the WP0 modules and are never redefined here.
"""
from .arith import dec, flow_amount
from .dates import (base_month, month_index, month_label, mortgage_start,
                    property_sales, retirement_date, retirement_dates)
from .flows.adjustment import is_percent, new_amount, target_of
from .triggers import prepared
from .persons import items_by_id, owned_types, owner_of, person_items, retirement_person
from . import jurisdictions

REQUIRED = {
    "property": ["purchaseDate", "price", "annualAppreciation"],
    # A mortgage may name the property it is secured by (ADR-0024); its startDate then
    # defaults to that property's purchaseDate (a financed purchase, ADR-0025).
    "mortgage": ["principal", "annualRate", "amortizationYears"],
    # Running costs are associated expenses (ADR-0067; annualMaintenance converted on load).
    "vehicle": ["purchaseDate", "price", "annualDepreciation"],
    # Plus an amount (see flow_amount); a startDate, own or set by a trigger (ADR-0065).
    "income": [],
    "expense": [],
    "extraPayment": ["mortgage", "startDate", "monthlyAmount"],
    # A paymentDate (own or set by a trigger, ADR-0065); an amount or payOff (ADR-0059).
    "lumpSum": ["mortgage"],
    "renewal": ["mortgage", "startDate", "annualRate"],   # optional amortizationYears, keepPayment
    # Construction or renovation on a property already owned (ADR-0046).
    "improvement": ["property", "improvementDate", "cost"],   # optional valueAdded
    # Investment accounts (ADR-0011): an account type of the jurisdiction (ADR-0071).
    "account": ["accountType", "annualReturn"],   # optional openingBalance, openedDate
    "contribution": ["account", "startDate"],      # plus amount/per, see flow_amount()
    # startDate may be blank: the withdrawal then starts at retirement (ADR-0059).
    "withdrawal": ["account", "method"],
    # Guaranteed (defined-benefit) pension (ADR-0052): amount in base-date dollars.
    "pension": [],               # amount/per; optional startDate, endDate, indexing
    # Sale of a property (SaleEvent, ADR-0031, ADR-0034, ADR-0047).
    # A saleDate (own or set by a trigger, ADR-0065); optional sellingCostRate, salePenalty.
    "sale": ["property"],
    # Market adjustment of a property's value (Revaluation, ADR-0033): percent or newValue.
    "marketAdjustment": ["property", "adjustmentDate"],
    # One-off transfer from cash into an account (OneOffTransfer, ADR-0025): a
    # transferDate (own or set by a trigger, ADR-0065).
    "transfer": ["account", "amount"],
    # Retirement (RetirementEvent, ADR-0059): at most one; its month is the retirement month.
    "retirement": ["retirementDate"],
    # A person of the household (ADR-0061): id (checked in check_persons); optional
    # name, effectiveTaxRate, retirementTaxRate (blank = the scenario's).
    "person": [],
    # Adjustment of a cash flow's amount (ADR-0062): flow (checked below), the date and
    # the new amount; optional per (default the flow's).
    # A percent withdrawal takes a new annualRate instead of an amount (amendment).
    "adjustment": ["adjustmentDate"],
    # The actual cash balance at the end of a month (ADR-0063).
    "cashBalance": ["balanceDate", "balance"],
    # Trigger (ADR-0065): checked and resolved by triggers.resolve before validation.
    "trigger": ["event", "target", "action"],
    # Associated expense / cost (ADR-0067): a parent with a lifetime; amount or a rate of
    # a basis looked up from the parent (checked below).
    "associatedExpense": ["parent"],
    "associatedCost": ["parent"],
    # Associated income / one-off (ADR-0068): parent an income or a pension (below).
    "associatedIncome": ["parent"],
    "associatedOneOff": ["parent"],
}




class ItemCheck:
    """What a jurisdiction's ``validate_item`` may need: the scenario, its persons, the
    horizon, and ``seen`` (its own state across items, e.g. one room item per type)."""

    def __init__(self, scenario, persons, start, end):
        self.scenario, self.persons, self.start, self.end = scenario, persons, start, end
        self.seen = {}


def required_fields(rules):
    """The required fields of every item type the jurisdiction ``rules`` offers."""
    return dict(REQUIRED, **rules.required)
# Older files' "even" is converted to "annuity" by upgrade.py (ADR-0039 amendment 2026-11-11).
WITHDRAWAL_METHODS = ("amount", "percent", "annuity")


def validate(scenario):
    """Raise ValueError with a readable message if the scenario is malformed."""
    scenario = prepared(scenario)           # upgrade, off items left out, triggers resolved
    for field in ("horizon", "openingCash", "items"):
        if field not in scenario:
            raise ValueError(f"scenario: missing field {field!r}")
    h = scenario["horizon"]
    start = month_index(h.get("start"), "horizon.start")
    end = month_index(h.get("end"), "horizon.end")
    if end < start:
        raise ValueError("horizon: end is before start")
    dec(scenario, "openingCash", "scenario")
    if scenario.get("annualInflation") and not -1 < dec(scenario, "annualInflation", "scenario") < 1:
        raise ValueError("scenario: annualInflation must be a fraction between -1 and 1, "
                         f"e.g. 0.02 for 2%; got {scenario['annualInflation']!r}")
    if scenario.get("dollarsOf"):
        base_month(scenario)  # a readable error for a bad date
    events = [i for i in scenario["items"] if i.get("type") == "retirement"]
    if not person_items(scenario) and len(events) > 1:
        raise ValueError("scenario: only one retirement event is allowed")
    owners = [owner_of(e, scenario) for e in events]
    for pid in owners:
        if owners.count(pid) > 1:
            raise ValueError(f"scenario: person {pid!r} has more than one retirement event")
    if scenario.get("retirementTaxRate") and not 0 <= dec(scenario, "retirementTaxRate", "scenario") < 1:
        raise ValueError("scenario: retirementTaxRate must be a fraction between 0 and 1, "
                         f"e.g. 0.20 for 20%; got {scenario['retirementTaxRate']!r}")
    retirement_dates_by_person = retirement_dates(scenario)
    targets = items_by_id(scenario)

    def retirement_of(item):
        """The date of the retirement ``item`` follows (ADR-0061), or ''."""
        return retirement_dates_by_person.get(retirement_person(item, scenario, targets), "")

    if (scenario.get("incomeMode") or "modelled") not in ("modelled", "expensesCovered"):
        raise ValueError("scenario: incomeMode must be modelled or expensesCovered; "
                         f"got {scenario['incomeMode']!r}")
    if scenario.get("effectiveTaxRate") and not 0 <= dec(scenario, "effectiveTaxRate", "scenario") < 1:
        raise ValueError("scenario: effectiveTaxRate must be a fraction between 0 and 1, "
                         f"e.g. 0.25 for 25%; got {scenario['effectiveTaxRate']!r}")
    persons = check_persons(scenario)
    mortgages = {i.get("id"): i for i in scenario["items"] if i.get("type") == "mortgage"}
    properties = {i.get("id"): i for i in scenario["items"] if i.get("type") == "property"}
    accounts = {i.get("id"): i for i in scenario["items"] if i.get("type") == "account"}
    pensions = {i.get("id"): i for i in scenario["items"] if i.get("type") == "pension"}
    sales = property_sales(scenario["items"])
    vehicles = {i.get("id"): i for i in scenario["items"] if i.get("type") == "vehicle"}
    assets = dict(properties, **vehicles)           # what a loan may be tied to
    renewal_months = set()
    rules = jurisdictions.of(scenario)              # ADR-0071
    required = required_fields(rules)
    elsewhere = jurisdictions.own_item_types()
    check = ItemCheck(scenario, persons, start, end)
    for i, item in enumerate(scenario["items"]):
        kind = item.get("type")
        where = f"item {item.get('name') or item.get('id') or i}"
        if kind not in required:
            if kind in elsewhere:
                raise ValueError(f"{where}: {kind} is not available in {rules.name} "
                                 f"(it belongs to {jurisdictions.get(elsewhere[kind]).name})")
            raise ValueError(f"{where}: unknown type {kind!r}")
        check_person_refs(item, kind, where, persons, rules)
        retirement = retirement_of(item)
        for field in required[kind]:
            if field in ("property", "accountType", "method", "event", "target", "action",
                         "parent") or field in rules.choice_fields:
                continue    # a reference or a choice, checked per type below
            if field == "account":
                allowed = dict(accounts, **pensions) if kind == "contribution" else accounts
                if item.get("account") not in allowed:
                    raise ValueError(f"{where}: refers to unknown account {item.get('account')!r}")
                continue
            if field == "mortgage":
                if item.get("mortgage") not in mortgages:
                    raise ValueError(f"{where}: refers to unknown mortgage {item.get('mortgage')!r}")
            elif field.endswith("Date"):
                if field not in item:
                    raise ValueError(f"{where}: missing field {field!r}")
                idx = month_index(item[field], f"{where}.{field}")
                # Property and vehicles bought before the horizon are carried in at their
                # value at the start; a later purchase must fall inside the horizon.
                if kind in ("property", "vehicle") and idx > end:
                    raise ValueError(f"{where}: {field} is after the horizon end")
                if kind == "mortgage" and not start <= idx <= end:
                    raise ValueError(f"{where}: {field} is outside the horizon")
            else:
                dec(item, field, where)
        if kind == "mortgage":
            # A loan secures a property, or (ADR-0074 amendment) finances a vehicle.
            if item.get("property") and item["property"] not in assets:
                raise ValueError(f"{where}: refers to unknown property {item['property']!r}")
            at = mortgage_start(item, assets, where)
            if not start <= at <= end:
                raise ValueError(f"{where}: startDate is outside the horizon")
            if item.get("property"):
                prop = assets[item["property"]]
                if at < month_index(prop["purchaseDate"], where):
                    raise ValueError(f"{where}: starts before its property is purchased")
                sale = sales.get(item["property"])
                if sale and at >= month_index(sale["saleDate"], where):
                    raise ValueError(f"{where}: starts after its property is sold")
        if kind == "property":
            if item.get("marketValue") and dec(item, "marketValue", where) < 0:
                raise ValueError(f"{where}: marketValue must not be negative")
        if kind == "sale" and item.get("salePrice") and dec(item, "salePrice", where) < 0:
            raise ValueError(f"{where}: salePrice must not be negative")
        if kind in ("property", "sale"):
            if item.get("sellingCostRate") and not 0 <= dec(item, "sellingCostRate", where) < 1:
                raise ValueError(f"{where}: sellingCostRate must be a fraction between 0 and 1, "
                                 f"e.g. 0.05 for 5%; got {item['sellingCostRate']!r}")
        if kind == "sale":
            # A sale may sell a property or a vehicle (SaleEvent on any asset).
            prop = properties.get(item["property"]) or vehicles.get(item["property"])
            if prop is None:
                raise ValueError(f"{where}: refers to unknown property {item['property']!r}")
            check_date(item, where, "saleDate")
            if item.get("saleDate"):
                sold = month_index(item["saleDate"], f"{where}.saleDate")
                if sold < start:
                    raise ValueError(f"{where}: sale of {prop.get('name') or prop.get('id')} on "
                                     f"{item['saleDate'][:7]} is before the horizon start "
                                     f"{month_label(start)}; remove the asset, or move the horizon")
                if not month_index(prop["purchaseDate"], where) < sold <= end:
                    raise ValueError(f"{where}: saleDate must be after the purchase and within the horizon")
        if kind in ("income", "expense"):
            flow_amount(item, where)
            if item.get("taxable", False) not in (True, False):
                raise ValueError(f"{where}: taxable must be true or false")
            check_date(item, where, "startDate")
            month_index(item["startDate"], f"{where}.startDate")
            indexing = item.get("indexing") or "none"
            if indexing not in ("none", "inflation", "custom"):
                raise ValueError(f"{where}: indexing must be none, inflation or custom; got {indexing!r}")
            if (item.get("amountIn") or "start") not in ("start", "base"):
                raise ValueError(f"{where}: amountIn must be start or base; got {item['amountIn']!r}")
            if indexing == "custom" and not -1 < dec(item, "indexRate", where) < 1:
                raise ValueError(f"{where}: indexRate must be a fraction between -1 and 1, "
                                 f"e.g. 0.03 for 3%; got {item['indexRate']!r}")
        if item.get("endDate") and item.get("startDate"):
            if month_index(item["endDate"], f"{where}.endDate") < month_index(item["startDate"], where):
                raise ValueError(f"{where}: endDate is before startDate")
        # Rate ranges (ADR-0045): interest 0 <= r < 1; value and indexing rates -1 < r < 1.
        for field in ("annualAppreciation", "annualRate", "annualDepreciation"):
            if field in required[kind]:
                low = 0 if field == "annualRate" else -1
                r = dec(item, field, where)
                if not (low <= r < 1 if low == 0 else low < r < 1):
                    span = "between 0 and 1" if low == 0 else "between -1 and 1"
                    raise ValueError(f"{where}: {field} must be a fraction {span}, "
                                     f"e.g. 0.0379 for 3.79%; got {item[field]!r}")
        # Penalties (ADR-0047): optional amounts in dollars of the event date.
        for field in ("salePenalty", "penalty"):
            if item.get(field) and dec(item, field, where) < 0:
                raise ValueError(f"{where}: {field} must not be negative")
        if kind == "renewal":
            mtg = mortgages[item["mortgage"]]
            if month_index(item["startDate"], where) <= mortgage_start(mtg, assets, where):
                raise ValueError(f"{where}: startDate must be after the mortgage start")
            # Keep the payment and derive the amortisation (ADR-0043 amendment, C-M7).
            if not isinstance(item.get("keepPayment", False), bool):
                raise ValueError(f"{where}: keepPayment must be true or false")
            if item.get("keepPayment") and item.get("amortizationYears"):
                raise ValueError(f"{where}: keepPayment and amortizationYears are mutually "
                                 "exclusive; keeping the payment derives the amortization")
            if item.get("amortizationYears"):
                check_amortization(item, where)
            # A renewal in or after the month the securing property is sold would find no
            # loan, and its penalty would be lost (C-M10).
            sale = sales.get(mtg.get("property"))
            if sale:
                renew_at = month_index(item["startDate"], where)
                sold_at = month_index(sale["saleDate"], where)
                prop = assets[mtg["property"]]
                if renew_at >= sold_at:
                    when = "in the same month as" if renew_at == sold_at else "after"
                    raise ValueError(f"{where}: renewal of {mtg.get('name') or mtg.get('id')} on "
                                     f"{item['startDate'][:7]} is {when} the sale of "
                                     f"{prop.get('name') or prop.get('id')}; remove the renewal, "
                                     "or put the penalty on the sale")
            key = (item["mortgage"], month_index(item["startDate"], where))
            if key in renewal_months:
                raise ValueError(f"{where}: another renewal of this mortgage starts in the same month")
            renewal_months.add(key)
        if kind == "lumpSum":
            mtg = mortgages[item["mortgage"]]
            if item.get("payOff", False) not in (True, False):
                raise ValueError(f"{where}: payOff must be true or false")
            check_date(item, where, "paymentDate")
            if item.get("payOff") and item.get("amount"):
                raise ValueError(f"{where}: give an amount or payOff, not both")
            if month_index(item["paymentDate"], where) <= mortgage_start(mtg, assets, where):
                raise ValueError(f"{where}: paymentDate must be after the mortgage start")
        if kind == "lumpSum" and (item.get("paidFrom") or "cash") not in ("cash", "outside"):
            raise ValueError(f"{where}: paidFrom must be cash or outside; got {item['paidFrom']!r}")
        if kind == "extraPayment" or (kind == "lumpSum" and not item.get("payOff")):
            amount = dec(item, "monthlyAmount" if kind == "extraPayment" else "amount", where)
            if amount <= 0:
                raise ValueError(f"{where}: amount must be positive")
        if kind == "account":
            if item["accountType"] not in rules.account_types:
                raise ValueError(f"{where}: accountType must be one of "
                                 f"{', '.join(rules.account_types)}")
            if not -1 < dec(item, "annualReturn", where) < 1:
                raise ValueError(f"{where}: annualReturn must be a fraction between -1 and 1, "
                                 f"e.g. 0.05 for 5%; got {item['annualReturn']!r}")
            if item.get("withdrawalTaxRate") and not 0 <= dec(item, "withdrawalTaxRate", where) < 1:
                raise ValueError(f"{where}: withdrawalTaxRate must be a fraction between 0 and 1")
            if item.get("openingBalance") and dec(item, "openingBalance", where) < 0:
                raise ValueError(f"{where}: openingBalance must not be negative")
            if item.get("openedDate") and not month_index(item["openedDate"], where) <= end:
                raise ValueError(f"{where}: openedDate is after the horizon")
            source = item.get("openingFrom") or ""
            if source not in ("", "cash", "outside"):
                raise ValueError(f"{where}: openingFrom must be cash or outside; got {source!r}")
            # Opened inside the horizon with a balance: its source must be stated (ADR-0057).
            if (item.get("openedDate") and month_index(item["openedDate"], where) > start
                    and item.get("openingBalance") and dec(item, "openingBalance", where) > 0
                    and not source):
                raise ValueError(f"{where}: opens {item['openedDate'][:7]}, inside the horizon, with "
                                 "a balance; set openingFrom: cash (moved from cash) or outside "
                                 "(an existing balance not modelled before)")
        if kind == "pension":
            flow_amount(item, where)
            if not item.get("startDate") and not retirement:
                raise ValueError(f"{where}: needs a startDate or a retirement event")
            for field in ("startDate", "endDate"):
                if item.get(field):
                    month_index(item[field], f"{where}.{field}")
            # Effective start: its own start date, else the retirement date (C-M15).
            if item.get("startDate"):
                first, source = item["startDate"], "its start date"
            else:
                first, source = retirement, "retirement date"
            if item.get("endDate") and month_index(item["endDate"], where) < month_index(first, where):
                raise ValueError(f"{where}: ends {item['endDate'][:7]}, before its effective "
                                 f"start {first[:7]} ({source})")
            if item.get("taxable", True) not in (True, False):
                raise ValueError(f"{where}: taxable must be true or false")
            check_indexing(item, where)
        if kind == "contribution":
            flow_amount(item, where)
            if item.get("employerMatch") and not 0 <= dec(item, "employerMatch", where) <= 1:
                raise ValueError(f"{where}: employerMatch must be a fraction between 0 and 1, "
                                 f"e.g. 0.5 for 50%; got {item['employerMatch']!r}")
        if kind in ("contribution", "withdrawal"):
            check_indexing(item, where)
        if kind == "withdrawal":
            acct = accounts[item["account"]]
            # Blank start: from the retirement month (ADR-0059).
            begin = item.get("startDate") or retirement
            if not begin:
                raise ValueError(f"{where}: needs a startDate or a retirement event")
            month_index(begin, f"{where}.startDate")
            if item["method"] in ("percent", "annuity") and acct.get("openedDate"):
                opened = month_index(acct["openedDate"], where)
                if month_index(begin, f"{where}.startDate") < opened:
                    raise ValueError(f"{where}: starts {begin[:7]}, before its account "
                                     f"{acct.get('name') or acct.get('id')} opens "
                                     f"{acct['openedDate'][:7]}")
            if item["method"] not in WITHDRAWAL_METHODS:
                raise ValueError(f"{where}: method must be one of {', '.join(WITHDRAWAL_METHODS)}")
            # A percent withdrawal follows its balance: indexing cannot apply (C-M16).
            # A fixed amount or an annuity can be indexed (ADR-0039 amendment 2026-11-11).
            if item["method"] == "percent" and (item.get("indexing") or "none") != "none":
                raise ValueError(f"{where}: indexing applies only to methods 'amount' and "
                                 f"'annuity'; set indexing to none for method {item['method']!r}")
            if item["method"] == "amount" and not item.get("amount"):
                hint = (" To withdraw a percentage of the balance, choose method 'percent'."
                        if item.get("annualRate") else "")
                raise ValueError(f"{where}: method is 'amount' (a fixed amount) but no amount "
                                 f"is given.{hint}")
            if item["method"] == "percent" and not item.get("annualRate"):
                hint = (" To withdraw a fixed amount, choose method 'amount'."
                        if item.get("amount") else "")
                raise ValueError(f"{where}: method is 'percent' but no annualRate is given.{hint}")
            if item["method"] == "amount":
                flow_amount(item, where)
            if item["method"] == "percent" and not 0 < dec(item, "annualRate", where) < 1:
                raise ValueError(f"{where}: annualRate must be a fraction between 0 and 1, "
                                 f"e.g. 0.04 for 4%; got {item.get('annualRate')!r}")
        if kind == "transfer":
            if dec(item, "amount", where) <= 0:
                raise ValueError(f"{where}: amount must be positive")
            check_date(item, where, "transferDate")
            at = month_index(item["transferDate"], f"{where}.transferDate")
            if not start <= at <= end:
                raise ValueError(f"{where}: transferDate must be within the horizon")
            acct = accounts[item["account"]]
            if acct.get("openedDate") and at < month_index(acct["openedDate"], where):
                raise ValueError(f"{where}: transfers {item['transferDate'][:7]}, before its account "
                                 f"{acct.get('name') or acct.get('id')} opens")
        rules.validate_item(item, where, check)        # its own item types (ADR-0071)
        if kind in ("mortgage", "renewal"):
            check_closure(item, where)                  # ADR-0073
        if kind == "associatedExpense" and item.get("alsoWhenRenting", False) not in (True, False):
            raise ValueError(f"{where}: alsoWhenRenting must be true or false")
        if kind == "income" and item.get("earnedIncome", True) not in (True, False):
            raise ValueError(f"{where}: earnedIncome must be true or false")
        if kind == "retirement":
            at = month_index(item["retirementDate"], f"{where}.retirementDate")
            # outsideHorizon: an older file's retirementDate setting (upgrade.py).
            if not start <= at <= end and not item.get("outsideHorizon"):
                raise ValueError(f"{where}: retirementDate must be within the horizon")
        if kind == "cashBalance" and not start <= month_index(item["balanceDate"], where) <= end:
            raise ValueError(f"{where}: balanceDate must be within the horizon")
        if kind == "adjustment":
            flow = target_of(item, scenario["items"])
            if flow is None:
                raise ValueError(f"{where}: refers to unknown income, expense, contribution, "
                                 f"withdrawal, associated expense or associated income {item.get('flow')!r}")
            if flow["type"] == "withdrawal" and flow.get("method") not in ("amount", "percent"):
                raise ValueError(f"{where}: an annuity withdrawal cannot be adjusted (its "
                                 "amount is derived); adjust a fixed-amount or percent one")
            if is_percent(flow):
                if item.get("amount"):
                    raise ValueError(f"{where}: a percent withdrawal or percentage expense "
                                     "takes a new annualRate, not an amount")
                if not 0 < dec(item, "annualRate", where) < 1:
                    raise ValueError(f"{where}: annualRate must be a fraction between 0 and 1, "
                                     f"e.g. 0.04 for 4%; got {item['annualRate']!r}")
            else:
                if item.get("annualRate"):
                    raise ValueError(f"{where}: annualRate applies only to percent withdrawals "
                                     "and percentage expenses or incomes; give an amount")
                if dec(item, "amount", where) < 0:
                    raise ValueError(f"{where}: amount must not be negative")
                new_amount(item, flow, where)
            if not start <= month_index(item["adjustmentDate"], where) <= end:
                raise ValueError(f"{where}: adjustmentDate must be within the horizon")
        if kind == "marketAdjustment":
            # A property or (ADR-0033 amendment) a vehicle.
            prop = properties.get(item["property"]) or vehicles.get(item["property"])
            if prop is None:
                raise ValueError(f"{where}: refers to unknown property {item['property']!r}")
            at = month_index(item["adjustmentDate"], f"{where}.adjustmentDate")
            if at < start:
                raise ValueError(f"{where}: adjustmentDate is before the horizon start; include "
                                 "it in the property's marketValue instead")
            if at < month_index(prop["purchaseDate"], where) or at > end:
                raise ValueError(f"{where}: adjustmentDate must be on or after the purchase "
                                 "and within the horizon")
            sale = sales.get(item["property"])
            if sale and at >= month_index(sale["saleDate"], where):
                raise ValueError(f"{where}: adjustmentDate must be before the sale")
            if bool(item.get("percent")) == bool(item.get("newValue")):
                raise ValueError(f"{where}: give either percent or newValue, not both")
            if item.get("percent") and not -1 < dec(item, "percent", where) < 1:
                raise ValueError(f"{where}: percent must be a fraction between -1 and 1, "
                                 f"e.g. -0.15 for -15%; got {item['percent']!r}")
            if item.get("newValue") and dec(item, "newValue", where) < 0:
                raise ValueError(f"{where}: newValue must not be negative")
        if kind == "improvement":
            prop = properties.get(item["property"])
            if prop is None:
                raise ValueError(f"{where}: refers to unknown property {item['property']!r}")
            at = month_index(item["improvementDate"], f"{where}.improvementDate")
            if at < start:
                raise ValueError(f"{where}: improvementDate is before the horizon start; include "
                                 "it in the property's marketValue instead")
            if at < month_index(prop["purchaseDate"], where) or not at <= end:
                raise ValueError(f"{where}: improvementDate must be on or after the purchase "
                                 "and within the horizon")
            sale = sales.get(item["property"])
            if sale and at >= month_index(sale["saleDate"], where):
                raise ValueError(f"{where}: improvementDate must be before the sale")
            if dec(item, "cost", where) < 0 or (item.get("valueAdded")
                                                and dec(item, "valueAdded", where) < 0):
                raise ValueError(f"{where}: cost and valueAdded must not be negative")
        if kind in ("associatedExpense", "associatedCost"):
            check_associated(item, kind, where, scenario["items"], start, end)
        if kind in ("associatedIncome", "associatedOneOff"):
            check_associated_income(item, kind, where, scenario["items"], start, end)
        if kind == "mortgage" and item.get("firstPaymentDate"):
            first_pay = month_index(item["firstPaymentDate"], f"{where}.firstPaymentDate")
            if first_pay <= mortgage_start(item, assets, where):
                raise ValueError(f"{where}: firstPaymentDate must be after the mortgage start")
        if kind == "mortgage":
            check_amortization(item, where)


def check_associated(item, kind, where, items, start, end):
    """An associated expense or cost (ADR-0067)."""
    from .flows.associated import AT, BASES, PARENTS, parent_of
    parent = parent_of(item, items)
    if parent is None or parent.get("type") not in PARENTS:
        raise ValueError(f"{where}: parent refers to unknown item {item.get('parent')!r} (a "
                         "property, vehicle, account, mortgage or recurring item)")
    rate_field = "annualRate" if kind == "associatedExpense" else "rate"
    if bool(item.get("amount")) == bool(item.get(rate_field)):
        raise ValueError(f"{where}: give either an amount or a {rate_field}, not both")
    if item.get(rate_field):
        if not 0 < dec(item, rate_field, where) < 1:
            raise ValueError(f"{where}: {rate_field} must be a fraction between 0 and 1, "
                             f"e.g. 0.01 for 1%; got {item[rate_field]!r}")
        bases = BASES.get(parent["type"], ())
        if item.get("basis") not in bases:
            choices = " or ".join(bases) if bases else "none (use an amount)"
            raise ValueError(f"{where}: basis must be {choices} for a {parent['type']}; "
                             f"got {item.get('basis')!r}")
    elif kind == "associatedExpense":
        flow_amount(item, where)
        check_indexing(item, where)
    elif dec(item, "amount", where) < 0:
        raise ValueError(f"{where}: amount must not be negative")
    if kind == "associatedCost":
        at = item.get("at") or "start"
        if at not in AT:
            raise ValueError(f"{where}: at must be start, end or date; got {at!r}")
        if at == "date":
            check_date(item, where, "costDate")
            if not start <= month_index(item["costDate"], f"{where}.costDate") <= end:
                raise ValueError(f"{where}: costDate must be within the horizon")


def check_associated_income(item, kind, where, items, start, end):
    """An associated income or one-off income (ADR-0068)."""
    from .flows.associated import AT, parent_of
    from .flows.associated_income import PAID, PARENTS
    parent = parent_of(item, items)
    if parent is None or parent.get("type") not in PARENTS:
        raise ValueError(f"{where}: parent refers to unknown item {item.get('parent')!r} "
                         "(an income or a pension)")
    rate_field = "annualRate" if kind == "associatedIncome" else "rate"
    if bool(item.get("amount")) == bool(item.get(rate_field)):
        raise ValueError(f"{where}: give either an amount or a {rate_field}, not both")
    if item.get(rate_field):
        if not 0 < dec(item, rate_field, where) <= 10:
            raise ValueError(f"{where}: {rate_field} must be a positive fraction, "
                             f"e.g. 0.1 for 10%; got {item[rate_field]!r}")
    elif kind == "associatedIncome":
        flow_amount(item, where)
        check_indexing(item, where)
    elif dec(item, "amount", where) < 0:
        raise ValueError(f"{where}: amount must not be negative")
    if kind == "associatedIncome":
        paid = item.get("paid") or "monthly"
        if paid not in PAID:
            raise ValueError(f"{where}: paid must be monthly or lump; got {paid!r}")
        if paid == "lump" and (item.get("per") or "month") == "month":
            raise ValueError(f"{where}: a lump is paid per quarter or per year; set per")
    else:
        at = item.get("at") or "start"
        if at not in AT:
            raise ValueError(f"{where}: at must be start, end or date; got {at!r}")
        if at == "date":
            check_date(item, where, "paymentDate")
            if not start <= month_index(item["paymentDate"], f"{where}.paymentDate") <= end:
                raise ValueError(f"{where}: paymentDate must be within the horizon")


def check_indexing(item, where):
    """indexing is none, inflation or custom; custom needs an indexRate in (-1, 1)."""
    indexing = item.get("indexing") or "none"
    if indexing not in ("none", "inflation", "custom"):
        raise ValueError(f"{where}: indexing must be none, inflation or custom")
    if indexing == "custom" and not -1 < dec(item, "indexRate", where) < 1:
        raise ValueError(f"{where}: indexRate must be a fraction between -1 and 1")


def check_date(item, where, field):
    """A one-off item happens on ``field``, its own or set by a trigger (ADR-0065)."""
    if not item.get(field):
        raise ValueError(f"{where}: missing field {field!r} (give a date, or add a trigger)")


def check_persons(scenario):
    """Person items (ADR-0061): unique ids, rates as fractions. Returns their ids."""
    ids = []
    for item in person_items(scenario):
        where = f"item {item.get('name') or item.get('id')}"
        if not item.get("id"):
            raise ValueError(f"{where}: a person needs an id (owners refer to it)")
        if item["id"] in ids:
            raise ValueError(f"{where}: another person has the id {item['id']!r}")
        ids.append(item["id"])
        for field in ("effectiveTaxRate", "retirementTaxRate"):
            if item.get(field) and not 0 <= dec(item, field, where) < 1:
                raise ValueError(f"{where}: {field} must be a fraction between 0 and 1, "
                                 f"e.g. 0.25 for 25%; got {item[field]!r}")
        if item.get("birthDate"):                   # optional (ADR-0071)
            month_index(item["birthDate"], f"{where}.birthDate")
    return ids


def check_person_refs(item, kind, where, persons, rules=None):
    """owner, contributor and retirementOf name a person (ADR-0061)."""
    for field in ("owner", "contributor", "retirementOf"):
        pid = item.get(field)
        if not pid:
            continue
        if pid not in persons:
            raise ValueError(f"{where}: {field} refers to unknown person {pid!r}"
                             + ("" if persons else " (add a person item first)"))
    owned = owned_types()
    if item.get("owner") and kind not in owned:
        raise ValueError(f"{where}: owner applies only to {', '.join(owned)}; a "
                         f"{kind} belongs to the household (or to its account's owner)")
    if item.get("contributor"):
        rules = rules or jurisdictions.get(jurisdictions.DEFAULT)
        takes = [code for code, t in rules.account_types.items() if "contributor" in t.fields]
        kind_of = rules.account_types.get(item.get("accountType"))
        if kind != "account" or kind_of is None or "contributor" not in kind_of.fields:
            raise ValueError(f"{where}: contributor applies only to "
                             f"{' or '.join(takes) or 'no'} accounts"
                             + (" (spousal RRSP)" if takes == ["rrsp"] else ""))
        owner = item.get("owner") or persons[0]
        if item["contributor"] == owner:
            raise ValueError(f"{where}: contributor is the owner; leave contributor blank")


CLOSURE_FIELDS = {"flat": "penaltyAmount", "interestLeft": "penaltyRate",
                  "monthsInterest": "penaltyMonths"}


def check_closure(item, where):
    """A mortgage's or renewal's term and early-closure penalty (ADR-0073): termMonths a
    whole number > 0; penaltyMethod flat (penaltyAmount), interestLeft (penaltyRate, a
    fraction) or monthsInterest (penaltyMonths); both or neither."""
    months, method = item.get("termMonths"), item.get("penaltyMethod")
    if months in (None, "") and not method:
        return
    if months in (None, "") or not method:
        raise ValueError(f"{where}: give termMonths and penaltyMethod together")
    term = dec(item, "termMonths", where)
    if term <= 0 or term != term.to_integral_value():
        raise ValueError(f"{where}: termMonths must be a whole number of months, e.g. 60")
    if method not in CLOSURE_FIELDS:
        raise ValueError(f"{where}: penaltyMethod must be one of {', '.join(CLOSURE_FIELDS)}; "
                         f"got {method!r}")
    field = CLOSURE_FIELDS[method]
    if item.get(field) in (None, ""):
        raise ValueError(f"{where}: penaltyMethod {method} needs {field}")
    value = dec(item, field, where)
    if value < 0 or (field == "penaltyRate" and value > 1):
        raise ValueError(f"{where}: {field} must be " + ("a fraction between 0 and 1, e.g. "
                         "0.5 for 50%" if field == "penaltyRate" else "positive"))


def check_amortization(item, where):
    """Amortization in years must be a whole number of months, at least 1 (C-M11)."""
    months = dec(item, "amortizationYears", where) * 12
    if months < 1 or months != months.to_integral_value():
        raise ValueError(f"{where}: amortizationYears must be a whole number of months, at "
                         f"least 1 (e.g. 25, or 2.5 for 30 months); got {item['amortizationYears']!r}")
