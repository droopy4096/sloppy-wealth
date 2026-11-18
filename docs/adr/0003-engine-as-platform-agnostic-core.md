# ADR-0003: The engine is a platform-agnostic core; everything else is an adapter

- **Status:** Accepted
- **Date:** 2026-11-04

## Context
The way the tool is distributed is undecided: an offline HTML app, a web service with an
app, or a mobile app. More than one competing front-end (e.g. mobile and browser) may be
built. The system has an MVC-style split, and the View is the least defined part.

## Decision
- The calculation **engine** is designed first, as a self-contained core with no
  dependencies on UI, transport, storage or platform.
- Controllers, views, transport (HTTP or in-process) and persistence (import/export) are
  **adapters** around the engine.
- The **implementation language is deferred**: it will be chosen in a later ADR, once the
  requirements are clear.

## Alternatives considered
- Design around a specific UI or framework first: rejected, because it would lock in the
  distribution model before it is decided.

## Consequences
- The engine's API must be expressible as data in and data out (see ADR-0008), so it can be
  called in-process or remotely.
- Several front-ends can share one engine.
- **Open:** where the engine runs is undecided. Candidates include fully client-side
  (offline HTML, mobile), local execution, and a stateless serverless function (e.g. a
  Google Cloud function) that anyone can invoke for backend tasks. See open-questions Q-01.

## Amendment (2026-11-04): engine is stateless per invocation
- None of the hosting candidates can be ruled out, so the engine must suit all of them,
  serverless included: **each invocation is self-contained**. Its input is the complete
  scenario (or set of scenarios) and its output is the result. Nothing is kept between
  calls.
- This matches ADR-0008 (ephemeral state, JSON payloads) and ADR-0006 (a goal optimiser
  may call the engine many times).
