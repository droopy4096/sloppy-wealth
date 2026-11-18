"""Derived views of a scenario and of a run (ADR-0069 decision 3): pure functions that any
front-end can use, moved out of the Flask layer.

- ``builder_view(scenario)``: what the builder shows about the items: each item's
  effective start, the items in display order (modifiers under their host, triggers
  under their target), which items are off and why, which dates triggers set, and the
  choices for reference fields.
- ``ledger_month(scenario, result, month)``: one month of a run: its movements with
  their signed effect on cash, the net cash change, each holding's balances, the tax
  record and the events view.
"""
from decimal import Decimal

from .dates import base_month, month_label, retirement_date, retirement_dates
from .enabled import off_reasons
from .engine import upgrade
from .flows.associated import PARENTS as ASSOCIATED_PARENTS
from .flows.associated_income import PARENTS as EARNER_PARENTS
from .persons import person_items, retirement_person
from .triggers import START_FIELD, event_month, resolve

# Modifier item types (D-E1) and the field naming their host: listed under their host.
HOST_FIELD = {"renewal": "mortgage", "extraPayment": "mortgage", "lumpSum": "mortgage",
              "sale": "property", "improvement": "property", "marketAdjustment": "property",
              "contribution": "account", "withdrawal": "account", "transfer": "account",
              "adjustment": "flow", "trigger": "target", "associatedExpense": "parent",
              "associatedCost": "parent", "associatedIncome": "parent",
              "associatedOneOff": "parent"}
ADJUSTABLE_FLOWS = ("income", "expense", "contribution", "associatedExpense",
                    "associatedIncome")


def effective_start(item, scenario):
    """The month an item takes effect, 'YYYY-MM', or '' if it never starts. ``scenario``
    has its triggers resolved (dates set by triggers are in place). Mortgages without a
    date start with their property; pensions and withdrawals without a date start at the
    retirement date; accounts default to the horizon start; a trigger shows its event's;
    associated items their parent's (ADR-0067, ADR-0068)."""
    items = {i.get("id"): i for i in scenario["items"]}
    retirement = retirement_dates(scenario).get(retirement_person(item, scenario), "")
    kind = item.get("type")
    if kind == "trigger":
        event = items.get(item.get("event"))
        if event and (item.get("on") or "start") == "end":
            sales = {i.get("property"): i for i in scenario["items"] if i.get("type") == "sale"}
            try:
                at = event_month(event, "", "end", sales)
            except (KeyError, ValueError):
                return ""
            return month_label(at) if at is not None else ""
        return effective_start(event, scenario) if event else ""
    if kind in ("associatedExpense", "associatedIncome") or (
            kind in ("associatedCost", "associatedOneOff")
            and (item.get("at") or "start") == "start"):
        parent = items.get(item.get("parent"))
        return effective_start(parent, scenario) if parent else ""
    if kind in ("associatedCost", "associatedOneOff") and item.get("at") == "end":
        parent = items.get(item.get("parent"), {})
        sale = next((i for i in scenario["items"] if i.get("type") == "sale"
                     and i.get("property") == parent.get("id")), {})
        return (sale.get("saleDate") or parent.get("endDate") or "")[:7]
    date = item.get(START_FIELD.get(kind, "startDate")) or ""
    if not date and kind == "mortgage":
        date = items.get(item.get("property"), {}).get("purchaseDate") or ""
    if not date and kind in ("pension", "withdrawal"):
        date = retirement
    if not date and kind == "account":
        date = scenario["horizon"]["start"]
    return date[:7]


def starts(scenario):
    """item id -> its effective start, with the dates triggers set (ADR-0065); the
    scenario as given if a trigger is invalid."""
    try:
        resolved = resolve(upgrade(scenario))
    except ValueError:
        resolved = scenario
    return {i.get("id"): effective_start(i, resolved) for i in resolved["items"]}


def grouped_items(scenario, starts):
    """Items for display as (item, nested) pairs: hosts and standalone items in order of
    their start (undated last), each followed by its modifiers (D-E1), also in order of
    their start. A modifier whose host is missing is listed on its own. Triggers
    (ADR-0065) follow their target, wherever it is listed."""
    by_start = lambda i: starts.get(i.get("id")) or "9999-99"
    ids = {i.get("id") for i in scenario["items"]}
    hosts = {i.get("id") for i in scenario["items"] if i.get("type") not in HOST_FIELD}
    tops, modifiers, triggers = [], {}, {}
    for item in scenario["items"]:
        host = item.get(HOST_FIELD.get(item.get("type"), ""))
        if item.get("type") == "trigger" and host in ids:
            triggers.setdefault(host, []).append(item)
        elif host and host in hosts:
            modifiers.setdefault(host, []).append(item)
        else:
            tops.append(item)
    with_triggers = lambda item, nested: [(item, nested)] + [
        (t, True) for t in sorted(triggers.get(item.get("id"), []), key=by_start)]
    return [pair for top in sorted(tops, key=by_start)
            for item in [top] + sorted(modifiers.get(top.get("id"), []), key=by_start)
            for pair in with_triggers(item, item is not top)]


def off_items(scenario):
    """Off items (ADR-0064): id -> None (switched off itself) or the id it follows."""
    try:
        return {scenario["items"][n].get("id"): via
                for n, via in off_reasons(scenario["items"]).items()}
    except ValueError:
        return {}


def set_by(scenario, off):
    """'target id:field' -> the name of the (on) trigger that sets that date."""
    found = {}
    by_id = {i.get("id"): i for i in scenario["items"]}
    for t in scenario["items"]:
        target = by_id.get(t.get("target"))
        if t.get("type") != "trigger" or target is None or t.get("id") in off:
            continue
        action = t.get("action")
        fields = ([START_FIELD.get(target["type"], "startDate")]
                  if action in ("start", "startAndEnd") else []) + (
                 ["endDate"] if action in ("end", "startAndEnd") else [])
        for field in fields:
            found[f'{target["id"]}:{field}'] = t.get("name") or t["id"]
    return found


def choices(scenario):
    """Choices for reference fields, by choice list name -> {id: label}: mortgage,
    property, account (with pensions, ADR-0052), person, asset, flow (adjustable, ADR-0062),
    dated / event / target (ADR-0065), lifetime / parent (ADR-0067), earner (ADR-0068),
    any (every item's name)."""
    items = [i for i in scenario["items"] if i.get("id")]
    name = lambda i: i.get("name") or i["id"]
    label = lambda i: f'{name(i)} ({i["type"]})'
    names = {kind: {i["id"]: name(i) for i in items if i["type"] == kind}
             for kind in ("mortgage", "property", "account", "person")}
    names["asset"] = {i["id"]: name(i) for i in items if i["type"] in ("property", "vehicle")}
    names["flow"] = {i["id"]: label(i) for i in items
                     if i["type"] in ADJUSTABLE_FLOWS
                     or (i["type"] == "withdrawal" and i.get("method") in ("amount", "percent"))}
    names["dated"] = {i["id"]: label(i) for i in items if i["type"] in START_FIELD}
    names["event"] = names["target"] = names["dated"]
    names["lifetime"] = names["parent"] = {i["id"]: label(i) for i in items
                                           if i["type"] in ASSOCIATED_PARENTS}
    names["earner"] = {i["id"]: label(i) for i in items if i["type"] in EARNER_PARENTS}
    names["account"].update({i["id"]: f'{name(i)} (pension)' for i in items
                             if i["type"] == "pension"})
    names["any"] = {i["id"]: i.get("name") for i in items}
    return names


def _cards(scenario):
    from .cards import cards          # the card layout and estimates (ADR-0070)
    return cards(scenario)


def builder_view(scenario):
    """Everything the builder derives from the scenario (see the module docstring)."""
    first = starts(scenario)
    off = off_items(scenario)
    return {"starts": first, "ordered": grouped_items(scenario, first), "off": off,
            "set_by": set_by(scenario, off), "names": choices(scenario),
            "summary": summary(scenario), "cards": _cards(scenario),
            # The items as the cards show them (older forms upgraded), by id.
            "items": {i["id"]: i for i in upgrade(scenario)["items"] if i.get("id")}}


def summary(scenario):
    """Scenario facts the pages show: the base month of real values ("dollars of",
    ADR-0013), the retirement date (ADR-0059), and each person's retirement when there
    is more than one person (ADR-0061) as [[name, 'YYYY-MM-DD'], ...]."""
    people = person_items(scenario)
    dates = retirement_dates(scenario) if len(people) > 1 else {}
    try:
        dollars_of = month_label(base_month(scenario))
    except (KeyError, ValueError):
        dollars_of = ""
    return {"dollarsOf": dollars_of, "retirement": retirement_date(scenario),
            "retirements": [[p.get("name") or p["id"], dates[p["id"]]] for p in people
                            if dates.get(p["id"])]}


# ---------------------------------------------------------------- a run
def ledger_month(scenario, result, month=None):
    """One month of a detailed run (ADR-0053); the first month if ``month`` is not one.
    Movements get ``cash``: + into cash, - out of cash, None if cash is not involved."""
    months = [r["month"] for r in result["rows"]]
    month = month if month in months else months[0]
    names = {h["id"]: h["name"] for h in result["holdings"]}
    names.update({i.get("id"): i.get("name") for i in scenario["items"]})
    names.update({p["id"]: p.get("name") or p["id"] for p in person_items(scenario)})
    indices = [n for n, x in enumerate(result["ledger"]) if x["month"] == month]
    # This month's movements, copied with their effect on cash (the result is unchanged).
    ledger = dict(enumerate(result["ledger"]))
    for n in indices:
        x = ledger[n] = dict(ledger[n])
        x["cash"] = (x["amount"] if x["to"] == "cash" else
                     -x["amount"] if x["from"] == "cash" else None)
    movements = [ledger[n] for n in indices]
    net_cash = sum((x["cash"] for x in movements if x["cash"] is not None), Decimal("0.00"))
    balances = [(h, p) for h in result["holdings"] for p in h["points"] if p["month"] == month]
    return {"month": month, "months": months, "movements": movements, "indices": indices,
            "net_cash": net_cash, "balances": balances, "names": names,
            "tax": result["tax"][month],
            "events": month_events(result, month, months[0], ledger)}


def month_events(result, month, first_month, ledger=None):
    """The events view (D-E4): this month's event records, or None when the run gives no
    event log. Each record gets its log index ``n``, follow-up ``depth``, and the
    ``(index, movement)`` pairs of its ledger range (from ``ledger``, index -> movement,
    if given). Records of the INITIAL step (month None) are shown with the first month."""
    ledger = ledger if ledger is not None else dict(enumerate(result["ledger"]))
    log = result.get("events")
    if log is None:
        return None
    shown, depth = [], {}
    for n, e in enumerate(log):
        depth[n] = depth.get(e["cause"], -1) + 1 if e["cause"] is not None else 0
        if e["month"] != month and not (e["month"] is None and month == first_month):
            continue
        start, end = e["ledger"]
        shown.append(dict(e, n=n, depth=depth[n],
                          movements=[(i, ledger[i]) for i in range(start, end)]))
    return shown
