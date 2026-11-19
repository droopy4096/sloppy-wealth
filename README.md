# Sloppy Wealth

Sloppy Wealth is sloppy in more ways than one. It was designed by a human and largely
vibe-coded with an LLM, and it is not meant to be a precise instrument: it is a ballpark
calculator for a household's big financial questions.

Over the years I kept asking questions like these:

- [Would it be cheaper to lease a vehicle than to keep and maintain one for 20 years?](docs/user/vehicle-lease-or-own.md)
- When can I sell the house without losing the money I put into buying and maintaining it?
- Would it be cheaper to rent?
- When can I retire with an income of $NNN in today's dollars?
- How much net worth am I really adding each year, in today's dollars?

I built calculators for some of them, but never had the time for one tool that combines
them all, let alone one that isn't command-line based. Enter the LLM. I brought the ideas
(how to design it, what to design it for, and what *I* need) and let the LLM fill the
gaps, tuning its approach as we went. This project is the result.

## What it does
It models a household month by month over a lifetime: incomes, expenses, accounts,
pensions, properties and mortgages, vehicles and taxes. It projects cash, investments,
property, debts and net worth (also in today's dollars), compares scenarios side by side,
and has calculators for a property's break-even and rent equivalent and for a vehicle's
cost of ownership per month.

You don't have to model everything at once. A scenario can hold just one property, to see
its costs and break-even, or just one vehicle, to see what it costs to own, and nothing
else. Every item, and every expense attached to it, can be switched off and on with one
click, so you can see straight away what a different setup changes: the same house
without its renovation, or the same car without its insurance.

It understands Canadian and US tax rules and accounts (RRSP, TFSA, RESP; 401(k), IRA,
HSA). That doesn't mean it can't be used elsewhere, but it may lack what other
jurisdictions need to represent all of a household's finances, so beware. Or open a pull
request: jurisdictions are pluggable (see "Contributing a jurisdiction" in
[webapp/state_machine/README.md](webapp/state_machine/README.md)).

## Your data stays with you
Everything you enter stays on your side. The scenario lives in your browser tab (its
session storage) while you work, and **Save** downloads it as a JSON file that you can
keep, load again later, compare with another one, or share. The server stores nothing:
each page sends it the scenario, gets the results back, and it forgets the scenario
(ADR-0069). There are no accounts and no database. The tab's copy is gone once the tab is
closed, so save before you close it; the app warns you about unsaved changes.

## Where it is going
I will be phasing out LLM use in favour of human contributors. The next goal is developer
documentation thorough enough for that to happen.

## How it is organised
1. **Design**: architecture decisions (ADRs), the domain model and diagrams. Design
   decisions live here; the code follows them.
2. **The app** (`webapp/`): a Python/Flask web app over a JSON API and an event-driven
   engine.

Start with [CLAUDE.md](CLAUDE.md) (working rules for developers and agents), then
[docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md) (what is built, what is
backlog).

## Repository map
| Path | What |
|---|---|
| `docs/user/` | User tutorials: how to answer the questions above with the app, with screenshots and example scenario files |
| `docs/adr/` | Architecture Decision Records 0001–0074, many with dated amendments. The source of truth for decisions. |
| `docs/open-questions.md` | Decisions still open, deferred or on watch |
| `docs/glossary.md` | Domain terms |
| `docs/scenarios/` | The use cases the model must serve (rent vs buy, two houses, retirement readiness, ...) |
| `docs/IMPLEMENTATION_STATUS.md` | Which ADRs and review decisions the app implements; the backlog |
| `docs/poc-review-2026-11-07.md` | Lessons from the first prototype that fed back into the design |
| `diagrams/*.mmd` | Mermaid diagrams: feature mind map, engine pipeline, scenario domain model (02), sequences, output model, event-emitter conceptual model (06). `scripts/render-diagrams.sh` renders them (output is not committed). |
| `CRITIQUE.md` | Adversarial review of the design and the app (2026-11-08): findings, rulings, work plan |
| `CRITIQUE_RESPONSES.md` | The user's decision on every critique finding, with rationale |
| `webapp/` | The app: `app.py` (server), `api.py` (JSON API), `web/` (pages, an API client), `state_machine/` (engine), `SPEC.md` (scenario JSON and semantics), `samples/`, tests, `build_docs.py` + `static/docs/` (Documentation tab) |

## Contributing
`main` is protected: every change goes through a pull request.

1. Branch off `main` (one branch per change, e.g. `feature/<topic>` or `docs/<topic>`).
2. Make the change with its records (ADR, open questions, SPEC, IMPLEMENTATION_STATUS,
   see [CLAUDE.md](CLAUDE.md)) and run the gates below; commit only when they pass.
3. Open a pull request against `main`; it is reviewed, then merged.

Adding a tax jurisdiction: see "Contributing a jurisdiction" in
[webapp/state_machine/README.md](webapp/state_machine/README.md). All sample and test
data must be synthetic.

## Quick start
```
git clone https://github.com/droopy4096/sloppy-wealth.git && cd sloppy-wealth/webapp
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # once
.venv/bin/python app.py                                              # http://127.0.0.1:5000
.venv/bin/python -m unittest -q test_engine test_keep_payment test_ui_emitters test_api test_docs
.venv/bin/python -m unittest discover -s state_machine/tests -t .    # engine + golden suite
```
The app has a **Help** tab (`/docs`) with the user guide and tutorials; the developer
documentation (every design document and rendered diagram) is at `/docs/dev`, linked from
the bottom of the Help sidebar.
