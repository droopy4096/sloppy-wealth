# ADR-0066: Timeline view of a scenario

- **Status:** Proposed (experiment on branch `poc/sm-triggers`, with ADR-0065)
- **Date:** 2026-11-13
- **Relates to:** ADR-0065 (triggers), ADR-0064 (enabled), D-E1 (modifiers at their host)

## Context
The builder lists items as a table. With triggers (ADR-0065) the dependencies between
items (a property tax that lives with its house, a salary that ends at retirement) are
separate rows; the owner asked for a picture of the scenario over time.

## Decision
- A **Timeline** tab draws the scenario as an SVG built by the app (`webapp/timeline.py`,
  no JavaScript library), on a time axis of the horizon, one month accurate:
  - each lasting item (recurring flow, asset, mortgage, account) is a **lane** from its
    first to its last month, clipped to the horizon;
  - git-graph style, a lane **branches off** its parent's lane where it starts and
    **merges back** where it ends: the parent is its host (D-E1: a mortgage's property, a
    contribution's account, a flow's adjustments, ...), else the lasting item whose date
    starts it by a trigger (e.g. property tax with the house), else the household trunk;
  - one-off items (sale, renewal, adjustment, retirement, ...) are **dots** on their
    parent's lane, else on the trunk; each retirement also gets a vertical guide;
  - triggers are dashed amber links (branch/merge) or **arrows** from the event's month
    to the start or end they set;
  - items switched off are drawn greyed at the dates they would have.
- Dates come from the scenario with its triggers resolved (the dates the engine uses);
  a mortgage ends at its last movement in the run (payoff or sale); a modifier lane
  stops with its host. Names and dots link to the item's row in the builder.

## Amendment (2026-11-13): vertical graph, like `git log --graph`
- The Timeline tab opens on a **vertical graph** (`timeline.graph`): one row per
  happening (a lane's start or end, a one-off item) in time order, not to scale; each
  lasting item is a column that branches off its parent's column and merges back,
  columns are reused once free (as git does); each row has a line of text: the month,
  the item, its type, and "⚡ <trigger>" when a trigger sets that date. Within a month:
  one-off items, then ends (children before their parent), then starts (parents first).
- "Oldest first" is the default (a plan reads forward); "newest first" (git's order) and
  the horizontal **time axis** (to scale) are a click away (`?order=newest`,
  `?view=axis`).
- **One row per month** (amended later the same day): the month's nodes sit side by side
  on one row; after the month, its happenings are comma-separated: one-off items, then
  "ends:", then "starts:" (each name links to the builder, has its tip, and "⚡" when a
  trigger sets that date); a long month wraps onto more lines under the same date. A
  column freed by an end is reused from the next month.
- Every point, line and curve has a mouse-over tip saying what it stands for (a lane: the
  item, its type, months and the item it belongs to; a curve: the start or end and its
  trigger; a point: the start, end or one-off item and its trigger; "switched off" when
  off). Thin lines have an invisible 10px-wide hover area.

## Alternatives considered
- **Mermaid `gitGraph`**: branch/merge look, but no time scale (commits evenly spaced).
- **Mermaid `gantt`**: time scale, but no arrows or branches.
- **A JavaScript charting library**: interactive, but a new dependency for a PoC.

## Consequences
- A read-only view; no input is changed. Hover shows dates, click finds the item.
- Many items starting at retirement give a bundle of arrows on its guide line.
