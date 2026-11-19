"""The item-type schema (ADR-0069 decision 4): what each item type's form has (fields in
SPEC JSON key order, choices, hints, legends, groups), served by the API's schema
endpoint so any client can build its forms; the Jinja builder uses it too.

The core types are here; a jurisdiction adds its own item types, account types, wording
and groups (ADR-0071): ``describe(code)`` merges them for one jurisdiction and leaves
out every other jurisdiction's types."""
import copy

from state_machine import jurisdictions
from state_machine.persons import OWNED_TYPES
from state_machine.views import HOST_FIELD

# Fields per item type, in SPEC JSON key order (after type, id, name).
FIELDS = {
    "property": ["purchaseDate", "price", "marketValue", "annualAppreciation"],
    # A term with its early-closure penalty (ADR-0073), here and on renewals.
    "mortgage": ["property", "startDate", "principal", "annualRate", "amortizationYears",
                 "firstPaymentDate", "termMonths", "penaltyMethod", "penaltyAmount",
                 "penaltyRate", "penaltyMonths"],
    # Running costs are associated expenses (ADR-0067).
    "vehicle": ["purchaseDate", "price", "annualDepreciation"],
    "income": ["startDate", "endDate", "amount", "per", "amountIn",
               "taxable", "earnedIncome", "indexing", "indexRate"],
    "expense": ["startDate", "endDate", "amount", "per",
                "amountIn", "indexing", "indexRate"],
    "extraPayment": ["mortgage", "startDate", "endDate", "monthlyAmount"],
    "lumpSum": ["mortgage", "paymentDate", "covers", "amount", "paidFrom",
                "penalty"],
    "renewal": ["mortgage", "startDate", "annualRate", "keepPayment", "amortizationYears",
                "penalty", "termMonths", "penaltyMethod", "penaltyAmount", "penaltyRate",
                "penaltyMonths"],
    "improvement": ["property", "improvementDate", "cost", "valueAdded"],
    "account": ["accountType", "openingBalance", "openedDate", "openingFrom", "annualReturn",
                "withdrawalTaxRate"],
    "contribution": ["account", "startDate", "endDate", "amount", "per",
                     "employerMatch", "indexing", "indexRate"],
    "withdrawal": ["account", "method", "startDate", "endDate", "amount", "per",
                   "annualRate", "indexing", "indexRate"],
    "pension": ["amount", "per", "startDate", "endDate", "taxable", "indexing",
                "indexRate"],
    # Selling costs are associated costs at the asset's end (ADR-0067).
    "sale": ["property", "saleDate", "salePrice", "salePenalty"],
    "marketAdjustment": ["property", "adjustmentDate", "percent", "newValue"],
    "transfer": ["account", "transferDate", "amount"],
    "retirement": ["retirementDate"],
    # A person of the household (ADR-0061); birthDate for age rules (ADR-0071).
    "person": ["birthDate", "effectiveTaxRate", "retirementTaxRate"],
    # A new amount for a cash flow from a date (ADR-0062).
    "adjustment": ["flow", "adjustmentDate", "amount", "per", "annualRate"],
    # The actual cash balance at the end of a month (ADR-0063).
    "cashBalance": ["balanceDate", "balance"],
    # Ties a target's start or end to an event item's date (ADR-0065).
    "trigger": ["event", "on", "target", "action"],
    # Items that live with a parent item (ADR-0067): an amount, or a rate of a basis.
    "associatedExpense": ["parent", "amount", "per", "indexing", "indexRate", "annualRate",
                          "basis", "alsoWhenRenting"],
    "associatedCost": ["parent", "at", "costDate", "amount", "rate", "basis"],
    # Income that lives with an income or a pension (ADR-0068): an amount or a % of it.
    "associatedIncome": ["parent", "amount", "per", "paid", "indexing", "indexRate",
                         "annualRate"],
    "associatedOneOff": ["parent", "at", "paymentDate", "amount", "rate"],
}

# Person fields (ADR-0061), shown only once the scenario has a person: whose item it is,
# and whose room a spousal RRSP uses (contributor: only where an account type takes it,
# ADR-0071). (Which retirement an item follows is now the
# trigger's event, ADR-0065.)
PERSON_FIELDS = {
    "owner": OWNED_TYPES,
    "contributor": ("account",),
}
for _field, _kinds in PERSON_FIELDS.items():
    for _kind in _kinds:
        FIELDS[_kind].append(_field)

# Form legends (default: the type name, capitalised).
LEGENDS = {
    "extraPayment": "Extra monthly payment (mortgage)",
    "lumpSum": "Lump-sum payment (mortgage)",
    "renewal": "Renewal or switch to another lender (mortgage)",
    "improvement": "Improvement: construction or renovation (property)",
    "account": "Investment account",
    "contribution": "Contribution (account)",
    "withdrawal": "Withdrawal (account)",
    "pension": "Guaranteed pension (defined benefit, government pension)",
    "sale": "Sale (property or vehicle): pays off a property's mortgages",
    "marketAdjustment": "Market adjustment (property or vehicle): a one-off change in value",
    "adjustment": "Adjustment: a new amount (or a percent withdrawal's new rate) from a date",
    "cashBalance": "Cash balance: set cash to an actual statement balance",
    "transfer": "One-off transfer from cash into an account",
    "retirement": "Retirement: tie items to it with triggers",
    "trigger": "Trigger: tie an item's start or end to another item's date (e.g. retirement)",
    "person": "Person: an earner with own tax, accounts, limits and retirement",
    "associatedExpense": "Associated expense: paid while its parent exists (e.g. property "
                         "tax, maintenance, account fees)",
    "associatedCost": "Associated cost: one-off at its parent's start, end or a date "
                      "(e.g. closing or selling costs)",
    "associatedIncome": "Associated income: paid while its income or pension runs (e.g. a "
                        "bonus, a 13th-month pension); taxed as its parent",
    "associatedOneOff": "Associated one-off income: at its parent's start, end or a date "
                        "(e.g. signing bonus, severance)",
}

# Hints after a field label: by (type, field) first, then by field.
HINTS = {
    ("associatedExpense", "parent"): "it is paid from this item's start to its end",
    ("associatedExpense", "amount"): "either an amount (indexed as an expense) ...",
    ("associatedExpense", "annualRate"): "... or a yearly % of the basis, re-set on each "
                                         "anniversary of the parent's start",
    ("associatedCost", "parent"): "the item it belongs to",
    ("associatedCost", "at"): "the parent's start (purchase), end (sale) or the date below",
    ("associatedCost", "costDate"): "only for at a date; it is dropped if the parent is gone",
    ("associatedCost", "amount"): "either an amount ...",
    ("associatedCost", "rate"): "... or a % of the basis that month (at a sale: the sale price)",
    ("associatedIncome", "parent"): "an income or pension; taxed and owned as it",
    ("associatedIncome", "amount"): "either an amount (indexed as an income) ...",
    ("associatedIncome", "annualRate"): "... or a yearly % of the parent's yearly amount, "
                                        "re-set on each anniversary of its start",
    ("associatedIncome", "paid"): "a lump: the whole quarter or year (per) at its end; "
                                  "a partial last one is not paid",
    ("associatedOneOff", "parent"): "an income or pension; taxed and owned as it",
    ("associatedOneOff", "at"): "the parent's start, its last month or the date below",
    ("associatedOneOff", "paymentDate"): "only for at a date; dropped if the parent is not "
                                         "running then",
    ("associatedOneOff", "amount"): "either an amount ...",
    ("associatedOneOff", "rate"): "... or a % of the parent's yearly amount that month",
    "basis": "with a %: property/vehicle value or price; account balance; mortgage principal "
             "or balance; income amount",
    ("renewal", "amortizationYears"): "optional: new amortization, e.g. new lender; "
                                      "not with keep the payment",
    ("renewal", "keepPayment"): "yes: the payment stays, prepayment savings shorten the "
                                "loan; falls back to a new payment if it cannot repay it",
    ("mortgage", "startDate"): "blank = purchase date",
    ("mortgage", "property"): "the property it is secured by, or the vehicle it finances",
    ("withdrawal", "method"): "choose first: which of the fields below is used",
    ("income", "earnedIncome"): "counts for contribution limits (salary); blank = same as "
                                "taxable",
    ("person", "birthDate"): "optional; age rules (e.g. catch-up contributions)",
    ("person", "effectiveTaxRate"): "blank = the scenario's income tax",
    ("person", "retirementTaxRate"): "blank = the scenario's retirement tax",
    "owner": "blank = the first person",
    "contributor": "whose limits and deduction; blank = the owner",
    ("withdrawal", "startDate"): "blank = retirement",
    ("retirement", "retirementDate"): "pensions and draws without a start begin, tax "
                                      "switches to the retirement rate",
    ("trigger", "event"): "the item whose date is used, e.g. a retirement or a sale",
    ("trigger", "on"): "end: the month after the event's last month; for a property or "
                       "vehicle, its sale (never ends: no effect)",
    ("trigger", "target"): "the item whose date is set; the trigger's date replaces its own",
    ("withdrawal", "amount"): "only for method fixed amount",
    ("withdrawal", "per"): "only for method fixed amount",
    ("withdrawal", "annualRate"): "only for method percent, e.g. 4",
    ("withdrawal", "indexing"): "fixed amount or annuity: inflation keeps the purchasing "
                                "power; keep none for percent",
    ("pension", "amount"): "in today's dollars, i.e. of the base date",
    ("income", "startDate"): "blank only if a trigger sets it",
    ("expense", "startDate"): "blank only if a trigger sets it; tie it to a property, vehicle "
                              "or income with triggers (start with it, end on its end)",
    ("pension", "startDate"): "blank = retirement date",
    ("contribution", "account"): "an account or a pension plan",
    "endDate": "blank = never, or set by a trigger",
    "indexRate": "only for custom",
    "sellingCostRate": "optional",
    "salePenalty": "optional, $ on that date",
    "penalty": "optional, $ on that date",
    "firstPaymentDate": "blank = month after start",
    # Early-closure penalty of a term (ADR-0073).
    "termMonths": "optional: term length from its start, e.g. 60; with a penalty method",
    "penaltyMethod": "early-closure penalty during the term (a sale or payoff without "
                     "its own penalty, and the break-even)",
    "penaltyAmount": "only for a flat amount",
    "penaltyRate": "only for a share of the interest left in the term, e.g. 100",
    "penaltyMonths": "only for months of interest, e.g. 3",
    ("renewal", "penalty"): "optional, $ for breaking the previous term now",
    "alsoWhenRenting": "yes: a renter pays it too (e.g. utilities), left out of the "
                       "break-even's ownership costs",
    "valueAdded": "optional, blank = cost",
    "marketValue": "optional, blank = price",
    "openingBalance": "blank = 0",
    "openedDate": "blank = horizon start",
    "openingFrom": "needed if opened inside the horizon with a balance",
    "withdrawalTaxRate": "optional, tax-deferred accounts only; blank = income tax rate",
    "employerMatch": "optional, share of each contribution",
    "maintenanceIncrease": "optional, yearly on the purchase anniversary",
    ("cashBalance", "balanceDate"): "cash is set at the end of that month",
    ("cashBalance", "balance"): "the actual balance; the difference is shown as a "
                                "reconciliation, not taxed",
    ("adjustment", "flow"): "an income, expense, contribution, or a fixed-amount or percent "
                            "withdrawal",
    ("adjustment", "amount"): "not for percent withdrawals; in dollars of the adjustment "
                              "date, indexing continues from it",
    ("adjustment", "per"): "with amount; usually the same as the item's",
    ("adjustment", "annualRate"): "only for percent withdrawals: the new rate, e.g. 5",
    ("marketAdjustment", "property"): "property or vehicle",
    ("marketAdjustment", "percent"): "e.g. -15 for a 15% drop; or leave blank and give newValue",
    ("marketAdjustment", "newValue"): "or: the value at the end of that month",
    ("sale", "property"): "property or vehicle",
    ("sale", "salePrice"): "optional, blank = its value that month",
    ("sale", "saleDate"): "blank only if a trigger sets it",
    ("lumpSum", "paymentDate"): "blank only if a trigger sets it",
    ("transfer", "transferDate"): "blank only if a trigger sets it",
    ("transfer", "account"): "any account; deducted where its type is deductible",
    ("lumpSum", "amount"): "only for the amount below",
    ("sale", "sellingCostRate"): "optional, e.g. agent fees or a trade-in discount",
}

# What a blank date means, shown in the Items table's Details.
BLANK_SHOWN = {("pension", "startDate"): "at retirement",
               ("withdrawal", "startDate"): "at retirement",
               ("mortgage", "startDate"): "with its property",
               ("account", "openedDate"): "horizon start"}

# Pre-selected dropdown values (default: the first option).
DEFAULTS = {}

# Item types whose form needs another item to exist first.
NEEDS = {"extraPayment": "mortgage", "lumpSum": "mortgage", "renewal": "mortgage",
         "improvement": "property", "contribution": "account", "withdrawal": "account",
         "sale": "asset", "marketAdjustment": "asset", "transfer": "account",
         "adjustment": "flow", "trigger": "dated", "associatedExpense": "lifetime",
         "associatedCost": "lifetime", "associatedIncome": "earner",
         "associatedOneOff": "earner"}

# Modifier item types (D-E1) and the field naming their host: views.HOST_FIELD. In "Add
# an item" their forms are grouped per host type.

# "Add an item" form groups: (heading or None, item types, hint shown when none is enabled).
FORM_GROUPS = [
    (None, [k for k in FIELDS if k not in HOST_FIELD], None),
    ("Mortgage changes", ["extraPayment", "lumpSum", "renewal"],
     "Add a mortgage to enable extra payments, lump sums and renewals."),
    ("Property and vehicle changes", ["improvement", "marketAdjustment", "sale"],
     "Add a property or vehicle to enable improvements, market adjustments and sales."),
    ("Account changes", ["contribution", "withdrawal", "transfer"],
     "Add an account to enable contributions and withdrawals."),
    ("Cash flow changes", ["adjustment"],
     "Add an income, expense, contribution or fixed-amount withdrawal to enable adjustments."),
    ("Triggers", ["trigger"], "Add an item with a date to enable triggers."),
    ("Associated expenses and costs", ["associatedExpense", "associatedCost"],
     "Add a property, vehicle, account, mortgage or recurring item to enable associated "
     "expenses and costs."),
    ("Associated income", ["associatedIncome", "associatedOneOff"],
     "Add an income or a pension to enable associated income."),
]
assert sorted(k for _, kinds, _ in FORM_GROUPS for k in kinds) == sorted(FIELDS)

# Rate fields are typed as percentages in the form (3.79) and stored as fractions (0.0379).
# Fields shown as dropdowns: (value, label), first one is the default.
SELECTS = {
    "per": [("month", "per month"), ("quarter", "per quarter"), ("year", "per year")],
    "taxable": [("yes", "yes, before tax"), ("no", "no, after tax")],
    "covers": [("amount", "the amount below"), ("all", "the whole balance (pay off)")],
    # Associated items (ADR-0067).
    "basis": [("", "- (an amount)"), ("value", "value (property, vehicle)"),
              ("price", "purchase price (property, vehicle)"),
              ("balance", "balance (account, mortgage)"),
              ("principal", "principal (mortgage)"), ("amount", "its amount (income)")],
    "paid": [("monthly", "monthly"), ("lump", "a lump at the end of each quarter / year")],
    "at": [("start", "its start (purchase, opening)"), ("end", "its end (sale, last month)"),
           ("date", "on the date below")],
    # Trigger actions (ADR-0065).
    "on": [("start", "its date (start, purchase, sale...)"),
           ("end", "its end (last month + 1, or sale)")],
    "action": [("start", "start: starts (or happens) in the event's month"),
               ("end", "end: last month is the month before the event"),
               ("startAndEnd", "start and end: only in the event's month")],
    "method": [("amount", "fixed amount"), ("percent", "percent of balance, reset yearly"),
               ("annuity", "annuity: spend the account down by the end")],
    "paidFrom": [("cash", "cash"), ("outside", "outside money (not from cash)")],
    # Renewal (ADR-0043 amendment, C-M7): stored as a JSON bool.
    "keepPayment": [("no", "no: lower the payment"),
                    ("yes", "yes: keep the payment, shorten the amortization")],
    "amountIn": [("start", "dollars of its start date"),
                 ("base", "today's dollars (base date), inflated to the start")],
    "openingFrom": [("", "not needed"), ("cash", "moved from cash"),
                    ("outside", "existing balance, not modelled before")],
    "indexing": [("none", "none (fixed)"), ("inflation", "inflation"), ("custom", "custom rate")],
    "earnedIncome": [("", "same as taxable"), ("yes", "yes"), ("no", "no")],
    "penaltyMethod": [("", "none"), ("flat", "flat amount"),
                      ("interestLeft", "% of the interest left in the term"),
                      ("monthsInterest", "months of interest")],
    "alsoWhenRenting": [("no", "no: an ownership cost"), ("yes", "yes: renters pay it too")],
}

PERCENT_FIELDS = {"annualAppreciation", "annualRate", "annualDepreciation", "indexRate", "rate",
                  "sellingCostRate", "annualReturn", "withdrawalTaxRate", "employerMatch",
                  "percent", "maintenanceIncrease", "effectiveTaxRate",
                  "retirementTaxRate", "penaltyRate"}


# Builder cards (ADR-0070): the item types that can be added on an open card of each
# type, and the field that links a new item to the card it is added on.
CARD_ADDS = {
    "property": ["mortgage", "sale", "improvement", "marketAdjustment", "renewal",
                 "extraPayment", "lumpSum", "associatedExpense", "associatedCost", "trigger"],
    "vehicle": ["mortgage", "sale", "marketAdjustment", "associatedExpense", "associatedCost",
                "trigger"],
    "mortgage": ["renewal", "extraPayment", "lumpSum", "associatedExpense", "associatedCost",
                 "trigger"],
    "income": ["adjustment", "associatedIncome", "associatedOneOff", "associatedExpense",
               "associatedCost", "trigger"],
    "pension": ["associatedIncome", "associatedOneOff", "associatedExpense", "trigger"],
    "account": ["contribution", "withdrawal", "transfer", "associatedExpense", "trigger"],
    "expense": ["adjustment", "associatedExpense", "associatedCost", "trigger"],
}
# The flat builder's "+ Add" bar, by category (ADR-0070 amendment); every type once.
# Sale and market adjustment work for properties and vehicles alike; they are listed
# with properties.
ADD_GROUPS = [
    ("People & settings", ["person", "retirement", "cashBalance"]),
    ("Income & pensions", ["income", "pension", "associatedIncome", "associatedOneOff"]),
    ("Accounts", ["account", "contribution", "withdrawal", "transfer"]),
    ("Properties & mortgages", ["property", "mortgage", "renewal", "extraPayment", "lumpSum",
                                "improvement", "marketAdjustment", "sale"]),
    ("Vehicles", ["vehicle"]),
    ("Expenses", ["expense", "associatedExpense", "associatedCost", "adjustment"]),
    ("Triggers", ["trigger"]),
]
assert sorted(k for _, kinds in ADD_GROUPS for k in kinds) == sorted(FIELDS)
HEAD_ADDS = {"person": ["retirement"], "scenario": ["person", "cashBalance"]}
LINK_FIELD = {"mortgage": "property", "sale": "property", "improvement": "property",
              "marketAdjustment": "property", "renewal": "mortgage", "extraPayment": "mortgage",
              "lumpSum": "mortgage", "contribution": "account", "withdrawal": "account",
              "transfer": "account", "adjustment": "flow", "associatedExpense": "parent",
              "associatedCost": "parent", "associatedIncome": "parent",
              "associatedOneOff": "parent", "trigger": "target"}


def merged(code=None):
    """The schema for one jurisdiction (ADR-0071): the core plus its own item types,
    account types, wording and groups; other jurisdictions' types left out."""
    rules = jurisdictions.get(code or jurisdictions.DEFAULT)
    fields = copy.deepcopy(FIELDS)
    for kind, own in rules.form_fields.items():
        fields[kind] = list(own) + (["owner"] if kind in rules.owned_types else [])
    if not any("contributor" in t.fields for t in rules.account_types.values()):
        fields["account"].remove("contributor")
    # Fields only some account types take (e.g. an RESP's grant history, ADR-0072).
    at = fields["account"].index("withdrawalTaxRate") + 1
    extra = [f for t in rules.account_types.values() for f in t.fields
             if f != "contributor" and f not in fields["account"]]
    fields["account"][at:at] = list(dict.fromkeys(extra))
    person_fields = {f: [k for k in kinds if k in fields] for f, kinds in PERSON_FIELDS.items()}
    person_fields["owner"] += [k for k in rules.owned_types if k in fields]
    person_fields = {f: kinds for f, kinds in person_fields.items()
                     if f != "contributor" or "contributor" in fields["account"]}
    selects = dict(SELECTS, **rules.selects)
    selects["accountType"] = [(code_, t.label) for code_, t in rules.account_types.items()]
    form_groups = [(h, list(kinds), missing) for h, kinds, missing in FORM_GROUPS]
    form_groups[0][1].extend(k for k in rules.form_fields if k not in HOST_FIELD)
    add_groups = [(t, list(kinds) + list(rules.add_groups.get(t, ()))) for t, kinds in ADD_GROUPS]
    head_adds = {k: list(v) + list(rules.head_adds.get(k, ())) for k, v in HEAD_ADDS.items()}
    return {"jurisdiction": rules, "fields": fields, "person_fields": person_fields,
            "legends": {**LEGENDS, **rules.legends}, "hints": {**HINTS, **rules.hints},
            "selects": selects, "percent_fields": PERCENT_FIELDS | set(rules.percent_fields),
            "form_groups": form_groups, "add_groups": add_groups, "head_adds": head_adds}


def describe(code=None):
    """The schema of one jurisdiction (default Canada) as JSON values (tuples as lists;
    (type, field) keys as "type.field"); ``jurisdictions`` lists every one to choose from."""
    pair = lambda key: ".".join(key) if isinstance(key, tuple) else key
    m = merged(code)
    rules = m["jurisdiction"]
    return {
        "jurisdiction": {"code": rules.code, "name": rules.name, "labels": rules.labels,
                         "columns": rules.limits.columns},
        "jurisdictions": [{"code": c, "name": j.name}
                          for c, j in sorted(jurisdictions.registered().items())],
        "fields": m["fields"],
        "personFields": m["person_fields"],
        "legends": m["legends"],
        "hints": {pair(k): v for k, v in m["hints"].items()},
        "blankShown": {pair(k): v for k, v in BLANK_SHOWN.items()},
        "defaults": {pair(k): v for k, v in DEFAULTS.items()},
        "needs": NEEDS,
        "hostField": HOST_FIELD,
        "formGroups": [{"heading": h, "types": kinds, "missing": missing}
                       for h, kinds, missing in m["form_groups"]],
        "selects": {f: [{"value": v, "label": label} for v, label in options]
                    for f, options in m["selects"].items()},
        "percentFields": sorted(m["percent_fields"]),
        "cardAdds": CARD_ADDS, "headAdds": m["head_adds"], "linkField": LINK_FIELD,
        "addGroups": [{"title": t, "types": kinds} for t, kinds in m["add_groups"]],
    }
