"""Scenario commands (ADR-0069 decision 3): pure functions, scenario + command -> outcome.

Every command takes the present scenario (a JSON-shaped dict) and returns an outcome
dict ``{"scenario", "ok", "messages"}``:

- ``ok`` True: ``scenario`` is the new scenario (upgraded, validated);
- ``ok`` False: ``scenario`` is the scenario as given, unchanged, and ``messages`` says
  why the change was refused.

``messages`` may also carry notes on an accepted change (e.g. an item added switched off
while it waits for a trigger). The input is never changed. Values are JSON values
(decimal strings as fractions, booleans); turning form text into them is the client's
job.
"""
import copy
import uuid

from .engine import upgrade, validate
from .dates import month_index
from .enabled import LINK_FIELDS
from .triggers import START_FIELD
from . import jurisdictions

SCHEMA_VERSION = 1
# Request limits (ADR-0069 decision 6).
MAX_ITEMS = 1000
MAX_YEARS = 100
# Items naming a person (ADR-0061): blank means the first person.
PERSON_FIELDS = ("owner", "contributor")


def outcome(scenario, ok=True, messages=()):
    return {"scenario": scenario, "ok": ok, "messages": list(messages)}


def refused(scenario, message):
    return outcome(scenario, False, [message])


def new_id():
    return uuid.uuid4().hex[:8]


def empty_scenario(jurisdiction=None):
    return {"schemaVersion": SCHEMA_VERSION, "name": "Untitled",
            "jurisdiction": jurisdiction or jurisdictions.DEFAULT,
            "horizon": {"start": "2027-01-01", "end": "2051-12-01"},
            "openingCash": "0", "items": []}


def _checked(original, candidate, notes=()):
    """The outcome of a change: the candidate if it validates, else the original."""
    try:
        validate(candidate)
    except ValueError as e:
        return refused(original, str(e))
    return outcome(candidate, True, notes)


def _prepared(scenario):
    """A working copy in the current format (older files upgraded, ADR-0069 decision 4)."""
    return copy.deepcopy(upgrade(scenario))


def over_limits(scenario):
    """Why a scenario is too large to accept (ADR-0069 decision 6), or None."""
    if not isinstance(scenario, dict):
        return "the scenario must be a JSON object"
    items = scenario.get("items")
    if isinstance(items, list) and len(items) > MAX_ITEMS:
        return f"a scenario may have at most {MAX_ITEMS} items; this one has {len(items)}"
    horizon = scenario.get("horizon")
    if isinstance(horizon, dict):
        try:
            years = (month_index(horizon["end"], "horizon.end")
                     - month_index(horizon["start"], "horizon.start")) / 12
        except (KeyError, TypeError, ValueError):
            return None                 # reported by validation
        if years > MAX_YEARS:
            return f"the horizon may be at most {MAX_YEARS} years; this one is {years:.0f}"
    return None


# ---------------------------------------------------------------- commands
def load(data):
    """A scenario from a file's JSON: checked, upgraded, every item given an id."""
    if not isinstance(data, dict):
        return refused(empty_scenario(), "not a JSON object")
    if data.get("schemaVersion") != SCHEMA_VERSION:
        return refused(empty_scenario(),
                       f"unsupported schemaVersion {data.get('schemaVersion')!r}")
    try:
        validate(data)
        candidate = _prepared(data)
    except (ValueError, TypeError, AttributeError, KeyError) as e:
        return refused(empty_scenario(), str(e))
    for item in candidate["items"]:
        item.setdefault("id", new_id())
    return outcome(candidate)


def settings(scenario, values):
    """Scenario settings: name, horizon {start, end}, openingCash, incomeMode, dollarsOf,
    annualInflation, effectiveTaxRate, retirementTaxRate (blank: no switch, ADR-0059).
    Missing keys keep their defaults as the builder's form gives them."""
    candidate = _prepared(scenario)
    candidate["name"] = (values.get("name") or "").strip() or "Untitled"
    horizon = values.get("horizon") or {}
    candidate["horizon"] = {"start": horizon.get("start", ""), "end": horizon.get("end", "")}
    candidate["openingCash"] = values.get("openingCash", "")
    candidate["incomeMode"] = values.get("incomeMode") or "modelled"
    candidate["dollarsOf"] = values.get("dollarsOf", "")
    for field in ("annualInflation", "effectiveTaxRate"):
        candidate[field] = values.get(field) or "0"
    candidate["retirementTaxRate"] = values.get("retirementTaxRate") or ""
    code = values.get("jurisdiction")
    if code and code != candidate.get("jurisdiction"):
        problem = switch_problem(candidate, code)
        if problem:
            return refused(scenario, problem)
        candidate["jurisdiction"] = code
    return _checked(scenario, candidate)


def switch_problem(scenario, code):
    """Why the scenario cannot change to jurisdiction ``code`` (ADR-0071 decision 2), or
    None: unknown code, or items the new one does not offer (named)."""
    if code not in jurisdictions.registered():
        return f"unknown jurisdiction {code!r}"
    new = jurisdictions.get(code)
    kept = set(new.item_types)
    own = jurisdictions.own_item_types()
    blocking = []
    for item in scenario.get("items", []):
        kind = item.get("type")
        label = item.get("name") or item.get("id") or kind
        if kind in own and kind not in kept:
            blocking.append(f"{label} ({kind})")
        elif kind == "account" and item.get("accountType") not in new.account_types:
            blocking.append(f"{label} ({item.get('accountType')} account)")
    if not blocking:
        return None
    return (f"cannot change the jurisdiction to {new.name}: remove or change these items "
            f"first: {', '.join(blocking)}")


def add_item(scenario, item):
    """Add an item (``type`` required; an id and a name are given if missing). An item
    whose date is to come from a trigger is added switched off, with a note (ADR-0065);
    a trigger switches on the target that waited for it."""
    kind = item.get("type") if isinstance(item, dict) else None
    if not kind:
        return refused(scenario, "an item needs a type")
    candidate = _prepared(scenario)
    item = copy.deepcopy(item)
    item.setdefault("id", new_id())
    if not item.get("name"):
        item["name"] = kind[:1].upper() + kind[1:]
    if any(i.get("id") == item["id"] for i in candidate["items"]):
        return refused(scenario, f"an item with id {item['id']!r} already exists")
    candidate["items"].append(item)
    if kind == "trigger":
        _switch_on_target(candidate, item)
    try:
        validate(candidate)
    except ValueError as e:
        date_field = START_FIELD.get(kind)
        if date_field and not item.get(date_field) and f"missing field {date_field!r}" in str(e):
            item["enabled"] = False
            return _checked(scenario, candidate, [
                f"{e}. Added switched off: add a trigger that sets its {date_field}."])
        return refused(scenario, str(e))
    return outcome(candidate)


def _switch_on_target(candidate, trigger):
    """A target switched off only while it waited for a trigger's date is switched on
    when the trigger is added, if the scenario is then valid (ADR-0065)."""
    target = next((i for i in candidate["items"] if i.get("id") == trigger.get("target")), None)
    if target is None or target.get("enabled", True) is not False:
        return
    if trigger.get("action") == "end" or target.get(START_FIELD.get(target["type"], "")):
        return              # it did not wait for a start date
    del target["enabled"]
    try:
        validate(candidate)
    except ValueError:
        target["enabled"] = False


def update_item(scenario, item_id, values, clear=()):
    """Edit an item (ADR-0070 amendment): ``values`` replace its fields; the fields named
    in ``clear`` are removed (back to their defaults). Its id and type stay, so its links
    and triggers keep pointing at it; its on/off state stays unless ``values`` sets it."""
    if not isinstance(values, dict):
        return refused(scenario, "the new values must be an object")
    candidate = _prepared(scenario)
    item = next((i for i in candidate["items"] if i.get("id") == item_id), None)
    if item is None:
        return refused(scenario, f"no item {item_id!r}")
    if values.get("type", item["type"]) != item["type"]:
        return refused(scenario, f"an item's type cannot change ({item['type']} to "
                                 f"{values['type']}); add a new item instead")
    for field in clear:
        if field not in ("id", "type"):
            item.pop(field, None)
    item.update({k: copy.deepcopy(v) for k, v in values.items() if k not in ("id", "type")})
    if not item.get("name"):
        item["name"] = item["type"][:1].upper() + item["type"][1:]
    return _checked(scenario, candidate)


def toggle_item(scenario, item_id):
    """Switch an item off or back on (ADR-0064); on is the default, so switching on
    removes the field. Its dependents follow it in the run; the file keeps them."""
    candidate = _prepared(scenario)
    item = next((i for i in candidate["items"] if i.get("id") == item_id), None)
    if item is None:
        return refused(scenario, f"no item {item_id!r}")
    if item.get("enabled", True) is False:
        del item["enabled"]
    else:
        item["enabled"] = False
    return _checked(scenario, candidate)


def delete_item(scenario, item_id):
    """Delete an item and everything that depends on it: items linked to it (LINK_FIELDS:
    a property's mortgages, sales, ...; an account's flows; a flow's adjustments; an
    associated item's parent; triggers on it) and the items its triggers start, then
    their dependents in turn. Deleting a person also deletes their retirement event and
    contribution room; their other items fall back to the first person."""
    candidate = _prepared(scenario)
    items = candidate["items"]
    if not any(i.get("id") == item_id for i in items):
        return refused(scenario, f"no item {item_id!r}")
    gone = {item_id}
    target = next(i for i in items if i.get("id") == item_id)
    if target.get("type") == "person":
        gone |= {i["id"] for i in items if i.get("owner") == item_id
                 and i.get("type") in ("retirement", "contributionRoom")}
    while True:
        started = {t.get("target") for t in items if t.get("type") == "trigger"
                   and t.get("action") in ("start", "startAndEnd") and t.get("event") in gone}
        more = {i.get("id") for i in items if i.get("id") not in gone
                and (any(i.get(f) in gone for f in LINK_FIELDS) or i.get("id") in started)}
        if not more:
            break
        gone |= more
    candidate["items"] = [i for i in items if i.get("id") not in gone]
    for i in candidate["items"]:
        for field in PERSON_FIELDS:
            if i.get(field) in gone:
                del i[field]
    return _checked(scenario, candidate)
