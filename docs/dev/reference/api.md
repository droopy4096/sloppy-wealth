# JSON API

`webapp/api.py`, a Flask blueprint under `/api` (ADR-0069). It is the only part of the
app that uses the engine. The server keeps nothing between requests: every POST carries
the whole present scenario and gets JSON back.

## Conventions

- Request bodies are JSON objects (`Content-Type: application/json`).
- Every response has `schemaVersion` (1), `ok` (bool) and `messages` (list of strings).
- Money and rates are decimal strings; `Decimal` values are serialized with `str`, sets
  as sorted lists.
- Scenarios are upgraded from older forms on arrival (`state_machine/upgrade.py`).
- Responses over 1 KB are gzip-compressed when the request has `Accept-Encoding: gzip`.

**Commands** (`state_machine/ops.py`) answer `{scenario, ok, messages}`: when `ok` is true,
`scenario` is the new, validated scenario; when false, it is the scenario as sent and
`messages` says why. `messages` may also carry notes on an accepted change. Status is 200
either way.

**Views** answer `{ok, messages, ...}` with their own fields.

## Errors and limits

| Case | Status | Body |
|---|---|---|
| Body over 1 MB | 413 | `ok: false`, "the request is larger than 1024 KB" |
| Body not a JSON object; a required key missing or of the wrong type | 400 | `ok: false`, message names the key |
| More than 1,000 items, or a horizon over 100 years (`ops.over_limits`) | 400 | `ok: false`, message |
| `ValueError`, `KeyError`, `TypeError`, `AttributeError` raised while reading a scenario | 400 | `ok: false`, "the scenario cannot be read: …" |
| Invalid scenario for a run or view | 200 | `ok: false`, the validation message |

## Endpoints

| Method | Path | Request | Response (besides `ok`, `messages`) |
|---|---|---|---|
| GET | `/api/schema?jurisdiction=XX` | — | The form schema of one jurisdiction (default CA): `jurisdiction` {code, name, labels, columns}, `jurisdictions` [{code, name}], `fields`, `personFields`, `legends`, `hints`, `blankShown`, `defaults`, `needs`, `hostField`, `formGroups`, `selects`, `percentFields`, `cardAdds`, `headAdds`, `linkField`, `addGroups` (`schema.describe`). Unknown code: 400. |
| GET | `/api/new?jurisdiction=XX` | — | Command: an empty scenario (name "Untitled", horizon 2027-01 to 2051-12, openingCash "0"). Unknown code: 400. |
| POST | `/api/load` | `{data}` | Command: `data` (a file's JSON) checked (`schemaVersion` must be 1), validated, upgraded, every item given an id. Refused: an empty scenario. |
| POST | `/api/validate` | `{scenario}` | Command: the scenario upgraded, or refused with the validation message. |
| POST | `/api/settings` | `{scenario, settings}` | Command. `settings` keys: `name`, `horizon` {start, end}, `openingCash`, `incomeMode`, `dollarsOf`, `annualInflation`, `effectiveTaxRate`, `retirementTaxRate`, `jurisdiction`. Missing keys take the form's defaults (blank rates become "0"; blank retirementTaxRate stays blank). A jurisdiction change is refused while items need the old one. |
| POST | `/api/items/add` | `{scenario, item}` | Command. `item.type` must be a core type or any jurisdiction's own type (else 400); validation refuses another jurisdiction's type. Id (8 hex chars) and name filled in if missing; a duplicate id is refused. An item missing its trigger-set date is added switched off, with a note; adding a trigger switches its waiting target on. |
| POST | `/api/items/update` | `{scenario, id, item, clear}` | Command. `item`: new field values; `clear`: list of field names to remove. Id and type stay; a type change is refused. |
| POST | `/api/items/toggle` | `{scenario, id}` | Command. Switches `enabled` off, or back on (removes the field). |
| POST | `/api/items/delete` | `{scenario, id}` | Command. Deletes the item and everything linked to it (link fields, triggers on it, items its start triggers start), transitively. Deleting a person also deletes their retirement and contributionRoom; their other items lose the `owner`/`contributor` field. |
| POST | `/api/view/builder` | `{scenario}` | `starts`, `ordered` [{id, nested}], `off`, `set_by`, `names`, `summary`, `cards`, `items` ([outputs.md](outputs.md#derived-views)). |
| POST | `/api/run` | `{scenario}` | `scenario` (as sent), `result` {rows, holdings, ledger, tax, events} ([outputs.md](outputs.md)), `summary`. Invalid: `ok: false`, `scenario`. |
| POST | `/api/view/ledger` | `{scenario, month}` | One month of the run: `month` (the first if `month` is not one), `months`, `movements` (ledger lines with signed `cash`), `indices`, `net_cash`, `balances` [{holding, point}], `names`, `tax`, `events` (records with `n`, `depth`, `movements` [{index, movement}]). |
| POST | `/api/view/break-even` | `{scenario, property}` | `view` (property, name, rows, summary, notes) for the property (default: the first), `properties` [{id, name}]. No properties: `view: null`. |
| POST | `/api/view/vehicle-cost` | `{scenario, vehicle}` | `view` (vehicle, name, rows, summary, notes, financed) for the vehicle (default: the first), `vehicles` [{id, name}]. No vehicles: `view: null`. |
| POST | `/api/timeline` | `{scenario}` | The timeline model: `start`, `end`, `lanes`, `links`, `dots`, `arrows`, `guides`, `set_by` (`timeline.layout`). |
| POST | `/api/compare` | `{a, b}` | `a`, `b` (rows of each run), `summaries` {a, b}. Different horizons: `ok: false` (ADR-0028). |

Example:

```
POST /api/run
{"scenario": {"schemaVersion": 1, "jurisdiction": "CA",
  "horizon": {"start": "2027-01-01", "end": "2027-12-01"}, "openingCash": "1000",
  "items": [{"type": "income", "id": "pay", "startDate": "2027-01-01", "amount": "3000"}]}}
-> {"schemaVersion": 1, "ok": true, "messages": [], "scenario": {...},
    "result": {"rows": [{"month": "2027-01", "cash": "4000.00", ...}, ...], ...},
    "summary": {"dollarsOf": "2027-01", "retirement": "", "retirements": []}}
```

## How the web pages call it

`webapp/web/` never imports the engine. `web/client.py` is its only way in:

- `client.call(path, payload)` posts, `client.get(path)` gets. By default the call goes
  in-process through Flask's test client (same app, same contract). With the environment
  variable `WEB_API_URL` set (e.g. `http://localhost:5001`) it goes over HTTP.
- Answers are decoded; values of known numeric keys (`NUMERIC`, plus keys ending in `Room`
  or `Limit`) become `Decimal`, except inside `scenario` and label tables.

The browser keeps the scenario in the tab's sessionStorage and posts it (form field
`scenario`) with every page request (`web/static/web.js`). `web/pages.py` routes:

| Page route | API call |
|---|---|
| `/`, `/flat` (builder) | `GET /schema`, `POST /view/builder` |
| `POST /settings` | `POST /settings` (form percentages converted to fractions) |
| `POST /items/add` | `POST /items/add` (form text to JSON values: `form_item`) |
| `POST /items/<id>/update` | `POST /items/update` (blank fields go to `clear`) |
| `POST /items/<id>/toggle`, `/delete` | `POST /items/toggle`, `/items/delete` |
| `/load` | `POST /load` |
| `/new` | `GET /new?jurisdiction=` |
| `/compare` | `POST /load` (each file), `POST /compare` |
| `/run`, `/run/holdings` | `POST /run` |
| `/run/ledger?month=` | `POST /view/ledger` |
| `/run/break-even?property=` | `POST /view/break-even` |
| `/run/vehicle-cost?vehicle=` | `POST /view/vehicle-cost` |
| `/timeline` | `POST /timeline` |

Form conversion (`pages.form_item`): percentage fields (`schema.PERCENT_FIELDS` plus the
jurisdiction's) are divided by 100; `taxable`, `keepPayment`, `alsoWhenRenting` become
booleans; `earnedIncome` yes/no/blank; `covers` becomes `payOff`; blank person fields and
`on: start` are left out.
