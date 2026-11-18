"""Item on/off switch (``"enabled": false``) — ADR-0064.

An item that is off is left out of the run, and so is every item that refers to an off
item (cascade, transitively): through a link field (``LINK_FIELDS``, the links the
builder's Delete follows) or a person field (``PERSON_FIELDS``). The file keeps them.
An item started by a trigger (ADR-0065: action start or startAndEnd) whose event is off
never starts, so it is off too; an end trigger's target just runs on.

``active(scenario)`` is applied right after ``upgrade`` by validation, the compiler and
``dates.retirement_dates``: the rest of the engine never sees an off item. It returns the
scenario itself when every item is on, else a copy without the off items.
"""
# Fields naming the item an item depends on.
LINK_FIELDS = ("property", "mortgage", "account", "flow", "event", "target", "parent")
# Fields naming a person (ADR-0061).
PERSON_FIELDS = ("owner", "contributor", "retirementOf")
REF_FIELDS = LINK_FIELDS + PERSON_FIELDS


def is_off(item):
    """True if the item itself is switched off; ``enabled`` must be a boolean."""
    value = item.get("enabled", True)
    if not isinstance(value, bool):
        where = item.get("name") or item.get("id") or item.get("type")
        raise ValueError(f"item {where}: enabled must be true or false; got {value!r}")
    return value is False


def off_reasons(items):
    """{position: id of the switched-off item it follows, or None if it is off itself}
    for every item that is off, directly or through its references."""
    off = {n: None for n, i in enumerate(items) if isinstance(i, dict) and is_off(i)}
    off_ids = {items[n].get("id"): None for n in off if items[n].get("id")}
    starters = [i for i in items if isinstance(i, dict) and i.get("type") == "trigger"
                and i.get("action") in ("start", "startAndEnd")]
    while True:
        more = {}
        for n, item in enumerate(items):
            if n in off or not isinstance(item, dict):
                continue
            hit = next((item[f] for f in REF_FIELDS if item.get(f) in off_ids), None)
            if hit is None and item.get("id"):
                hit = next((t["event"] for t in starters if t.get("target") == item["id"]
                            and t.get("event") in off_ids), None)
            if hit is not None:
                more[n] = off_ids[hit] or hit      # the root that is off itself
        if not more:
            return off
        off.update(more)
        off_ids.update({items[n].get("id"): r for n, r in more.items() if items[n].get("id")})


def active(scenario):
    if not isinstance(scenario, dict) or not isinstance(scenario.get("items"), list):
        return scenario                 # malformed: validation reports it
    off = off_reasons(scenario["items"])
    if not off:
        return scenario
    return dict(scenario, items=[i for n, i in enumerate(scenario["items"]) if n not in off])
