"""The Jinja builder as a client of the JSON API (ADR-0069 decision 5).

The server keeps nothing: the browser holds the scenario in the tab's sessionStorage
(decision 1) and posts it with every request (form field ``scenario``, JSON text); the
page that comes back carries the new scenario (``<script id="scenario-state">``) for
``static/web.js`` to store.

- ``GET`` of a page returns a shell; the script then posts the stored scenario to the
  same URL and shows the page that comes back (so refresh and back keep working).
- ``POST`` of a page renders it for the posted scenario.
- Actions (settings, add, switch, delete, load) call the API's commands and render the
  builder (or the load page) with the new scenario and the command's messages.
- Save is done in the browser (a download of the stored scenario).

No engine imports: everything comes from ``client`` (the API).
"""
from collections import defaultdict
import functools
import json
import os
from decimal import Decimal

from flask import Blueprint, abort, render_template, request
from markupsafe import Markup

from . import client, timeline_draw

web = Blueprint("web", __name__, template_folder="templates", static_folder="static",
                static_url_path="/web/static")
ZERO = Decimal(0)


# ---------------------------------------------------------------- the schema
@functools.lru_cache(maxsize=16)
def _schema_json(code):
    return client.get("/schema?jurisdiction=" + code, convert=False)


def jurisdiction_of(scenario):
    """The scenario's jurisdiction code (ADR-0071; files without one are Canadian)."""
    code = scenario.get("jurisdiction") if isinstance(scenario, dict) else None
    return code if isinstance(code, str) and code.isalpha() else "CA"


def schema(scenario=None):
    """The item-type schema of the scenario's jurisdiction (ADR-0071) with (type, field)
    keys and (value, label) choices, as the templates use them."""
    s = _schema_json(jurisdiction_of(scenario))
    if not s.get("ok", True) or "fields" not in s:
        s = _schema_json("CA")
    pair = lambda key: tuple(key.split(".")) if "." in key else key
    return {
        "jurisdiction": s["jurisdiction"], "jurisdictions": s["jurisdictions"],
        "fields": s["fields"], "legends": s["legends"], "needs": s["needs"],
        "hints": {pair(k): v for k, v in s["hints"].items()},
        "blank_shown": {pair(k): v for k, v in s["blankShown"].items()},
        "defaults": {pair(k): v for k, v in s["defaults"].items()},
        "form_groups": [(g["heading"], g["types"], g["missing"]) for g in s["formGroups"]],
        "selects": {f: [(o["value"], o["label"]) for o in options]
                    for f, options in s["selects"].items()},
        "percent_fields": set(s["percentFields"]),
        "person_fields": s["personFields"],
        "card_adds": s["cardAdds"], "head_adds": s["headAdds"], "link_field": s["linkField"],
        "add_groups": [(g["title"], g["types"]) for g in s["addGroups"]],
    }


# ---------------------------------------------------------------- filters
@web.app_template_filter("percent")
def percent_filter(value):
    return f"{(Decimal(str(value)) * 100).normalize():f}%"


@web.app_template_filter("money")
def money_filter(value):
    return f"{value:,.2f}"


@web.app_template_filter("state_json")
def state_json(value):
    """JSON for a <script type="application/json"> block, in its own key order."""
    text = json.dumps(value, ensure_ascii=False)
    return Markup(text.replace("&", "\\u0026").replace("<", "\\u003c")
                  .replace(">", "\\u003e"))


def percent_to_fraction(text):
    try:
        return str(Decimal(text) / 100)
    except Exception:
        return text  # validation reports it


# ---------------------------------------------------------------- the posted state
def posted_scenario():
    """(scenario, messages) from the request's ``scenario`` field; a new empty scenario
    if there is none (a new tab) or it cannot be read."""
    text = request.form.get("scenario", "").strip()
    if text:
        try:
            scenario = json.loads(text)
            if (isinstance(scenario, dict) and isinstance(scenario.get("horizon"), dict)
                    and isinstance(scenario.get("items"), list)):
                return scenario, []
        except ValueError:
            pass
        messages = ["The stored scenario could not be read; a new one was started."]
    else:
        messages = []
    return client.get("/new")["scenario"], messages


def page(template, scenario, messages=(), **context):
    """A full page for ``scenario`` (carried back to the browser), with its jurisdiction's
    wording (ADR-0071)."""
    context.setdefault("jurisdiction", schema(scenario)["jurisdiction"])
    return render_template(template, scenario=scenario, messages=list(messages), zero=ZERO,
                           **context)


def shell():
    """A page without content: web.js posts the stored scenario to fill it in."""
    return render_template("base.html", shell=True, messages=[])


# ---------------------------------------------------------------- builder
VIEWS = {"cards": "builder.html", "flat": "flat.html"}


def current_view():
    """Which builder view an action renders: the one it was sent from (web.js sends
    X-Builder-View; a form may send ``view``), else the cards."""
    view = request.headers.get("X-Builder-View") or request.form.get("view") or ""
    return view if view in VIEWS else "cards"


def builder_page(scenario, messages=(), view=None, refused=False):
    """``refused``: the command was turned down; web.js then reopens the form that was
    sent, with what was typed in it."""
    template = VIEWS[view or current_view()]
    answer = client.call("/view/builder", {"scenario": scenario})
    if not answer.get("ok"):
        return page(template, scenario, list(messages) + answer["messages"], refused=refused,
                    **_builder_context(scenario, None))
    return page(template, scenario, messages, refused=refused,
                **_builder_context(scenario, answer))


def _builder_context(scenario, view):
    by_id = {i.get("id"): i for i in scenario.get("items", [])}
    if view is None:
        view = {"ordered": [{"id": i.get("id"), "nested": False}
                            for i in scenario.get("items", [])],
                "starts": {}, "off": {}, "set_by": {},
                # No choices: every list (names.property, ...) is empty.
                "names": defaultdict(dict)}
    names = view["names"]
    s = schema(scenario)
    layout = view.get("cards") or {"base": "", "sections": [], "estimates": {}}
    by_id = dict(by_id, **view.get("items", {}))
    base = layout["base"]

    def fixed_for(kind, ctx):
        """Fields filled in for a new item: the card it is added on (by its link field),
        or the section's person as owner."""
        if "card" in ctx:
            field = s["link_field"].get(kind)
            if field == "mortgage" and ctx["type"] != "mortgage":
                return {}                       # on a property card: choose the mortgage
            return {field: ctx["card"]} if field else {}
        return {k: v for k, v in ctx.items() if k in s["fields"][kind]}

    def addable(kinds, ctx):
        """The kinds whose form can be shown here (their references exist)."""
        shown = []
        for kind in kinds:
            need = s["needs"].get(kind)
            fixed = fixed_for(kind, ctx)
            if need is None or names.get(need) or fixed:
                if kind in ("renewal", "extraPayment", "lumpSum") and not fixed \
                        and not names.get("mortgage"):
                    continue
                shown.append(kind)
        return shown

    return dict(layout=layout, by_id=by_id, fixed_for=fixed_for, addable=addable,
                form_values=lambda item: form_values(item, scenario),
                linked_kinds=s["card_adds"], head_kinds=s["head_adds"],
                add_groups=s["add_groups"],
                estimate_tip=(f"Estimate for {base}: each item's own amount per month, indexed "
                              f"to {base} with its own indexing (adjustments included); "
                              "percentages of their stated basis; mortgage payments from "
                              "their terms. A hint only: the run gives the exact amounts."),
                fields=s["fields"], ordered=[(by_id[o["id"]], o["nested"])
                                             for o in view["ordered"] if o["id"] in by_id],
                starts=view["starts"], off=view["off"], set_by=view["set_by"], names=names,
                blank_shown=s["blank_shown"], percent_fields=s["percent_fields"],
                selects=s["selects"], legends=s["legends"], hints=s["hints"],
                needs=s["needs"], defaults=s["defaults"], form_groups=s["form_groups"],
                person_fields=s["person_fields"], jurisdiction=s["jurisdiction"],
                jurisdictions=s["jurisdictions"])


def command(path, payload, messages=()):
    """Run an API command; render the builder with its outcome."""
    answer = client.call(path, payload)
    scenario = answer.get("scenario", payload["scenario"])
    return builder_page(scenario, list(messages) + answer["messages"],
                        refused=not answer.get("ok"))


@web.route("/", methods=["GET", "POST"])
def builder():
    if request.method == "GET":
        return shell()
    scenario, messages = posted_scenario()
    return builder_page(scenario, messages, view="cards")


@web.route("/flat", methods=["GET", "POST"])
def flat():
    """The flat builder: every item in one list (ADR-0070 amendment)."""
    if request.method == "GET":
        return shell()
    scenario, messages = posted_scenario()
    return builder_page(scenario, messages, view="flat")


@web.post("/settings")
def settings():
    """The settings form: text to JSON values (percentages to fractions)."""
    scenario, messages = posted_scenario()
    f = request.form
    value = lambda field: f.get(field, "").strip()
    percent = lambda field: percent_to_fraction(value(field)) if value(field) else ""
    return command("/settings", {"scenario": scenario, "settings": {
        "name": value("name"), "horizon": {"start": value("start"), "end": value("end")},
        "openingCash": value("openingCash"), "incomeMode": f.get("incomeMode") or "",
        "dollarsOf": value("dollarsOf"), "annualInflation": percent("annualInflation"),
        "effectiveTaxRate": percent("effectiveTaxRate"),
        "retirementTaxRate": percent("retirementTaxRate"),
        "jurisdiction": f.get("jurisdiction") or ""}}, messages)


@web.post("/items/add")
def add_item():
    scenario, messages = posted_scenario()
    kind = request.form.get("type")
    if kind not in schema(scenario)["fields"]:
        return builder_page(scenario, messages + [f"unknown item type {kind!r}"],
                            refused=True)
    item = form_item(kind, request.form, scenario)
    return command("/items/add", {"scenario": scenario, "item": item},
                   messages)


def form_item(kind, form, scenario=None):
    """A form's text as an item's JSON values: percentages to fractions, yes / no to
    booleans, "covers" to payOff; blank defaults left out (earnedIncome: as taxable,
    ADR-0060; on: the event's date, ADR-0065; persons: the first, ADR-0061)."""
    s = schema(scenario)
    item = {"type": kind, "name": form.get("name", "").strip() or kind.capitalize()}
    for field in s["fields"][kind]:
        item[field] = form.get(field, "").strip()
        if field in s["percent_fields"] and item[field]:
            item[field] = percent_to_fraction(item[field])
        if field in ("taxable", "keepPayment", "alsoWhenRenting"):
            item[field] = item[field] == "yes"
        if field == "earnedIncome":
            if item[field]:
                item[field] = item[field] == "yes"
            else:
                del item[field]
        if field == "on" and item[field] != "end":
            del item[field]
        if field in s["person_fields"] and not item[field]:
            del item[field]
    if "covers" in item:
        item["payOff"] = item.pop("covers") == "all"
        if item["payOff"]:
            item["amount"] = ""
    return item


def form_values(item, scenario=None):
    """An item's values as its form shows them (ADR-0070 amendment, editing): rates as
    percentages, yes / no for flags, "covers" from payOff; for web.js to fill the form."""
    s = schema(scenario)
    kind = item.get("type")
    values = {"name": item.get("name") or ""}
    for field in s["fields"].get(kind, []):
        value = item.get(field)
        if field in ("taxable", "keepPayment", "alsoWhenRenting"):
            default = kind == "pension" if field == "taxable" else False
            values[field] = "yes" if (default if value is None else value) else "no"
        elif field == "earnedIncome":
            values[field] = "" if value is None else ("yes" if value else "no")
        elif field == "covers":
            values[field] = "all" if item.get("payOff") else "amount"
        elif field == "on":
            values[field] = value or "start"
        elif field in s["percent_fields"] and value not in (None, ""):
            try:
                values[field] = f"{(Decimal(str(value)) * 100).normalize():f}"
            except Exception:
                values[field] = str(value)
        elif field == "amountIn":
            values[field] = value or "start"
        else:
            values[field] = "" if value is None else str(value)
    return values


@web.post("/items/<item_id>/update")
def update_item(item_id):
    """An edit form: its text to JSON values; fields left blank go back to their
    defaults (cleared)."""
    scenario, messages = posted_scenario()
    kind = request.form.get("type")
    fields = schema(scenario)["fields"]
    if kind not in fields:
        return builder_page(scenario, messages + [f"unknown item type {kind!r}"],
                            refused=True)
    values = form_item(kind, request.form, scenario)
    clear = [f for f in fields[kind] if f not in values]
    if "covers" in fields[kind] and not values.get("payOff"):
        clear.append("payOff")
    return command("/items/update", {"scenario": scenario, "id": item_id, "item": values,
                                      "clear": clear}, messages)


@web.post("/items/<item_id>/toggle")
def toggle_item(item_id):
    scenario, messages = posted_scenario()
    return command("/items/toggle", {"scenario": scenario, "id": item_id}, messages)


@web.post("/items/<item_id>/delete")
def delete_item(item_id):
    scenario, messages = posted_scenario()
    return command("/items/delete", {"scenario": scenario, "id": item_id}, messages)


# ---------------------------------------------------------------- load / compare
def _uploaded(upload):
    """The JSON of an uploaded file, or raise ValueError with a readable message."""
    try:
        return json.loads(upload.read().decode("utf-8"))
    except ValueError as e:     # json.JSONDecodeError and UnicodeDecodeError
        raise ValueError(f"{upload.filename}: {e}") from e


@web.route("/load", methods=["GET", "POST"])
def load():
    if request.method == "GET":
        return shell()
    scenario, messages = posted_scenario()
    if request.form.get("action") != "load":
        return page("load.html", scenario, messages)
    upload = request.files.get("file")
    if not upload or not upload.filename:
        return page("load.html", scenario, ["load: no file chosen"])
    try:
        answer = client.call("/load", {"data": _uploaded(upload)})
    except ValueError as e:
        return page("load.html", scenario, [f"load: {e}"])
    if not answer["ok"]:
        return page("load.html", scenario, [f"load: {upload.filename}: {answer['messages'][0]}"])
    return builder_page(answer["scenario"], view="cards")


@web.route("/new", methods=["GET", "POST"])
def new():
    """A new, empty scenario for the jurisdiction chosen (ADR-0071)."""
    if request.method == "GET":
        return shell()
    first = not request.form.get("scenario", "").strip()
    scenario, messages = posted_scenario()
    listed = schema(scenario)["jurisdictions"]
    if request.form.get("action") != "new":
        return page("new.html", None if first else scenario, messages, jurisdictions=listed, first=first)
    code = request.form.get("jurisdiction") or ""
    if code not in {j["code"] for j in listed}:
        return page("new.html", None if first else scenario, [f"unknown jurisdiction {code!r}"],
                    jurisdictions=listed, first=first)
    return builder_page(client.get("/new?jurisdiction=" + code)["scenario"], view="cards")


@web.route("/compare", methods=["GET", "POST"])
def compare():
    """Run two uploaded scenarios side by side; the current scenario is not changed."""
    if request.method == "GET":
        return shell()
    scenario, messages = posted_scenario()
    if request.form.get("action") != "compare":
        return page("compare.html", scenario, messages)
    loaded = []
    for slot in ("a", "b"):
        upload = request.files.get(slot)
        error = None
        if not upload or not upload.filename:
            error = "no file chosen"
        else:
            try:
                answer = client.call("/load", {"data": _uploaded(upload)})
                if answer["ok"]:
                    loaded.append(answer["scenario"])
                else:
                    error = f"{upload.filename}: {answer['messages'][0]}"
            except ValueError as e:
                error = str(e)
        if error:
            return page("compare.html", scenario, error=f"scenario {slot.upper()}: {error}")
    a, b = loaded
    answer = client.call("/compare", {"a": a, "b": b})
    if not answer["ok"]:
        return page("compare.html", scenario, error=answer["messages"][0])
    return page("compare.html", scenario, a=a, b=b, rows=list(zip(answer["a"], answer["b"])),
                summaries=answer["summaries"])


# ---------------------------------------------------------------- run views
NO_SUMMARY = {"dollarsOf": "", "retirement": "", "retirements": []}


def _run(scenario):
    answer = client.call("/run", {"scenario": scenario})
    return answer, (None if answer["ok"] else answer["messages"][0])


@web.route("/run", methods=["GET", "POST"])
def run():
    if request.method == "GET":
        return shell()
    scenario, messages = posted_scenario()
    answer, error = _run(scenario)
    rows = [] if error else answer["result"]["rows"]
    return page("run.html", scenario, messages, rows=rows, error=error,
                summary=answer.get("summary", NO_SUMMARY))


@web.route("/run/holdings", methods=["GET", "POST"])
def run_holdings():
    """Per-holding detail (ADR-0053): one holding's balances month by month."""
    if request.method == "GET":
        return shell()
    scenario, messages = posted_scenario()
    answer, error = _run(scenario)
    if error:
        return page("run.html", scenario, messages, rows=[], error=error, summary=NO_SUMMARY)
    holdings = [h for h in answer["result"]["holdings"] if h["points"]]
    chosen = next((h for h in holdings if h["id"] == request.args.get("id")),
                  next((h for h in holdings if h["kind"] != "cash"), holdings[0]))
    return page("holdings.html", scenario, messages, holdings=holdings, chosen=chosen)


@web.route("/run/break-even", methods=["GET", "POST"])
def run_break_even():
    """A property's break-even and rent equivalent per month (ADR-0073)."""
    if request.method == "GET":
        return shell()
    scenario, messages = posted_scenario()
    answer = client.call("/view/break-even", {"scenario": scenario,
                                              "property": request.args.get("property")})
    if not answer.get("ok"):
        return page("break_even.html", scenario, messages, properties=[], view=None,
                    error=answer["messages"][0])
    view = answer.get("view")
    return page("break_even.html", scenario, messages, properties=answer["properties"],
                view=view, error=None)


@web.route("/run/vehicle-cost", methods=["GET", "POST"])
def run_vehicle_cost():
    """A vehicle's cost of ownership per month (ADR-0074)."""
    if request.method == "GET":
        return shell()
    scenario, messages = posted_scenario()
    answer = client.call("/view/vehicle-cost", {"scenario": scenario,
                                                "vehicle": request.args.get("vehicle")})
    if not answer.get("ok"):
        return page("vehicle_cost.html", scenario, messages, vehicles=[], view=None,
                    error=answer["messages"][0])
    return page("vehicle_cost.html", scenario, messages, vehicles=answer["vehicles"],
                view=answer.get("view"), error=None)


@web.route("/run/ledger", methods=["GET", "POST"])
def run_ledger():
    """Every movement of one month (ADR-0053)."""
    if request.method == "GET":
        return shell()
    scenario, messages = posted_scenario()
    answer = client.call("/view/ledger", {"scenario": scenario,
                                          "month": request.args.get("month")})
    if not answer["ok"]:
        return page("run.html", scenario, messages, rows=[], error=answer["messages"][0],
                    summary=NO_SUMMARY)
    month = {k: v for k, v in answer.items() if k not in ("ok", "messages", "schemaVersion")}
    month["balances"] = [(b["holding"], b["point"]) for b in month["balances"]]
    if month["events"] is not None:
        month["events"] = [dict(e, movements=[(m["index"], m["movement"])
                                              for m in e["movements"]])
                           for e in month["events"]]
    return page("ledger.html", scenario, messages, **month)


@web.route("/timeline", methods=["GET", "POST"])
def timeline_page():
    """The scenario over time (ADR-0066): ``view=graph`` (default) or ``view=axis``;
    ``order=newest`` puts the latest month on top of the graph."""
    if request.method == "GET":
        return shell()
    scenario, messages = posted_scenario()
    view = "axis" if request.args.get("view") == "axis" else "graph"
    newest = request.args.get("order") == "newest"
    answer = client.call("/timeline", {"scenario": scenario})
    picture, error = None, None
    if answer["ok"]:
        model = {k: v for k, v in answer.items() if k not in ("ok", "messages", "schemaVersion")}
        # JSON object keys are strings; the drawing looks lanes up by id (None: trunk).
        picture = Markup(timeline_draw.svg(model) if view == "axis"
                         else timeline_draw.graph(model, newest_first=newest))
    else:
        error = answer["messages"][0]
    return page("timeline.html", scenario, messages, picture=picture, error=error,
                view=view, newest=newest)


# ---------------------------------------------------------------- documentation
DOCS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "static", "docs")


@web.route("/docs/dev", methods=["GET", "POST"])
def docs_dev():
    """The developer documentation's first page."""
    return docs(area="dev")


@web.route("/docs", methods=["GET", "POST"])
@web.route("/docs/<slug>", methods=["GET", "POST"])
def docs(slug=None, area="user"):
    """The Help tab: the user guide (docs/user) at /docs; the developer documentation
    (planning docs, ADRs, specs, diagrams) at /docs/dev, out of the way (owner's request
    2026-11-18). Pre-compiled by build_docs.py. Not scenario pages: GET and POST give the
    same page."""
    try:
        with open(os.path.join(DOCS_DIR, "index.json")) as f:
            index = json.load(f)
    except FileNotFoundError:
        return render_template("docs.html", sections=[], page=None, area=area, messages=[],
                               body=Markup("<p>Documentation is not compiled: run "
                                           "<code>webapp/build_docs.py</code>.</p>"))
    pages = {a: {p["slug"]: p for s in index[a] for p in s["pages"]} for a in index}
    if slug is not None:
        area = next((a for a in pages if slug in pages[a]), None)
        if area is None:
            abort(404)
    elif pages[area]:
        slug = next(iter(pages[area]))
    else:
        abort(404)
    with open(os.path.join(DOCS_DIR, "pages", slug + ".html")) as f:
        body = Markup(f.read())
    return render_template("docs.html", sections=index[area], page=pages[area][slug],
                           area=area, body=body, messages=[])
