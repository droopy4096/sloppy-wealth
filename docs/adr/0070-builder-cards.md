# ADR-0070: The builder as cards, by person and category

- **Status:** Proposed (design agreed 2026-11-15, Q-45; implemented on `poc/sm-cards`)
- **Date:** 2026-11-15
- **Relates to:** ADR-0061 (persons), ADR-0067 / ADR-0068 (associated items), ADR-0065
  (triggers), ADR-0069 (pages as an API client), D-E1 (modifiers under their host)

## Context
The builder lists every item in one table (start, type, name, a long line of details),
modifiers and triggers indented under their host. With 70 items (the owner's scenario)
it is hard to see what an asset or an income costs or brings in, and what belongs to it.
The owner asked for cards grouped in categories: e.g. a "Pickup truck" card showing its average
monthly cost, which expands on click to its associated expenses, triggers and so on.

## Decision
1. **Sections by person, then categories (Q-45a).** One section per person (e.g. Alex,
   Sam) with the categories Income, Accounts and Pensions, holding the items that
   person owns (ADR-0061: an item without an owner belongs to the first person;
   contributions and withdrawals follow their account). A Household section holds the
   shared categories Properties, Vehicles and Expenses. Each card holds its own
   modifiers, associated items, adjustments and triggers.
2. **A collapsed card shows an estimated monthly figure (Q-45b, revised by Q-45f).** The
   net monthly amount of the item and its children, worked out from the items' own
   fields, not from a run, so the builder stays cheap: it is a hint, shown greyed with a
   tooltip saying how it is estimated. Plus one fact per type: value or balance for
   assets and accounts (as entered), the dates for flows.
3. **An open card lists its linked items as rows (Q-45c).** Clicking a card opens it:
   the item's own details (as the old Details column), then one row per linked item
   (associated items, modifiers, adjustments, triggers on it), each with its own
   next-12-month monthly figure, its details, and its on/off switch and delete. Several
   cards can be open at once; which are open is kept across page updates.
4. **Items are added in context (Q-45d).** Each category has "+ Add" for the item types
   that belong there (in a person's section with that person as owner); each open card
   has "+ Add linked" for the types that can attach to it, with the parent (host,
   flow, target) filled in. Forms open inline; the list of forms at the bottom of the
   page goes away.
5. **Person cards and the Scenario card (Q-45e).** Each person's section starts with a
   person card (tax rates, retirement date, RRSP / TFSA room) that holds their
   retirement event and contribution room items, and lists the triggers fired by that
   retirement. Household starts with a Scenario card (name, horizon, opening cash,
   inflation, tax rates, dollars of) that holds the cash balances. A scenario without
   persons has one implicit person: their section is titled "You". A trigger is listed on
   its target's card and on its event's card.
6. **How the estimate is made, and where (Q-45f).** In the engine's builder view
   (`views.py`, part of `POST /api/view/builder`: no extra call, no run). Each amount is
   turned into a monthly figure (`per`) and brought to the base date (`dollarsOf`,
   default the horizon start) with its own indexing (inflation or a custom rate, yearly
   steps from its start, `amountIn` respected); adjustments in effect at the base date
   replace the amount. A percentage is its rate times the stated basis (price,
   principal, opening balance); a mortgage payment comes from its principal, rate and
   amortization (the latest renewal at the base date), plus extra payments. Income and
   inflows are positive, expenses and payments negative. An item not running at the base
   date shows "from YYYY-MM" (or "until YYYY-MM") instead of a figure. The tooltip states
   the method and that the run gives the exact amounts.
7. **Editing is not part of this step, but the design allows it (Q-45g).** Each row
   and card renders its details from the item and the schema in one place, so an
   "Edit" action can later swap it for the item's form pre-filled from the same schema;
   the add forms are built so they can be reused that way (fields from the schema,
   values optional), and an engine command that replaces an item's fields (keeping its
   id and links) would join `ops.py`.
8. **Vertical layout, collapsible (owner, 2026-11-15).** Sections are full-width bands
   stacked top to bottom, and their categories are stacked inside them, so unrelated
   items are not shown side by side; only cards of one category sit next to each other
   (wrapping). Each section and each category collapses to its title line with its
   estimated total, so the page can be reduced to a few lines; an open card takes the
   full width.

## Alternatives considered
- **Six categories without persons** (Properties, Vehicles, Income & pensions, Accounts,
  Expenses, Household).
- **Eight categories** (Mortgages and Pensions separate).
- **Linked items as nested cards, or a detail panel** (one card at a time).
- **A separate "Plan" category** for settings, persons, retirements, rooms and cash
  balances.
- **One "Add item" button** with a type chooser, or **the forms at the bottom** as now.
- **Card figure from the run** (next 12 months from the base date; exact, but every
  builder update would run the engine, about 0.5 s): chosen first, then replaced by the
  estimate (Q-45f), since the figures are a hint and the builder should stay cheap.
- **Card figure as a lifetime average** (hides today's level), or **amounts as entered**
  (no indexing, no formulas: Living would show 4,500 instead of about 5,276).

## Consequences
- The builder page is reorganised; the scenario, the engine and the golden suite are
  unchanged. The builder view (`views.py`, `/api/view/builder`) gains the card layout
  (sections, categories, cards, linked items) and the estimated figures; other
  front-ends get the same grouping.
- The figures are estimates and can differ from the run (e.g. balance-dependent amounts,
  partial years); the Run page stays the exact view.
- The add forms move from the bottom of the page into the categories and cards.
- Implemented on `poc/sm-cards` (2026-11-15): `state_machine/cards.py` (layout and
  estimates, in `/api/view/builder` as `cards`, with the upgraded items as `items`);
  `schema.py` `CARD_ADDS`, `HEAD_ADDS`, `LINK_FIELD` (served by `/api/schema`); the
  builder template (`<details>` sections, categories and cards); `web.js` copies a type's
  form from a `<template>` when a "+ Add" button is used (the card's link or the
  section's owner as hidden fields; one form per type keeps the page small) and keeps
  which details are open in sessionStorage. Details settled in the implementation:
  cards and rows are in order of their effective start, as the old table; a property's
  card lists its mortgages and their renewals and prepayments one level deeper; a
  mortgage modifier added on a property card chooses its mortgage in the form; items
  whose host is missing go to a Household "Other" category.

## Amendment (2026-11-15): a flat view next to the cards, and incomes after tax
- **Two views, one source.** The card builder is titled "Builder" (`/`); the flat list
  of the earlier builder comes back as "Builder (flat)" (`/flat`): one table of all
  items in order of their start, modifiers and triggers indented under their host,
  with a "+ Add" bar at the top. Both views use the same builder view from the API and
  the same template building blocks (an item's details, figure, switch, delete, the
  "+ Add" buttons; `web/templates/_items.html`); only the arrangement differs. A test
  renders both views of one scenario and checks they list every item with the same
  figure and controls, so neither can fall behind silently.
- **Incomes are estimated after tax** (owner's request: spending is paid from after-tax
  money). A taxable income, a taxable pension, an associated income or one-off of a
  taxable parent, and a withdrawal from an RRSP are reduced by the tax rate of their
  person in the base month: the retirement rate once retired (ADR-0059, ADR-0061), else
  the income tax rate (a person's own rate, else the scenario's); an RRSP withdrawal
  uses its account's `withdrawalTaxRate` if set. Non-taxable items are unchanged. The
  rate used is shown in the figure's tooltip. Deductions (e.g. RRSP contributions) are
  not estimated.
- **Flows that have not started show their figure too** (owner's request 2026-11-16,
  e.g. pensions at retirement): "from YYYY-MM: X/mo (Y before tax)", the item's first
  month worked out as above (after the tax of then, e.g. the retirement rate), brought
  back to base-month dollars with inflation in the same whole-year steps indexing uses,
  so an inflation-indexed amount stated in today's dollars shows as entered (a pension
  of 2,000 a month shows 1,600 after 20% tax, 2,000 before); it is not part of any card,
  category or section total, which are for the base month.
- **Withdrawals also appear under Pensions** (owner's request 2026-11-16): a withdrawal
  from an account stays a row of its account card and is shown again as a card in its
  person's Pensions category, marked "from <account>", as retirement income. It is
  counted once, under its account, not again in the Pensions total.
- **The flat view's "+ Add" bar is grouped by category** (owner's request 2026-11-16):
  People & settings, Income & pensions, Accounts, Properties & mortgages, Vehicles,
  Expenses, Triggers (`schema.py` `ADD_GROUPS`, served by `/api/schema` as
  `addGroups`; every item type in exactly one group).

## Amendment (2026-11-16): editing, and icons on cards
- **Items can be edited** (decision 7's "later" is now; tag `sm-cards-before-editing`
  marks the state before). The pencil fills the item's type form (the same form as
  adding) with its values, rates as percentages; Save replaces its fields through a new
  engine command, `ops.update_item(scenario, id, values, clear)` (API `POST
  /api/items/update`): the id and type stay, so links and triggers keep pointing at it;
  fields left blank go back to their defaults (cleared); an invalid result is refused
  with the scenario unchanged and the message. The type cannot change (add a new item
  instead).
- **Icons** at the top right of each card that supports them, and in each row of both
  views: "+" (blue) opens the card and shows its "+ Add" buttons; a pencil (green)
  edits; a trash can (red) deletes after a confirmation naming what goes with it. They
  sit in the card's title line without opening or closing it. The Scenario card has
  "+" only (its settings are its form); a person card has all three.
- **On/off checkmark on cards** (owner's request 2026-11-16): each item card has its
  switch (ADR-0064) at the left of its title line, styled as a checkmark (green tick
  when on, an empty grey box when off), so a vehicle or a property can be switched off
  with everything linked to it in one click without opening the card; rows in both views
  use the same checkmark.
- Found while testing: the web module's in-process API calls sent the scenario through
  Flask's JSON, which sorts keys, so saved files had their items' fields reordered
  (since ADR-0069); the call now sends plain `json.dumps` and the order is kept.
- **A refused form keeps what was typed** (owner's report 2026-11-16: an error on add or
  edit lost all input). A command that is turned down renders `<main data-refused>`;
  web.js then reopens the form that was sent (the same "+ Add" button with the same
  link, the same item's pencil, or the settings form), fills in what was typed and shows
  the reasons above it, scrolled into view. Successful commands are unchanged.
- Found from the owner's report (2026-11-16): the card estimates counted a switched-off
  sale, so switching off a planned sale and adding a new one was "sold more than once"
  and the builder failed. Estimates now read sales from the items that are on; and a
  builder view that fails renders the page with the reason (empty choice lists) instead
  of a server error.
