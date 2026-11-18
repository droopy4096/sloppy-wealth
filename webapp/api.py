"""The JSON API (ADR-0069): the server keeps nothing between requests.

Every POST takes a JSON body carrying the present scenario and returns JSON; every
response carries ``schemaVersion``. Money and rates are decimal strings (ADR-0009).

Commands (decision 3) answer ``{schemaVersion, scenario, ok, messages}``: the new
scenario, or the scenario as sent with the reason it was refused.

    GET  /api/schema                         item types, fields, choices, hints, groups
    GET  /api/new                            an empty scenario
    POST /api/load       {data}              a file's JSON -> checked, upgraded scenario
    POST /api/validate   {scenario}          ok / messages; the scenario upgraded
    POST /api/settings   {scenario, settings}
    POST /api/items/add  {scenario, item}
    POST /api/items/update {scenario, id, item, clear}   edit: new values; fields to clear
    POST /api/items/toggle {scenario, id}
    POST /api/items/delete {scenario, id}

Views of a scenario or a run answer ``{schemaVersion, ok, messages, ...}``:

    POST /api/view/builder {scenario}        starts, display order, off, set_by, choices,
                                             summary (dollars of, retirements)
    POST /api/run        {scenario}          {scenario (as sent), result (full, decision 2),
                                             summary}
    POST /api/view/ledger {scenario, month}  one month of the run
    POST /api/view/break-even {scenario, property}  a property's break-even (ADR-0073)
    POST /api/view/vehicle-cost {scenario, vehicle}  a vehicle's cost of ownership (ADR-0074)
    POST /api/timeline   {scenario}          the timeline model (ADR-0066)
    POST /api/compare    {a, b}              both runs' rows (same horizon, ADR-0028)

Limits (decision 6): a body over 1 MB is refused (413); a scenario over the item or
horizon limits is refused with a message. Responses are gzip-compressed when the client
accepts it.
"""
import gzip
import json
from decimal import Decimal

from flask import Blueprint, Response, request

import schema
import timeline
from state_machine import break_even, engine, jurisdictions, ops, vehicle_cost, views

api = Blueprint("api", __name__, url_prefix="/api")
MAX_BODY = 1024 * 1024


def _json_default(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def reply(payload, status=200):
    """A JSON response with ``schemaVersion``, gzip-compressed if the client accepts it."""
    body = json.dumps(dict({"schemaVersion": ops.SCHEMA_VERSION}, **payload),
                      default=_json_default, separators=(",", ":")).encode()
    headers = {"Content-Type": "application/json"}
    if len(body) > 1024 and "gzip" in request.headers.get("Accept-Encoding", ""):
        body = gzip.compress(body, 6)
        headers.update({"Content-Encoding": "gzip", "Vary": "Accept-Encoding"})
    return Response(body, status, headers)


def failed(messages, status=400, **extra):
    return reply(dict({"ok": False, "messages": list(messages)}, **extra), status)


class BadRequest(Exception):
    pass


def body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise BadRequest("the request body must be a JSON object")
    return data


def scenario_of(data, key="scenario"):
    s = data.get(key)
    if not isinstance(s, dict):
        raise BadRequest(f"the request needs a {key!r} object")
    problem = ops.over_limits(s)
    if problem:
        raise BadRequest(problem)
    return s


@api.errorhandler(BadRequest)
def bad_request(e):
    return failed([str(e)])


@api.errorhandler(KeyError)
@api.errorhandler(TypeError)
@api.errorhandler(AttributeError)
@api.errorhandler(ValueError)
def malformed(e):
    """A scenario the views cannot read (validation would refuse it too)."""
    return failed([f"the scenario cannot be read: {type(e).__name__}: {e}"])


@api.errorhandler(413)
def too_large(e):
    return failed([f"the request is larger than {MAX_BODY // 1024} KB"], 413)


@api.before_request
def limit_body():
    if request.content_length is not None and request.content_length > MAX_BODY:
        return too_large(None)


# ---------------------------------------------------------------- schema
@api.get("/schema")
def get_schema():
    """?jurisdiction=US: that jurisdiction's forms (ADR-0071); default Canada."""
    try:
        described = schema.describe(request.args.get("jurisdiction") or None)
    except ValueError as e:
        raise BadRequest(str(e))
    return reply(dict(described, ok=True, messages=[]))


# ---------------------------------------------------------------- commands
@api.get("/new")
def new():
    """?jurisdiction=US: a new scenario for that jurisdiction (ADR-0071); default Canada."""
    code = request.args.get("jurisdiction") or None
    if code and code not in jurisdictions.registered():
        raise BadRequest(f"unknown jurisdiction {code!r}")
    return reply(ops.outcome(ops.empty_scenario(code)))


@api.post("/load")
def load():
    data = body()
    if "data" not in data:
        raise BadRequest("the request needs 'data' (a scenario file's JSON)")
    problem = ops.over_limits(data["data"]) if isinstance(data["data"], dict) else None
    if problem:
        raise BadRequest(problem)
    return reply(ops.load(data["data"]))


@api.post("/validate")
def validate():
    s = scenario_of(body())
    try:
        engine.validate(s)
        return reply(ops.outcome(engine.upgrade(s)))
    except ValueError as e:
        return reply(ops.refused(s, str(e)))


@api.post("/settings")
def settings():
    data = body()
    values = data.get("settings")
    if not isinstance(values, dict):
        raise BadRequest("the request needs a 'settings' object")
    return reply(ops.settings(scenario_of(data), values))


@api.post("/items/add")
def add_item():
    data = body()
    item = data.get("item")
    if not isinstance(item, dict):
        raise BadRequest("the request needs an 'item' object")
    # Any jurisdiction's type; validation refuses one the scenario's does not offer.
    if item.get("type") not in schema.FIELDS and item.get("type") not in \
            jurisdictions.own_item_types():
        raise BadRequest(f"unknown item type {item.get('type')!r}")
    return reply(ops.add_item(scenario_of(data), item))


@api.post("/items/update")
def update_item():
    data = body()
    item = data.get("item")
    if not isinstance(item, dict):
        raise BadRequest("the request needs an 'item' object (the new values)")
    clear = data.get("clear") or []
    if not isinstance(clear, list):
        raise BadRequest("'clear' must be a list of field names")
    return reply(ops.update_item(scenario_of(data), data.get("id"), item, clear))


@api.post("/items/toggle")
def toggle_item():
    data = body()
    return reply(ops.toggle_item(scenario_of(data), data.get("id")))


@api.post("/items/delete")
def delete_item():
    data = body()
    return reply(ops.delete_item(scenario_of(data), data.get("id")))


# ---------------------------------------------------------------- views and runs
@api.post("/view/builder")
def builder_view():
    s = scenario_of(body())
    view = views.builder_view(s)
    view["ordered"] = [{"id": item.get("id"), "nested": nested}
                       for item, nested in view["ordered"]]
    return reply(dict(view, ok=True, messages=[]))


def _run(s):
    """The full detailed result, or a refusal message."""
    try:
        return engine.run_detailed(s), None
    except ValueError as e:
        return None, str(e)


@api.post("/run")
def run():
    s = scenario_of(body())
    result, error = _run(s)
    if error:
        return reply({"ok": False, "messages": [error], "scenario": s})
    return reply({"ok": True, "messages": [], "scenario": s, "result": result,
                  "summary": views.summary(s)})


@api.post("/view/ledger")
def ledger_view():
    data = body()
    s = scenario_of(data)
    result, error = _run(s)
    if error:
        return reply({"ok": False, "messages": [error]})
    month = views.ledger_month(s, result, data.get("month"))
    month["balances"] = [{"holding": {k: v for k, v in h.items() if k != "points"},
                          "point": p} for h, p in month["balances"]]
    month["events"] = None if month["events"] is None else [
        dict(e, movements=[{"index": i, "movement": m} for i, m in e["movements"]])
        for e in month["events"]]
    return reply(dict(month, ok=True, messages=[]))


@api.post("/view/break-even")
def break_even_view():
    """{scenario, property}: a property's break-even and rent equivalent per month from
    the run (ADR-0073); ``properties`` lists them all; without ``property``, the first."""
    data = body()
    s = scenario_of(data)
    result, error = _run(s)
    if error:
        return reply({"ok": False, "messages": [error]})
    listed = break_even.properties(s)
    pid = data.get("property") or (listed[0][0] if listed else None)
    if pid is None:
        return reply({"ok": True, "messages": [], "properties": [], "view": None})
    try:
        view = break_even.break_even(s, result, pid)
    except ValueError as e:
        return reply({"ok": False, "messages": [str(e)]})
    return reply({"ok": True, "messages": [], "view": view,
                  "properties": [{"id": i, "name": n} for i, n in listed]})


@api.post("/view/vehicle-cost")
def vehicle_cost_view():
    """{scenario, vehicle}: a vehicle's cost of ownership per month from the run
    (ADR-0074); ``vehicles`` lists them all; without ``vehicle``, the first."""
    data = body()
    s = scenario_of(data)
    result, error = _run(s)
    if error:
        return reply({"ok": False, "messages": [error]})
    listed = vehicle_cost.vehicles(s)
    vid = data.get("vehicle") or (listed[0][0] if listed else None)
    if vid is None:
        return reply({"ok": True, "messages": [], "vehicles": [], "view": None})
    try:
        view = vehicle_cost.cost_of_ownership(s, result, vid)
    except ValueError as e:
        return reply({"ok": False, "messages": [str(e)]})
    return reply({"ok": True, "messages": [], "view": view,
                  "vehicles": [{"id": i, "name": n} for i, n in listed]})


@api.post("/timeline")
def timeline_model():
    s = scenario_of(body())
    try:
        model = timeline.layout(s)
    except (ValueError, KeyError, TypeError) as e:
        return reply({"ok": False, "messages": [str(e)]})
    return reply(dict(model, ok=True, messages=[]))


@api.post("/compare")
def compare():
    data = body()
    a, b = scenario_of(data, "a"), scenario_of(data, "b")
    span = lambda s: tuple(engine.month_index(s["horizon"][k], k) for k in ("start", "end"))
    try:
        same = span(a) == span(b)
    except (KeyError, TypeError, ValueError) as e:
        return reply({"ok": False, "messages": [str(e)]})
    if not same:
        return reply({"ok": False, "messages": [
            "compared scenarios must share a horizon (ADR-0028): "
            f"A is {a['horizon']['start']}..{a['horizon']['end']}, "
            f"B is {b['horizon']['start']}..{b['horizon']['end']}"]})
    rows = []
    for key, s in (("A", a), ("B", b)):
        try:
            rows.append(engine.run(s))
        except ValueError as e:
            return reply({"ok": False, "messages": [f"scenario {key}: {e}"]})
    return reply({"ok": True, "messages": [], "a": rows[0], "b": rows[1],
                  "summaries": {"a": views.summary(a), "b": views.summary(b)}})
