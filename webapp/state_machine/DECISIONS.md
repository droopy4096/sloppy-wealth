# State-machine re-implementation: coordinator decisions

Coordinator: main session. Inputs: FEASIBILITY.md (90301c6). Branch: `poc/state-machine`.
`main` and `poc/python-flask` are protected: never modified.

| # | Question (FEASIBILITY.md §7) | Decision |
|---|---|---|
| D1 | Aggregates PLANNED from the start vs created by events | **Events create the aggregates** (the user's design). Parity of output order is restored by ordering: the household keeps aggregates keyed and iterated by **scenario item index**, and result assembly emits a holdings entry for every item that would have a holding, including ones not created yet (empty points). No PLANNED placeholder objects. |
| D2 | Retirement: resolved at load vs runtime event | **Runtime `RetirementEvent`**, dispatched first in its month: it sets `household.retired` and switches the tax rate. Flows tied to retirement start/stop by consulting household state. The retirement *date* is also known up front (scenario lookahead) where forward-looking values need it (pension value, drawdown months). Results must be identical either way. |
| D3 | Validation | **One pure function, ported verbatim** (identical first error message). |
| D4 | Standalone package; which engine leads afterwards | **Standalone**: `webapp/state_machine/` must not import `webapp/engine.py` (only the differential harness loads it, as the reference). Which engine leads after parity is the user's call later. |
| D5 | Commit fixtures like the owner's personal scenario | **No** personal data committed. The harness takes extra local paths on the command line. WP2 adds a **synthetic kitchen-sink scenario** (every item type and same-month interaction, invented figures) under `webapp/state_machine/fixtures/`. |

## Process
- One commit per task, message prefix `state-machine:` (or `sm-wpN:` on sub-branches); git log is the transaction log.
- Parallel work packages run on sub-branches `poc/sm-wpN-<name>` cut from `poc/state-machine` after WP0, merged back by the coordinator.
- Files are added by explicit path; never commit the owner's personal scenario files (see `.gitignore`), diagrams/svg/.

## Event emitters (2026-11-10, user decisions on EMITTERS_FEASIBILITY.md)
Form inputs become **event emitters**: event-producing factories with their own rules.
The Scenario walks the date range over the Household (main object), asks emitters for
events and applies them.

| # | Question | Decision |
|---|---|---|
| D-E1 | Modifiers (renewal, extraPayment, lumpSum on a mortgage; sale, improvement, marketAdjustment on an asset) | **Separate emitters attached to their host**, timed at the host's position; the form groups them under their host. One form input = one emitter. |
| D-E2 | How the loop collects events | **Order number built into each emitter class** (instance may override). The Scenario sorts all emitters by order (ties: scenario item index) and splits them into as many phases as it needs; each month it walks the sorted list, asks each emitter for events and applies them immediately, so later emitters see earlier state. Reordering = changing a number. An item acting at several points of a month (e.g. mortgage advance vs servicing) yields several emitters with their own orders. Defaults reproduce today's 17-phase order (parity). |
| D-E3 | Sale and secured loans | **Follow-up events**: the sale event emits a payoff event per secured loan, then the penalty, applied immediately; each loan settles itself. |
| D-E4 | Event log | **Public**: `run_detailed()` gains an `events` key and the app a view of it. A deliberate interface addition; rows, holdings, ledger and tax stay identical, the diff harness ignores `events`. |

## Iterations and the reference engine (2026-11-10, user decisions)
| # | Question | Decision |
|---|---|---|
| D4 (resolved) | Which engine leads for new features | **Iteration 2 (this event-emitter engine) is the only PoC.** New features go here. |
| D6 | Branch layout | `poc/state-machine` was **rebased onto `main`** with its history kept (baseline commit importing iteration 1's `webapp/`, then the replayed commits; pre-rebase history in tag `poc/state-machine-before-rebase`). `poc/python-flask` is **kept, not renamed**: iteration 1, tag `poc-iteration-1`. |
| D7 | Iteration 1 on this branch | **Retired.** `webapp/engine.py`, the parity shims and the diff/record tools were deleted; `app.py` and all tests use `state_machine.engine`. Iteration 1's results are frozen in the golden suite (`tests/golden/`). For iteration-1 references use branch `poc/python-flask`. |
