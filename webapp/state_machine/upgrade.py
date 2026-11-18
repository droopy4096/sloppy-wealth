"""Older input forms converted to the current ones, in one place.

``upgrade(scenario)`` is called at the start of ``validation.validate`` and
``compiler.compile_scenario`` (and by the app on load), so the rest of the engine only
knows the current forms. It returns the scenario itself when nothing needs converting,
else a converted copy (the caller's dict is never changed). Converting twice is a no-op.

Converted forms:
- ``monthlyAmount`` on a flow (income, expense, contribution, withdrawal, pension) without
  ``amount``: ``amount`` per month (SPEC: older files).
- withdrawal method ``even``: ``annuity`` (the unindexed annuity, ADR-0039 amendment
  2026-11-11). ``even`` with indexing was never valid: the same error is raised here.
- the scenario's ``retirementDate`` setting: a retirement event (ADR-0059), owned by the
  first person. Older files may date it before the horizon start (every month counts as
  retired) or after its end (never happens), which an event may not: such an event gets
  ``"outsideHorizon": true``. A bad date, or the setting next to an event, raises the
  error validation gave before.
- a property's own ``saleDate`` (with ``salePrice``, ``sellingCostRate``, ``salePenalty``): a sale
  item right after the property, without an id, so its movements keep the property id as
  their source.
- ``startsAtRetirement``, ``endsAtRetirement`` and ``atRetirement`` (ADR-0059): a trigger
  item (ADR-0065) on the retirement event of the item's person (``retirementOf``, its
  owner, else the first person), appended after the items. Without such an event
  starts/ends at retirement are dropped (they never applied); at retirement is an error.
  The event and the target get an id if they have none (the target's ``item{n}``, the
  same as its compile-time id).
- an expense's ``attachedTo`` (ADR-0040 amendments): without dates of its own, the
  expense becomes an associated expense of the item it names (ADR-0067); with a startDate
  or endDate, triggers (ADR-0065 amendment): start at the purchase (property, vehicle) or
  start (income) of the item it names, end on that item's end (``on: end``). The start
  trigger is left out when the expense's own startDate is not earlier than the event's.
  An unknown ``attachedTo``, or one on another item type, raises the error validation
  gave before; a blank one is dropped.
- a vehicle's ``annualMaintenance`` (+ ``maintenanceIncrease``): an associated expense
  of the vehicle, per year, custom-indexed by the increase (ADR-0067); none when 0.
- a sale's ``sellingCostRate``: an associated cost at the end of the asset it sells,
  ``rate`` x its value (the sale price) (ADR-0067); none when 0.
  Both are appended after the items, with ids (the parent gets its compile-time id).
- no ``jurisdiction``: ``"CA"``, the only jurisdiction before ADR-0071 (inserted after
  ``name``, or first).
"""
import copy

from .dates import month_index
from .persons import owner_of, retirement_person

FLOW_TYPES = ("income", "expense", "contribution", "withdrawal", "pension")
FLAGS = ("startsAtRetirement", "endsAtRetirement", "atRetirement")
# The date field an at-retirement item would otherwise give, and the verb in messages.
AT_FIELD = {"sale": ("saleDate", "sells"), "lumpSum": ("paymentDate", "paid"),
            "transfer": ("transferDate", "transfers")}


def upgrade(scenario):
    if not isinstance(scenario, dict) or not isinstance(scenario.get("items"), list):
        return scenario                 # malformed: validation reports it
    if not _needs_upgrade(scenario):
        return scenario
    s = copy.deepcopy(scenario)
    if not s.get("jurisdiction"):
        s = _with_jurisdiction(s)
    if "retirementDate" in s:
        _retirement_setting(s)
    _property_sales(s)
    for n, item in enumerate(s["items"]):
        if _old_monthly(item):
            item["amount"] = item.pop("monthlyAmount")
            item["per"] = "month"
        if _old_even(item):
            if (item.get("indexing") or "none") != "none":
                where = f"item {item.get('name') or item.get('id') or n}"
                raise ValueError(f"{where}: indexing applies only to methods 'amount' and "
                                 "'annuity'; set indexing to none for method 'even'")
            item["method"] = "annuity"
    _retirement_flags(s)
    _attached(s)
    _built_in_costs(s)
    return s


def _built_in_costs(s):
    """Vehicle maintenance and sale selling costs -> associated items (ADR-0067)."""
    added = []
    for n, item in enumerate(s["items"]):
        if not isinstance(item, dict):
            continue
        if item.get("type") == "vehicle" and "annualMaintenance" in item:
            amount = item.pop("annualMaintenance")
            increase = item.pop("maintenanceIncrease", None)
            if _zero(amount):
                continue
            item.setdefault("id", f"item{n}")
            cost = {"type": "associatedExpense",
                    "id": _free_id(s, f"{item['id']}-maintenance"),
                    "name": f"{item.get('name') or item['id']} maintenance",
                    "parent": item["id"], "amount": amount, "per": "year",
                    "indexing": "none" if _zero(increase) else "custom"}
            if not _zero(increase):
                cost["indexRate"] = increase
            added.append(cost)
            s["items"].append(cost)          # reserves its id for _free_id
        elif item.get("type") == "sale" and "sellingCostRate" in item:
            rate = item.pop("sellingCostRate")
            if _zero(rate) or not item.get("property"):
                continue
            asset = item["property"]
            cost = {"type": "associatedCost", "id": _free_id(s, f"{asset}-selling-cost"),
                    "name": f"{item.get('name') or asset} selling cost", "parent": asset,
                    "at": "end", "rate": rate, "basis": "value"}
            s["items"].append(cost)
    return added


def _zero(value):
    """Blank or a number equal to 0 (a bad number is left for validation)."""
    if value in (None, "", 0):
        return True
    try:
        return float(value) == 0
    except (TypeError, ValueError):
        return False


def _attached(s):
    """An expense's attachedTo -> triggers (ADR-0065 amendment)."""
    by_id = {i.get("id"): i for i in s["items"] if isinstance(i, dict) and i.get("id")}
    triggers = []
    for n, item in enumerate(s["items"]):
        if not _old_attached(item):
            continue
        where = f"item {item.get('name') or item.get('id') or n}"
        host_id = item.pop("attachedTo")
        if not host_id:
            continue
        if item.get("type") != "expense":
            raise ValueError(f"{where}: attachedTo applies only to expenses")
        host = by_id.get(host_id)
        if not host or host.get("type") not in ("property", "vehicle", "income"):
            raise ValueError(f"{where}: attachedTo refers to unknown property, vehicle or "
                             f"income {host_id!r}")
        if not item.get("startDate") and not item.get("endDate"):
            item["type"] = "associatedExpense"          # lives with it (ADR-0067)
            item["parent"] = host_id
            item.pop("startDate", None)
            item.pop("endDate", None)
            continue
        item.setdefault("id", f"item{n}")
        host_name = host.get("name") or host_id
        start_field = "startDate" if host["type"] == "income" else "purchaseDate"
        if not _not_earlier(item.get("startDate"), host.get(start_field)):
            triggers.append({"type": "trigger", "id": f"{item['id']}-start-with-{host_id}",
                             "name": f"With {host_name}", "event": host_id,
                             "target": item["id"], "action": "start"})
        triggers.append({"type": "trigger", "id": f"{item['id']}-end-with-{host_id}",
                         "name": f"Ends with {host_name}", "event": host_id,
                         "target": item["id"], "action": "end", "on": "end"})
    s["items"].extend(triggers)


def _not_earlier(own, other):
    """True if the plain date ``own`` is not before ``other`` (both given)."""
    try:
        return bool(own and other) and month_index(own, "") >= month_index(other, "")
    except (TypeError, ValueError):
        return False


def _retirement_flags(s):
    """At-retirement fields -> triggers (ADR-0065)."""
    triggers = []
    for n, item in enumerate(s["items"]):
        if not _old_flags(item):
            continue
        where = f"item {item.get('name') or item.get('id') or n}"
        flags = {f: item.pop(f) for f in FLAGS if f in item}
        for flag, value in flags.items():
            if value not in (True, False):
                raise ValueError(f"{where}: {flag} must be true or false")
        if flags.get("startsAtRetirement") and flags.get("endsAtRetirement"):
            raise ValueError(f"{where}: cannot both start and end at retirement")
        event = _retirement_event(item, s)
        if flags.get("atRetirement"):
            field, did = AT_FIELD.get(item.get("type"), ("startDate", "starts"))
            if item.get(field):
                raise ValueError(f"{where}: give a {field} or atRetirement, not both")
            if event is None:
                raise ValueError(f"{where}: {did} at retirement, but the scenario has no "
                                 f"retirement event (add one, or give a {field})")
        if event is None:
            if flags.get("startsAtRetirement") and not item.get("startDate"):
                raise ValueError(f"{where}: starts at retirement, but the scenario has no "
                                 "retirement event (add one, or give a startDate)")
            continue
        action = "end" if flags.get("endsAtRetirement") else (
            "start" if flags.get("startsAtRetirement") or flags.get("atRetirement") else None)
        if action is None:
            continue
        item.setdefault("id", f"item{n}")
        if not event.get("id"):
            event["id"] = _free_id(s, "retirement")
        label = "Ends at" if action == "end" else "At"
        triggers.append({"type": "trigger", "id": f"{item['id']}-{action}-at-retirement",
                         "name": f"{label} {event.get('name') or 'retirement'}",
                         "event": event["id"], "target": item["id"], "action": action})
    s["items"].extend(triggers)


def _retirement_event(item, s):
    pid = retirement_person(item, s)
    return next((e for e in s["items"] if isinstance(e, dict) and e.get("type") == "retirement"
                 and owner_of(e, s) == pid), None)


def _free_id(s, base):
    taken = {i.get("id") for i in s["items"] if isinstance(i, dict)}
    n, candidate = 1, base
    while candidate in taken:
        n += 1
        candidate = f"{base}-{n}"
    return candidate


def _old_attached(item):
    return isinstance(item, dict) and "attachedTo" in item


def _old_costs(item):
    return isinstance(item, dict) and (
        (item.get("type") == "vehicle" and "annualMaintenance" in item)
        or (item.get("type") == "sale" and "sellingCostRate" in item))


def _old_flags(item):
    return isinstance(item, dict) and any(f in item for f in FLAGS)


def _retirement_setting(s):
    date = s.pop("retirementDate")
    if not date:
        return
    if any(isinstance(i, dict) and i.get("type") == "retirement" for i in s["items"]):
        raise ValueError("scenario: has both a retirement event and a retirementDate setting; "
                         "keep the event")
    at = month_index(date, "retirementDate")
    event = {"type": "retirement", "name": "Retirement", "retirementDate": date}
    try:
        h = s["horizon"]
        inside = month_index(h["start"], "") <= at <= month_index(h["end"], "")
    except (KeyError, TypeError, ValueError):
        inside = True               # a bad horizon is reported by validation
    if not inside:
        event["outsideHorizon"] = True
    s["items"].append(event)


def _property_sales(s):
    """Each property with its own saleDate gets a sale item right after it."""
    out = []
    for item in s["items"]:
        out.append(item)
        if not _old_sale(item):
            continue
        sale = {"type": "sale", "name": item.get("name") or item.get("id"),
                "property": item.get("id"), "saleDate": item.pop("saleDate")}
        for field in ("salePrice", "sellingCostRate", "salePenalty"):
            if field in item:
                sale[field] = item[field]
        item.pop("salePrice", None)
        item.pop("salePenalty", None)
        out.append(sale)
    s["items"] = out


def _old_sale(item):
    return isinstance(item, dict) and item.get("type") == "property" and bool(item.get("saleDate"))


def _old_even(item):
    return isinstance(item, dict) and item.get("type") == "withdrawal" and item.get("method") == "even"


def _old_monthly(item):
    return (isinstance(item, dict) and item.get("type") in FLOW_TYPES
            and "amount" not in item and "monthlyAmount" in item)


def _with_jurisdiction(s):
    """The scenario with ``jurisdiction`` CA, placed after ``name`` (else first)."""
    s.pop("jurisdiction", None)
    keys = list(s)
    at = keys.index("name") + 1 if "name" in keys else 0
    keys.insert(at, "jurisdiction")
    s["jurisdiction"] = "CA"
    return {k: s[k] for k in keys}


def _needs_upgrade(scenario):
    return (not scenario.get("jurisdiction") or "retirementDate" in scenario
            or any(_old_monthly(i) or _old_even(i) or _old_sale(i) or _old_flags(i)
                   or _old_attached(i) or _old_costs(i)
                   for i in scenario["items"]))
