# ADR-0012: One-off events, recurring cash flows, and event generators

- **Status:** Accepted
- **Date:** 2026-11-04

## Context
A scenario contains things that happen once (buy a house, sell a car, a lump-sum
prepayment), things that recur (salary, rent, contributions, doubled mortgage payments
from a date), and changes that follow a pattern (salary raised 2% each year on a given
date).

## Decision
- An **Event** is a one-off occurrence with an absolute date.
- A **Cash Flow** is a recurring movement of money with a start date and an optional end
  date. Recurring changes such as "double payments from July 2027" are modelled as cash
  flows.
- An **Event Generator** (event factory) is a rule that **produces concrete events**
  following a pattern, e.g. "salary +2% every 1 April from 2027". Generators are expanded
  into events during the event-placement stage (ADR-0010).
- Events, cash flows and event generators are all **time-shiftable** (ADR-0007).

## Alternatives considered
- Treating everything as an event: a recurring cash flow would become hundreds of events
  to edit and shift.
- Building recurrence rules into events themselves: the nuanced patterns would end up
  inside one overloaded type.

## Consequences
- The scenario input stores **generators**, not the events they produce. Generated
  events exist only in the pipeline state after event placement, so shifting a generator
  shifts every event it produces.
- Generators are a natural extension point: new patterns mean new generator types.
