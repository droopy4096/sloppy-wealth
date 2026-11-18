# ADR-0064: Item on/off switch (`enabled`)

- **Status:** Accepted
- **Date:** 2026-11-12
- **Relates to:** ADR-0012 (events and generators), ADR-0061 (persons), ADR-0062
  (adjustment), D-E1 (modifiers at their host)

## Context
The owner keeps several variations of a plan (sell or keep a property, retire earlier,
replace the vehicles, one earner or two). Today each variation is a separate file, or
items are deleted and re-entered. One file should hold all of them, with items switched
on and off in the builder instead.

## Decision
Every scenario item has an optional **`enabled`** field (JSON boolean, default `true`).
An item with `"enabled": false` is **off**: the engine runs as if it were not in the file.
The builder shows an on/off switch on every item (a checkbox at the front of its row).

**Dependents follow their target (cascade, owner's choice).** An item is also off while
an item it refers to is off, transitively:
- link fields: `property`, `mortgage`, `account`, `flow`, `attachedTo` (the same links
  the builder's Delete follows);
- person fields: `owner`, `contributor`, `retirementOf` (switching a person off switches
  off their own items, retirement event and contribution room).

The builder shows such items as "off via <target>". Their own `enabled` is unchanged, so
switching the target back on brings them back.

### Mechanics (defaults; not separate owner decisions)
- Static: an item is on or off for the whole run. Switching off during a run (dated
  suspend/resume) is not part of this decision; it would apply only to recurring cash
  flows (see Alternatives).
- Off items are removed right after the older forms are converted (`upgrade`), before
  validation and compilation, so off items are neither validated nor run. The file keeps
  them unchanged.
- Items with a blank owner belong to the first person that is on.
- Items tied to retirement by date (`atRetirement`, `startsAtRetirement`) do not refer to
  the retirement event by id: switching the event off leaves them on, and validation
  reports any that then need a retirement date.
- `enabled` must be a boolean if given.

## Alternatives considered
- **Validation error** for a dependent still on while its target is off: every
  dependent must be switched by hand; flipping a variation takes many clicks.
- **Error except for modifiers**: halfway; the line between a modifier and a reference
  (a withdrawal from an account) is not obvious to the user.
- **Dynamic suspend/resume during a run**: possible (the runner asks every emitter every
  month), but structural emitters (loan servicing, growth, tax, openings) cannot be
  sensibly paused, one-shot events would be lost, and annuity/percent amounts reset on
  anniversaries. Kept for later, for recurring cash flows only.

## Consequences
- One file can hold several variations; results reflect only the items that are on.
- Default `true`: existing files and the golden suite are unchanged.
- Off items are not validated, so an off item may be incomplete or wrong until it is
  switched on (switching it on is refused with the error, like any edit).
