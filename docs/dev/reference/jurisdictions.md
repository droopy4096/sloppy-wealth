# Jurisdictions

A jurisdiction is a tax country as a plug-in package (ADR-0071). It decides the account
types and how each is taxed, its own item types, its contribution limits and their result
columns, and wording for the forms. The core engine has no country rules.

- API: `state_machine/jurisdictions/__init__.py`.
- Packages: `state_machine/jurisdictions/ca/` (Canada), `state_machine/jurisdictions/us/`
  (United States).
- A scenario names one with `"jurisdiction": "CA"`; a scenario without the field is
  Canadian (`DEFAULT = "CA"`; `upgrade.py` inserts it).

## Treatment

Frozen dataclass: how money in an account type is taxed.

| Flag | Meaning |
|---|---|
| `deductible` | Money put in reduces the contributor's taxable income. |
| `returns_taxed` | The monthly return is taxable income of the owner (a loss gives no credit). |
| `withdrawal_taxed` | Money taken out is taxable income of the owner (or taxed at the account's `withdrawalTaxRate`). |

Predefined: `DEFERRED` (True, False, True), `EXEMPT` (False, False, False), `TAXABLE`
(False, True, False). The US package adds `HSA` (True, False, False).

## AccountType

Frozen dataclass `AccountType(code, label, treatment, short="", fields=())`:

| Attribute | Meaning |
|---|---|
| `code` | Stored in the account item's `accountType`. |
| `label` | Shown in forms (the `accountType` choices of `/api/schema`). |
| `treatment` | A `Treatment`. |
| `short` | Card label. |
| `fields` | Extra account fields only this type takes (e.g. `"contributor"`, RESP fields). `schema.merged` adds them to the account form. |

## Jurisdiction

Base class; subclass it and register it with `@jurisdiction("XX")`.

| Attribute | Meaning |
|---|---|
| `code` | ISO 3166 alpha-2 code; set by the decorator. |
| `name` | Display name. |
| `account_types` | `{code: AccountType}`. Validation refuses other `accountType` values. |
| `item_types` | Own item types, e.g. `("contributionRoom",)`. Other jurisdictions refuse them by name. |
| `required` | `{own type: [required fields]}`, merged into `validation.REQUIRED`. |
| `choice_fields` | Required fields that are choices, not numbers or dates (checked in `validate_item`). |
| `owned_types` | Own types that take an `owner`. |
| `labels` | Wording keys `deductions`, `pool`, `earned` (ledger and forms). |
| `limits` | A `ContributionLimits` instance (default `NO_LIMITS`). |
| `form_fields` | `{own type: [fields in JSON order]}` for the forms. |
| `legends`, `hints` | Form legends and hints (`(type, field)` or field keys); also override core wording. |
| `percent_fields` | Own fields typed as percentages in the form. |
| `selects` | Dropdown choices of own fields: `{field: [(value, label)]}`. |
| `add_groups` | `{group title: [own types]}` added to the flat builder's "+ Add" groups. |
| `head_adds` | `{"person" | "scenario": [own types]}` added to person or Scenario cards. |

| Method | Meaning |
|---|---|
| `treatment(account)` | The `Treatment` of an account object, or `None`. |
| `on_contribute`, `on_return`, `on_withdraw` | Tax hooks, see [Hooks](#hooks). |
| `validate_item(item, where, check)` | Checks for its own item types (and anything else); raise `ValueError`. Called for every item after the core checks. `check` is a `validation.ItemCheck` with `scenario`, `persons`, `start`, `end` and `seen` (a dict for its own state across items, e.g. one item per type). |
| `label(key, default)` | `labels.get(key, default)`. |

## Hooks

Called by the account events with the rounded amount `household.move` returned.

| Hook | Called from | Default |
|---|---|---|
| `on_contribute(household, account, amount, source=None)` | `InvestmentAccount.accept_contribution` (own share only), `Transfer.apply` | If `deductible` and the scenario is not `expensesCovered`: `tax_of(account.contributor).add_deduction(amount)`. |
| `on_return(household, account, ret)` | `AccountReturn.apply` | If `returns_taxed`: `tax_of(account.owner).add_taxable(max(0, ret))`. |
| `on_withdraw(household, account, amount)` | `Withdrawal.apply` | If `withdrawal_taxed`: with `withdrawalTaxRate`, `add_own_rate_tax(amount × rate)`; else `add_taxable(amount)` for the owner. |

Not called for `OPENING_TRANSFER` / `OPENING_BALANCE` or the employer match.
Override a hook and call `super()` for the rest (Canada does this for the RESP grant).

## ContributionLimits

Interface for limits; the base class allows everything (`NO_LIMITS`).

| Member | Meaning |
|---|---|
| `columns` | `{result column: heading}`. Names must end in `Room` or `Limit` (the conformance test checks; `web/client.py` converts such columns to Decimal). |
| `cap(household, account, amount, match=False)` | The part of `amount` the account may receive now; uses it up. `match=True` for an employer match. |
| `note_earned(household, amount, person=None)` | Earned income of a person this month. |
| `note_withdrawal(household, account, amount)` | A withdrawal (limits that give room back). |
| `remaining(household)` | `{column: amount or None}` added to each result row. |

`capped_note(requested, allowed)` gives the event-log note when a movement was capped.

## Registration and discovery

- `@jurisdiction("XX")` sets `cls.code` and stores one instance in `REGISTRY`.
- `discover()` imports every sub-package of `jurisdictions/` and every module inside it
  (so `@item_type` factories in, e.g., `ca/room.py` register too). `compiler.discover()`
  calls it.
- Look-ups: `registered()` (all), `get(code)` (`ValueError` if unknown), `of(scenario)`,
  `of_or_default(scenario)`, `code_of(scenario)`, `own_item_types()` (`{type: code}`).
- The household keeps its jurisdiction as `household.jurisdiction`.
- Changing a scenario's jurisdiction (`POST /api/settings`) is refused while items need
  the old one (`ops.switch_problem` names them).

## CA

Canada, `jurisdictions/ca/`.

| accountType | Label | Treatment | Extra fields |
|---|---|---|---|
| `tfsa` | TFSA (tax-free) | EXEMPT | |
| `rrsp` | RRSP (tax-deferred) | DEFERRED | `contributor` (spousal RRSP) |
| `nonRegistered` | non-registered (returns taxed) | TAXABLE | |
| `resp` | RESP (education savings, with the CESG grant) | EXEMPT | `unusedGrantRoom`, `grantReceived`, `contributedSoFar` |

- Own item type: [contributionRoom](items.md#contributionroom) (`ca/room.py`).
- Limits: `RoomLimits` (`ca/room.py`), columns `rrspRoom`, `tfsaRoom`. Room per (person,
  account type); a movement uses its account's contributor's room. For an `resp` account
  `cap` applies the RESP lifetime limit instead ($50,000 less `contributedSoFar`).
- `on_contribute` override: after the default, an RESP pays the CESG grant
  (`ca/resp.py` `pay_grant`, a [GRANT](ledger.md#grant) movement): 20 % of the amount,
  limited by the grant room ($500 per calendar year from the horizon's first year plus
  `unusedGrantRoom`), $1,000 a year and $7,200 lifetime less `grantReceived` (ADR-0072).
- `validate_item`: contributionRoom checks; RESP fields only on `resp` accounts, not
  negative.
- Sample: `jurisdictions/ca/sample.json`.

## US

United States, `jurisdictions/us/`.

| accountType | Label | Treatment |
|---|---|---|
| `traditional401k` | 401(k), traditional (tax-deferred) | DEFERRED |
| `roth401k` | 401(k), Roth (tax-free) | EXEMPT |
| `traditionalIra` | IRA, traditional (tax-deferred) | DEFERRED |
| `rothIra` | IRA, Roth (tax-free) | EXEMPT |
| `hsa` | HSA (health savings account) | HSA (deductible only) |
| `brokerage` | brokerage (returns taxed) | TAXABLE |

- Own item type: [contributionLimit](items.md#contributionlimit) (`us/limits.py`).
- Limits: `YearlyLimits`, columns `k401Limit`, `iraLimit`, `hsaLimit`. Groups:
  `traditional401k` and `roth401k` → `401k`; the IRAs → `ira`; `hsa` → `hsa`. Per
  calendar year, no carry-over; the match is not capped.
- No hook overrides. Social Security is a [pension](items.md#pension) item; federal and
  state tax and FICA are in the flat rate. Not modelled: RMDs, early-withdrawal penalty,
  HSA medical rules, 529 plans, Roth conversions.
- Sample: `jurisdictions/us/sample.json`.

## Conformance test

`state_machine/tests/test_conformance.py` runs over every registered jurisdiction. A new
package must pass it unchanged:

- declarations: two-letter upper-case code, a name, at least one account type,
  `AccountType` keys equal their codes, extra fields appear on the account form, limit
  columns end in `Room` or `Limit`;
- own item types: each has an `@item_type` factory, `required`, `form_fields` and a
  `legend`, belongs to one jurisdiction only; `owned_types`, `add_groups`, `head_adds`
  list only own types;
- forms: `schema.describe(code)` builds, every type is in exactly one add group, the
  `accountType` choices are the account types, other jurisdictions' types are absent;
- sample: `jurisdictions/<code>/sample.json` exists, uses every account type and own item
  type, validates, runs, shows a limit column, and is in the jurisdiction's golden set.

Run: `cd webapp && .venv/bin/python -m unittest state_machine.tests.test_conformance`.

## Golden sets

Each jurisdiction has its own golden results (`state_machine/tools/update_golden.py`):
Canada's set is `state_machine/tests/golden/` (`scenarios.json`, `golden.json`,
`values.json`); another jurisdiction's is `state_machine/tests/golden/<code>/` (US:
`golden/us/`). `update_golden.py --check` compares all sets; `--jurisdiction XX` picks
one, and `--add FILE` adds a synthetic scenario to it. Steps for a new jurisdiction:
`state_machine/README.md`, "Contributing a jurisdiction".
