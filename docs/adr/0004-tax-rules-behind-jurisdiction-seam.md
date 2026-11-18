# ADR-0004: Simple, static tax rules behind a jurisdiction seam; Canada first

- **Status:** Accepted
- **Date:** 2026-11-04

## Context
Account types (TFSA, RRSP, non-registered) behave differently for tax. We want useful
results without building a full tax engine, while keeping room to grow.

## Decision
- The first jurisdiction is **Canada**.
- Tax modelling is **simple**: tax-free, tax-deferred and taxable treatment categories with
  simple rules, and no income-tax bracket engine.
- Rules are **static** within a projection.
- The engine **queries** tax rules through an interface (a tax-rules or jurisdiction
  provider) and never embeds them as constants.

## Alternatives considered
- Canadian rules hard-wired into the engine: rejected, because adding another jurisdiction
  would mean rewriting the core.
- Several jurisdictions or a full bracket-based model from the start: unnecessary for now.

## Consequences
- Adding another jurisdiction, or rules that vary by year (e.g. indexed contribution limits,
  changing brackets), means a new implementation of the interface, not changes to the core.
- The interface has to take the date or period as an input now, even though the rules are
  static, so time-varying rules fit later without changing the API.
