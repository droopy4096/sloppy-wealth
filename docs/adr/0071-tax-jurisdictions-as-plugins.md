# ADR-0071: Tax jurisdictions as plug-in packages; the US next to Canada

- **Status:** Proposed (design agreed 2026-11-18, Q-47; not implemented)
- **Date:** 2026-11-18
- **Relates to:** ADR-0004 (tax rules behind a jurisdiction seam, Canada first), ADR-0011
  (investment accounts), ADR-0048 (RRSP deduction), ADR-0060 (contribution room),
  ADR-0061 (persons, spousal RRSP)

## Context
ADR-0004 put tax rules behind a jurisdiction seam, but the PoC has no jurisdiction
interface: Canadian rules are spread through the core. Account types `rrsp`, `tfsa`,
`nonRegistered` are named in `validation.py`, `schema.py` and `cards.py`; their tax
treatment is `if account_type == "rrsp"` in `rules/investment.py`; contribution room
(`rules/contribution_room.py`) is RRSP/TFSA-specific; the spousal RRSP `contributor`
and UI labels ("Deductions (RRSP, pension plan)", `rrspRoom` / `tfsaRoom`) are Canadian.
Income, expenses, properties, mortgages, vehicles, triggers, associated items, the
runner and the flat effective tax rate are not country-specific.

The owner wants the US added next to Canada, with a pluggable structure so that others
can contribute jurisdictions. A scenario targets one jurisdiction; the UI shows only its
inputs (RRSP and TFSA for Canada, 401(k) and Roth for the US). Mixed jurisdictions may
come later and are out of scope.

## Decision
1. **Code layout (Q-47 a, owner 2026-11-18): a Python package per jurisdiction.**
   `state_machine/jurisdictions/<code>/` (first `ca`, then `us`), registered with a
   `@jurisdiction("<code>")` decorator and auto-discovered like `@item_type`. A package
   holds its account types with their tax treatments, its rules, its own item types,
   form fields, labels and validation. The core names no country.
2. **Scenario format (Q-47 b, owner 2026-11-18):** a top-level `"jurisdiction"` field
   holding an ISO country code (`"CA"`, `"US"`). Files without it load as `"CA"`
   (`upgrade` adds it). Validation refuses item types and account types the jurisdiction
   does not offer. Changing the jurisdiction is refused while the scenario has items that
   exist only in the current one; the message names them.
3. **Core / plug-in boundary (Q-47 c, owner 2026-11-18): treatment flags plus hooks.**
   - Each account type a jurisdiction declares (`AccountType`: code, label, extra form
     fields) carries a `Treatment` of three flags: `deductible` (money put in reduces
     taxable income), `returns_taxed`, `withdrawal_taxed`. RRSP and traditional 401(k):
     deductible, sheltered, withdrawals taxed; TFSA and Roth: none of the three;
     non-registered and brokerage: returns taxed.
   - The `Jurisdiction` base class has three hooks, `on_contribute`, `on_return` and
     `on_withdraw`, whose defaults do what the flags say; a jurisdiction overrides one for
     anything special (Canada: an RRSP withdrawal at the account's own rate, ADR-0048;
     US: the early-withdrawal penalty).
   - Contribution limits are one interface, `ContributionLimits` (`cap`, `note_earned`,
     `note_withdrawal`, `remaining`), which ADR-0060's room rule already has: Canada plugs
     in today's room rule, the US plugs in yearly limits. The result columns of limits
     (`rrspRoom`, `tfsaRoom`) come from the jurisdiction.
   - The core picks the scenario's jurisdiction once per run; events call its hooks and
     limits; validation and the form schema take account types, item types and labels
     from it. The Canadian package is today's code moved, so Canadian results are
     unchanged (golden suite).
4. **First US version (Q-47 d, owner 2026-11-18): accounts and limits.**
   - Accounts: traditional and Roth 401(k), traditional and Roth IRA, HSA, brokerage.
   - Yearly contribution limits: the 401(k) employee limit shared by traditional and Roth,
     the IRA limit shared the same way, the HSA limit, and catch-up contributions from age
     50. Employer match as today
     (ADR-0051), outside the employee limit.
   - Age (owner 2026-11-18): an optional `birthDate` (YYYY-MM-DD) on the person item, in
     the core, since later rules need it too (RMDs at 73, the 59½ penalty, CPP/OAS ages,
     retirement by age). US catch-up applies from January of the year the person turns
     50; without a birth date there is no catch-up.
   - Social Security is a pension item (ADR-0052). Federal tax, state tax and FICA are
     folded into the flat effective rate (ADR-0004).
   - Deferred: required minimum distributions, the 10% early-withdrawal penalty, HSA
     medical rules, 529 plans, Roth conversions.
5. **UI (Q-47 e, owner 2026-11-18): a New page, and the jurisdiction in the settings.**
   - A "New" link in the nav opens a page that asks for the jurisdiction (Canada, United
     States, ... from the registry), warns about unsaved changes, and starts an empty
     scenario.
   - The Scenario card's settings show the jurisdiction as a dropdown; switching follows
     decision 2 (refused while country-specific items exist, naming them).
   - Forms, add groups, account choices, card categories and labels (the ledger's
     deductions line, the room columns) come from the scenario's jurisdiction
     (`/api/schema` takes it). The nav shows the current jurisdiction.
6. **Contributing a jurisdiction (Q-47 f, owner 2026-11-18): in the repository, with a
   conformance suite.** A new folder `state_machine/jurisdictions/<code>/` is found
   automatically. A shared conformance test runs against every registered jurisdiction:
   account types and labels complete, the form schema builds, a sample scenario validates
   and runs, limits implement the interface. Each jurisdiction keeps its own golden
   scenarios (`tests/golden/<code>/`) and unit tests. A CONTRIBUTING section lists the
   steps, with `ca/` and `us/` as the examples.

## Alternatives considered
- Data files per jurisdiction (JSON or YAML) read by generic core rules: easiest to
  contribute, but rules with logic (TFSA withdrawals re-adding room, RRSP room from
  earned income, required minimum distributions) would need special cases in the core.
- Hybrid (package plus a data file for limits and labels): more structure up front.
- Jurisdiction required (no default): every existing file would be refused until edited.
- Switching converts accounts (RRSP to Traditional IRA, TFSA to Roth IRA, ...): the
  treatments differ in detail, so a silent mapping would mislead.
- Hooks only (each jurisdiction implements the whole account tax rule): every
  jurisdiction would re-implement the common cases.
- Flags only: anything unusual (required minimum distributions, penalties, HSA medical
  use) would need new flags in the core.
- The jurisdiction only in the settings (a fresh tab starts as Canada): a US user would
  always start by switching.
- One jurisdiction per deployment (environment variable): one instance could not serve
  both.
- Separately installed packages discovered through an entry point: more to maintain, and
  third-party code would run on the server. Possible later.
- No conformance suite: nothing would check that a new jurisdiction is complete.
- A separate engine per jurisdiction: duplicates the runner and every shared item.

## Consequences
- Canadian results must not change: the golden suite guards the refactor.
- Implementation order: (1) the seam with Canada moved into `jurisdictions/ca/`, results
  byte-identical; (2) the `jurisdiction` field, person `birthDate`, schema and validation
  by jurisdiction; (3) the US package; (4) the New page and settings dropdown; (5) the
  conformance suite and CONTRIBUTING.
- Domain model diagram 02 v0.55: `Jurisdiction`, `Person.birthDate`.

## Implementation notes (2026-11-18, `poc/sm-jurisdictions`)
- Catch-up age per group, as the IRS has it: 50 for 401(k) and IRA, **55 for HSA**
  (decision 4 said "from age 50"; the HSA case is 55 in US law).
- US limits: each calendar year starts at the limit (indexed, rounded down to $500, HSA
  $50); nothing carries over. The employer match is outside the employee limit
  (`ContributionLimits.cap(..., match=True)`); Canada still caps it at room (ADR-0060).
  The match is a share of what was actually contributed.
- A tax-deferred account's own `withdrawalTaxRate` (ADR-0035) is in the default
  `on_withdraw`, so a traditional 401(k) or IRA can have one too; Canada needs no
  override.
- A jurisdiction's own required fields that are choices (US `limitType`) are listed in
  `choice_fields`, so the core does not read them as numbers.
- The current jurisdiction is a badge at the top left of the nav, before the menu items
  (owner's request 2026-11-18: it was not visible enough at the end of the nav); it
  links to the Scenario settings, where it is changed.
