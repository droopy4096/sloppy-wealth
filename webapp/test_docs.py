"""Documentation tab (pre-compiled by build_docs.py). Run: .venv/bin/python -m unittest -v test_docs"""
import json
import os
import re
import unittest

import app
import build_docs

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(HERE, "static", "docs", "index.json")


class DocumentationTab(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()
        with open(INDEX) as f:
            index = json.load(f)
        self.user, self.dev = index["user"], index["dev"]
        self.sections = self.user + self.dev

    def test_every_page_and_diagram_is_served(self):
        for section in self.sections:
            for page in section["pages"]:
                r = self.client.get(f"/docs/{page['slug']}")
                self.assertEqual(r.status_code, 200, page["path"])
                body = r.data.decode()
                for src in re.findall(r'(?:src|href)="(/static/docs/(?:diagrams|files)/[^"]+)"',
                                      body):
                    self.assertEqual(self.client.get(src).status_code, 200, src)
        self.assertEqual(self.client.get("/docs/no-such-page").status_code, 404)

    def test_index_covers_the_documentation(self):
        paths = {p["path"] for s in self.sections for p in s["pages"]}
        for expected in ("webapp/state_machine/OBJECTS.md", "webapp/state_machine/DECISIONS.md",
                         "CRITIQUE.md", "docs/glossary.md", "diagrams/02-scenario-domain-model.mmd",
                         "docs/adr/0059-retirement-event-and-retirement-tax-rate.md"):
            self.assertIn(expected, paths)
        on_disk = {p for _, ps in build_docs.collect() for p in ps}
        self.assertEqual(paths, on_disk, "static/docs is stale: run webapp/build_docs.py")

    def test_diagrams_are_compiled_not_source(self):
        page = self.client.get("/docs/diagrams-02-scenario-domain-model").data.decode()
        self.assertIn('<figure class="diagram">', page)
        self.assertNotIn("Diagram not compiled", page)
        page = self.client.get("/docs/webapp-state-machine-feasibility").data.decode()
        self.assertIn('<figure class="diagram">', page)            # ```mermaid block

    def test_nav_has_the_tab(self):
        self.assertIn('href="/docs" title="user guide and tutorials">Help',
                      self.client.get("/").data.decode())

    def test_help_shows_the_user_guide_and_dev_docs_are_apart(self):
        """The Help tab (/docs) is the user guide; developer documentation is at /docs/dev,
        linked from the bottom of the Help sidebar (owner's request 2026-11-18)."""
        user_paths = {p["path"] for s in self.user for p in s["pages"]}
        self.assertIn("docs/user/README.md", user_paths)
        self.assertIn("docs/user/vehicle-lease-or-own.md", user_paths)
        self.assertTrue(all(p.startswith("docs/user/") for p in user_paths))
        help_page = self.client.get("/docs").data.decode()
        self.assertIn("<h1", help_page)
        self.assertIn("Getting started", help_page)               # the first page
        self.assertNotIn("Architecture decisions", help_page)          # no dev sections
        self.assertIn('href="/docs/dev"', help_page)
        dev = self.client.get("/docs/dev").data.decode()
        self.assertIn("Architecture decisions", dev)
        self.assertIn("&larr; Help (user guide)", dev)
        adr = self.client.get("/docs/docs-adr-0059-retirement-event-and-retirement-tax-rate")
        self.assertIn("Architecture decisions", adr.data.decode())     # its own area
        tutorial = self.client.get("/docs/docs-user-vehicle-lease-or-own").data.decode()
        self.assertIn('src="/static/docs/files/docs/user/images/vehicle-lease-or-own/', tutorial)
        self.assertIn('href="/static/docs/files/docs/user/files/vehicle-lease-or-own.json"',
                      tutorial)

    def test_markdown_subset(self):
        links = lambda t: t
        html = build_docs.markdown("# T\n\n- a **b `c`**\n  - nested\n\n| x | y |\n|---|---|\n| 1 | 2 |\n",
                                   None, "t", links)
        self.assertIn("<strong>b <code>c</code></strong>", html)
        self.assertIn("<ul><li>a <strong>b <code>c</code></strong><ul><li>nested</li></ul></li></ul>",
                      html)
        self.assertIn("<td>1</td><td>2</td>", html)
        image = build_docs.markdown("See ![Builder](img/a.png) and [it](b.md).", None, "t", links)
        self.assertIn('<img src="img/a.png" alt="Builder" loading="lazy">', image)
        self.assertIn('<a href="b.md">it</a>', image)


if __name__ == "__main__":
    unittest.main()
