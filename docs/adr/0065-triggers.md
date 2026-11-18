# ADR-0065: Triggers instead of "at retirement" fields

- **Status:** Proposed (experiment on branch `poc/sm-triggers`; the owner test-drives it
  before deciding)
- **Date:** 2026-11-12
- **Relates to:** ADR-0059 (retirement event, at-retirement fields), ADR-0061 (one
  retirement per person, `retirementOf`), ADR-0062 (adjustment), ADR-0064 (enabled)

## Context
Items tied to retirement carry their own fields: `startsAtRetirement`,
`endsAtRetirement` (income, expense, contribution, withdrawal, extraPayment, pension) and
`atRetirement` (sale, lump sum, transfer), with `retirementOf` choosing the person. Each
type handles them separately (`flow_window`, sale, loan, transfer, 18 validation checks,
builder choices), and only retirement can be the anchor.

## Decision (proposed)
A **`trigger` item** ties a date of one item to the date of another item, an **event**:
`{"type": "trigger", "event": <item id>, "target": <item id>, "action": "start" | "end" |
"startAndEnd"}`. It has its own form in the builder, like any item, and is listed under
its target.

- **Static (compile time):** right after older forms are converted and off items are left
  out, a resolve step writes the event's date into the target:
  - `start`: the target happens or starts in the event's month (its date field:
    `startDate`, `saleDate`, `paymentDate`, `transferDate`, `openedDate`, …); the
    trigger's date replaces the target's own.
  - `end`: the target's last month is the month before the event (its `endDate`, or the
    earlier of the two if it has one; recurring items only).
  - `startAndEnd`: only in the event's month (recurring items only).
- **Event:** any item with a date (retirement, sale, purchase, account opening, transfer,
  lump sum, a flow's start, …), including one whose date comes from another trigger
  (resolved in dependency order; a cycle is an error).
- **Logged:** each trigger records one entry in the event log in its month (no state
  change), like an adjustment.
- **Older files:** `startsAtRetirement`, `endsAtRetirement` and `atRetirement` are
  converted on load to triggers on the retirement event of the item's person; the engine,
  validation and builder no longer know the fields.
- **On/off (ADR-0064):** a trigger refers to its event and target, so it is off when
  either is off. A target whose trigger is off keeps its own dates.

### Mechanics kept as before (defaults)
- Pensions and withdrawals with a blank start still start at their person's retirement
  (implicit, not a trigger); `retirementOf` remains for that.
- The retirement tax rate switch belongs to the retirement event.
- `enable` / `disable` actions equal `start` / `end` on a static timeline; they are left
  for run-time triggers (option B, not built).

### Builder (experiment)
- The "starts / ends / sells / paid on / transfers at retirement" choices and
  `retirementOf` are gone from the forms; an end is just `endDate` (blank = never).
- Triggers are listed under their target (also under a modifier, e.g. a sale), marked ⚡.
- An item added without its date (because a trigger will set it) is kept switched off
  (ADR-0064) with a message; adding a start trigger for it switches it on.
- A salary no longer pre-fills "ends at retirement": add an end trigger.
- The Items table's Details name the trigger that sets a date ("startDate=⚡ With
  House"; with its own endDate too: "2040-01-01 or ⚡ … if earlier"), say what a blank
  date means ("endDate=never", "startDate=at retirement", …) and leave out other empty
  fields (no "-"). The file keeps empty strings.

## Amendment (2026-11-13): `on`, and `attachedTo` replaced
- A trigger may say which date of its event counts: `on: start` (default, the event's
  date) or `on: end`: the month after the event's last month (recurring items) or its
  sale month (property, vehicle). `end` on an event's end therefore makes the target's
  last month the event's last month. An event that never ends never fires: an end
  trigger leaves the target as it is; a start trigger makes the target never run.
- An expense's `attachedTo` (ADR-0040 amendments) is replaced by triggers: "With X"
  (start at X's purchase or start) and "Ends with X" (end, `on: end`). Older files are
  converted on load; the start trigger is left out when the expense's own startDate is
  not earlier than X's. Results are unchanged. The engine's emit-time asset check and
  the income-window cut are removed; the builder's attachedTo field is gone.
- On/off and delete: an item started by a trigger whose event is off (or deleted) is
  off (deleted) too, as an attached expense was with its asset; a target of an end
  trigger just runs on.
- Known difference: an attached expense with its own start before the purchase used to
  be indexed from its own start (paid from the purchase); converted, it is indexed from
  the purchase.

## Alternatives considered
- **Keep the at-retirement fields** (status quo).
- **Run-time triggers** (option B): the trigger listens to the event log during the run
  and switches emitters; needs dates unknown before the run (indexing, anniversaries,
  validation). Possible later with the same item.

## Consequences
- Items lose their at-retirement fields; any dated item can anchor another.
- Results are unchanged (golden suite); error messages about at-retirement items change.
- Builder: the "at retirement" choices are replaced by trigger items; a salary no longer
  pre-fills "ends at retirement".
