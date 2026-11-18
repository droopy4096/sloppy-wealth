"""Pre-compile the project documentation for the app's Documentation tab.

    webapp/.venv/bin/python webapp/build_docs.py

Renders every Markdown document (planning docs, ADRs, critique, PoC and state-machine
docs) to an HTML fragment and every Mermaid diagram (diagrams/*.mmd and ```mermaid
blocks inside documents) to SVG, into webapp/static/docs/. The app only serves the result,
so it needs no Markdown or Mermaid tooling at run time.

Mermaid rendering uses mermaid-cli (`mmdc`): $MMDC, then `mmdc` on PATH, then a copy
cached by an earlier `npx @mermaid-js/mermaid-cli` run. An SVG is named by a hash of its
source and reused while the source is unchanged, so a rebuild without mmdc still works
for diagrams that have not changed.
"""
import glob
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "webapp", "static", "docs")

# (section, [paths or globs relative to the repo root]) in sidebar order.
SECTIONS = [
    ("Start here", ["README.md", "CLAUDE.md", "docs/IMPLEMENTATION_STATUS.md"]),
    ("Planning", ["docs/glossary.md", "docs/open-questions.md", "docs/scenarios/*.md",
                  "docs/poc-review-2026-11-07.md"]),
    ("Review", ["CRITIQUE.md", "CRITIQUE_RESPONSES.md"]),
    ("Architecture decisions", ["docs/adr/*.md"]),
    ("Diagrams", ["diagrams/*.mmd"]),
    ("PoC (iterations, spec)", ["webapp/README.md", "webapp/SPEC.md"]),
    ("PoC iteration 2: event emitters", ["webapp/state_machine/README.md", "webapp/state_machine/DECISIONS.md",
                              "webapp/state_machine/FEASIBILITY.md",
                              "webapp/state_machine/EMITTERS_FEASIBILITY.md",
                              "webapp/state_machine/OBJECTS.md",
                              "webapp/state_machine/INTERFACES.md"]),
]


def find_mmdc():
    for candidate in (os.environ.get("MMDC"), shutil.which("mmdc"),
                      *sorted(glob.glob(os.path.expanduser(
                          "~/.npm/_npx/*/node_modules/.bin/mmdc")))):
        if candidate and os.path.exists(candidate):
            return candidate
    return None


class Diagrams:
    """Renders Mermaid sources to OUT/diagrams/<hash>.svg, reusing existing files."""

    def __init__(self):
        self.mmdc = find_mmdc()
        self.dir = os.path.join(OUT, "diagrams")
        os.makedirs(self.dir, exist_ok=True)
        self.used, self.missing = set(), []

    def svg(self, source, label):
        """File name of the rendered SVG, or None if it cannot be rendered."""
        name = hashlib.sha1(source.encode()).hexdigest()[:16] + ".svg"
        path = os.path.join(self.dir, name)
        if not os.path.exists(path) and self.mmdc:
            with tempfile.TemporaryDirectory() as tmp:
                src = os.path.join(tmp, "in.mmd")
                with open(src, "w") as f:
                    f.write(source)
                done = subprocess.run([self.mmdc, "-i", src, "-o", path, "-b", "white"],
                                      capture_output=True, text=True)
                if done.returncode != 0 or not os.path.exists(path):
                    print(f"  mermaid failed for {label}: {done.stderr.strip()[-300:]}")
        if os.path.exists(path):
            self.used.add(name)
            return name
        self.missing.append(label)
        return None

    def figure(self, source, label):
        name = self.svg(source, label)
        if name:
            return (f'<figure class="diagram"><a href="/static/docs/diagrams/{name}" '
                    f'target="_blank"><img src="/static/docs/diagrams/{name}" '
                    f'alt="{html.escape(label)}"></a></figure>')
        return ('<p class="flash">Diagram not compiled (mermaid-cli not found); '
                f'source:</p><pre><code>{html.escape(source)}</code></pre>')

    def prune(self):
        for path in glob.glob(os.path.join(self.dir, "*.svg")):
            if os.path.basename(path) not in self.used:
                os.remove(path)


# ---------- a small Markdown converter (the subset these documents use) ----------

def inline(text, links):
    """Inline Markdown: code, links, bold, italic; everything else escaped. Code spans are
    swapped for placeholders first, so emphasis may contain code."""
    codes = []

    def keep(m):
        codes.append(f"<code>{html.escape(m.group(1))}</code>")
        return f"\x00{len(codes) - 1}\x00"
    s = re.sub(r"`([^`]+)`", keep, text)
    s = html.escape(s, quote=False)
    s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)",
               lambda m: f'<a href="{links(html.unescape(m.group(2)))}">{m.group(1)}</a>', s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", s)
    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], s)


def table(rows, links):
    def cells(line):
        line = line.strip().strip("|")
        return [c.strip() for c in re.split(r"(?<!\\)\|", line)]
    head, body = cells(rows[0]), [cells(r) for r in rows[2:]]
    out = ["<table>", "<tr>" + "".join(f"<th>{inline(c, links)}</th>" for c in head) + "</tr>"]
    for r in body:
        out.append("<tr>" + "".join(f"<td>{inline(c, links)}</td>" for c in r) + "</tr>")
    out.append("</table>")
    return "\n".join(out)


LIST_ITEM = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")


def lists(lines, links):
    """Nested lists from consecutive list lines: indentation decides the level."""
    root = {"indent": -1, "children": []}
    stack = [root]
    for line in lines:
        m = LIST_ITEM.match(line)
        if not m:                # continuation line of the previous item
            stack[-1]["text"] += " " + line.strip()
            continue
        indent = len(m.group(1).expandtabs(4))
        while len(stack) > 1 and indent <= stack[-1]["indent"]:
            stack.pop()
        item = {"indent": indent, "ordered": m.group(2)[0].isdigit(), "text": m.group(3),
                "children": []}
        stack[-1]["children"].append(item)
        stack.append(item)

    def render(items):
        tag = "ol" if items[0]["ordered"] else "ul"
        inner = "".join(f"<li>{inline(i['text'], links)}"
                        + (render(i["children"]) if i["children"] else "") + "</li>"
                        for i in items)
        return f"<{tag}>{inner}</{tag}>"
    return render(root["children"])


def markdown(text, diagrams, label, links):
    lines = text.split("\n")
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            lang = line[3:].strip()
            j = i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                j += 1
            code = "\n".join(lines[i + 1:j])
            if lang == "mermaid":
                out.append(diagrams.figure(code, f"{label} diagram"))
            else:
                out.append(f"<pre><code>{html.escape(code)}</code></pre>")
            i = j + 1
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            text_ = m.group(2).strip()
            anchor = re.sub(r"[^a-z0-9]+", "-", text_.lower()).strip("-")
            out.append(f'<h{level} id="{anchor}">{inline(text_, links)}</h{level}>')
            i += 1
            continue
        if re.match(r"^\s*(-{3,}|\*{3,})\s*$", line):
            out.append("<hr>")
            i += 1
            continue
        if line.lstrip().startswith("|") and i + 1 < len(lines) and re.match(
                r"^\s*\|?\s*:?-{3,}", lines[i + 1]):
            j = i
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                j += 1
            out.append(table(lines[i:j], links))
            i = j
            continue
        if LIST_ITEM.match(line):
            j = i
            block = []
            while j < len(lines) and lines[j].strip() and (
                    LIST_ITEM.match(lines[j]) or lines[j].startswith((" ", "\t"))):
                block.append(lines[j])
                j += 1
            out.append(lists(block, links))
            i = j
            continue
        if line.startswith(">"):
            j = i
            quote = []
            while j < len(lines) and lines[j].startswith(">"):
                quote.append(lines[j][1:].lstrip())
                j += 1
            out.append(f"<blockquote>{markdown(chr(10).join(quote), diagrams, label, links)}"
                       "</blockquote>")
            i = j
            continue
        if not line.strip():
            i += 1
            continue
        j = i
        para = []
        while j < len(lines) and lines[j].strip() and not (
                lines[j].startswith(("#", "```", ">", "|")) or LIST_ITEM.match(lines[j])):
            para.append(lines[j].strip())
            j += 1
        out.append(f"<p>{inline(' '.join(para), links)}</p>")
        i = j
    return "\n".join(out)


# ---------- pages ----------

def slug_for(path):
    return re.sub(r"[^a-z0-9]+", "-", os.path.splitext(path)[0].lower()).strip("-")


def title_for(path, text):
    if path.endswith(".mmd"):
        m = re.search(r"^title:\s*(.+)$", text, re.M)
        return m.group(1).strip() if m else os.path.basename(path)
    m = re.search(r"^#\s+(.+)$", text, re.M)
    return re.sub(r"[`*]", "", m.group(1)).strip() if m else os.path.basename(path)


def collect():
    sections = []
    for title, patterns in SECTIONS:
        paths = []
        for pattern in patterns:
            for path in sorted(glob.glob(os.path.join(ROOT, pattern))):
                rel = os.path.relpath(path, ROOT)
                if rel not in paths:
                    paths.append(rel)
        sections.append((title, paths))
    return sections


def build():
    if os.path.isdir(os.path.join(OUT, "pages")):
        shutil.rmtree(os.path.join(OUT, "pages"))
    os.makedirs(os.path.join(OUT, "pages"))
    diagrams = Diagrams()
    print(f"mermaid-cli: {diagrams.mmdc or 'not found (existing SVGs reused)'}")
    sections = collect()
    slugs = {rel: slug_for(rel) for _, paths in sections for rel in paths}

    index = []
    for title, paths in sections:
        pages = []
        for rel in paths:
            with open(os.path.join(ROOT, rel)) as f:
                text = f.read()
            here = os.path.dirname(rel)

            def links(target, here=here):
                if re.match(r"^[a-z]+:|^#", target):
                    return target
                path, _, frag = target.partition("#")
                resolved = os.path.normpath(os.path.join(here, path))
                if resolved in slugs:
                    return f"/docs/{slugs[resolved]}" + (f"#{frag}" if frag else "")
                return target

            if rel.endswith(".mmd"):
                body = (f"<h1>{html.escape(title_for(rel, text))}</h1>"
                        f"<p><code>{html.escape(rel)}</code></p>"
                        + diagrams.figure(text, rel)
                        + f"<details><summary>Mermaid source</summary><pre><code>"
                          f"{html.escape(text)}</code></pre></details>")
            else:
                body = markdown(text, diagrams, rel, links)
            slug = slugs[rel]
            with open(os.path.join(OUT, "pages", slug + ".html"), "w") as f:
                f.write(body + "\n")
            pages.append({"slug": slug, "title": title_for(rel, text), "path": rel})
        index.append({"title": title, "pages": pages})
    diagrams.prune()
    with open(os.path.join(OUT, "index.json"), "w") as f:
        json.dump({"sections": index}, f, indent=1)
        f.write("\n")
    count = sum(len(s["pages"]) for s in index)
    print(f"{count} pages, {len(diagrams.used)} diagrams -> {os.path.relpath(OUT, ROOT)}")
    if diagrams.missing:
        print("NOT COMPILED: " + ", ".join(diagrams.missing))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(build())
