"""United States (ADR-0071, first version): traditional and Roth 401(k) and IRA, HSA,
brokerage; yearly contribution limits with catch-up (``limits.py``). Social Security is a
pension item; federal tax, state tax and FICA are folded into the flat effective rate
(ADR-0004). Not modelled yet: required minimum distributions, the 10% early-withdrawal
penalty, HSA medical rules, 529 plans, Roth conversions."""
from .. import (DEFERRED, EXEMPT, TAXABLE, AccountType, Jurisdiction, Treatment,
                jurisdiction)
from .limits import LIMIT_TYPES, YearlyLimits

# HSA: contributions deductible, growth and (medical) withdrawals tax-free.
HSA = Treatment(deductible=True, returns_taxed=False, withdrawal_taxed=False)


@jurisdiction("US")
class UnitedStates(Jurisdiction):
    name = "United States"
    account_types = {
        "traditional401k": AccountType("traditional401k", "401(k), traditional (tax-deferred)",
                                       DEFERRED, "401(k)"),
        "roth401k": AccountType("roth401k", "401(k), Roth (tax-free)", EXEMPT, "Roth 401(k)"),
        "traditionalIra": AccountType("traditionalIra", "IRA, traditional (tax-deferred)",
                                      DEFERRED, "IRA"),
        "rothIra": AccountType("rothIra", "IRA, Roth (tax-free)", EXEMPT, "Roth IRA"),
        "hsa": AccountType("hsa", "HSA (health savings account)", HSA, "HSA"),
        "brokerage": AccountType("brokerage", "brokerage (returns taxed)", TAXABLE,
                                 "brokerage"),
    }
    item_types = ("contributionLimit",)
    required = {"contributionLimit": ["limitType", "yearlyLimit"]}
    choice_fields = ("limitType",)
    owned_types = ("contributionLimit",)
    labels = {"deductions": "Deductions this month (traditional 401(k) and IRA, HSA, "
                            "pension plan)",
              "pool": "traditional 401(k), IRA, HSA and pension plan contributions",
              "earned": "counts as earned income (salary)"}
    limits = YearlyLimits()

    form_fields = {"contributionLimit": ["limitType", "yearlyLimit", "limitYear", "catchUp",
                                         "contributedSoFar", "indexing", "indexRate"]}
    legends = {
        "contributionLimit": "Contribution limit (401(k), IRA or HSA): caps each year's "
                             "contributions",
        "account": "Account: 401(k), IRA (traditional or Roth), HSA or brokerage",
        "pension": "Guaranteed pension (defined benefit, Social Security)",
    }
    hints = {
        ("contributionLimit", "limitType"): "401(k) covers traditional and Roth together; "
                                            "so does IRA; one item per type and person",
        ("contributionLimit", "yearlyLimit"): "the employee limit, e.g. 23500 (401(k)), "
                                              "7000 (IRA), 4300 (HSA)",
        ("contributionLimit", "limitYear"): "the year yearlyLimit applies to; blank = the "
                                            "horizon's first year",
        ("contributionLimit", "catchUp"): "extra from age 50 (HSA: 55), e.g. 7500 or 1000; "
                                          "needs the person's birth date",
        ("contributionLimit", "contributedSoFar"): "already contributed in the horizon's "
                                                   "first year",
        ("contributionLimit", "indexing"): "how the limits grow; rounded down to $500 "
                                           "($50 for HSA)",
        ("contributionLimit", "owner"): "whose limit; blank = the first person",
        ("income", "earnedIncome"): "earned income (salary); blank = same as taxable",
        "withdrawalTaxRate": "optional, traditional 401(k) and IRA only; blank = income tax "
                             "rate",
        ("transfer", "account"): "any account; into a traditional 401(k), IRA or HSA it is "
                                 "deducted",
        ("pension", "amount"): "in today's dollars, e.g. your Social Security estimate",
    }
    selects = {"limitType": [(t, label) for t, label in
                             zip(LIMIT_TYPES, ("401(k), traditional and Roth together",
                                               "IRA, traditional and Roth together",
                                               "HSA"))]}
    add_groups = {"People & settings": ["contributionLimit"]}
    head_adds = {"person": ["contributionLimit"]}

    def validate_item(self, item, where, check):
        if item.get("type") != "contributionLimit":
            return
        from ...arith import dec
        from ...persons import owner_of
        from ...validation import check_indexing
        if item.get("limitType") not in LIMIT_TYPES:
            raise ValueError(f"{where}: limitType must be one of {', '.join(LIMIT_TYPES)}; "
                             f"got {item.get('limitType')!r}")
        seen = check.seen.setdefault("limit_types", set())
        key = (owner_of(item, check.scenario), item["limitType"])
        if key in seen:
            raise ValueError(f"{where}: only one contributionLimit item per limit type "
                             f"({item['limitType']})"
                             + (f" and person ({key[0]})" if check.persons else ""))
        seen.add(key)
        for field in ("yearlyLimit", "catchUp", "contributedSoFar"):
            if item.get(field) not in (None, "") and dec(item, field, where) < 0:
                raise ValueError(f"{where}: {field} must not be negative")
        if item.get("limitYear") and not str(item["limitYear"]).strip().isdigit():
            raise ValueError(f"{where}: limitYear must be a year, e.g. 2026; "
                             f"got {item['limitYear']!r}")
        check_indexing(item, where)
