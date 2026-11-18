# ADR-0069: Stateless server; the scenario lives in the browser

- **Status:** Proposed (design agreed 2026-11-15, Q-44; implemented on `poc/sm-stateless`)
- **Date:** 2026-11-15
- **Relates to:** ADR-0003 (engine stateless per invocation), ADR-0008 (ephemeral state,
  JSON interchange), ADR-0028 (scenario sets)

## Context
ADR-0003 makes the engine stateless per invocation and ADR-0008 makes state ephemeral,
exchanged as JSON. The engine follows both, but the PoC web app has drifted: it keeps
each browser session's scenario in server memory (a session cookie), its endpoints
return HTML only, and rules that change the scenario (add with normalisation, switch
on/off, delete with its cascade) and derived views (effective starts, item grouping,
ledger cash effects) live in the Flask layer. A front-end on another platform could not
reuse them. The owner asked for the server to behave as a state machine: each endpoint
receives the present state as JSON and returns the new state as JSON, runs included.

## Decision
1. **The browser keeps the scenario in `sessionStorage` (Q-44a).** The page reads it on
   load and writes back every new state the server returns. It survives a refresh and
   back / forward in the tab; it is gone when the tab closes; each tab has its own
   scenario. Results are not stored. Saving a JSON file stays the way to keep work; the
   page warns before closing a tab with changes since the last save. (ADR-0008
   amendment 2026-11-15.)
2. **A run returns the full result together with the scenario as sent (Q-44b).** One
   call: the request carries the scenario; the response carries that scenario unchanged
   (an exact echo) and the full detailed result (rows, holdings, ledger, tax, event
   log), compressed. The page keeps the result in memory and slices it for the Run,
   Holdings and Ledger views (no re-run per view). A result is self-describing: it can be
   saved, shown again or compared without the original file (ADR-0008).
3. **Changes to a scenario are engine commands (Q-44c).** Pure functions in the engine
   (`state_machine`, e.g. `ops.py`): scenario + command -> `{scenario, ok, messages}`;
   one endpoint per command (add an item, switch on / off, delete, settings). The rules
   now in the Flask layer move there: a trigger switching its waiting target on, an item
   added switched off while it waits for a trigger's date, the delete cascade (links,
   start triggers, a person's retirement and room). A refused change returns the
   unchanged scenario with the error as data. Commands take JSON values (fractions,
   booleans); turning form text into them (e.g. % to a fraction) is the client's job.
4. **JSON contract (Q-44d).** Money and rates are decimal strings, as in scenario files
   (exact, ADR-0009). A scenario in a request is upgraded from older formats on arrival
   (`upgrade.py`); a command returns the upgraded scenario (a run echoes its input as
   sent, decision 2). Every response carries `schemaVersion`. A schema endpoint describes
   the item types, their fields, choices, hints and possible parents (today's `FIELDS`,
   `SELECTS`, `HINTS`, `NEEDS`), so any client can build its forms.
5. **The Jinja builder becomes a client module (Q-44e).** The server-rendered pages move
   to their own module (e.g. `web/`) that uses only the JSON API (over HTTP, or an
   in-process client with the same contract; no engine imports), deployed alongside it.
   The browser posts the scenario from `sessionStorage` with each form (sent by `fetch`,
   so refresh and back raise no resubmit prompts); the web module turns form text into
   a command (e.g. % to a fraction), calls the API and renders the next page, which
   carries the new scenario back for the page's script to store. Pages that show a run
   (Run, Holdings, Ledger month) post the scenario and re-run it.
6. **Request limits (Q-44f).** A request body over 1 MB is refused (HTTP 413); a
   scenario with more than 1,000 items or a horizon longer than 100 years is refused
   with a message (as data, decision 3).
7. **Order of work (Q-44g)**, each step leaving the app working and the gates green, one
   commit or more per step: (1) commands and derived views into the engine with tests,
   the Flask routes calling them; (2) the JSON API, schema endpoint and limits, with API
   tests; (3) the Jinja pages moved to the web module, API only, `sessionStorage` and
   `fetch`; (4) the server-side scenario store and session cookie removed.

## Alternatives considered
- **`localStorage`**: survives closing the browser, shared by all tabs; automatic
  persistence that ADR-0008 rejected.
- **Page memory only**: a refresh loses unsaved work.
- **Light run + per-month detail calls, or one call per view**: smaller payloads, but
  the engine re-runs (~0.5 s) for every view or month shown.
- **Hash only, or the scenario as run (upgraded, trigger dates filled in) + hash**
  instead of the echo: rejected; the result carries exactly the input it came from.
- **Only a generic "validate the new scenario" endpoint**: every client would
  re-implement the delete cascade and the trigger rules.
- **Numbers as JSON numbers**: floats lose exactness.
- **No schema endpoint**: every client hard-codes item types and fields.
- **Templates rendered in the browser (Nunjucks)** or **a plain JavaScript client
  page**: one run kept in memory, but the Jinja front-end is ported or retired.
- **Body size cap only, or no limit**: a small body can still describe a very long
  run.
- **Server memory per session** (status quo): not stateless; a restart loses work; one
  server per user session.

## Consequences
- The server keeps nothing between requests (ADR-0003 amendment holds for the whole
  app, not only the engine); any instance can answer any request, serverless included.
  A server restart loses no work; closing a tab does (hence the warning).
- Any front-end, in any language, can use the API; the Jinja builder is one such client
  and proves the API is sufficient.
- The engine gains a scenario-commands module and derived-view functions moved from
  `app.py`; the golden suite is unaffected (calculations do not change).
- Every view of a run re-runs the engine in the Jinja client (~0.5 s for a 25-year
  scenario); a client that keeps the result (decision 2) does not.
- `webapp/SPEC.md` gains the API (endpoints, commands, messages, limits).
- Implemented on `poc/sm-stateless` (2026-11-15). Steps 3 and 4 were done together
  (the pages could not use the API while the server still held the scenario). Details
  settled in the implementation: the page frame is a shell that `web.js` fills by
  posting the stored scenario, and in-app links swap the page in place, so the
  unsaved-changes warning appears only on a refresh, closing the tab or leaving the
  site; Save is a download made in the browser; a stored scenario that cannot be read
  (not an object with a horizon and items) starts a new one, with a message; the web
  module turns the API's decimal strings back into Decimal for a fixed list of numeric
  result fields (`web/client.py` `NUMERIC`), never inside the scenario; the timeline is
  split into its model (`timeline.py`, API) and its drawing (`web/timeline_draw.py`).
