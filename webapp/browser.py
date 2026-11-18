"""A test stand-in for a browser tab (ADR-0069): it keeps the scenario, as the tab's
sessionStorage does, posts it with every request (as web.js does) and keeps the
scenario each page carries back.

    client = Browser()
    client.scenario = {...}            # what the tab has stored
    page = client.get("/").data        # the builder for it
    client.post("/items/add", data={...})
    client.scenario                    # the new scenario
"""
import json
import re

import app

STATE = re.compile(rb'<script type="application/json" id="scenario-state">(.*?)</script>', re.S)
# Forms whose submit button sends an action (load.html, compare.html).
ACTIONS = {"/load": ("file", "load"), "/compare": ("a", "compare"),
           "/new": ("jurisdiction", "new")}


class Browser:
    def __init__(self, scenario=None):
        self.client = app.app.test_client()
        self.scenario = scenario

    def get(self, url, **kw):
        """Show a page: what web.js does after loading its shell."""
        return self.post(url, **kw)

    def post(self, url, data=None, follow_redirects=None, content_type=None, **kw):
        data = dict(data or {})
        field, action = ACTIONS.get(url.split("?")[0], (None, None))
        if field and field in data:
            data.setdefault("action", action)
        data["scenario"] = "" if self.scenario is None else json.dumps(self.scenario)
        if content_type:
            kw["content_type"] = content_type
        response = self.client.post(url, data=data, **kw)
        found = STATE.search(response.data)
        if found:
            self.scenario = json.loads(found.group(1))
        return response
