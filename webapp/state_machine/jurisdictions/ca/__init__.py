"""Canada (ADR-0004, ADR-0071): RRSP, TFSA, RESP and non-registered accounts; contribution
room per person and account type (ADR-0060, ``room.py``); the spousal RRSP's contributor
(ADR-0061); an RRSP withdrawal at the account's own rate (ADR-0035); the RESP's grant and
lifetime limit (ADR-0072, ``resp.py``)."""
from .. import DEFERRED, EXEMPT, TAXABLE, AccountType, Jurisdiction, jurisdiction
from . import resp
from .room import ROOM_TYPES, RoomLimits


@jurisdiction("CA")
class Canada(Jurisdiction):
    name = "Canada"
    account_types = {
        "tfsa": AccountType("tfsa", "TFSA (tax-free)", EXEMPT, "TFSA"),
        "rrsp": AccountType("rrsp", "RRSP (tax-deferred)", DEFERRED, "RRSP",
                            fields=("contributor",)),
        "nonRegistered": AccountType("nonRegistered", "non-registered (returns taxed)",
                                     TAXABLE, "non-registered"),
        # One beneficiary's education savings, with the CESG grant (ADR-0072).
        "resp": AccountType("resp", "RESP (education savings, with the CESG grant)", EXEMPT,
                            "RESP", fields=resp.FIELDS),
    }
    item_types = ("contributionRoom",)
    # Contribution room of one account type (ADR-0060): at most one per type; optional
    # maxYear (default: the as-of year), incomeRate (rrsp, default 0.18), indexing.
    required = {"contributionRoom": ["accountType", "room", "roomAsOfDate", "yearlyMax"]}
    owned_types = ("contributionRoom",)
    labels = {"deductions": "Deductions this month (RRSP, pension plan)",
              "pool": "RRSP and pension plan contributions",
              "earned": "counts for RRSP room (salary)"}
    limits = RoomLimits()

    # Forms (ADR-0071): contribution room per account type (ADR-0060).
    form_fields = {"contributionRoom": ["accountType", "room", "roomAsOfDate", "yearlyMax",
                                        "maxYear", "incomeRate", "indexing", "indexRate"]}
    legends = {
        "contributionRoom": "Contribution room (RRSP or TFSA): caps contributions and transfers",
        "account": "Account: RRSP, TFSA, RESP or non-registered",
        "pension": "Guaranteed pension (defined benefit, CPP, OAS)",
        "person": "Person: an earner with own tax, accounts, room and retirement",
    }
    hints = {
        ("contributionRoom", "accountType"): "rrsp or tfsa; one item per type, shared by its "
                                             "accounts",
        ("contributionRoom", "room"): "room available on the date below, e.g. from your "
                                      "notice of assessment",
        ("contributionRoom", "yearlyMax"): "RRSP dollar maximum or TFSA annual limit, e.g. "
                                           "33810 or 7000",
        ("contributionRoom", "maxYear"): "the year yearlyMax applies to; blank = year of the "
                                         "date",
        ("contributionRoom", "incomeRate"): "RRSP only: share of last year's earned income, "
                                            "blank = 18",
        ("contributionRoom", "indexing"): "how yearlyMax grows; rounded to $10 (RRSP) or $500 "
                                          "(TFSA)",
        ("contributionRoom", "owner"): "whose room; blank = the first person",
        ("income", "earnedIncome"): "counts for RRSP room (salary); blank = same as taxable",
        "contributor": "spousal RRSP only: whose room and deduction; blank = the owner",
        "withdrawalTaxRate": "optional, RRSP only; blank = income tax rate",
        "unusedGrantRoom": "RESP only: CESG room not used before the horizon (blank = 0)",
        "grantReceived": "RESP only: CESG received so far, of $7,200 (blank = 0)",
        "contributedSoFar": "RESP only: contributions so far, of the $50,000 limit "
                            "(blank = 0)",
        ("transfer", "account"): "RRSP, TFSA or non-registered; into an RRSP it is deducted",
    }
    percent_fields = ("incomeRate",)
    add_groups = {"People & settings": ["contributionRoom"]}
    head_adds = {"person": ["contributionRoom"]}

    def on_contribute(self, household, account, amount, source=None):
        super().on_contribute(household, account, amount, source)
        if getattr(account, "account_type", None) == "resp":
            resp.pay_grant(household, account, amount, source)       # ADR-0072

    def validate_item(self, item, where, check):
        if item.get("type") == "account":
            self.validate_account(item, where)
        if item.get("type") != "contributionRoom":
            return
        from ...arith import dec
        from ...dates import month_index
        from ...persons import owner_of
        from ...validation import check_indexing
        if item.get("accountType") not in ROOM_TYPES:
            raise ValueError(f"{where}: accountType must be rrsp or tfsa; "
                             f"got {item.get('accountType')!r}")
        room_types = check.seen.setdefault("room_types", set())
        room_key = (owner_of(item, check.scenario), item["accountType"])
        if room_key in room_types:
            raise ValueError(f"{where}: only one contributionRoom item per account type "
                             f"({item['accountType']})"
                             + (f" and person ({room_key[0]})" if check.persons else ""))
        room_types.add(room_key)
        if not check.start <= month_index(item["roomAsOfDate"], where) <= check.end:
            raise ValueError(f"{where}: roomAsOfDate must be within the horizon")
        for field in ("room", "yearlyMax"):
            if dec(item, field, where) < 0:
                raise ValueError(f"{where}: {field} must not be negative")
        if item.get("maxYear") and not str(item["maxYear"]).strip().isdigit():
            raise ValueError(f"{where}: maxYear must be a year, e.g. 2026; got {item['maxYear']!r}")
        if item.get("incomeRate") and not 0 <= dec(item, "incomeRate", where) <= 1:
            raise ValueError(f"{where}: incomeRate must be a fraction between 0 and 1, "
                             f"e.g. 0.18 for 18%")
        check_indexing(item, where)

    @staticmethod
    def validate_account(item, where):
        """An RESP's own fields: amounts, not negative; only on an RESP (ADR-0072)."""
        from ...arith import dec
        for field in resp.FIELDS:
            if item.get(field) in (None, ""):
                continue
            if item.get("accountType") != "resp":
                raise ValueError(f"{where}: {field} applies only to resp accounts")
            if dec(item, field, where) < 0:
                raise ValueError(f"{where}: {field} must not be negative")
