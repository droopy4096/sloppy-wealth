# Working on this repository (for developers and AI agents)

Read [README.md](README.md) first (purpose, repo map, contributing). This file is the rule
book: how the owner works, how decisions are recorded, and the engineering conventions
that keep the PoC trustworthy.

## How the owner works
- **The owner drives decisions; you propose and record.** For design questions, give
  options with a clear recommendation, wait for the answer, then record it. Do not decide
  design questions unilaterally.
- **One question at a time.** Never dump a numbered list of questions. Ask one (with a
  recommendation), record the answer, then ask the next. Keep any longer agenda in
  `docs/open-questions.md` so context is not lost.
- **Every change gets its own commit**, made as part of the same step, with a message that
  names what changed (ADR numbers, files, finding IDs). Do not batch several discussion
  rounds into one commit. Commit trailer used throughout the history:
  `Co-Authored-By: <model> <noreply@anthropic.com>`.
- **Plain, brief answers.** The owner prefers short, to-the-point replies.
- **Design before code.** Design questions are settled and recorded (ADRs, Mermaid
  diagrams) before implementation; implementation happens when the owner asks for it.
- **Pull requests only.** `main` is protected: work on a branch per change, run the
  gates, open a pull request against `main`; the owner reviews and merges. Never push to
  `main` directly.
- **Ask before** deleting or renaming branches, rewriting history or force-pushing.

## Where decisions are recorded
| Kind of decision | Where |
|---|---|
| Architecture / domain / accounting rules | `docs/adr/NNNN-*.md` (Status, Context, Decision, Alternatives, Consequences). Change a decision with a dated **Amendment** section in the same ADR; new topic = new ADR. Update `diagrams/02-scenario-domain-model.mmd` (bump its DRAFT version) and `docs/glossary.md` when the model changes. |
| Open / deferred questions | `docs/open-questions.md` (Q-NN, status) |
| Answers to the adversarial review | `CRITIQUE_RESPONSES.md` (finding ID, choice, decision, owner's rationale, where recorded) |
| PoC iteration-2 engineering decisions | `webapp/state_machine/DECISIONS.md` (D1–D5, D-E1–D-E4) |
| What is built vs backlog | `docs/IMPLEMENTATION_STATUS.md` (keep it current when you implement something) |
| Scenario JSON format and engine semantics | `webapp/SPEC.md` (binding for the PoC) |

Decisions the owner already made are not to be re-litigated; if a new fact undermines
one, say so and ask (as done for C-P2 "revisited").

## The PoC engine (iteration 2) in one paragraph
`webapp/state_machine/`: a **Household** (main object: cash, holdings = *aggregates*, ledger,
tax accumulator) is changed only by **events**. **Emitters** (one or more per scenario
item, built by factories registered with `@item_type` in `compiler.py`) decide each month
whether an event happens; each emitter class has a built-in **order** number
(`clock.Order`), and the **ScenarioRunner** walks emitters sorted by `(order, ordinal,
sub)`, applying each event immediately (follow-up events depth-first). **Rules**
(`rules/`) are calculators (tax, indexing, investment income). `results.py` builds the
outputs; `run_detailed()` returns rows, holdings, ledger, tax and the event log. Details:
`webapp/state_machine/README.md`, `INTERFACES.md` (contracts, ORDER table), `OBJECTS.md`
(every object, formula and deliberate quirk), diagram `diagrams/06-event-emitter-conceptual.mmd`.

## Engineering conventions (PoC)
- **Money**: `decimal.Decimal`, every movement rounded half-even to cents when computed
  (`arith.money`), rates at full precision (ADR-0009). Rates are fractions in JSON,
  percentages in the UI (ADR-0045).
- **Every balance change goes through `Household.move()`** (one ledger line each).
- **Emitters decide, events act**: `emit()` may read state but never change it;
  balance-dependent amounts are computed in the event's `apply()`. Emit nothing in months
  where nothing happens.
- **Adding an item type**: new module under `holdings/`, `events/`, `flows/` or `rules/`
  with an `@item_type("name")` factory returning emitters; validation in `validation.py`;
  form fields in `webapp/schema.py` (`FIELDS`, `HINTS`, `SELECTS`); `webapp/SPEC.md`; tests. No
  shared registry edits are needed (auto-discovery). Anything country-specific (account
  types, tax treatment, limits, own item types and their form wording) belongs in a
  jurisdiction package `state_machine/jurisdictions/<code>/` (ADR-0071), not in the core.
- **Modifiers** (renewal, extra payment, lump sum on a mortgage; sale, improvement,
  market adjustment on an asset) are separate emitters placed at their host (D-E1).
- **Regression guard: the golden suite** (`webapp/state_machine/tests/golden/`,
  `test_golden.py`), frozen from iteration 1. An *intended* behaviour change: run
  `webapp/.venv/bin/python webapp/state_machine/tools/update_golden.py --check`, review every
  difference, then regenerate (`update_golden.py`, `--values`) and commit with a message
  explaining why results changed. Never regenerate to silence an unexplained difference.
- **Gates before every commit** (from `webapp/`): the two test commands in README.md
  "Quick start". Commit only when they pass.
- **Documentation tab**: after editing any document or diagram, run
  `webapp/.venv/bin/python webapp/build_docs.py` and commit `webapp/static/docs/` (`test_docs.py`
  fails when it is stale). Mermaid rendering uses `mmdc` (`$MMDC`, PATH, or a copy cached
  by an earlier `npx @mermaid-js/mermaid-cli` run); unchanged diagrams reuse their SVGs.

## Never commit
The owner's personal files at the repo root (scenario JSON files such as
`*_financials*.json`, `Untitled.json`, `Optimal.json`; listed in `.gitignore`), `diagrams/svg/` (local renderings), `webapp/.venv`, `webapp/tags` (ctags),
`.worktrees/`. Add files by explicit path, never `git add -A`.

## Practical notes
- Parallel agents: use a git worktree and branch per agent (`.worktrees/<name>`),
  symlink `webapp/.venv` into it, open a pull request when the gates pass, then remove
  the worktree.
- `webapp/tags` can be regenerated for editor navigation:
  `cd webapp && ctags -R --languages=Python --python-kinds=-iv --exclude=.venv --exclude=__pycache__ --exclude=static --exclude=state_machine/fixtures -f tags .`
