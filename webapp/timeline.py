"""Scenario timeline model (ADR-0066): every item on a time axis, git-graph style.

``layout(scenario)`` returns the picture as data (lanes, dots, links, arrows, guides),
from the scenario with its triggers resolved (ADR-0065), so the dates are the ones the
engine uses. The API serves it (``POST /api/timeline``); the web module draws it
(``web/timeline_draw.py``: ``svg`` horizontal, ``graph`` vertical).

- A **lane** is an item that lasts: a recurring flow, an asset, a mortgage, an account.
  It runs from its first to its last month (clipped to the horizon).
- A lane **branches off** its parent's lane where it starts and **merges back** where it
  ends (if before the horizon end). The parent is the host of a modifier (a mortgage's
  property, a contribution's account, ...), else the lasting item whose date starts it by
  a trigger (e.g. property tax with its house), else the household trunk.
- A **dot** is a one-off item (sale, renewal, adjustment, retirement, ...), on its
  parent's lane, else on the trunk.
- An **arrow** is a trigger not already shown by a branch or merge: from the event's
  month to the start or end it sets (e.g. Retirement -> end of a salary).
- Items switched off (ADR-0064) are drawn greyed, at the dates they would have.
"""
import copy

from state_machine import engine, jurisdictions
from state_machine.dates import month_index, retirement_dates
from state_machine.enabled import active, off_reasons
from state_machine.persons import retirement_person
from state_machine.triggers import RECURRING, START_FIELD, event_month, resolve

# Modifier and dependent items: the field naming their parent lane.
PARENT_FIELD = {"renewal": "mortgage", "extraPayment": "mortgage", "lumpSum": "mortgage",
                "sale": "property", "improvement": "property", "marketAdjustment": "property",
                "mortgage": "property", "contribution": "account", "withdrawal": "account",
                "transfer": "account", "adjustment": "flow",
                "associatedExpense": "parent", "associatedCost": "parent",      # ADR-0067
                "associatedIncome": "parent", "associatedOneOff": "parent"}     # ADR-0068
ASSOCIATED_LANES = ("associatedExpense", "associatedIncome")
LASTING = RECURRING + ("property", "vehicle", "mortgage", "account") + ASSOCIATED_LANES
# Persons, triggers and every jurisdiction's own settings items (contribution room or
# limits, ADR-0071) have no dates of their own to draw.
SKIPPED = ("person", "trigger") + tuple(jurisdictions.own_item_types())


def layout(scenario):
    raw = engine.upgrade(scenario)
    h0 = month_index(raw["horizon"]["start"], "horizon.start")
    h1 = month_index(raw["horizon"]["end"], "horizon.end")
    off = {raw["items"][n].get("id") for n in off_reasons(raw["items"])}
    # Every item at the dates it would have when on (off items are drawn greyed).
    all_on = copy.deepcopy(raw)
    for item in all_on["items"]:
        item.pop("enabled", None)
    try:
        s = resolve(all_on)
    except ValueError:                  # e.g. an off trigger clashing: only the on ones
        s = resolve(active(raw))
    items = [i for i in s["items"] if isinstance(i, dict)]
    for n, item in enumerate(items):
        item.setdefault("id", f"item{n}")
    by_id = {i["id"]: i for i in items}
    sales = {i.get("property"): i for i in items if i.get("type") == "sale"}
    retirements = _retirements(raw)
    mortgage_ends = _mortgage_ends(scenario, items)

    def month(item, field):
        value = item.get(field)
        try:
            return month_index(value, field) if value else None
        except ValueError:
            return None

    def window(item):
        kind = item["type"]
        if kind in ASSOCIATED_LANES:
            return None                     # its parent's: set below
        if kind in RECURRING:
            first = month(item, "startDate")
            if first is None and kind in ("pension", "withdrawal"):
                first = retirements.get(retirement_person(item, raw))
            last = month(item, "endDate")
            last = h1 if last is None else last
        elif kind in ("property", "vehicle"):
            first = month(item, "purchaseDate")
            sale = sales.get(item["id"])
            sold = month(sale, "saleDate") if sale else None
            last = h1 if sold is None else sold - 1
        elif kind == "mortgage":
            first = month(item, "startDate")
            if first is None:
                first = month(by_id.get(item.get("property"), {}), "purchaseDate")
            last = mortgage_ends.get(item["id"], h1)
        else:                                       # account
            first = month(item, "openedDate")
            first, last = (h0 if first is None else first), h1
        if first is None or last < max(first, h0) or first > h1:
            return None
        return first, last

    windows = {i["id"]: window(i) for i in items if i["type"] in LASTING}
    # An associated expense lives with its parent (ADR-0067), also a nested one.
    for _ in range(3):
        for i in items:
            if i["type"] in ASSOCIATED_LANES and windows.get(i.get("parent")):
                windows[i["id"]] = windows[i["parent"]]
    lanes_ids = {iid for iid, w in windows.items() if w}
    starters = {}                       # target -> (event, trigger) of its start trigger
    for t in items:
        if t["type"] == "trigger" and t.get("action") in ("start", "startAndEnd"):
            starters[t.get("target")] = t

    def parent(item):
        host = item.get(PARENT_FIELD.get(item["type"], ""))
        if host in lanes_ids:
            return host, False
        t = starters.get(item["id"])
        if t and t.get("event") in lanes_ids and (t.get("on") or "start") == "start":
            return t["event"], True
        return None, False

    parents = {i["id"]: parent(i) for i in items if i["type"] not in SKIPPED}
    children = {}
    for iid, (p, _) in parents.items():
        if iid in lanes_ids:
            children.setdefault(p, []).append(iid)

    # Lanes in tree order: trunk, then each item followed by its children, by start.
    order = []

    def visit(pid, depth):
        for iid in sorted(children.get(pid, []), key=lambda i: (windows[i][0], i)):
            order.append((iid, depth))
            visit(iid, depth + 1)
    visit(None, 1)
    row = {iid: n + 1 for n, (iid, _) in enumerate(order)}
    row[None] = 0
    # A modifier lane stops with its host (e.g. prepayments with the mortgage).
    for iid, depth in order:
        p, by_trigger = parents[iid]
        if p and not by_trigger and by_id[iid]["type"] in PARENT_FIELD:
            first, last = windows[iid]
            windows[iid] = (first, min(last, windows[p][1]))
    lanes = [{"id": None, "name": "Household (cash)", "type": "trunk", "depth": 0,
              "first": h0, "last": h1, "off": False, "parent": None, "row": 0}]
    for iid, depth in order:
        item = by_id[iid]
        first, last = windows[iid]
        p, by_trigger = parents[iid]
        lanes.append({"id": iid, "name": item.get("name") or iid, "type": item["type"],
                      "depth": depth, "first": first, "last": last, "off": iid in off,
                      "parent": p, "row": row[iid], "by_trigger": by_trigger})

    links = []
    for lane in lanes[1:]:
        if lane["first"] > h0:
            links.append({"kind": "branch", "from": lane["parent"], "to": lane["id"],
                          "month": lane["first"], "trigger": lane["by_trigger"]})
        if lane["last"] < h1:
            merge_trigger = any(
                t["type"] == "trigger" and t.get("target") == lane["id"]
                and t.get("event") == lane["parent"] and t.get("action") == "end"
                and t.get("on") == "end" for t in items)
            links.append({"kind": "merge", "from": lane["id"], "to": lane["parent"],
                          "month": lane["last"] + 1, "trigger": merge_trigger})

    dots = []
    for item in items:
        kind = item["type"]
        if kind in SKIPPED or kind in LASTING:
            continue
        at = month(item, START_FIELD.get(kind, ""))
        if kind in ("associatedCost", "associatedOneOff"):
            at = _cost_month(item, windows, by_id, h1, month)
        if at is None or not h0 <= at <= h1:
            continue
        p = parents[item["id"]][0]
        dots.append({"id": item["id"], "name": item.get("name") or item["id"], "type": kind,
                     "month": at, "row": row.get(p, 0), "off": item["id"] in off})
    dot_at = {d["id"]: d for d in dots}

    def point(iid, end):
        """(month, row) of an item's start, or its end (month after its last)."""
        if iid in dot_at:
            return dot_at[iid]["month"], dot_at[iid]["row"]
        lane = next((ln for ln in lanes if ln["id"] == iid), None)
        if lane is None:
            return None
        return (lane["last"] + 1 if end else lane["first"]), lane["row"]

    arrows = []
    for t in items:
        if t["type"] != "trigger" or t.get("event") not in by_id or t.get("target") not in by_id:
            continue
        target = by_id[t["target"]]
        action, on = t.get("action"), t.get("on") or "start"
        lane = next((ln for ln in lanes if ln["id"] == t["target"]), None)
        if lane and lane["parent"] == t["event"] and (
                (action == "start" and on == "start" and lane["by_trigger"])
                or (action == "end" and on == "end")):
            continue                            # shown by the branch or merge
        try:
            at = event_month(by_id[t["event"]], "", on, sales)
        except (KeyError, ValueError):
            continue
        source = point(t["event"], on == "end")
        dest = point(target["id"], action == "end")
        if at is None or source is None or dest is None or not h0 <= at <= h1 + 1:
            continue
        arrows.append({"id": t["id"], "name": t.get("name") or t["id"], "month": at,
                       "from_row": source[1], "to_month": dest[0], "to_row": dest[1],
                       "off": t["id"] in off})

    guides = [{"name": i.get("name") or "Retirement", "month": month(i, "retirementDate")}
              for i in items if i["type"] == "retirement" and month(i, "retirementDate")
              and h0 <= month(i, "retirementDate") <= h1 and i["id"] not in off]
    # "<target>:start|end" -> the name of the trigger that sets it (graph labels).
    set_by = {}
    for t in items:
        if t["type"] == "trigger" and t.get("target") in by_id:
            for end in {"start": (False,), "end": (True,), "startAndEnd": (False, True)}.get(
                    t.get("action"), ()):
                set_by[f'{t["target"]}:{"end" if end else "start"}'] = t.get("name") or t["id"]
    return {"start": h0, "end": h1, "lanes": lanes, "links": links, "dots": dots,
            "arrows": arrows, "guides": guides, "set_by": set_by}


def _cost_month(item, windows, by_id, h1, month):
    """The month of an associated cost (ADR-0067) or one-off income (ADR-0068): its
    parent's start, end, or its date."""
    at = item.get("at") or "start"
    if at == "date":
        return month(item, START_FIELD[item["type"]])
    w = windows.get(item.get("parent"))
    if w is None:
        return None
    if at == "start":
        return w[0]
    parent = by_id.get(item.get("parent"), {})
    if w[1] >= h1:
        return None                         # does not end within the horizon
    # An asset or mortgage ends in its sale month; a recurring item in its last month.
    return w[1] + 1 if parent.get("type") in ("property", "vehicle", "mortgage") else w[1]


def _retirements(scenario):
    try:
        return {pid: month_index(d, "retirementDate")
                for pid, d in retirement_dates(scenario).items() if d}
    except ValueError:
        return {}


def _mortgage_ends(scenario, items):
    """mortgage id -> its last month with a movement (it or its renewals, prepayments)."""
    try:
        ledger = engine.run_detailed(copy.deepcopy(scenario))["ledger"]
    except ValueError:
        return {}
    owner = {i["id"]: i.get("mortgage") for i in items
             if i["type"] in ("renewal", "extraPayment", "lumpSum")}
    owner.update({i["id"]: i["id"] for i in items if i["type"] == "mortgage"})
    ends = {}
    for line in ledger:
        mid = owner.get(line["source"])
        if mid:
            m = month_index(line["month"] + "-01", "")
            ends[mid] = max(ends.get(mid, m), m)
    return ends


# ---------------------------------------------------------------- drawing
