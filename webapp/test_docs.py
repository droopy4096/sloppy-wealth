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
            self.sections = json.load(f)["sections"]

    def test_every_page_and_diagram_is_served(self):
        for section in self.sections:
            for page in section["pages"]:
                r = self.client.get(f"/docs/{page['slug']}")
                self.assertEqual(r.status_code, 200, page["path"])
                for svg in re.findall(r'src="(/static/docs/diagrams/[^"]+)"', r.data.decode()):
                    self.assertEqual(self.client.get(svg).status_code, 200, svg)
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
        self.assertIn('href="/docs">Documentation', self.client.get("/").data.decode())

    def test_markdown_subset(self):
        links = lambda t: t
        html = build_docs.markdown("# T\n\n- a **b `c`**\n  - nested\n\n| x | y |\n|---|---|\n| 1 | 2 |\n",
                                   None, "t", links)
        self.assertIn("<strong>b <code>c</code></strong>", html)
        self.assertIn("<ul><li>a <strong>b <code>c</code></strong><ul><li>nested</li></ul></li></ul>",
                      html)
        self.assertIn("<td>1</td><td>2</td>", html)


if __name__ == "__main__":
    unittest.main()
