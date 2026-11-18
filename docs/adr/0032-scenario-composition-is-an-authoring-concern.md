# ADR-0032: Composing scenarios from a base is the authoring tool's concern

- **Status:** Accepted
- **Date:** 2026-11-04

## Context
The scenarios in a set repeat the same income, expenses, accounts and assumptions, and
differ only in one area (e.g. housing).

## Decision
- The engine always receives **complete, self-contained scenarios** (ADR-0003, ADR-0008).
- Deriving variants from a base (e.g. "copy base, replace everything tagged housing:*") is
  done by **authoring tooling** outside the engine.

## Consequences
- The engine and its JSON contract stay simple, with no inheritance or overlay resolution.
- Authoring tooling becomes a component to design later (with the time-shift tool and the
  ages-to-dates conversion).
