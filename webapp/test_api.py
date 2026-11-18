"""The JSON API (ADR-0069): state in, state out; nothing kept between requests.

    cd webapp && .venv/bin/python -m unittest test_api
"""
import gzip
import json
import unittest

import app


def scenario(*items):
    return {"schemaVersion": 1, "name": "api", "jurisdiction": "CA",
            "horizon": {"start": "2027-01-01", "end": "2028-12-01"},
            "openingCash": "1000", "effectiveTaxRate": "0.3",
            "items": [{"type": "income", "id": "job", "name": "Job", "startDate": "2027-01-01",
                       "amount": "6000", "per": "month", "taxable": True}, *items]}


HOUSE = {"type": "property", "id": "h", "name": "House", "purchaseDate": "2028-01-01",
         "price": "100000", "annualAppreciation": "0"}


class Api(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()

    def post(self, url, payload, status=200):
        r = self.client.post(url, json=payload)
        self.assertEqual(r.status_code, status, r.data[:300])
        data = r.get_json()
        self.assertEqual(data["schemaVersion"], 1)
        return data

    def test_no_server_state(self):
        s = scenario()
        self.post("/api/items/add", {"scenario": s, "item": HOUSE})
        self.post("/api/run", {"scenario": s})
        page = self.client.post("/", data={"scenario": json.dumps(s)})
        self.assertFalse(hasattr(app, "SCENARIOS"))
        self.assertNotIn("Set-Cookie", page.headers)     # no session cookie either
        self.assertIsNone(app.app.secret_key)

    def test_commands_return_the_new_state(self):
        s = scenario()
        added = self.post("/api/items/add", {"scenario": s, "item": HOUSE})
        self.assertTrue(added["ok"])
        self.assertEqual([i["id"] for i in added["scenario"]["items"]], ["job", "h"])
        off = self.post("/api/items/toggle", {"scenario": added["scenario"], "id": "h"})
        self.assertIs(off["scenario"]["items"][1]["enabled"], False)
        edited = self.post("/api/items/update", {"scenario": off["scenario"], "id": "h",
                                                  "item": {"name": "Home"}, "clear": []})
        self.assertEqual(edited["scenario"]["items"][1]["name"], "Home")
        gone = self.post("/api/items/delete", {"scenario": off["scenario"], "id": "h"})
        self.assertEqual(gone["scenario"], s)
        changed = self.post("/api/settings", {"scenario": s, "settings": {
            "name": "Renamed", "horizon": s["horizon"], "openingCash": "5"}})
        self.assertEqual((changed["scenario"]["name"], changed["scenario"]["openingCash"]),
                         ("Renamed", "5"))

    def test_refusals_are_data(self):
        s = scenario()
        r = self.post("/api/items/add", {"scenario": s, "item": dict(HOUSE, purchaseDate="x")})
        self.assertEqual((r["ok"], r["scenario"]), (False, s))
        self.assertIn("bad date", r["messages"][0])
        r = self.post("/api/validate", {"scenario": dict(s, horizon={"start": "x", "end": "y"})})
        self.assertFalse(r["ok"])
        r = self.post("/api/items/add", {"scenario": s, "item": {"type": "bogus"}}, 400)
        self.assertEqual(r["messages"], ["unknown item type 'bogus'"])
        self.assertEqual(self.post("/api/run", {}, 400)["messages"],
                         ["the request needs a 'scenario' object"])

    def test_run_echoes_the_scenario_with_the_full_result(self):
        s = scenario(HOUSE)
        r = self.post("/api/run", {"scenario": s})
        self.assertTrue(r["ok"])
        self.assertEqual(r["scenario"], s)
        self.assertEqual(set(r["result"]), {"rows", "holdings", "ledger", "tax", "events"})
        self.assertEqual(r["result"]["rows"][0]["month"], "2027-01")
        self.assertIsInstance(r["result"]["rows"][0]["cash"], str)        # decimal strings
        bad = self.post("/api/run", {"scenario": dict(s, openingCash="x")})
        self.assertFalse(bad["ok"])

    def test_views(self):
        s = scenario(HOUSE)
        b = self.post("/api/view/builder", {"scenario": s})
        self.assertEqual(b["ordered"], [{"id": "job", "nested": False},
                                        {"id": "h", "nested": False}])
        self.assertEqual(b["starts"]["h"], "2028-01")
        ledger = self.post("/api/view/ledger", {"scenario": s, "month": "2028-01"})
        self.assertEqual(ledger["month"], "2028-01")
        self.assertTrue(any(m["source"] == "h" for m in ledger["movements"]))
        self.assertTrue(self.post("/api/timeline", {"scenario": s})["lanes"])

    def test_compare_needs_one_horizon(self):
        s = scenario()
        self.assertTrue(self.post("/api/compare", {"a": s, "b": s})["ok"])
        other = dict(s, horizon={"start": "2027-01-01", "end": "2029-12-01"})
        self.assertIn("share a horizon",
                      self.post("/api/compare", {"a": s, "b": other})["messages"][0])

    def test_load_upgrades(self):
        old = dict(scenario(), items=[{"type": "expense", "startDate": "2027-01-01",
                                       "monthlyAmount": "5"}])
        r = self.post("/api/load", {"data": old})
        self.assertEqual(r["scenario"]["items"][0]["amount"], "5")

    def test_schema(self):
        r = self.client.get("/api/schema").get_json()
        self.assertEqual(r["fields"], app.FIELDS)
        self.assertIn("associatedIncome.paid", r["hints"])
        self.assertIn({"value": "lump", "label": "a lump at the end of each quarter / year"},
                      r["selects"]["paid"])

    def test_jurisdiction_in_schema_and_new(self):
        """ADR-0071: the schema and a new scenario are per jurisdiction (default Canada)."""
        r = self.client.get("/api/schema?jurisdiction=CA").get_json()
        self.assertEqual(r["jurisdiction"]["code"], "CA")
        self.assertIn({"code": "CA", "name": "Canada"}, r["jurisdictions"])
        self.assertEqual(r["jurisdiction"]["columns"]["rrspRoom"], "RRSP room left")
        self.assertEqual(self.client.get("/api/schema?jurisdiction=ZZ").status_code, 400)
        new = self.client.get("/api/new?jurisdiction=CA").get_json()["scenario"]
        self.assertEqual(new["jurisdiction"], "CA")
        self.assertEqual(self.client.get("/api/new").get_json()["scenario"]["jurisdiction"], "CA")
        self.assertEqual(self.client.get("/api/new?jurisdiction=ZZ").status_code, 400)

    def test_limits(self):
        r = self.client.post("/api/run", data="x" * (1024 * 1024 + 1),
                             content_type="application/json")
        self.assertEqual(r.status_code, 413)
        many = scenario(*[{"type": "expense", "id": f"e{n}", "startDate": "2027-01-01",
                           "amount": "1"} for n in range(1000)])
        self.assertIn("at most 1000 items", self.post("/api/run", {"scenario": many},
                                                      400)["messages"][0])
        long = dict(scenario(), horizon={"start": "2027-01-01", "end": "2140-01-01"})
        self.assertIn("at most 100 years", self.post("/api/validate", {"scenario": long},
                                                     400)["messages"][0])

    def test_gzip(self):
        r = self.client.post("/api/run", json={"scenario": scenario()},
                             headers={"Accept-Encoding": "gzip"})
        self.assertEqual(r.headers["Content-Encoding"], "gzip")
        self.assertTrue(json.loads(gzip.decompress(r.data))["ok"])


if __name__ == "__main__":
    unittest.main()
