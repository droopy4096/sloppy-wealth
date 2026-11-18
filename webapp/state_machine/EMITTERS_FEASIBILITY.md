# Event emitters: feasibility (branch poc/state-machine)

## 1. Verdict
**Feasible, and close to the current code.** It is mostly a refactor that splits each
handler's `fire()` into two steps: *decide* (the emitter, which owns the rule) and
*apply* (the event, which mutates the Household). It is not a rewrite.

Caveats:
- **Do not compute state-dependent amounts at emit time.** The Household changes inside
  the month: a sale pays off a loan before debt service, a contribution lands before a
  withdrawal, and tax needs the month's accumulator. So either poll emitters per phase,
  or have events carry *intent* ("withdraw up to X") that is resolved when applied.
- **Order is still the hard part.** Parity needs the 17-phase `(phase, ordinal, sub)`
  order exactly. Emitters do not remove that need; they only move it.
- Most ledger lines come from recurring processes, as README notes. So the event stream
  will be long: about 5–15 events per item per month. This costs some performance and
  makes debugging noisier. It is not a correctness problem.

Distance from the current code:

| Already matches | Differs |
|---|---|
| `@item_type` factories = emitter constructors (one per form item type, plus a registry) | Factories return handlers that are **precompiled per phase**, and `Clock` calls `fire()`, which mutates directly |
| `Event` (one-shot, dated) and `Process` (window `first..last`, `due(m)`) = emitter schedules | There is no Event value object between the decision and the mutation, so there is no event stream/log |
| `Household` is the main object with aggregates, `move`, tax accumulator, month state | Some intra-item logic lives inside one handler (DebtService runs renewal, then accrue or pay, then extras), so it is not separate events |
| Rules are separate (`TaxRule`, `WithdrawalTaxRule`, `IndexingRule`) | `Clock.run` is the "Scenario loop", but it iterates over handlers, not emitted events |
| `RetirementEvent` already works as a runtime state change (D2) | Some cross-item wiring happens at compile time (`env.bucket`, `env.sales`), i.e. modifiers are folded into their host |

## 2. Model sketch
```
class Event:           # value object, immutable intent
    key: (phase, ordinal, sub)        # for ordering and ledger order
    source: str                       # item id (ledger attribution)
    def apply(self, household) -> None   # resolve state-dependent parts here, then household.move(...)

class Emitter:         # one per scenario item (the form input)
    ordinal: int                      # item index / holding slot
    schedule: Schedule                # OneShot(m) | Window(first, last) | Always | Anniversary
    def emit(self, month, household, phase) -> Iterable[Event]   # may read state, never writes it

class Rule: ...        # unchanged: TaxRule, IndexingRule, WithdrawalTaxRule, ...

class Scenario:
    def run(self):
        for e in emitters: e.initial(household)          # INITIAL (carry-ins, accounts at start)
        for m in months:
            household.begin_month(m)
            for phase in MONTHLY_PHASES:                 # poll per phase (recommended)
                evs = [ev for e in emitters_by_phase[phase] if e.schedule.due(m)
                          for ev in e.emit(m, household, phase)]
                for ev in sorted(evs, key=attrgetter("key")): ev.apply(household); log.append(ev)
```
- **How ordering works:** poll emitters per phase. Within a phase, sort by
  `(ordinal, sub)`. This reproduces `Clock` exactly, and the uniqueness check in
  `Clock.register` carries over to emitter registration. The alternative is to emit
  everything at the start of the month and sort by the full key. That is only safe if
  every event resolves its amount in `apply()`, so it is stricter and more fragile.
  Recommendation: poll per phase **and** resolve in apply, which covers both cases.
- How state-dependent emission works:
  - **Withdrawal:** the emitter emits `Withdraw(account, requested)`. `apply` caps the
    amount at the current balance and skips if the balance is None or 0. Strategy state
    (the percent anniversary, the latched even amount) stays on the emitter. The emitter
    may read `household.opening`.
  - **Payoff (lumpSum with `payOff`):** emits `Prepay(loan, amount=None)`. `apply` uses
    the balance at that moment.
  - **Sale:** emits `Sale(asset)`. `apply` emits or performs the follow-up movements:
    SALE, SELLING_COST, `LOAN_PAYOFF` for each secured loan (current balances), PENALTY.
    Choose one: either keep these as a single compound event (simplest, gives parity), or
    have the Household *dispatch* follow-up events (`Sale -> LoanPayoff*`) inline,
    depth-first, which keeps the ledger order.
  - **Tax:** the scenario-level `TaxEmitter` emits `TaxDue()` in phase TAX. `apply` runs
    `TaxRule` on `household.tax`. Retirement: the `RetirementEmitter` emits `Retire()` in
    OPEN (sub 0), as today.
  - **Mortgage service:** emits, in order (sub 0..n): `Renew?`, then `Accrue` or
    `SettleAccrued` + `Interest` + `ScheduledPayment`, then `Prepay*`. The emitter checks
    `is_opened` and `balance > 0` at emit time (SERVICE_DEBT runs after SELL, so this is
    correct when polling per phase).

## 3. Form/JSON item to emitter mapping
| Item type | Emitter kind | Events emitted |
|---|---|---|
| property, vehicle | one-shot dated (purchase/carry-in) + recurring | Purchase/CarryIn; Appreciation (GROW); vehicle Maintenance (MAINTAIN) |
| mortgage | one-shot + recurring, state-gated | LoanAdvance; DebtService sub-events |
| account | one-shot (or initial) + recurring | AccountOpening; Return (GROW) + investment income tax |
| pension | initial + windowed recurring + always | PensionCreation; PensionPayment; Revaluation |
| income, expense | windowed recurring, indexed | Income (+taxable) / Expense |
| contribution | windowed recurring | Contribute (+match, +deduction) |
| withdrawal | windowed recurring, state-capped | Withdraw (+withdrawal tax rule) |
| transfer, improvement, marketAdjustment | one-shot dated | Transfer / Improve+Revalue / Adjust |
| sale | one-shot dated (or at retirement), compound | Sale -> LoanPayoff* -> Penalty |
| retirement (+ legacy `retirementDate`) | scenario-level, one-shot | Retire |
| (none: tax, incomeMode, inflation) | scenario-level, always | TaxDue; settings stay on Household |

**Modifiers** (they change another emitter rather than act on their own):
renewal, extraPayment and lumpSum modify a mortgage. improvement, marketAdjustment and sale
modify an asset.
- Today they are folded in at compile time (`env.bucket`, `env.sales`), and the host
  runs them.
- **Recommended model:** a modifier is its own emitter, but it emits at its **host's
  key**: `(host.phase, host.ordinal, sub)`. For example, the Sale emitter emits in SELL
  at the asset's slot, because the reference loops over holdings. Extras emit in
  SERVICE_DEBT at the mortgage slot, after the scheduled payment, in item order.
- The form then shows each modifier as a child of its host emitter, as the builder
  already does with mortgage/property selects.
- One caveat: a renewal must apply *before* the payment, and "last renewal per month
  wins". So the host emitter still needs to query its modifiers, or the modifiers need
  sub-ordering such as `sub=(stage, item_index)`.
- improvement and marketAdjustment are not tied to the host's slot (they use the item
  index), so they can stay plain one-shot emitters.

## 4. Parity
**Yes, achievable.** The safety net already exists: `run_reference_tests.py` (151),
`tools/diff_engines.py` (242 scenarios, byte-identical), and package tests WP0–WP8. The
first pass should be a pure refactor, with every diff kept at 0 after each step.

Risks:
1. **Emit-time vs apply-time values.** Any amount read too early, e.g. an emitter reading
   the balance before a same-month sale or contribution, silently changes results. The
   kitchen_sink and ordering_quirks fixtures cover this.
2. **Order keys for modifiers and compound events.** The sale's LOAN_PAYOFF order across
   multiple secured loans, renewal before payment, extras in item order, and the
   "last renewal wins" duplicate rule.
3. **Rounding and quirks stay in apply.** `move()` rounding, 0 moves recording nothing,
   Decimal('0') vs '0.00', the late-first-payment window that drops extras. These must
   not move into emitters.
4. **Results expect holdings in slot order with empty points** (D1). This is unchanged,
   provided Household keeps `_order`.

## 5. Effort and plan
Effort: about 1–2 focused days. Most of the ~2,700 lines are reused. The touched parts
are `base.py`, `clock.py` (into `scenario.py`), `compiler.py`, and the `fire`/`run`
bodies of ~20 handler classes, which split into an emitter and its events.

1. **Core:** add `Event` (value, key, apply), `Emitter` (schedule, emit) and a `Scenario`
   loop with per-phase polling. Add an adapter so old Handlers can run as emitters. Diff
   = 0.
2. **Simple types:** convert one-shot items (transfer, improvement, marketAdjustment,
   purchase, account opening, loan advance). Diff = 0.
3. **Recurring items:** convert income, expense, contribution, withdrawal, growth,
   pension, maintenance, tax and retirement. Add the event log as a by-product (the
   ledger stays the output).
4. **Mortgage and sale:** convert the mortgage with its modifier emitters, and the sale
   compound. Remove `env.bucket`/`env.sales` folding where possible. Diff = 0.
5. **Update the docs:** INTERFACES/OBJECTS. Optionally have the builder form group
   modifiers under their host.

Decisions for the user:
- **D-E1:** Should modifiers (renewal/extra/lumpSum; sale/improvement/adjustment) be
  separate emitters keyed at their host's slot, or parameters of the host emitter? This
  is also a form/UI choice.
- **D-E2:** For ordering, poll per phase (recommended, gives exact parity), or use one
  sorted event list per month? Either way, should every event resolve amounts in
  `apply()`?
- **D-E3:** Should compound effects (sale -> loan payoffs) be one event, or cascaded
  follow-up events dispatched by the Household?
- **D-E4:** Should the event log become a public output next to the ledger (a new API
  field, a deliberate interface change), or stay internal?
