# Implementation status: planning decisions vs the PoC

Audit date: 2026-11-10. PoC = **iteration 2** on `poc/python-flask` (developed on `poc/state-machine`, merged 2026-11-18; `webapp/state_machine/`,
UI `webapp/web/` over the JSON API `webapp/api.py`, spec `webapp/SPEC.md`). Iteration 1 is frozen on tag `poc-iteration-1`; its
results are the golden suite, so iteration 2 behaves the same.
Verified against the code (grep/read) and the test suites (175 app tests + 214 package tests pass).
Paths are relative to `webapp/state_machine/` unless they start with `webapp/`.

**Status keys:** Implemented · Partial · Not implemented (decided, not built) · N/A (planning-only,
deferred, superseded, or "no change" decisions).
The planning model is much broader than the PoC. "Not implemented" is a normal status.

**Summary:** ADRs 0001–0061: 16 Implemented, 26 Partial, 14 Not implemented, 5 N/A.
CRITIQUE findings (37): 13 implemented, 13 decided but not built, 11 need no code (no change or documentation only).

PoC field names differ from the domain model: `dollarsOf` = `baseDate`; `openedDate` / `openingBalance` = `openedOn` / `openingValue`;
`annualReturn` = `returnRate`; `nonRegistered` / `rrsp` / `tfsa` = TAXABLE / TAX_DEFERRED / TAX_FREE.
The PoC has no warnings channel: every "the result warns" decision is unbuilt.

## 1. Per ADR

| ADR | Topic | Status | Where / gap |
|---|---|---|---|
| 0001 | ADRs and diagrams as text | N/A | Process |
| 0002 | Personal tool, single economic unit | Implemented | One household (`household.py` Household), no auth |
| 0002 am. | Persons inside the economic unit | Implemented | `household.persons` (ADR-0061) |
| 0003 | Platform-agnostic engine core | Implemented | Package `state_machine` has no Flask import; `api.py` run/run_detailed; UI is an adapter |
| 0003 am. | Stateless per invocation | Implemented | `engine.run(scenario)` builds a fresh Household each call |
| 0004 | Tax rules behind a jurisdiction seam | Partial | ADR-0071 seam: `state_machine/jurisdictions/` (Canada in `ca/`); `rules/tax.py`, `rules/capital_gains.py` |
| 0005 | Deterministic, time-varying rate series | Partial | Deterministic yes; rates constant per item (only renewals and the retirement tax rate change a rate); no rate-source seam |
| 0006 | Scenarios, goals, comparable results | Partial | Scenario + horizon + result rows; `/compare` (webapp/web/pages.py, `/api/compare`); no goals |
| 0006 am. | Goals observed, not solved | Not implemented | No goals |
| 0007 | Monthly time on real dates, dated events | Partial | Monthly calendar (`dates.py`, `runner.py`); shift tooling not built |
| 0008 | Ephemeral state, JSON save/interchange | Partial | Browser tab sessionStorage (ADR-0069) + Save (in the browser) / `/load`; no YAML; no injection at stage boundaries |
| 0008 am. | Schema version | Implemented | `schemaVersion: 1` checked in `state_machine/ops.py` `load`; strategy still open (Q-07) |
| 0009 (+am.) | Decimal money, half-even, 2 dp per movement | Implemented | `arith.py` `money`, `household.move` rounds every movement |
| 0010 | Pipeline of pure stages + one stepping stage | Partial | Different design: compile (`compiler.py`) → `ScenarioRunner` (`runner.py`) → `results.assemble`; stages are not pure or serialisable (DECISIONS D-E1..D-E4) |
| 0011 | Holding hierarchy | Implemented | `base.py` Aggregate; `holdings/` Cash, RealEstate, Vehicle, Mortgage, InvestmentAccount, Pension |
| 0012 | Events, cash flows, event generators | Partial | Events (`events/`) and flows (`flows/`) yes; event generators no |
| 0013 | Per-flow indexing; nominal and real reporting | Implemented | `arith.indexed`, `rules/indexing.py`; real columns `results.add_real_net_worth` |
| 0013 am. | Amount in dollars of its start | Implemented | `flows/income_expense.py` `flow_terms` |
| 0013 am. | Base date named and settable | Implemented | Scenario `dollarsOf` (`dates.base_month`); columns labelled with it (webapp/web/templates/run.html) |
| 0013 am. | Yearly step on the anniversary | Implemented | `arith.indexed` (full years since start) |
| 0013 am. | Base date is scenario input | Implemented | `dollarsOf` saved in the scenario |
| 0013 am. C-P14 | Base date input only; separate `displayDollarsOf` | Not implemented | One `dollarsOf` drives both inputs (pensions, `amountIn: base`) and display; builder labels it "Show real values in dollars of" |
| 0013 am. | `amountIn: base` | Implemented | `flows/income_expense.py` `flow_terms` |
| 0014 (+am.) | Global/local goals, REACH/MAINTAIN | Not implemented | — |
| 0015 | Debits capped, shortfalls | Not implemented | PoC simplification: cash may go negative (C-M17) |
| 0016 | Reference birth date, ages | Not implemented | — |
| 0017 | Capital gains on asset sale, principal-residence flag | Not implemented | `rules/capital_gains.py` CapitalGainsRule is a no-op (C-M8 gap) |
| 0017 am. | One flat rate for every effect | Implemented | `effectiveTaxRate` in `rules/tax.py` TaxRule (plus the RRSP's own `withdrawalTaxRate`, ADR-0035) |
| 0017 am. | Taxable-account income = income yield only | Not implemented | Whole non-registered return is taxable, `max(0, ·)` (`Jurisdiction.on_return`); see ADR-0054 |
| 0017 am. C-P6 | `SaleEvent.taxRate` | Not implemented | No CG tax at all |
| 0017 am. C-P13 | Partial exemption by designated years | Not implemented | See ADR-0056 |
| 0018 (+am.) | Order of steps within a month | Partial | `clock.Order` (income → events → debt service → expenses → maintenance → contributions → withdrawals → growth → tax → close); no capping/shortfalls, no sweeps (7a), no tallies/goals (9–10), no CG tax at sale; costs come after expenses (ADR: before) |
| 0019 | Rate generators; compounding per holding | Partial | Mortgage semi-annual (`arith.monthly_rate`), assets/accounts effective annual → monthly; no RateGenerator types; renewals stand in for TermScheduleRate |
| 0020 (+am.) | Income net, `taxable` flag; JSON false, UI true | Implemented | `flows/income_expense.py` Income adds gross to taxable; tax in the tax step (`rules/tax.py`); UI default in webapp/app.py |
| 0021 (+am.) | Monthly flows; per month/quarter/year | Implemented | `arith.PER`, `flow_amount` |
| 0022 | Variable cost = rate × acquisition price | Not implemented | Only vehicle `annualMaintenance` (fixed amount, optional `maintenanceIncrease`, `holdings/vehicle.py`) |
| 0023 | Tags | Not implemented | Ledger has no tags |
| 0024 | Generic Loan, Mortgage specialisation | Partial | Mortgage only (`holdings/mortgage.py`), secured by a property; sale settles every loan secured by the asset (`events/sale.py` LoanPayoff) |
| 0025 | OneOffTransfer; financed purchase | Partial | Financed purchase: mortgage with `property` and blank start (`dates.mortgage_start`); `transfer` is cash → account only (`events/transfer.py`) |
| 0025 am. | Purchase `marketValue` | Implemented | `events/purchase.py` |
| 0025 am. C-P12 | Closing costs inside the mortgage | N/A | Assumption only; nothing to build |
| 0026 (+am.) | Holdings not owned (lease, buyout) | Not implemented | — |
| 0027 | Tallies, monthly goal evaluation | Not implemented | — |
| 0028 | Scenario sets in lockstep | Partial | `/compare` runs two files side by side, same horizon enforced; no ScenarioSet, lockstep or set goals |
| 0028 am. | Inflation may differ; shown per scenario | Implemented | webapp/web/templates/compare.html header shows each inflation |
| 0028 am. C-P17 | Per-scenario deflator | Implemented | Each run deflates by its own `annualInflation` |
| 0029 | Engine derives loan payments | Implemented | `arith.mortgage_terms`/`annuity`; fixed under prepayments; recalculated at renewal (`Mortgage.renew`) |
| 0029 am. | Final payment clears the balance | Implemented | `Mortgage.pay_scheduled` |
| 0029 am. | First payment month after advance; `firstPaymentDate` | Implemented | `LoanTerms.first_pay` |
| 0029 am. C-P15 | No fixed-payment variable / interest-only loans | N/A | Not modelled by decision |
| 0029 am. C-M6 | Interest adjustment before a late first payment | Implemented | `Mortgage.accrue` / `settle_accrued` (INTEREST_ADJUSTMENT); amortisation from first payment |
| 0029 am. C-M7 | Prepayments shorten "until the next renewal" | Implemented | Default renewal recalculates the payment (`Mortgage.renew`) |
| 0030 | Surplus-cash sweep rules | Not implemented | — |
| 0031 | Selling costs; liquidation net worth | Partial | `sellingCostRate` on the sale (`events/sale.py` SELLING_COST); no liquidation net worth |
| 0031 am. C-P6 | `liquidationTaxRate` | Not implemented | — |
| 0032 | Composition is authoring's concern | N/A | Engine takes complete scenarios; no composition tool |
| 0033 | Revaluation event | Partial | `marketAdjustment` on properties and vehicles (`events/adjustment.py`; vehicles since the 2026-11-11 amendment) |
| 0033 am. | Set value is the month's closing value | Implemented | `events/adjustment.py`, growth skipped (`holdings/real_estate.py`) |
| 0033 am. C-P16 | Market adjustment on accounts | Not implemented | Validation accepts only properties |
| 0034 | Negative-equity sale settlement | Partial | Order SALE → SELLING_COST → LoanPayoff → PENALTY (`events/sale.py`); no CG step; deficit makes cash negative (no shortfall); proceeds always to cash |
| 0035 | Tax-deferred withdrawals; `taxPaidFrom` | Partial | `withdrawalTaxRate`, gross withdrawals (`Jurisdiction.on_withdraw`); tax always from cash |
| 0036 | Pensions as income flows; no RRIF | N/A | Superseded by ADR-0052 (pension holding); "RRIF not modelled" holds |
| 0037 | Period tallies, goal active window | Not implemented | — |
| 0038 | Variant sweeps (authoring) | Not implemented | — |
| 0039 | Even drawdown (fixed at start) | Superseded | Retired by the 2026-11-11 amendment; `even` is read as an unindexed annuity |
| 0039 am. C-P3 | Annuity at expected return, yearly recompute, `indexed` | Implemented (2026-11-11) | `flows/withdrawal.py` AnnuityStrategy; `indexed` = the `indexing` field; about one month's return is left |
| 0039 am. 2026-11-11 | Amount (given/annuity) × indexing; `even` retired | Implemented | `validation.py`, app load conversion |
| 0040 | Minimal input, neutral defaults, implicit cash | Partial | Optional fields default to neutral values; implicit cash; no list of applied defaults |
| 0040 am. | Asset value rate essential | Implemented | `validation.REQUIRED` (`annualAppreciation`, `annualDepreciation`) |
| 0040 am. C-P11 | `sellingCostRate` essential for RealEstate | Not implemented | Optional in validation and UI ("optional") |
| 0040 am. 2026-11-11 | Expense attached to an asset or an income (`attachedTo`) | Implemented (on `poc/sm-triggers`: replaced by triggers, converted on load) | `flows/income_expense.py` ExpenseEmitter asset check; `validation.py`; builder select. Branch: `upgrade.py` `_attached` |
| 0041 | Shift start, end or both | Not implemented | — |
| 0042 | Free income `netOf` | N/A | Deferred |
| 0043 | Renewal and lender switch | Partial | `renewal` (`events/loan.py`, `Mortgage.renew`): new rate, optional new amortisation, `penalty`; no term length / `termAt` |
| 0043 am. C-M7 | `keepPayment` | Partial | `arith.keep_payment_months`, `Mortgage.renew`; fallback noted only in the event log, not as a result warning |
| 0044 (+am.) | Income-less mode; lump-sum source; contributions/withdrawals; pensions still pay | Implemented | `household.covered`, `recurring_source`; `lumpSum.paidFrom`; `holdings/pension.py` |
| 0045 | Rates as fractions, UI percent, range checks | Implemented | `validation.py`; webapp/web/pages.py `percent_to_fraction` |
| 0046 | Improvement event | Implemented | `events/improvement.py`; a mortgage on the property starting that month funds it; no cost basis (no CG) |
| 0047 | Early-closure penalty is manual | Partial | `salePenalty`, renewal `penalty`, lump-sum `penalty` from cash; one penalty per sale, not per secured loan |
| 0047 am. C-P20 | Warning for in-term closure without penalty | Not implemented | No term length, no warnings |
| 0047 am. C-M12 | Penalty from paymentFrom even for outside lump sums | Implemented | `events/loan.py` PENALTY from cash |
| 0048 | Deduction in the same month | Implemented | `Jurisdiction.on_contribute`; `rules/tax.py` |
| 0048 am. | Employer match not deductible; DB contributions deductible | Implemented | `holdings/account.py` accept_contribution; `holdings/pension.py` accept_contribution |
| 0048 am. C-P2 | Refund credit | N/A | Superseded by the pool |
| 0048 am. C-P2 rev. | Carry-forward pool | Implemented | `rules/tax.py` TaxRule (`tax.pool`), `run_detailed()["tax"]` |
| 0048 am. | Deductions and pool per person | Implemented | `Jurisdiction.on_contribute` (contributor), `rules/tax.py` per person |
| 0049 | Percent-of-balance withdrawal | Implemented | `flows/withdrawal.py` PercentStrategy |
| 0050 | Result columns, assets net worth | Partial | `results.row`; no liquidation net worth |
| 0050 am. | Pension value in Investments | Implemented | `results.row` (`account`, `pension`) |
| 0050 am. C-P4 | Pension in liquidation net worth | Not implemented | — |
| 0051 | Contributions and employer match | Implemented | `flows/contribution.py`, `employerMatch` |
| 0052 | Pension holding; retirement date | Partial | `holdings/pension.py` Pension (value, payment, revaluation) |
| 0052 am. | No discounting, amount in base-date dollars (Q-36) | Implemented | `Pension.value` / `payment`; superseded in the plan by C-P4 |
| 0052 am. | `endsAtRetirement`, `startsAtRetirement`, own start/end, member contributions | Implemented | `flows/income_expense.py`, `holdings/pension.py`, `flows/contribution.py` |
| 0052 am. C-P4 | `pensionDiscountRate` (2% real) | Not implemented | Value undiscounted |
| 0052 am. C-P5 | Warning when retirement date varies | Not implemented | No warnings, no sweeps |
| 0052 am. C-P14 | Amount fixed by base date | Partial | Uses `dollarsOf`, which is also the display date (see 0013) |
| 0052 am. C-M13 | Drift within a year | Implemented | Behaviour as documented (`Pension.value`) |
| 0053 | Output model, three levels | Partial | rows, holdings (opening/closing/rate; loans interest/principal), ledger (kind/from/to/amount/source), tax detail, event log (`results.assemble`, `api.run_detailed`); no SetResult, applied defaults, cost basis, tags, tallies, goals, shortfalls, liquidation NW |
| 0054 | Taxable-account return split, cost basis | Not implemented | — |
| 0055 | OAS clawback, GIS, splitting not modelled | N/A | Records a bias; nothing to build |
| 0056 | ResidenceSwitchEvent | Not implemented | — |
| 0057 | Account opening balance source | Partial | `openingFrom` validation; `holdings/account.py` AccountOpening (OPENING_TRANSFER / OPENING_BALANCE), AccountAtStart (statement balance); no warning about the net-worth jump; no cost basis |
| 0058 | Holdings before the horizon | Partial | Assets carried in grown from purchase (`events/purchase.py` CarryInEmitter); pre-horizon improvements/adjustments rejected; loan replay and `balanceAtHorizonStart` not built |
| 0059 (+4 am.) | RetirementEvent, `retirementTaxRate`; ends at retirement; sale/lump sum/payOff/transfer at retirement | Implemented | `events/retirement.py`, `household.current_tax_rate`, `flows/contribution.flow_window`, `events/sale.py`, `events/loan.py`, `events/transfer.py` |
| 0059 am. | One retirement per person; `retirementOf` | Implemented | `events/retirement.py` setup per person; `compiler.CompileContext.retirement_for` |
| 0060 | RRSP/TFSA contribution room | Implemented | `jurisdictions/ca/room.py`; caps in `holdings/account.py`, `events/transfer.py`; earned income in `flows/income_expense.py`; rows `rrspRoom`/`tfsaRoom` |
| 0060 am. | Room per person | Implemented | `jurisdictions/ca/room.py` keyed by (person, type) |
| 0063 | Cash balance reconciliation | Implemented | `events/cash_balance.py` (CASH_RECONCILIATION); builder form |
| 0062 | Cash flow adjustment (new amount from a date) | Implemented | `flows/adjustment.py`; used by income, expense, contribution, withdrawal (amount; percent: new annualRate, amendment); builder 'Cash flow changes'; change rate not built |
| 0061 | Second earner: persons, owners, retirement/tax/room per person, spousal RRSP | Implemented | `persons.py`, `rules/person.py`, `household.py` Person, `env.retirement_for`, `rules/tax.py` per person, UI owner fields and ledger tax per person; not built: pension splitting, attribution rule (decided deferred / not modelled) |
| 0064 | Item on/off switch (`enabled`, cascade to dependents) | Implemented | `enabled.py` (`active` after `upgrade` in validation, compiler, `retirement_dates`); builder "On" checkbox at the front of each row (`app.toggle_item`), off rows greyed with "off via" |
| 0065 (proposed) | Triggers instead of at-retirement fields | Implemented on `poc/sm-triggers` (experiment) | `triggers.py` (resolve, `prepared`), `events/trigger.py` (log), `upgrade.py` (flags → triggers); builder Trigger form, triggers under their target, date-less items kept off. Amendment 2026-11-13: `on: start|end` (`triggers.event_month`), attachedTo → triggers, start triggers carry their target off/deleted with the event |
| 0066 (proposed) | Timeline view (lanes, branches, trigger arrows) | Implemented on `poc/sm-triggers` (experiment) | `webapp/timeline.py` (`layout`), `webapp/web/timeline_draw.py` (`svg`, `graph`), `/timeline`, `templates/timeline.html`; builder rows get `id="item-<id>"` |
| 0067 (proposed) | Associated expense / cost (lives with a parent; amount or % of a looked-up basis) | Implemented on `poc/sm-triggers` | `flows/associated.py`; `upgrade.py` (`attachedTo`, vehicle maintenance, sale `sellingCostRate` converted); validation `check_associated`; adjustments; builder forms; timeline. Not built: cost at a scheduled mortgage payoff |
| 0068 (proposed) | Associated income / one-off income (lives with an income or pension; amount or % of its yearly amount; monthly or a lump in arrears) | Implemented on `poc/sm-triggers` | `flows/associated_income.py`; validation `check_associated_income`; adjustments; builder forms ("Associated income"); timeline. No conversion on load |
| 0070 (proposed) | Builder as cards by person and category; estimated monthly figures; adding in context | Implemented on `poc/sm-cards` (with the flat view `/flat`, after-tax incomes, editing (`ops.update_item`, `/api/items/update`) and card icons, amendments) | `state_machine/cards.py`; `/api/view/builder` `cards`; `web/templates/_items.html` shared by `builder.html` and `flat.html`; `schema.py` `CARD_ADDS`; `web/templates/builder.html`; `web.js` (add forms, open state); tests `test_cards.py`, `test_ui_emitters.BuilderCards` |
| 0071 (proposed) | Tax jurisdictions as plug-in packages; the US next to Canada | Implemented on `poc/sm-jurisdictions`: (1) seam with Canada moved (results unchanged); (2) `jurisdiction` field (CA default via upgrade), person `birthDate`, schema / validation / settings switch / run columns / ledger labels by jurisdiction; (3) US: 401(k) and IRA (traditional, Roth), HSA, brokerage, `contributionLimit` (yearly, catch-up); (4) New page (`/new`), jurisdiction dropdown in the settings, nav label; (5) conformance suite, golden set per jurisdiction (`tests/golden/us/`), samples, CONTRIBUTING in `state_machine/README.md` | `state_machine/jurisdictions/` (`ca/`, `us/`); `schema.merged`, `describe(code)`; `ops.settings` `switch_problem`; tests `test_jurisdictions.py`, `test_us.py`, `test_conformance.py`, `test_golden.GoldenUnitedStates`, `test_ui_emitters.UnitedStatesInTheApp` |
| 0072 (proposed) | RESP accounts with the CESG grant (Canada) | Implemented on `poc/sm-resp` | `jurisdictions/ca/resp.py` (grant via `Canada.on_contribute`, lifetime cap via `RoomLimits.cap`); `AccountType.fields` on the account form (`schema.merged`); tests `test_resp.py`, `test_ui_emitters.RespInTheApp`; Canada's sample has an RESP |
| 0073 (proposed) | Property break-even and rent equivalent; penalty formula per term | Implemented on `poc/sm-break-even` | `holdings/mortgage.py` (`ClosureTerm`, `penalty_at`), `events/sale.py`, `events/loan.py` (`ClosurePenalty`); `state_machine/break_even.py`; `/api/view/break-even`; `/run/break-even` (summary and table); tests `test_closure_penalty.py`, `test_break_even.py`, `test_ui_emitters.BreakEvenInTheApp` |
| 0074 (proposed) | Vehicle cost of ownership per month | Implemented on `poc/sm-vehicle-cost` | `state_machine/vehicle_cost.py`; `/api/view/vehicle-cost`; `/run/vehicle-cost` (chart icon on vehicle cards and rows); tests `test_vehicle_cost.py`, `test_ui_emitters.VehicleCostInTheApp` |
| 0069 (proposed) | Stateless server, scenario in the browser (sessionStorage), JSON API, Jinja builder as an API client | Implemented on `poc/sm-stateless` (steps 1-4) | `state_machine/ops.py` (commands: load, settings, add, toggle, delete with cascade; outcome `{scenario, ok, messages}`), `state_machine/views.py` (effective starts, display order, off items, trigger-set dates, choices, ledger month); `app.py` routes call them. JSON API `api.py` (`/api/...`, schema `schema.py`, limits, gzip; `test_api.py`). Pages in `web/` (API client only; `web/static/web.js` keeps the scenario in sessionStorage); no server-side store, no session cookie. Tests use `browser.py` |

## 2. Per CRITIQUE finding

| ID | User's decision (short) | PoC status | Where |
|---|---|---|---|
| C-P1 | Return split, deferred growth, average cost | Not implemented | ADR-0054 |
| C-P2 | Carry-forward pool (revisited) | Implemented | `rules/tax.py` TaxRule |
| C-P3, C-M3 | Annuity drawdown, yearly recompute, `indexed` | Implemented (2026-11-11) | ADR-0039 amendments; `method: annuity` |
| C-P4 | `pensionDiscountRate`; pension after tax in liquidation NW | Not implemented | ADR-0052/0050 amendments |
| C-P5 | Constant amount; warning when retirement varies | Not implemented (warning) | ADR-0052 amendment |
| C-P6 | `SaleEvent.taxRate`, `liquidationTaxRate` | Not implemented | ADR-0017/0031 amendments |
| C-P7 | No change | N/A | — |
| C-P8 | No change | N/A | — |
| C-P9 | Record the bias | N/A (doc) | ADR-0055 |
| C-P10 | No change | N/A | — |
| C-P11 | `sellingCostRate` essential for RealEstate | Not implemented | Still optional (`validation.py`, webapp/schema.py) |
| C-P12 | Closing costs inside the mortgage | N/A (assumption) | ADR-0025 amendment |
| C-P13 | ResidenceSwitchEvent, exempt share | Not implemented | ADR-0056 |
| C-P14 | `baseDate` input only; `displayDollarsOf` | Not implemented | `dollarsOf` still does both |
| C-P15 | Not modelled | N/A | — |
| C-P16 | Account market adjustment (percent) | Not implemented | ADR-0033 amendment |
| C-P17 | Per-scenario deflator | N/A (matches PoC) | — |
| C-P18 | No change | N/A | — |
| C-P19 | No change | N/A | — |
| C-P20 | In-term closure warning | Not implemented | Needs term length and warnings |
| C-M1 | Percent/even can't start before the account opens; empty → 0 | Implemented | `validation.py` withdrawal check; `flows/withdrawal.py` PercentStrategy |
| C-M2 | Reject a sale before the horizon start | Implemented | `validation.py` sale check |
| C-M4 | `openingFrom` for in-horizon accounts; pre-horizon = statement balance | Implemented (no warning) | `validation.py`; `holdings/account.py` |
| C-M5 | Replay pre-horizon loans, `balanceAtHorizonStart` | Not implemented | SPEC warns against the fake advance |
| C-M6 | Interest adjustment at a late first payment | Implemented | `holdings/mortgage.py` accrue/settle_accrued |
| C-M7 | `keepPayment` | Implemented | `holdings/mortgage.py` renew, `arith.keep_payment_months` |
| C-M8 | Capital-gains tax on sale (Phase 4.5) | Not implemented | `rules/capital_gains.py` no-op; SPEC lists the gap |
| C-M9 | Non-registered return taxable as max(0, ·) | Implemented | `Jurisdiction.on_return` (`returns_taxed`) |
| C-M10 | Reject renewal in/after the sale month | Implemented | `validation.py` renewal check |
| C-M11 | Amortisation a whole number of months ≥ 1 | Implemented | `validation.check_amortization` |
| C-M12 | Penalty from paymentFrom (no change) | Implemented (as before) | `events/loan.py` |
| C-M13 | Document pension drift | N/A (doc) | ADR-0052 amendment |
| C-M14 | Pension contribution cash → outside | Implemented | `holdings/pension.py` accept_contribution |
| C-M15 | Reject a pension ending before its effective start | Implemented | `validation.py` pension check |
| C-M16 | Reject indexing on percent withdrawals (and legacy even); form hides the field | Implemented (validation); form shows a hint instead of hiding | `validation.py`; webapp/app.py hint |
| C-M17 | No change (negative cash) | N/A | — |

## 3. Backlog (decided, not built)
Ordered as CRITIQUE.md Phase 4 (impact on rent vs buy and retirement readiness), then the rest of the planned model.
Phase 4 items whose decision was "no change" are dropped (4.6 C-P8, 4.11 C-P12, 4.12 C-P10, 4.14 C-P15, 4.15 C-P17); 4.2 (C-P2) is done.

| # | Item | ADR | Scope |
|---|---|---|---|
| 1 | Taxable-account return split (CR 4.1, C-P1) | 0054, 0017 am. | `incomeYield`, `openingCostBasis`, average-cost basis, realised gain on withdrawal taxed at inclusion × rate; show cost basis |
| 2 | ~~Annuity drawdown (4.3, C-P3/C-M3)~~ | 0039 am. | **Done 2026-11-11** (`method: annuity`) |
| 3 | Result warnings channel + pension warning (4.4, C-P5) | 0052 am. | `warnings` in the result; first use: pension start tied to a varying retirement date. Also: keepPayment fallback (0043), OUTSIDE opening jump (0057) |
| 4 | Capital-gains tax on sale (4.5, C-M8, C-P6, C-P13) | 0017 (+am.), 0056, 0034 | Gain = price − cost − selling costs (cost basis incl. improvements), inclusion rate, `SaleEvent.taxRate`, principal residence + ResidenceSwitchEvent exempt share; replaces the no-op CapitalGainsRule |
| 5 | Pension discount + liquidation net worth (4.7, C-P4, C-P6) | 0052 am., 0050 am., 0031 (+am.) | `pensionDiscountRate` (2% real); liquidation NW column: selling costs, CG tax, tax-deferred and unrealised gains at `liquidationTaxRate`, pension × (1 − rate) |
| 6 | Separate display date (4.8, C-P14) | 0013 am., 0052 am. | `baseDate` input only (pensions, `amountIn`); `displayDollarsOf` view setting rescales real columns |
| 7 | `sellingCostRate` essential for properties (4.9, C-P11) | 0040 am. | Validation error when missing (explicit 0 allowed); UI note that carrying costs go in living expenses |
| 8 | Pre-horizon loans (4.10, C-M5) | 0058 | Replay schedule from the loan's start without cash; `balanceAtHorizonStart`; allow pre-horizon improvements/adjustments in carry-in |
| 9 | Account market adjustment (4.13, C-P16) | 0033 am. | Percent revaluation on accounts, cost basis unchanged |
| 10 | In-term closure warning (4.16, C-P20) | 0047 am., 0019, 0043 | Needs term length on mortgages/renewals (`termAt`), then the warning |
| 11 | Shortfalls instead of negative cash | 0015, 0034, 0035 | Capped debits, shortfall per flow, sale deficit shortfall, `taxPaidFrom` |
| 12 | Goals and tallies | 0006, 0014, 0027, 0037 | HoldingMetric/NetWorth/TagSum/Derived tallies, REACH/MAINTAIN, active window |
| 13 | Scenario sets in lockstep | 0028, 0053 | SetResult, set-level goals |
| 14 | Sweep rules | 0030 | Surplus cash above a buffer to an account after tax |
| 15 | Tags and shift/sweep tooling | 0023, 0007, 0038, 0041 | Tags on items and ledger; time shifts (START/END/BOTH); variant sweeps |
| 16 | Rate series and generators | 0005, 0019 | Segmented/term rates, compounding per holding, Monte-Carlo seam |
| 17 | Remaining model pieces | 0012, 0016, 0022, 0024, 0025, 0026, 0040, 0053 | Event generators; birth date/ages; variable costs; generic loans; generic OneOffTransfer; leased (not owned) holdings; applied-defaults list |

## 4. Known PoC simplifications and gaps
| Source | Behaviour |
|---|---|
| SPEC, ADR-0015, C-M17 | Cash may go negative; no shortfalls (the UI highlights negative cash) |
| SPEC, C-M8 | No capital-gains tax on any sale |
| SPEC | No warnings in the result; the keepPayment fallback is noted only in the Renew event's log detail |
| SPEC, C-M5 | A mortgage cannot start before the horizon; a fake new mortgage at the start overstates net worth by its advance |
| SPEC, ADR-0057 | A pre-horizon account enters at its stated balance (not grown); an OUTSIDE opening makes net worth jump |
| SPEC | Improvements and market adjustments must fall inside the horizon |
| SPEC | No return on cash |
| ADR-0017, C-P18 | Capital losses give no credit; a non-registered loss gives no credit (C-M9) |
| ADR-0017 | One flat effective rate for all taxable effects (plus RRSP `withdrawalTaxRate`, `retirementTaxRate`) |
| ADR-0029 | No mid-month interest adjustment; whole months only |
| ADR-0048 | Unused deduction pool is lost at the horizon end; contribution room not checked (Q-06) |
| ADR-0051 | Employer matching caps not modelled |
| ADR-0055 | OAS before clawback, no GIS, no pension splitting |
| ADR-0036, C-P10 | No RRIF conversion or minimum withdrawals |
| ADR-0052, C-P5 | Pension amount does not change with its start date |
| ADR-0052, C-M13 | Pension value in real columns drifts by up to a year's inflation within each year |
| ADR-0025, C-P12 | Closing costs assumed inside the mortgage principal |
| ADR-0040, C-P11 | Carrying costs belong in living expenses; nothing warns |
| ADR-0029, C-P15 | Amortising loans only |
| ADR-0047 | One `salePenalty` per sale, not per secured loan |
| OBJECTS §9.1 | A JSON number `0` (not `"0"`) for marketValue, salePrice, valueAdded, withdrawalTaxRate, retirementTaxRate or a renewal's amortizationYears is read as "not given" |
| OBJECTS §9.2 | Some bad input raises KeyError, not a readable ValueError (sale/improvement/marketAdjustment without `property`, account without `accountType`, withdrawal without `method`) |
| OBJECTS §9.3 | Duplicate ids keep the first slot; items without id become `item{n}` and cannot be referenced |
| OBJECTS §9.4 | Before a late first payment the debt shows the accrued interest (simple, on the rounded principal); lump sums and extra payments in that window are dropped |
| OBJECTS §9.5 | A renewal or lump sum on a loan already at 0 is lost with its penalty; a lump-sum penalty is charged even when its prepayment rounds to 0 |
| OBJECTS §9.6 | The payment is annuitised on the unrounded principal; the advance uses the rounded one |
| OBJECTS §9.7 | Loan detail `interest`/`paid` default `Decimal('0')` vs `0.00`; pension `rate` is the annual indexing rate, others monthly |
| OBJECTS §9.8 | Sold assets stay with balance 0.00 and keep reporting points |
| OBJECTS §9.9 | Income-less mode drops expense/maintenance/pension-contribution lines but keeps loan-payment and contribution lines with `from None`; tax still comes from cash |
| OBJECTS §9.10 | Own-rate tax and `amountIn: base` amounts stay unrounded until final use |
| OBJECTS §9.11 | Percent withdrawal re-bases on the opening balance (current balance in the account's opening month); a percent withdrawal that started before the horizon pays 0 until its first in-horizon anniversary; the annuity is set from the current balance at the first month with a balance |
| OBJECTS §9.12 | Pension indexing counts years from the base date; other flows from their own start |
| ADR-0018 | Within a month expenses come before vehicle maintenance (ADR: costs before expenses); no effect while debits are uncapped |

## 5. Docs vs code inconsistencies found
- `webapp/SPEC.md` "Simplified income tax" says taxable income is credited net (gross − round(gross × rate)). The code credits gross and taxes it in the monthly tax step with the deduction pool (`rules/tax.py`). **Fixed 2026-11-10** (SPEC rewritten for iteration 2, commit 18c14da).
- ADR-0020 amendment says the PoC will later be aligned to tax in the tax step. It already does.
- `webapp/SPEC.md` Layout, Engine semantics and Commits still describe iteration 1 (`engine.py`, a 4-step month, branch `poc/python-flask`). `webapp/state_machine/README.md` and `clock.Order` are current. **Fixed 2026-11-10** (SPEC rewritten for iteration 2, commit 18c14da).
- The builder labels `dollarsOf` "Show real values in dollars of". It also fixes pension amounts and `amountIn: base` (C-P14 not built).
- C-M16's decision says the form hides indexing for percent withdrawals. The form only shows a hint.
- CRITIQUE Phase 1.6 asks for a SPEC note on pension drift (C-M13). `webapp/SPEC.md` has none; ADR-0052 has it. **Fixed 2026-11-10** (SPEC rewritten for iteration 2, commit 18c14da).
- ADR-0058 says pre-horizon improvements and market adjustments are included in the carried-in value. The PoC rejects them.
