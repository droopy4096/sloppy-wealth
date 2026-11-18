"""The builder's cards (ADR-0070): the scenario grouped by person and category, each card
with its linked items and an estimated monthly figure. A view: nothing here changes the
scenario, and nothing runs the engine (decision 6: the figures are cheap hints).

    cards(scenario) -> {
      "base": "YYYY-MM",                        # the month the figures are for
      "estimates": {item id: estimate},         # every item's own figure (both views)
      "sections": [{
        "key": person id | "household", "title": str, "kind": "person" | "household",
        "head": card,                           # the person card, or the Scenario card
        "categories": [{"key", "title", "types": [item types added here],
                        "cards": [card, ...], "total": Decimal | None}],
        "total": Decimal | None}]}
    card = {"id", "name", "type", "off", "estimate", "fact",
            "rows": [{"id", "name", "type", "depth", "off", "estimate"}, ...],
            "total": Decimal | None,            # the item and its rows, per month
            "via": str | None}                  # shown again here (also under its host)
    estimate = {"monthly": Decimal | None,      # signed: + into cash, - out of cash
                "oneOff": Decimal | None, "at": "YYYY-MM" | None,
                "note": str | None,             # e.g. "from 2030-01", "until 2029-12"
                "tax": Decimal | None,          # the rate taken off a taxable inflow
                "later": {"monthly", "at", "tax"} | None}   # not started yet: its figure
                                                # at its start, in base-month dollars

Sections (decision 1): one per person (Income, Accounts, Pensions; an item without an
owner belongs to the first person; a scenario without persons has one, titled "You"),
then Household (Properties, Vehicles, Expenses, and Other for items whose host is
missing). A withdrawal from an account is a row of its account and is shown again as a
card under its person's Pensions, as retirement income ("via" its account; not counted
twice in the totals). A card's rows are everything linked to it, depth first: modifiers, associated
items, adjustments, a property's mortgages and theirs, and the triggers that set its
dates or that it fires. A person card holds the person's retirement and contribution
room; the Scenario card holds the cash balances.

The estimate (decision 6) is for the base month (``dollarsOf``, default the horizon
start): each amount per month, brought to that month with its own indexing (the latest
adjustment at or before it replaces the amount); a percentage times its stated basis; a
mortgage payment from its terms and renewals (a simple schedule without prepayments). An
item not running in the base month gets a note instead of a figure. Taxable inflows are
shown after tax (ADR-0070 amendment): the person's rate in the base month (retirement
rate once retired); a withdrawal from an account type whose withdrawals are taxed (an
RRSP, a traditional 401(k), ADR-0071) at its account's withdrawalTaxRate if set.
"""
from decimal import Decimal

from .arith import ONE, PER, D, indexing_rate, money, monthly_rate
from .dates import base_month, month_index, month_label, property_sales
from .enabled import active
from . import jurisdictions
from .engine import upgrade
from .persons import IMPLICIT, first_person, owner_of, person_items
from .triggers import resolve

LINK = {"renewal": "mortgage", "extraPayment": "mortgage", "lumpSum": "mortgage",
        "sale": "property", "improvement": "property", "marketAdjustment": "property",
        "mortgage": "property", "contribution": "account", "withdrawal": "account",
        "transfer": "account", "adjustment": "flow", "associatedExpense": "parent",
        "associatedCost": "parent", "associatedIncome": "parent",
        "associatedOneOff": "parent"}
PERSON_CATEGORIES = [("income", "Income", ("income",)), ("accounts", "Accounts", ("account",)),
                     ("pensions", "Pensions", ("pension",))]
HOUSEHOLD_CATEGORIES = [("properties", "Properties", ("property", "mortgage")),
                        ("vehicles", "Vehicles", ("vehicle",)),
                        ("expenses", "Expenses", ("expense",)), ("other", "Other", ())]
CATEGORY_OF = {"income": "income", "account": "accounts", "pension": "pensions",
               "property": "properties", "mortgage": "properties", "vehicle": "vehicles",
               "expense": "expenses"}
INFLOWS = ("income", "pension", "associatedIncome", "withdrawal", "associatedOneOff", "sale")


def _month(text):
    try:
        return month_index(text, "") if text else None
    except (ValueError, TypeError):
        return None


def _dec(value, default=None):
    try:
        return D(value) if value not in (None, "") else default
    except Exception:
        return default


class Estimator:
    """Estimates for one scenario (triggers resolved) at its base month."""

    def __init__(self, scenario):
        self.s = scenario
        self.by_id = {i.get("id"): i for i in scenario["items"] if i.get("id")}
        self.base = base_month(scenario)
        self.dollars_of = self.base        # the scenario's base date (pensions' dollars)
        self.inflation = _dec(scenario.get("annualInflation"), Decimal(0))
        self.sales = property_sales(active(scenario)["items"])
        self.rules = jurisdictions.of_or_default(scenario)        # ADR-0071      # off sales left out
        self.retirements = {}
        for r in scenario["items"]:
            if r.get("type") == "retirement" and _month(r.get("retirementDate")) is not None:
                self.retirements[owner_of(r, scenario)] = _month(r["retirementDate"])
        self.persons = {p.get("id"): p for p in person_items(scenario)}
        self.adjustments = {}
        for a in scenario["items"]:
            if a.get("type") == "adjustment" and a.get("enabled", True) is not False:
                self.adjustments.setdefault(a.get("flow"), []).append(a)

    # ------------------------------------------------------------ windows
    def window(self, item, seen=()):
        """(first, last) month of an item's life, None where unknown or open."""
        kind = item.get("type")
        if kind in ("associatedExpense", "associatedIncome"):
            parent = self.by_id.get(item.get("parent"))
            if parent is None or parent.get("id") in seen:
                return None, None
            return self.window(parent, seen + (item.get("id"),))
        if kind in ("property", "vehicle"):
            sale = self.sales.get(item.get("id"))
            sold = _month(sale.get("saleDate")) if sale else None
            return _month(item.get("purchaseDate")), (sold - 1 if sold else None)
        if kind == "mortgage":
            start = _month(item.get("startDate")) or _month(
                self.by_id.get(item.get("property"), {}).get("purchaseDate"))
            return start, None
        if kind == "account":
            return _month(item.get("openedDate")) or _month(self.s["horizon"]["start"]), None
        first = _month(item.get("startDate"))
        if first is None and kind in ("pension", "withdrawal"):
            first = self.retirements.get(owner_of(item, self.s))
        return first, _month(item.get("endDate"))

    def status(self, item):
        """A note when the item is not running in the base month, else None."""
        first, last = self.window(item)
        if first is None:
            return "no start date yet"
        if self.base < first:
            return f"from {month_label(first)}"
        if last is not None and self.base > last:
            return f"until {month_label(last)}"
        return None

    # ------------------------------------------------------------ amounts
    def rate(self, item):
        try:
            return indexing_rate(item, self.inflation)
        except Exception:
            return Decimal(0)

    def flow_monthly(self, item, amount_field="amount"):
        """A fixed flow's monthly amount at the base month (unsigned)."""
        amount, per = _dec(item.get(amount_field)), item.get("per") or "month"
        if amount is None or per not in PER:
            return None
        first, _ = self.window(item)
        anchor = first if first is not None else self.base
        if item.get("amountIn") == "base" and self.inflation:
            amount = amount * (ONE + self.inflation) ** (Decimal(anchor - self.base) / 12)
        for adj in sorted(self.adjustments.get(item.get("id"), []),
                          key=lambda a: a.get("adjustmentDate") or ""):
            at = _month(adj.get("adjustmentDate"))
            new = _dec(adj.get("amount"))
            if at is not None and at <= self.base and new is not None:
                amount, per, anchor = new, adj.get("per") or per, at
        if item.get("type") == "pension":           # stated in base-date dollars
            years = (self.base - self.dollars_of) // 12
            return amount * (ONE + self.rate(item)) ** years / PER[per]
        years = max(self.base - anchor, 0) // 12
        return amount * (ONE + self.rate(item)) ** years / PER[per]

    def annual_rate(self, item):
        rate = _dec(item.get("annualRate"))
        for adj in sorted(self.adjustments.get(item.get("id"), []),
                          key=lambda a: a.get("adjustmentDate") or ""):
            at = _month(adj.get("adjustmentDate"))
            if at is not None and at <= self.base and _dec(adj.get("annualRate")) is not None:
                rate = _dec(adj["annualRate"])
        return rate

    def basis(self, item, parent):
        """The stated value a percentage applies to (yearly for an income's amount)."""
        if parent is None:
            return None
        basis = item.get("basis") or "amount"
        if basis == "price":
            return _dec(parent.get("price"))
        if basis == "value":
            return _dec(parent.get("marketValue")) or _dec(parent.get("price"))
        if basis == "principal":
            return _dec(parent.get("principal"))
        if basis == "balance":
            return _dec(parent.get("openingBalance")) or _dec(parent.get("principal"))
        monthly = self.flow_monthly(parent)
        return monthly * 12 if monthly is not None else None

    def mortgage_payment(self, item):
        """The scheduled payment at the base month: a plain schedule from the principal,
        with each renewal's rate and amortization (no prepayments); None if paid off."""
        first, _ = self.window(item)
        principal, rate = _dec(item.get("principal")), _dec(item.get("annualRate"))
        years = _dec(item.get("amortizationYears"))
        if None in (first, principal, rate, years):
            return None, None
        renewals = sorted((r for r in self.s["items"] if r.get("type") == "renewal"
                           and r.get("mortgage") == item.get("id")
                           and r.get("enabled", True) is not False
                           and _month(r.get("startDate")) is not None),
                          key=lambda r: _month(r["startDate"]))
        left = int(years * 12)
        balance = principal

        def payment(rate_, months):
            r = monthly_rate(rate_)
            if months <= 0:
                return balance
            return balance / months if r == 0 else balance * r / (ONE - (ONE + r) ** -months)
        pay = payment(rate, left)
        month = first + 1
        while month <= self.base:
            for r in renewals:
                if _month(r["startDate"]) == month:
                    rate = _dec(r.get("annualRate"), rate)
                    if r.get("amortizationYears"):
                        left = int(_dec(r["amortizationYears"]) * 12)
                    if not r.get("keepPayment"):
                        pay = payment(rate, left)
            interest = balance * monthly_rate(rate)
            balance = balance + interest - pay
            left -= 1
            if balance <= 0:
                return None, month
            month += 1
        return pay, None

    # ------------------------------------------------------------ tax
    def tax_rate(self, item):
        """The rate taken off a taxable inflow at the base month, or None if untaxed."""
        kind = item.get("type")
        source = item
        if kind in ("associatedIncome", "associatedOneOff"):
            source = self.by_id.get(item.get("parent")) or {}
        override = None
        if kind == "withdrawal":
            account = self.by_id.get(item.get("account")) or {}
            kind_of = self.rules.account_types.get(account.get("accountType"))
            if kind_of is None or not kind_of.treatment.withdrawal_taxed:
                return None
            override = _dec(account.get("withdrawalTaxRate"))
        elif source.get("type") == "pension":
            if not source.get("taxable", True):
                return None
        elif source.get("type") == "income":
            if not source.get("taxable"):
                return None
        else:
            return None
        if override is not None:
            return override
        person = owner_of(source if kind != "withdrawal" else item, self.s)
        own = self.persons.get(person, {})
        working = _dec(own.get("effectiveTaxRate")) or _dec(self.s.get("effectiveTaxRate"),
                                                             Decimal(0))
        retired_at = self.retirements.get(person)
        if retired_at is not None and self.base >= retired_at:
            return (_dec(own.get("retirementTaxRate")) or _dec(self.s.get("retirementTaxRate"))
                    or working)
        return working

    # ------------------------------------------------------------ one item
    def estimate(self, item):
        out = self._after_tax(item, self._estimate(item))
        out["later"] = self.later(item, out)
        return out

    def _after_tax(self, item, out):
        rate = self.tax_rate(item) if (out["monthly"] or out["oneOff"]) else None
        if rate:
            for key in ("monthly", "oneOff"):
                if out[key] is not None and out[key] > 0:
                    out[key] = money(out[key] * (ONE - rate))
        out["tax"] = rate
        return out

    def later(self, item, out):
        """For a flow that starts after the base month (e.g. a pension at retirement): its
        monthly figure in its first month, after the tax of then, brought back to
        base-month dollars with inflation; None otherwise. Not part of any total."""
        first, _ = self.window(item)
        if out["monthly"] is not None or first is None or first <= self.base:
            return None
        base = self.base
        try:
            self.base = first
            gross = self._estimate(item)["monthly"]
            then = self._after_tax(item, self._estimate(item))
        finally:
            self.base = base
        if then["monthly"] is None:
            return None
        step = (ONE + self.inflation) ** ((first - base) // 12) if self.inflation else ONE
        # Back to base-month dollars in the same whole-year steps that indexing uses, so an
        # inflation-indexed amount stated in today's dollars shows as stated.
        return {"monthly": money(then["monthly"] / step), "at": month_label(first),
                "tax": then["tax"], "gross": money(gross / step) if then["tax"] else None}

    def _estimate(self, item):
        kind = item.get("type")
        out = {"monthly": None, "oneOff": None, "at": None, "note": None}
        sign = ONE if kind in INFLOWS else -ONE
        one_offs = {"sale": ("saleDate", "salePrice"), "improvement": ("improvementDate", "cost"),
                    "lumpSum": ("paymentDate", "amount"), "transfer": ("transferDate", "amount")}
        if kind in one_offs:
            date, field = one_offs[kind]
            out["at"] = (item.get(date) or "")[:7] or None
            value = _dec(item.get(field))
            out["oneOff"] = money(sign * value) if value is not None else None
            if out["oneOff"] is None:
                out["note"] = {"sale": "at its value", "lumpSum": "pays it off"}.get(kind)
            return out
        if kind in ("associatedCost", "associatedOneOff"):
            parent = self.by_id.get(item.get("parent"))
            at = item.get("at") or "start"
            out["note"] = {"start": "at its start", "end": "at its end"}.get(at)
            if at == "date":
                out["at"] = (item.get("costDate") or item.get("paymentDate") or "")[:7] or None
            if item.get("amount"):
                out["oneOff"] = money(sign * D(item["amount"]))
            elif item.get("rate"):
                basis = self.basis(item, parent)
                if basis is not None:
                    out["oneOff"] = money(sign * basis * D(item["rate"]))
            return out
        if kind == "cashBalance":
            out["at"] = (item.get("balanceDate") or "")[:7] or None
            out["note"] = f"cash set to {item.get('balance')}"
            return out
        if kind not in ("income", "expense", "pension", "contribution", "withdrawal",
                        "extraPayment", "associatedExpense", "associatedIncome", "mortgage"):
            return out                   # assets, accounts, triggers, settings: no flow
        note = self.status(item)
        if note:
            out["note"] = note
            return out
        if kind == "mortgage":
            pay, paid_off = self.mortgage_payment(item)
            if paid_off is not None:
                out["note"] = f"paid off {month_label(paid_off)}"
            elif pay is not None:
                out["monthly"] = money(-pay)
            return out
        if kind == "extraPayment":
            monthly = _dec(item.get("monthlyAmount"))
        elif kind == "withdrawal" and item.get("method") == "percent":
            balance = _dec(self.by_id.get(item.get("account"), {}).get("openingBalance"))
            rate = self.annual_rate(item)
            monthly = balance * rate / 12 if None not in (balance, rate) else None
        elif kind == "withdrawal" and item.get("method") == "annuity":
            out["note"] = "worked out in the run"
            return out
        elif kind in ("associatedExpense", "associatedIncome") and item.get("annualRate"):
            basis = self.basis(item, self.by_id.get(item.get("parent")))
            rate = self.annual_rate(item)
            monthly = basis * rate / 12 if None not in (basis, rate) else None
        else:
            monthly = self.flow_monthly(item)
        if monthly is not None:
            out["monthly"] = money(sign * monthly)
        return out



def _amount(value):
    number = _dec(value)
    return f"{number:,.2f}" if number is not None else "-"


def _percent(value):
    number = _dec(value, Decimal(0))
    return f"{(number * 100).normalize():f}%"


def _fact(item, est, scenario):
    kind = item.get("type")
    if kind in ("property", "vehicle"):
        value = item.get("marketValue") or item.get("price")
        return f"value {_amount(value)} · bought {(item.get('purchaseDate') or '')[:7]}"
    if kind == "account":
        kind_of = jurisdictions.of_or_default(scenario).account_types.get(item.get("accountType"))
        kind = (kind_of.short or kind_of.code) if kind_of else item.get("accountType")
        return (f"{kind} · balance {_amount(item.get('openingBalance') or 0)} · "
                f"return {_percent(item.get('annualReturn'))}")
    if kind == "mortgage":
        return (f"principal {_amount(item.get('principal'))} at "
                f"{_percent(item.get('annualRate'))} · {item.get('amortizationYears')} years")
    first, last = est.window(item)
    if first is not None:
        return (f"{month_label(first)} to "
                f"{month_label(last) if last is not None else 'the end'}")
    return ""


def _total(estimates):
    values = [e["monthly"] for e in estimates if e and e.get("monthly") is not None]
    return sum(values, Decimal(0)) if values else None


def cards(scenario):
    """The card layout of a scenario (see the module docstring)."""
    raw = upgrade(scenario)
    try:
        resolved = resolve(raw)
    except ValueError:
        resolved = raw
    est = Estimator(resolved)
    items = [i for i in raw["items"] if i.get("id")]
    resolved_by_id = {i.get("id"): i for i in resolved["items"] if i.get("id")}
    by_id = {i["id"]: i for i in items}
    from .views import effective_start, off_items
    off = off_items(raw)
    # Cards and rows in order of their effective start (dates set by triggers included);
    # undated last, then file order.
    first = {i.get("id"): effective_start(i, resolved) for i in resolved["items"]}
    order = {i["id"]: n for n, i in enumerate(items)}
    by_start = lambda i: (first.get(i["id"]) or "9999-99", order[i["id"]])

    children = {}
    for item in items:
        if item["type"] == "trigger":
            for end in ("target", "event"):
                if item.get(end) in by_id and item.get(end) != item["id"]:
                    children.setdefault(item[end], []).append(item)
            continue
        host = item.get(LINK.get(item["type"], ""))
        if host in by_id and host != item["id"]:
            children.setdefault(host, []).append(item)

    estimates = {}

    def estimate(item):
        if item["id"] not in estimates:
            estimates[item["id"]] = est.estimate(resolved_by_id.get(item["id"], item))
        return estimates[item["id"]]

    def rows_of(iid, depth=1, seen=None):
        seen = seen if seen is not None else {iid}
        out = []
        for child in sorted(children.get(iid, []), key=by_start):
            if child["id"] in seen:
                continue
            seen.add(child["id"])
            out.append({"id": child["id"], "name": child.get("name") or child["id"],
                        "type": child["type"], "depth": depth, "off": child["id"] in off,
                        "estimate": estimate(child)})
            if child["type"] != "trigger":
                out += rows_of(child["id"], depth + 1, seen)
        return out

    def card(item):
        rows = rows_of(item["id"])
        own = estimate(item)
        return {"id": item["id"], "name": item.get("name") or item["id"], "type": item["type"],
                "via": None, "off": item["id"] in off, "estimate": own,
                "fact": _fact(resolved_by_id.get(item["id"], item), est, resolved),
                "rows": rows,
                "total": _total([own] + [r["estimate"] for r in rows
                                         if r["type"] != "trigger" and not r["off"]])}

    persons = person_items(raw)
    keys = [p.get("id") for p in persons] or [IMPLICIT]
    titles = {p.get("id"): p.get("name") or p.get("id") for p in persons} or {IMPLICIT: "You"}
    placed = {k: {c: [] for c, _, _ in PERSON_CATEGORIES} for k in keys}
    household = {c: [] for c, _, _ in HOUSEHOLD_CATEGORIES}
    person_rows = {k: [] for k in keys}
    scenario_rows = []
    linked = {c["id"] for rows in children.values() for c in rows}
    for item in items:
        kind = item["type"]
        if kind in ("income", "account", "pension"):
            owner = owner_of(item, raw)
            placed.get(owner, placed[keys[0]])[CATEGORY_OF[kind]].append(item)
        elif kind == "retirement" or kind in jurisdictions.own_item_types():
            person_rows.setdefault(owner_of(item, raw), person_rows[keys[0]]).append(item)
        elif kind == "cashBalance":
            scenario_rows.append(item)
        elif kind == "person":
            continue
        elif kind in CATEGORY_OF and item["id"] not in linked:
            household[CATEGORY_OF[kind]].append(item)
        elif item["id"] not in linked:
            household["other"].append(item)

    def head_card(card_id, name, kind, fact, row_items):
        rows = []
        for r in sorted(row_items, key=by_start):
            rows.append({"id": r["id"], "name": r.get("name") or r["id"], "type": r["type"],
                         "depth": 1, "off": r["id"] in off, "estimate": estimate(r)})
            rows += rows_of(r["id"], 2)
        return {"id": card_id, "name": name, "type": kind, "off": card_id in off,
                "estimate": {"monthly": None, "oneOff": None, "at": None, "note": None, "tax": None},
                "fact": fact, "rows": rows, "total": None}

    def category(key, title, types, members, also=()):
        made = [card(i) for i in sorted(members, key=by_start)]
        for item in sorted(also, key=by_start):    # shown again here; counted under its host
            made.append(dict(card(item), via=by_id.get(item.get("account"), {}).get("name")))
        return {"key": key, "title": title, "types": list(types), "cards": made,
                "total": _total([{"monthly": c["total"]} for c in made
                                 if not c["off"] and not c.get("via")])}

    sections = []
    for k in keys:
        person = by_id.get(k, {})
        retire = est.retirements.get(k)
        tax = person.get("effectiveTaxRate") or raw.get("effectiveTaxRate") or "0"
        fact = (f"retires {month_label(retire)}" if retire is not None else "no retirement date"
                ) + f" · tax {_percent(tax)}"
        draws = [i for i in items if i["type"] == "withdrawal" and i.get("account") in by_id
                 and owner_of(i, raw) == k]
        cats = [category(key, title, types, placed[k][key],
                         draws if key == "pensions" else ())
                for key, title, types in PERSON_CATEGORIES]
        sections.append({"key": k, "title": titles[k], "kind": "person",
                         "head": head_card(k, titles[k], "person", fact, person_rows.get(k, [])),
                         "categories": cats,
                         "total": _total([{"monthly": c["total"]} for c in cats])})
    horizon = raw.get("horizon", {})
    fact = (f"{(horizon.get('start') or '')[:7]} to {(horizon.get('end') or '')[:7]} · "
            f"inflation {_percent(raw.get('annualInflation'))} · opening cash "
            f"{_amount(raw.get('openingCash') or 0)}")
    cats = [category(key, title, types, household[key])
            for key, title, types in HOUSEHOLD_CATEGORIES if key != "other" or household[key]]
    sections.append({"key": "household", "title": "Household", "kind": "household",
                     "head": head_card("scenario", raw.get("name") or "Scenario", "scenario",
                                       fact, scenario_rows),
                     "categories": cats,
                     "total": _total([{"monthly": c["total"]} for c in cats])})
    for item in items:
        estimate(item)
    return {"base": month_label(est.base), "sections": sections, "estimates": estimates}
