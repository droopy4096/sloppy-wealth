# ADR-0023: Tags group scenario objects for attribution and time shifting

- **Status:** Accepted
- **Date:** 2026-11-04

## Context
Comparing options such as "new car vs lease vs used car" needs the total cost of each
option, i.e. the sum of every movement that belongs to it. Shifting an option in time (e.g.
buying the car 3 months later) must move all of its related dates together, such as the
warranty boundary in the maintenance rate. Dates are independent (ADR-0007), so the model
itself does not link them.

## Decision
- Holdings, cash flows, events, event generators and rate generators can carry **tags**
  (a set of labels, e.g. `vehicle`).
- **Attribution**: every movement in the result carries the tags of the object that
  produced it. Results can be aggregated by tag (e.g. the total cost of `vehicle`).
- **Shifting**: the time-shift tool can select objects by tag and shift them all by the
  same offset (ADR-0007).

## Alternatives considered
- Explicit groups as a container type: heavier, and an object could belong to only one
  group.
- Anchored dates: rejected in ADR-0007.

## Consequences
- Shared assumptions (e.g. the inflation generator) are simply left untagged, so shifting an
  option never moves them.
- Movements in the result need a tags field.
