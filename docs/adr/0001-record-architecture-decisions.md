# ADR-0001: Record architecture decisions and diagrams as text

- **Status:** Accepted
- **Date:** 2026-11-04

## Context
The project is in a planning phase. The output is blueprints (not code): decisions and
diagrams that describe the intended shape of the system. These need to be versionable,
diffable and reviewable.

## Decision
- Decisions are recorded as ADRs in `docs/adr/NNNN-kebab-title.md` using `0000-template.md`.
- Diagrams (class, sequence, state, mindmap, etc.) are written in Mermaid and stored in
  `diagrams/*.mmd`.
- ADRs are never rewritten after acceptance; a changed decision gets a new ADR that
  supersedes the old one.

## Consequences
- Everything lives in plain text and can go under git.
- Diagrams render in GitHub/GitLab/most IDEs; layout control is limited compared to
  dedicated modelling tools.
