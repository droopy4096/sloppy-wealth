"""Triggers (``type: "trigger"``) — ADR-0065 (proposed).

A trigger ties a date of its ``target`` to the date of its ``event`` (another item):

- ``start``: the target happens or starts in the event's month (``START_FIELD``); the
  trigger's date replaces the target's own;
- ``end``: the target's last month is the month before the event (``endDate``; the
  earlier of the two when the target has one) — recurring items only. If that is before
  the target's own startDate, the target never runs (left out with its dependents);
- ``startAndEnd``: only in the event's month — recurring items only.

``on`` (default ``start``) says which date of the event counts: its date (``START_FIELD``),
or ``end``: the month after its last month (recurring events), or its sale month (a
property or vehicle with a sale item), so ``end`` on an event's end makes the target's
last month the event's last month. An event that never
ends never fires: an end trigger leaves its target's endDate as it is, a start trigger
makes its target never run.

``resolve(scenario)`` runs right after ``upgrade`` and ``enabled.active``: it returns the
scenario with the dates written into the targets (a copy; the scenario itself when it has
no triggers), so the rest of the engine sees plain dates. Triggers whose event is itself a
target are resolved after that one's trigger (a cycle is an error).
"""
import copy

from .dates import month_index, month_label

ACTIONS = ("start", "end", "startAndEnd")
ONS = ("start", "end")
# The date an item happens or starts on.
START_FIELD = {"property": "purchaseDate", "vehicle": "purchaseDate", "lumpSum": "paymentDate",
               "improvement": "improvementDate", "sale": "saleDate",
               "marketAdjustment": "adjustmentDate", "adjustment": "adjustmentDate",
               "account": "openedDate", "retirement": "retirementDate",
               "transfer": "transferDate", "cashBalance": "balanceDate",
               "income": "startDate", "expense": "startDate", "contribution": "startDate",
               "withdrawal": "startDate", "pension": "startDate", "extraPayment": "startDate",
               "renewal": "startDate", "mortgage": "startDate",
               "associatedCost": "costDate",
               "associatedOneOff": "paymentDate"}
# Recurring items: they also have an endDate.
RECURRING = ("income", "expense", "contribution", "withdrawal", "pension", "extraPayment")
# Events with an end (``on: end``): recurring items, and assets (their sale).
ASSETS = ("property", "vehicle")


def _where(item):
    return f"trigger {item.get('name') or item.get('id')}"


def _first_of(month):
    return f"{month_label(month)}-01"


def check(trigger, by_id):
    """The trigger's event, target and action are usable; returns (event, target)."""
    where = _where(trigger)
    event, target = by_id.get(trigger.get("event")), by_id.get(trigger.get("target"))
    if event is None:
        raise ValueError(f"{where}: event refers to unknown item {trigger.get('event')!r}")
    if target is None:
        raise ValueError(f"{where}: target refers to unknown item {trigger.get('target')!r}")
    if event is target:
        raise ValueError(f"{where}: event and target are the same item")
    if event.get("type") not in START_FIELD:
        raise ValueError(f"{where}: {event.get('type')} items have no date to trigger on")
    action = trigger.get("action")
    if action not in ACTIONS:
        raise ValueError(f"{where}: action must be start, end or startAndEnd")
    on = trigger.get("on") or "start"
    if on not in ONS:
        raise ValueError(f"{where}: on must be start or end")
    if on == "end" and event.get("type") not in RECURRING + ASSETS:
        raise ValueError(f"{where}: on end applies only to recurring events "
                         f"({', '.join(RECURRING)}) and to assets (their sale)")
    kind = target.get("type")
    if action == "start" and kind not in START_FIELD:
        raise ValueError(f"{where}: {kind} items have no date to set")
    if action != "start" and kind not in RECURRING:
        raise ValueError(f"{where}: {action} applies only to recurring items "
                         f"({', '.join(RECURRING)})")
    return event, target


def resolve(scenario):
    if not isinstance(scenario, dict) or not isinstance(scenario.get("items"), list):
        return scenario                 # malformed: validation reports it
    if not any(isinstance(i, dict) and i.get("type") == "trigger" for i in scenario["items"]):
        return scenario
    s = dict(scenario, items=copy.deepcopy(scenario["items"]))
    by_id = {i.get("id"): i for i in s["items"] if isinstance(i, dict) and i.get("id")}
    pending = [t for t in s["items"] if t.get("type") == "trigger"]
    # Targets of end triggers -> their own endDate before the trigger.
    ended = {t.get("target"): by_id.get(t.get("target"), {}).get("endDate")
             for t in pending if t.get("action") == "end"}
    seen, never = set(), []
    for t in pending:
        event, target = check(t, by_id)
        for field in _fields(t["action"]):
            key = (t["target"], field)
            if key in seen:
                raise ValueError(f"{_where(t)}: {target.get('name') or t['target']} already "
                                 f"has a trigger setting its {field}")
            seen.add(key)
    sales = {i.get("property"): i for i in s["items"] if i.get("type") == "sale"}

    def needs(t):                   # the items whose dates the trigger reads
        sale = sales.get(t["event"]) if (t.get("on") or "start") == "end" else None
        return {t["event"], sale.get("id")} if sale else {t["event"]}

    while pending:
        targets = {t["target"] for t in pending}
        ready = [t for t in pending if not needs(t) & targets]
        if not ready:
            names = ", ".join(_where(t) for t in pending)
            raise ValueError(f"{names}: triggers depend on each other in a cycle")
        for t in ready:
            _apply(t, by_id[t["event"]], by_id[t["target"]], never, sales)
        pending = [t for t in pending if t not in ready]
    # Ended by its trigger before its own start: never runs, so it is left out of the run
    # like an off item, with its dependents (as at-retirement items did, ADR-0059).
    # (A target's own endDate before its startDate stays an error for validation.)
    never += [by_id[tid] for tid, own_end in ended.items() if by_id[tid].get("startDate")
              and by_id[tid].get("endDate") and _before_start(by_id[tid]["endDate"], by_id[tid])
              and not (own_end and _before_start(own_end, by_id[tid]))]
    if never:
        from .enabled import active
        for item in never:
            item["enabled"] = False
        s = active(s)
    return s


def _before_start(date, item):
    where = f"item {item.get('name') or item.get('id')}"
    return (month_index(date, f"{where}.endDate")
            < month_index(item["startDate"], f"{where}.startDate"))


def _fields(action):
    return {"start": ("start",), "end": ("end",), "startAndEnd": ("start", "end")}[action]


def event_month(event, where, on="start", sales=None):
    """Month index of an event item's date; for ``on`` end the month after its last month
    (an asset: its sale month), None if it never ends."""
    if on == "end" and event.get("type") in ASSETS:
        sale = (sales or {}).get(event.get("id"))
        return event_month(sale, where) if sale else None
    if on == "end":
        if not event.get("endDate"):
            return None
        name = event.get("name") or event.get("id")
        return month_index(event["endDate"], f"item {name}.endDate") + 1
    field = START_FIELD[event["type"]]
    item = f"item {event.get('name') or event.get('id')}"
    if not event.get(field):
        raise ValueError(f"{item}: missing field {field!r} (the event of {where})")
    return month_index(event[field], f"{item}.{field}")


def _apply(trigger, event, target, never, sales):
    where = _where(trigger)
    at = event_month(event, where, trigger.get("on") or "start", sales)
    action = trigger["action"]
    if at is None:                  # the event never ends: it never fires
        if action != "end":
            never.append(target)
        return
    if action in ("start", "startAndEnd"):
        target[START_FIELD[target["type"]]] = _first_of(at)
    if action == "end":
        last = at - 1
        if target.get("endDate"):
            last = min(last, month_index(target["endDate"], f"{where}.target endDate"))
        target["endDate"] = _first_of(last)
    if action == "startAndEnd":
        target["endDate"] = _first_of(at)


def prepared(scenario):
    """The scenario as the engine sees it: older forms converted (``upgrade``), off items
    left out (``enabled.active``, ADR-0064), triggers resolved."""
    from .enabled import active
    from .upgrade import upgrade
    return resolve(active(upgrade(scenario)))
