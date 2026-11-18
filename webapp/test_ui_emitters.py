"""UI for the event-emitter model (phase E6): the events view on the ledger page (D-E4)
and modifiers grouped under their host in the builder (D-E1).

    cd webapp && .venv/bin/python -m unittest -q test_ui_emitters

app.py runs the event-emitter engine (PoC iteration 2). The page without an event log
is checked by stripping ``events`` from the engine's result.
"""
import copy
from decimal import Decimal
import html
import json
import re
import unittest
from pathlib import Path
from unittest import mock

import app
from browser import Browser
from state_machine import ops
from state_machine.cards import LINK, cards
from state_machine import engine

HERE = Path(__file__).resolve().parent
SAMPLE = json.loads((HERE / "samples" / "household-baseline.json").read_text())
MONTH = "2020-01"


def client_with(scenario):
    client = Browser()
    client.get("/")
    client.scenario = copy.deepcopy(scenario)
    return client


def section(page, start, end):
    i = page.index(start)
    return page[i:page.index(end, i)]


def fake_events(result, month):
    """The engine's result with a hand-made event log for one month: a sale with a
    follow-up payoff (D-E3), a flow event, and a state event; ranges tile the ledger."""
    n = [i for i, x in enumerate(result["ledger"]) if x["month"] == month]
    a, b = n[0], n[-1] + 1
    rec = lambda **kw: dict({"month": month, "emitter": "E", "detail": "", "cause": None,
                             "source": None}, **kw)
    events = [rec(month="2019-08", key=(100, 0, 0), event="Earlier", kind="flow",
                  ledger=(0, 0)),
              rec(key=(100, 9, 0), event="IncomeFlow", kind="flow", source="job-b",
                  ledger=(a, a + 1)),
              rec(key=(500, 0, 0), event="Sale", emitter="SaleEmitter", kind="lifecycle",
                  source="maple-house", ledger=(a + 1, a + 1), detail="sold at value"),
              rec(key=(500, 0, 0), event="Payoff", kind="lifecycle",
                  source="maple-mtg", cause=2, ledger=(a + 1, a + 2)),
              rec(key=(1500, -1, 0), event="TaxStep", kind="state", ledger=(a + 2, b))]
    return dict(result, events=events)


class AppUsesTheEventEmitterEngine(unittest.TestCase):
    def test_default_engine_and_events_table(self):
        import state_machine.engine
        self.assertIs(app.engine, state_machine.engine)
        page = client_with(SAMPLE).get(f"/run/ledger?month={MONTH}").data.decode()
        self.assertIn("Events this month", page)


class LedgerPageWithoutEventLog(unittest.TestCase):
    def test_ledger_page_without_events(self):
        real = engine.run_detailed
        without = lambda s: {k: v for k, v in real(s).items() if k != "events"}  # noqa: E731
        client = client_with(SAMPLE)
        with mock.patch.object(app.engine, "run_detailed", without):
            page = client.get(f"/run/ledger?month={MONTH}").data.decode()
        self.assertNotIn("Events this month", page)
        self.assertNotIn('id="m', page)
        self.assertIn("<tr><th>Kind</th><th>From</th>", page)


class EventsViewWithFakeLog(unittest.TestCase):
    def page(self, query=""):
        real = engine.run_detailed
        with mock.patch.object(app.engine, "run_detailed",
                               lambda s: fake_events(real(s), MONTH)):
            return client_with(SAMPLE).get(f"/run/ledger?month={MONTH}{query}").data.decode()

    def test_table_rows_follow_ups_and_movement_links(self):
        page = self.page()
        # The events table is the last section of the page.
        self.assertLess(page.index("<h2>Tax step"), page.index("<h2>Events this month</h2>"))
        events = section(page, "<h2>Events this month</h2>", "</body>")
        # Only this month's events, in log order.
        self.assertEqual(re.findall(r'<tr id="e(\d+)">', events), ["1", "2", "3", "4"])
        self.assertIn("<td>state</td>", section(events, '<tr id="e4">', "</tr>"))
        self.assertIn("<td>500.0.0</td>", events)                       # order key
        self.assertIn("Sale: sold at value <span", events)              # event and detail
        self.assertIn("(SaleEmitter)", events)                          # emitter if different
        # The follow-up is indented and points at its cause.
        payoff = section(events, '<tr id="e3">', "</tr>")
        self.assertIn("padding-left: 2.0rem", payoff)
        self.assertIn('follow-up of <a href="#e2">#2</a>', payoff)
        self.assertIn("&#8627;", payoff)
        self.assertNotIn("&#8627;", section(events, '<tr id="e2">', "</tr>"))
        # Caused by: the item's name.
        self.assertIn("<td>Maple Street house</td>", section(events, '<tr id="e2">', "</tr>"))
        # Movement links resolve to anchored rows of the Movements table.
        links = re.findall(r'<a href="#m(\d+)">', events)
        self.assertTrue(links)
        movements = page[page.index("<h2>Movements</h2>"):]
        for i in links:
            self.assertIn(f'<tr id="m{i}">', movements)
        self.assertIn("<td>-</td>", section(events, '<tr id="e2">', "</tr>"))  # no movements


class EventsViewWithRealLog(unittest.TestCase):
    """The ledger page with the engine's own event log (no fakes)."""

    def test_events_table_with_new_engine(self):
        scenario = copy.deepcopy(SAMPLE)
        log = engine.run_detailed(copy.deepcopy(scenario))["events"]
        page = client_with(scenario).get(f"/run/ledger?month={MONTH}").data.decode()
        self.assertIn("Events this month", page)
        self.assertEqual(len(re.findall(r'<tr id="e\d+">', page)),
                         len([e for e in log if e["month"] == MONTH]))
        self.assertLessEqual({e["kind"] for e in log}, {"lifecycle", "flow", "valuation", "state"})
        # Every movement link points at an anchored movement row on the page, and every
        # movement of the month is produced by one of its events (ranges tile the ledger).
        anchors = sorted(re.findall(r'<tr id="(m\d+)">', page))
        self.assertTrue(anchors)
        self.assertEqual(sorted(set(re.findall(r'<a href="#(m\d+)">', page))), anchors)


class BuilderCards(unittest.TestCase):
    """ADR-0070: the builder as cards by person and category; linked items under their
    card; adding in context."""

    def layout(self, scenario):
        return cards(scenario)

    def test_every_item_is_listed_under_its_host(self):
        layout = self.layout(SAMPLE)
        page = client_with(SAMPLE).get("/").data.decode()
        shown, linked_to = set(), {}
        for section in layout["sections"]:
            heads = [section["head"]] + [c for cat in section["categories"] for c in cat["cards"]]
            for card in heads:
                shown.add(card["id"])
                parents = [card["id"]]
                for row in card["rows"]:
                    shown.add(row["id"])
                    parents = parents[:row["depth"]] + [row["id"]]
                    linked_to.setdefault(row["id"], set()).add(parents[row["depth"] - 1])
        ids = {i["id"] for i in SAMPLE["items"] if i["type"] != "person"}
        self.assertEqual(ids - shown, set())
        # A linked item sits under the item its link field names (triggers: target or event).
        by_id = {i["id"]: i for i in SAMPLE["items"]}
        for iid, parents in linked_to.items():
            item = by_id.get(iid)
            if item is None or item["type"] in ("retirement", "contributionRoom", "cashBalance"):
                continue
            refs = {item.get(f) for f in ("target", "event")} if item["type"] == "trigger" \
                else {item.get(LINK.get(item["type"], ""))}
            self.assertTrue(parents <= refs, (iid, parents, refs))
        for iid in shown:
            self.assertIn(f'id="item-{iid}"', page)

    def test_cards_in_order_of_their_start(self):
        from state_machine import views
        starts = views.starts(SAMPLE)
        for section in self.layout(SAMPLE)["sections"]:
            for cat in section["categories"]:
                order = [starts.get(c["id"]) or "9999-99" for c in cat["cards"]]
                self.assertEqual(order, sorted(order), cat["title"])

    def test_orphan_modifier_in_other_and_file_order_kept(self):
        s = copy.deepcopy(SAMPLE)
        s["items"].append({"type": "renewal", "id": "orphan", "name": "Orphan renewal",
                           "mortgage": "gone", "startDate": "2030-01-01", "annualRate": "0.04"})
        household = self.layout(s)["sections"][-1]
        other = next(c for c in household["categories"] if c["key"] == "other")
        self.assertEqual([c["id"] for c in other["cards"]], ["orphan"])
        client = client_with(s)
        client.get("/")
        self.assertEqual([i["id"] for i in client.scenario["items"]],
                         [i["id"] for i in s["items"]])

    def test_adding_in_context(self):
        s = copy.deepcopy(SAMPLE)
        page = client_with(s).get("/").data.decode()
        # One form per item type, copied into place by web.js.
        self.assertEqual(sorted(re.findall(r'<template id="form-(\w+)">', page)),
                         sorted(app.FIELDS))
        # A card offers the types that link to it, with the link filled in.
        house = next(i for i in s["items"] if i["type"] == "property")
        card = page[page.index(f'id="item-{house["id"]}"'):]
        card = card[:card.index("</details>")]
        buttons = dict(re.findall(r'data-kind="(\w+)" data-fixed="([^"]*)"', card))
        self.assertIn("sale", buttons)
        self.assertIn(f'&#34;property&#34;: &#34;{house["id"]}&#34;', buttons["sale"])
        self.assertIn(f'&#34;parent&#34;: &#34;{house["id"]}&#34;', buttons["associatedExpense"])
        # The associated income form only offers incomes and pensions as parents.
        form = page[page.index('<template id="form-associatedIncome">'):]
        form = form[:form.index("</template>")]
        parents = re.findall(r'<option value="[^"]*">[^<]*\((\w+)\)</option>',
                             re.search(r'name="parent">(.*?)</select>', form).group(1))
        self.assertTrue(parents)
        self.assertTrue(set(parents) <= {"income", "pension"}, parents)

    def test_both_views_list_every_item_with_the_same_figure_and_controls(self):
        """The flat view and the cards use the same data and building blocks (ADR-0070
        amendment): every item shows in both, with the same figure, switch and delete."""
        def per_item(page):
            found = {}
            for iid in {i["id"] for i in SAMPLE["items"] if i["type"] != "person"}:
                start = page.find(f'id="item-{iid}"')
                self.assertNotEqual(start, -1, iid)
                chunk = page[start:]
                switch = f'action="/items/{iid}/toggle"' in chunk[:6000]
                delete = f'action="/items/{iid}/delete"' in chunk[:8000]
                switch = switch and f'data-edit="{iid}"' in chunk[:8000]
                found[iid] = (switch, delete)
            return found
        cards = client_with(SAMPLE).get("/").data.decode()
        flat = client_with(SAMPLE).get("/flat").data.decode()
        self.assertIn("Scenario builder (flat)", flat)
        self.assertEqual(per_item(cards), per_item(flat))
        self.assertTrue(all(all(v) for v in per_item(flat).values()))
        # The same figure for every item: the flat row's figure is the item's own estimate.
        layout = self.layout(SAMPLE)
        for iid, estimate in layout["estimates"].items():
            row = flat[flat.index(f'<tr id="item-{iid}"'):]
            row = row[:row.index("</tr>")]
            if estimate["monthly"] is not None:
                self.assertIn(f'{estimate["monthly"]:,.2f}/mo', row, iid)

    def test_flat_add_bar_grouped_by_category(self):
        import schema
        page = client_with(SAMPLE).get("/flat").data.decode()
        bar = page[page.index('<fieldset class="add-groups">'):]
        bar = bar[:bar.index("</fieldset>")]
        groups = re.findall(r'<span class="muted">([^<]+):</span>(.*?)</p>', bar, re.S)
        shown = {html.unescape(title): re.findall(r'data-kind="(\w+)"', buttons)
                 for title, buttons in groups}
        self.assertEqual(list(shown), [t for t, _ in schema.ADD_GROUPS])
        self.assertEqual(shown["Income & pensions"][:2], ["income", "pension"])
        self.assertIn("renewal", shown["Properties & mortgages"])     # SAMPLE has a mortgage

    def test_a_refused_form_marks_the_page_for_reopening(self):
        """A refused add or edit renders <main data-refused>: web.js reopens the form
        with what was typed (nothing is lost). A command that succeeds does not."""
        s = copy.deepcopy(SAMPLE)
        house = next(i for i in s["items"] if i["type"] == "property")
        client = client_with(s)
        page = client.post("/items/add", data={"type": "property", "name": "Bad",
                                                "price": "abc"}).data.decode()
        self.assertIn("<main data-refused", page)
        self.assertEqual(client.scenario, s)
        page = client.post(f'/items/{house["id"]}/update',
                           data={"type": "property", "name": "X",
                                 "purchaseDate": "nope"}).data.decode()
        self.assertIn("<main data-refused", page)
        page = client.post(f'/items/{house["id"]}/toggle').data.decode()
        self.assertNotIn("data-refused", page)

    def test_the_builder_shows_why_its_view_failed(self):
        """A scenario the builder view cannot read (a property sold twice) still renders
        the page, with the reason, instead of a server error."""
        s = copy.deepcopy(SAMPLE)
        house = next(i for i in s["items"] if i["type"] == "property")
        s["items"] += [{"type": "sale", "id": f"sell{n}", "property": house["id"],
                        "saleDate": f"20{40 + n}-01-01"} for n in (1, 2)]
        for path in ("/", "/flat"):
            page = client_with(s).get(path)
            self.assertEqual(page.status_code, 200)
            self.assertIn(b"sold more than once", page.data)

    def test_editing_an_item_from_its_form(self):
        """ADR-0070 amendment: the pencil fills the item's form with its values (rates as
        percentages); saving replaces its fields and keeps its id and links."""
        s = copy.deepcopy(SAMPLE)
        house = next(i for i in s["items"] if i["type"] == "property")
        page = client_with(s).get("/").data.decode()
        button = re.search(r'data-edit="%s" data-kind="property" data-values="([^"]*)"'
                           % house["id"], page)
        values = json.loads(html.unescape(button.group(1)))
        self.assertEqual(values["name"], house["name"])
        rate = house.get("annualAppreciation")
        self.assertEqual(values["annualAppreciation"],
                         f"{(Decimal(rate) * 100).normalize():f}" if rate else "")
        client = client_with(s)
        form = dict(values, type="property", name="Renamed", price="123456")
        for view in ("cards", "flat"):
            page = client.post(f'/items/{house["id"]}/update', data=form,
                               headers={"X-Builder-View": view}).data.decode()
            item = next(i for i in client.scenario["items"] if i["id"] == house["id"])
            self.assertEqual((item["name"], item["price"]), ("Renamed", "123456"))
            self.assertEqual(Decimal(item["annualAppreciation"] or 0), Decimal(rate or 0))
            self.assertIn("(flat)" if view == "flat" else "<h1>Scenario builder</h1>", page)
        # The item's fields keep their order (no sorting on the way through the API).
        self.assertEqual(list(item)[:3], list(house)[:3])
        # Links kept: whatever named the house still does.
        linked = [i for i in client.scenario["items"] if house["id"] in
                  (i.get("property"), i.get("parent"), i.get("target"), i.get("event"))]
        self.assertTrue(linked)

    def test_actions_return_to_the_view_they_came_from(self):
        client = client_with(SAMPLE)
        iid = SAMPLE["items"][0]["id"]
        page = client.post(f"/items/{iid}/toggle", headers={"X-Builder-View": "flat"})
        self.assertIn("Scenario builder (flat)", page.data.decode())
        page = client.post(f"/items/{iid}/toggle")
        self.assertIn("<h1>Scenario builder</h1>", page.data.decode())

    def test_categories_have_the_add_icon(self):
        page = client_with(SAMPLE).get("/").data.decode()
        for match in re.finditer(r'<details class="category"[^>]*>\s*<summary>(.*?)</summary>',
                                 page, re.S):
            self.assertIn('class="icon add" data-open-add', match.group(1))

    def test_empty_scenario(self):
        page = client_with(ops.empty_scenario()).get("/").data.decode()
        self.assertIn("<h2>You", page)
        self.assertIn("<h2>Household", page)
        self.assertIn("None yet.", page)
        self.assertIn('data-kind="income"', page)
        self.assertNotIn('data-kind="renewal"', page)          # no mortgage to renew



class UnitedStatesInTheApp(unittest.TestCase):
    """ADR-0071: a US scenario shows only US account types and items, and its limit
    columns; adding a limit and an account through the forms works."""

    def scenario(self):
        return {"schemaVersion": 1, "name": "us", "jurisdiction": "US",
                "horizon": {"start": "2027-01-01", "end": "2027-12-01"},
                "openingCash": "100000", "effectiveTaxRate": "0.25",
                "items": [{"type": "person", "id": "pat", "name": "Pat",
                           "birthDate": "1975-06-01"}]}

    def test_builder_forms_and_run(self):
        client = client_with(self.scenario())
        page = client.get("/").data.decode()
        self.assertIn('value="traditional401k"', page)
        self.assertNotIn('value="rrsp"', page)
        self.assertIn('id="form-contributionLimit"', page)
        self.assertNotIn('id="form-contributionRoom"', page)
        client.post("/items/add", data={"type": "account", "name": "My 401k",
                                         "accountType": "traditional401k", "annualReturn": "0",
                                         "owner": "pat"})
        acc = client.scenario["items"][-1]
        client.post("/items/add", data={"type": "contribution", "account": acc["id"],
                                         "startDate": "2027-01-01", "amount": "3000",
                                         "per": "month", "indexing": "none"})
        client.post("/items/add", data={"type": "contributionLimit", "limitType": "401k",
                                         "yearlyLimit": "23500", "catchUp": "7500",
                                         "indexing": "none", "owner": "pat"})
        self.assertEqual([i["type"] for i in client.scenario["items"]],
                         ["person", "account", "contribution", "contributionLimit"])
        run = client.get("/run").data.decode()
        self.assertIn("401(k) limit left this year", run)
        ledger = client.get("/run/ledger").data.decode()
        self.assertIn("traditional 401(k) and IRA, HSA", ledger)


class ChoosingTheJurisdiction(unittest.TestCase):
    """ADR-0071 decision 5: the New page and the settings dropdown."""

    def test_new_page_starts_an_empty_scenario_for_the_choice(self):
        client = client_with(copy.deepcopy(SAMPLE))
        page = client.get("/new").data.decode()
        self.assertIn('value="CA"', page)
        self.assertIn('value="US"', page)
        self.assertIn("data-confirm-unsaved", page)
        page = client.post("/new", data={"jurisdiction": "US"}).data.decode()
        self.assertEqual((client.scenario["jurisdiction"], client.scenario["items"]), ("US", []))
        self.assertIn('data-jurisdiction="United States"', page)   # nav, via web.js
        self.assertIn('<option value="US" selected>United States</option>', page)

    def test_settings_switch_is_guarded(self):
        s = copy.deepcopy(SAMPLE)
        s["items"].append({"type": "account", "id": "my-rrsp", "name": "My RRSP",
                           "accountType": "rrsp", "annualReturn": "0"})
        client = client_with(s)
        settings = {"name": "x", "start": SAMPLE["horizon"]["start"],
                    "end": SAMPLE["horizon"]["end"], "openingCash": "0",
                    "jurisdiction": "US"}
        page = client.post("/settings", data=settings).data.decode()
        self.assertIn("cannot change the jurisdiction to United States", page)
        self.assertIn("My RRSP (rrsp account)", page)
        self.assertIn("<main data-refused", page)
        self.assertNotEqual(client.scenario.get("jurisdiction"), "US")
        empty = client_with(ops.empty_scenario())
        empty.post("/settings", data=dict(settings, start="2027-01-01", end="2051-12-01"))
        self.assertEqual(empty.scenario["jurisdiction"], "US")


class RespInTheApp(unittest.TestCase):
    """ADR-0072: the RESP's fields are on Canada's account form, not the US one."""

    def test_add_an_resp_with_its_grant_history(self):
        client = client_with(ops.empty_scenario())
        page = client.get("/").data.decode()
        self.assertIn('value="resp"', page)
        self.assertIn('name="grantReceived"', page)
        client.post("/items/add", data={"type": "account", "name": "Kid's RESP",
                                         "accountType": "resp", "annualReturn": "4",
                                         "grantReceived": "1800", "unusedGrantRoom": "500"})
        item = client.scenario["items"][-1]
        self.assertEqual((item["accountType"], item["grantReceived"], item["annualReturn"]),
                         ("resp", "1800", "0.04"))
        us = client_with(ops.empty_scenario("US")).get("/").data.decode()
        self.assertNotIn('name="grantReceived"', us)


class BreakEvenInTheApp(unittest.TestCase):
    """ADR-0073: the Break-even page, the link from a property card, the new form fields."""

    def scenario(self):
        return {"schemaVersion": 1, "name": "be", "jurisdiction": "CA",
                "horizon": {"start": "2027-01-01", "end": "2040-12-01"},
                "openingCash": "200000", "effectiveTaxRate": "0.3",
                "items": [{"type": "property", "id": "h", "name": "House",
                           "purchaseDate": "2027-01-01", "price": "500000",
                           "annualAppreciation": "0.04"},
                          {"type": "associatedCost", "id": "sell", "parent": "h", "at": "end",
                           "rate": "0.05", "basis": "value"}]}

    def test_page_card_link_and_forms(self):
        client = client_with(self.scenario())
        for view in ("/", "/flat"):          # the chart icon on the card / row
            page = client.get(view).data.decode()
            self.assertIn('class="icon chart" href="/run/break-even?property=h"', page)
        page = client.get("/run/break-even?property=h").data.decode()
        self.assertIn("Breaks even from", page)
        self.assertIn("Net proceeds", page)                          # the table, no chart
        for title in ("Owned (mo)", "Sale costs", "Loan balance", "Invested (owner)",
                      "Gain (all)", "Rent eq. (owner)"):
            self.assertIn(f">{title}</th>", page)
        client.post("/items/add", data={"type": "mortgage", "name": "Loan", "property": "h",
                                         "principal": "400000", "annualRate": "5",
                                         "amortizationYears": "25", "termMonths": "60",
                                         "penaltyMethod": "interestLeft", "penaltyRate": "100"})
        loan = client.scenario["items"][-1]
        self.assertEqual((loan["termMonths"], loan["penaltyMethod"], loan["penaltyRate"]),
                         ("60", "interestLeft", "1"))
        client.post("/items/add", data={"type": "associatedExpense", "parent": "h",
                                         "name": "Utilities", "amount": "250", "per": "month",
                                         "indexing": "none", "alsoWhenRenting": "yes"})
        self.assertIs(client.scenario["items"][-1]["alsoWhenRenting"], True)
        page = client.get("/run/break-even?property=h").data.decode()
        self.assertNotIn("No early-closure penalty", page)

    def test_api(self):
        r = app.app.test_client().post("/api/view/break-even",
                                       json={"scenario": self.scenario()}).get_json()
        self.assertTrue(r["ok"])
        self.assertEqual(r["properties"], [{"id": "h", "name": "House"}])
        self.assertEqual(r["view"]["rows"][0]["sellingCosts"], "25000.00")
        bad = app.app.test_client().post("/api/view/break-even",
                                         json={"scenario": self.scenario(), "property": "x"})
        self.assertFalse(bad.get_json()["ok"])


class VehicleCostInTheApp(unittest.TestCase):
    """ADR-0074: the cost-of-ownership page, opened by the chart icon of a vehicle."""

    def test_icon_page_and_api(self):
        s = {"schemaVersion": 1, "name": "car", "jurisdiction": "CA",
             "horizon": {"start": "2027-01-01", "end": "2030-12-01"},
             "openingCash": "100000", "effectiveTaxRate": "0.3",
             "items": [{"type": "vehicle", "id": "car", "name": "Car",
                        "purchaseDate": "2027-01-01", "price": "40000",
                        "annualDepreciation": "0.15"},
                       {"type": "associatedExpense", "id": "fuel", "parent": "car",
                        "amount": "200", "per": "month"}]}
        client = client_with(s)
        for view in ("/", "/flat"):
            self.assertIn('class="icon chart" href="/run/vehicle-cost?vehicle=car"',
                          client.get(view).data.decode())
        page = client.get("/run/vehicle-cost?vehicle=car").data.decode()
        for title in ("Owned (mo)", "Paid so far", "Cost/mo"):
            self.assertIn(f">{title}</th>", page)
        r = app.app.test_client().post("/api/view/vehicle-cost", json={"scenario": s}).get_json()
        self.assertEqual(r["view"]["rows"][0]["costPerMonth"], "200.00")


class ExpenseCardCosts(unittest.TestCase):
    def test_an_expense_card_adds_associated_costs(self):
        """A one-off cost at an expense's start, end or a date (e.g. a lease's fees) can be
        added on the expense's card, as on an income's."""
        s = {"schemaVersion": 1, "name": "lease", "jurisdiction": "CA",
             "horizon": {"start": "2027-01-01", "end": "2030-12-01"}, "openingCash": "50000",
             "items": [{"type": "expense", "id": "lease", "name": "Lease",
                        "startDate": "2027-01-01", "endDate": "2030-12-01", "amount": "650",
                        "per": "month", "indexing": "none"}]}
        client = client_with(s)
        card = section(client.get("/").data.decode(), 'id="item-lease"', "</details>")
        self.assertIn('data-kind="associatedCost"', card)
        client.post("/items/add", data={"type": "associatedCost", "parent": "lease",
                                         "name": "Disposition fee", "at": "end",
                                         "amount": "400"})
        self.assertEqual(client.scenario["items"][-1]["parent"], "lease")
        ledger = engine.run_detailed(client.scenario)["ledger"]
        self.assertIn(("2030-12", "COST"), {(x["month"], x["kind"]) for x in ledger})


if __name__ == "__main__":
    unittest.main()
