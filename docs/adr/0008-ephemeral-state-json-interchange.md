# ADR-0008: Ephemeral state; JSON as the save and interchange format

- **Status:** Accepted
- **Date:** 2026-11-04

## Context
We want to avoid a database or any persistent backend. The working system will probably
pass data between components, possibly over a network.

## Decision
- Application state is **ephemeral**: it exists only while the application runs.
- The user can explicitly **export and import** the state. Nothing is saved automatically.
- **JSON** (YAML accepted as an equivalent for editing by hand) is both the **save
  format** and the **interchange format** between components.
- Data can be **injected at various points**, e.g. a scenario fed straight into the engine,
  or a saved projection result fed straight into a view.

## Alternatives considered
- A database (local or server): rejected.
- Automatic persistence in browser or local storage: rejected for now.
- A binary or opaque format: rejected, because files must be readable and editable.

## Consequences
- Every domain object that crosses a boundary needs a defined, versioned JSON schema.
  Schema versioning matters because saved files will outlive changes to the code.
- The JSON shapes act as the contracts between engine, controllers and views.

## Amendment (2026-11-04): schema versioning
- Every exported document and interchange payload carries an explicit **schema version**.
- The versioning *strategy* (version format, compatibility rules, migration of old
  files) is still open. See open-questions Q-07.

## Amendment (2026-11-15): the browser tab keeps the working scenario
- The web front-end keeps the scenario in the tab's `sessionStorage` (ADR-0069): it
  survives a refresh, not closing the tab. This is not persistence across sessions;
  saving a file stays explicit, and the page warns before a tab with unsaved changes is
  closed. `localStorage` (kept across sessions) stays rejected.
