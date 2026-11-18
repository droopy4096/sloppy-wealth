# Adversarial review: planning (main) and PoC (poc/python-flask)

Date: 2026-11-08. Scope: ADR-0001..0053, glossary, open questions, domain/output models; PoC up to commit c5aea66.

| Role | Focus |
|---|---|
| CRITIC-PLAN | Canadian economics, tax, personal finance: the ADRs and model |
| CRITIC-POC | Math, economics, accounting: the PoC code and numbers |
| DEFENDER | Defends decisions from the ADRs and docs |
| ARBITER | Main session: final rulings |
| PLANNER | Work plan from the rulings |

**Exchange (5 turns):**
1. Critics raise findings.
2. Defender answers.
3. Critics rebut.
4. Defender replies.
5. CRITIC-PLAN has the final word on the one item still contested (C-P11).

**Column keys:**
- Defence: D = defend, C = concede, P = partial concession.
- Rebuttal: A = accept, M = maintain, N = narrow.
- Reply: H = hold, C = concede, AN = agree narrowed.

**Ruling keys:**
- UPHELD: fix needed.
- DOC: ADR or SPEC text only.
- USER: an earlier user decision is reopened for the user.
- REJECTED: the defence stands.

## Outcome
- **37 findings:** 20 against the plan, 17 against the PoC.
- **Rulings:**

  | Ruling | Plan | PoC | Total |
  |---|---|---|---|
  | UPHELD | 15 | 11 | 26 |
  | DOC | 1 (C-P9) | 3 (C-M7, C-M8, C-M13) | 4 |
  | USER | 2 (C-P3, C-P4) | 1 (C-M3) | 3 |
  | REJECTED | 2 (C-P18, C-P19) | 2 (C-M12, C-M17) | 4 |

  See the arbitration lists below.
- **Verified correct (CRITIC-POC):**
  - The ledger reconciles every holding in every month on all samples and on a private real-life scenario.
  - NW = cash + investments + assets − debts holds throughout.
  - Mortgage payment 2882.31 matches an independent float calculation.
  - The final payment (2882.70) clears the 0.39 remainder.
  - Renewal recalculation: 3158.55, exact.
  - Tax arithmetic is correct.
  - The percent-withdrawal amount is correct.
  - Pension real value at the base date: 608,000 = 2000 × 304.
  - 110/110 tests pass.

## A. Plan: Canadian economics (CRITIC-PLAN)

| ID | Sev | Source | Critique | Defence | Rebuttal | Reply | Ruling |
|---|---|---|---|---|---|---|---|
| C-P1 | High | ADR-0017 amendment, ADR-0004 | Taxable-account returns are taxed in full every month at the flat rate: no deferral, no 50% inclusion, no cost basis. Property gains get inclusion and are taxed only at sale. This biases rent vs buy. | P: deliberate (Q-09); concedes the asymmetry | M: "deliberate" doesn't make it neutral | C | UPHELD High |
| C-P2 | High | ADR-0020 × ADR-0048 | With net income (the JSON default), deductions = 0. An RRSP or DB contribution gets no refund (about $1.8k/yr on $500/mo at 30%). | P: the UI pre-fills gross; concedes the JSON case | M: a warning isn't enough; needs a refund credit | C | UPHELD High |
| C-P3 | High | ADR-0039 | Even drawdown (balance ÷ months, fixed) ignores returns. At 5% over 25 years the residual is about 1.43× the start (nominal), and real income falls about 45%. The ADR's "small balance remains" claim is false. | P: the user chose fixed; concedes the false claim | M: the decision rested on the false claim | C | USER High |
| C-P4 | High | ADR-0052 Q-36 amendment | The pension value is undiscounted and pre-tax, beside after-tax TFSA balances. The rationale "mirrors even drawdown" is wrong. The value is about 1.3–1.6× a commuted value. | P: explicit decision; concedes the rationale | M: no figure ever shows it after tax; real goals use the overstated value | C | USER High |
| C-P5 | High | ADR-0052 + ADR-0038/0041 | A DB pension moves with the retirement date at the same amount: no early-retirement reduction, no extra accrual. CPP and OAS adjustment factors are missing. Sweeps are biased toward early retirement. | P: CPP/OAS with their own start don't move; concedes DB | M | C | UPHELD High |
| C-P6 | High | ADR-0017 amendment, 0035, 0031 | One flat rate also covers large one-offs: a non-principal-residence sale, an RRIF collapse, the deemed disposition at death. That misstates tax by six figures (about 30% vs 45–53%). | P: flat is core; concedes one-offs | N: a per-sale override plus a terminal rate | AN | UPHELD High |
| C-P7 | High→Med | ADR-0020 | Rent is taxed gross, with no deductions (interest, property tax, CCA). | D: enter it as two flows (net taxable + rest) | N: the workaround drifts as interest falls; a loss can't be entered | AN | UPHELD Med (document now, tagging later) |
| C-P8 | High→Med | ADR-0030, 0048, Q-06 | No TFSA/RRSP room, so sweeps make all surplus tax-free. | D: recorded gap; the user picks the target | N: a room cap and overflow, or a warning | AN | UPHELD Med |
| C-P9 | Med | ADR-0036, 0052, Q-06 | No OAS clawback, GIS or pension splitting. | D: per-person rules are out of scope (ADR-0002) | N: at least record the bias in an ADR | AN | DOC Med |
| C-P10 | Med→Low | ADR-0036, 0049, Q-13 | No RRIF minimums or forced conversion at 71. | D: user responsibility; segmented rate | N: the segments work; an authoring preset and an after-71 flag are needed | AN | UPHELD Low-Med |
| C-P11 | Med→Low | ADR-0040 | Carrying costs and selling cost default silently to 0, which favours owning. | P: concedes sellingCostRate | N: carrying costs too | H: a single "monthly expenses" flow risks double counting | Turn 5 N: a warning, since the applied-defaults list can't catch an absent cost → UPHELD Low-Med |
| C-P12 | Med→Low | ADR-0025, 0046 | No closing costs (land transfer tax, CMHC, GST/HST). | D: a zero-value improvement raises cost basis | N: it also raises acquisitionPrice; the order within a month is undefined | AN (confirmed) | UPHELD Low |
| C-P13 | Med | ADR-0017 | The principal-residence flag is all or nothing: no designated years, no +1 formula, no anti-flipping rule. | P | M | C | UPHELD Med |
| C-P14 | Med | ADR-0013 vs ADR-0052 | The pension amount is in baseDate dollars, so changing a reporting date changes pension cash flows. | P | M | C | UPHELD Med |
| C-P15 | Med→Low | ADR-0019, 0024, 0029 | No fixed-payment variable mortgage (trigger rate), no interest-only loan. | P: monthly compounding is expressible | N | AN | UPHELD Low-Med |
| C-P16 | Med→Low | ADR-0005, 0049, 0039 | Deterministic only; no sequence-risk shock for accounts. | P: a segmented series exists | N: a one-month crash needs about −98.6%/yr | AN (confirmed) | UPHELD Low-Med |
| C-P17 | Low | ADR-0028 amendment, 0014 | Set-level real goals across scenarios use different deflators. | P | N | AN | UPHELD Low |
| C-P18 | Low | ADR-0017, 0034 | No capital-loss credit or carry-forward. | D: stated simplification | A (PoC C-M9 contradicts it) | — | REJECTED |
| C-P19 | Low | ADR-0022 | Variable costs are based on acquisition price, not current value. | D: custom indexing covers it | A | — | REJECTED |
| C-P20 | Low | ADR-0047 | A break inside a term with no penalty entered shows $0. | D: a default was rejected on purpose | N: a termAt() warning | AN | UPHELD Low |

## B. PoC: math and accounting (CRITIC-POC)

| ID | Sev | Source | Critique | Defence | Rebuttal | Reply | Ruling |
|---|---|---|---|---|---|---|---|
| C-M1 | High | engine.py withdraw() | A percent withdrawal raises KeyError 'monthly' when the account is empty or not yet open in its start or anniversary month. | C | — | — | UPHELD High (bug) |
| C-M2 | High | engine.py validate/events | A sale before the horizon start is accepted but never carried out; the asset and its costs stay (e.g. 692k house). | C | — | — | UPHELD High (bug) |
| C-M3 | High→Med | engine.py, ADR-0039 | Even drawdown: 100k at 7% over 30 years withdraws 100,000.80 and leaves 436,374.57. | P: the code follows the ADR | N: the defect is in the ADR | AN | USER Med (with C-P3) |
| C-M4 | Med | engine.py account setup | An account opened inside the horizon gets its balance from outside (in a private scenario, net worth jumped by the balance with no source). A pre-horizon account enters at face value without growth, unlike assets. | P | N | AN (confirmed) | UPHELD Med |
| C-M5 | Med | engine.py, SPEC | No mortgage before the horizon; the workaround fakes a LOAN_ADVANCE (cash overstated by the principal). | P: documented | N: SPEC warning | AN | UPHELD Med (warn now, feature later) |
| C-M6 | Med | engine.py, ADR-0029 | A late firstPaymentDate doesn't recalculate the payment, causing a balloon (final payment 10,696 vs 4,429). | C | — | — | UPHELD Med (bug) |
| C-M7 | Med→Low | ADR-0029 vs ADR-0043 | A renewal turns prepayment savings into a lower payment (2882.31→2565.67; payoff 2048-12→2052-01). | D: ADR-0043 Consequences decide it | N: ADR-0029 wording ("shortens") is wrong after a renewal | AN | DOC Low |
| C-M8 | Med→Low | engine.py sale, ADR-0017 | No capital-gains tax on sales; investment property sells tax-free. | P: deliberate scope | N: SPEC must list the gap | AN | DOC Low |
| C-M9 | Med | engine.py tax | A negative non-registered return offsets salary tax (tax 0 instead of 3,000), contradicting ADR-0017. | C | — | — | UPHELD Med (bug) |
| C-M10 | Low | engine.py | Renewal and sale in the same month: the renewal penalty is silently lost. | C | — | — | UPHELD Low (bug) |
| C-M11 | Low | engine.py | Amortization truncated by int(): 0 months causes a division error, or is ignored on a renewal. | C | — | — | UPHELD Low |
| C-M12 | Low | engine.py, ADR-0047 | A lump-sum penalty comes from cash even when the lump sum is paidFrom outside. | D: the loan's paymentFrom (ADR-0047/0044) | A | — | REJECTED |
| C-M13 | Low | engine.py pension value | Pension value deflates by whole years; drift within a year is up to about 2%. | P | A (document it) | — | DOC Low |
| C-M14 | Low | engine.py contributions | A pension contribution goes in, then a −REVALUATION reverses it (phantom inflow). | P: economics right | A (cosmetic) | — | UPHELD Low |
| C-M15 | Low | engine.py validate | A pension ending before its effective start silently has value 0. | C | — | — | UPHELD Low |
| C-M16 | Low | engine.py validate | Indexing on percent or even withdrawals is silently ignored. | C | — | — | UPHELD Low |
| C-M17 | Low | SPEC, ADR-0015 | Negative cash is free financing (a private scenario ended below zero). | D: documented PoC simplification | A | — | REJECTED |

## C. Work plan (PLANNER)

### Phase 0: PoC bugs and validation (one commit each, with tests)
| # | Resolves | Item |
|---|---|---|
| 0.1 | C-M1 | Set the percent-withdrawal yearly amount in the first month with a balance and on each anniversary; missing = 0 |
| 0.2 | C-M2 | Reject sales dated before the horizon start |
| 0.3 | C-M9 | Non-registered return goes into taxable income as max(0, return) |
| 0.4 | C-M6 | Recalculate the payment at a late firstPaymentDate |
| 0.5 | C-M4a | An account opened inside the horizon is funded from cash |
| 0.6 | C-M10 | Renewal and sale of the same property in the same month: charge the penalty, or reject |
| 0.7 | C-M11 | Validate amortization ≥ 1 whole month |
| 0.8 | C-M15 | Validate pension end ≥ effective start |
| 0.9 | C-M16 | Reject indexing on percent or even withdrawals |
| 0.10 | C-M14 | Book pension contributions as cash → outside |

### Phase 1: documentation only
| # | Resolves | Item |
|---|---|---|
| 1.1 | C-P3, C-M3 | ADR-0039 amendment: correct the residual claim |
| 1.2 | C-M7 | ADR-0029/0043: prepayments shorten amortization "until the next renewal" |
| 1.3 | C-P12 | ADR-0018: a purchase comes before an improvement in the same month |
| 1.4 | C-P7 | ADR-0020: the two-flow rent workaround and its drift; deductible tagging goes to open questions |
| 1.5 | C-P9 | ADR-0054: OAS clawback / GIS bias as a known limitation |
| 1.6 | C-M13 | ADR-0052 + SPEC: pension value drift within a year |
| 1.7 | C-M8 | SPEC: no capital-gains tax on sales (known gap) |
| 1.8 | C-M5 | SPEC: warn about the fake LOAN_ADVANCE workaround |
| 1.9 | C-M4b | SPEC: a pre-horizon account enters at face value |

### Phase 2: questions for the user (one at a time, recommended option in bold)
| Q | Resolves | Question | Options |
|---|---|---|---|
| Q1 | C-P1 | How are taxable-account returns taxed? | (a) all taxed monthly; (b) a taxable share of the return; **(c) yield taxed yearly + growth against a cost basis, taxed at inclusion on withdrawal or liquidation** |
| Q2 | C-P2 | How does the contribution deduction work? | (a) offset against modelled income only; **(b) refund credit = rate × own contribution, whether or not income is modelled**; (c) warning only |
| Q3 | C-P3, C-M3 | Which even-drawdown method? | (a) keep fixed; (b) recompute yearly; **(c) annuity at the expected return, recomputed on each anniversary, optionally indexed** |
| Q4 | C-P4 | How does pension value appear in net worth? | (a) undiscounted, labelled pre-tax; (b) discounted at the expected real return; **(c) discounted at a real-rate parameter (default about 2%), labelled pre-tax** |
| Q5 | C-P5 | How does a DB pension respond when the retirement date moves? | (a) same amount; **(b) per-month reduction or increase vs a reference date, with CPP/OAS presets**; (c) an amount per sweep variant |
| Q6 | C-P14 | What date is the pension amount stated in? | (a) baseDate; **(b) PensionEntitlement.amountAsOf (statement date)** |
| Q7 | C-P13 | How does the principal-residence exemption work? | (a) boolean; (b) a count of designated years; **(c) a list of designated years, the +1 formula, one designation per year across assets** |
| Q8 | C-P6 | How are large one-offs rated? | (a) flat rate; **(b) per-SaleEvent rate + Scenario.terminalTaxRate for liquidation**; (c) (b) + a deemed disposition at horizon end |
| Q9 | C-P8 | How is contribution room handled? | **(a) annual room cap on sweeps with an overflow target**; (b) a warning only |
| Q10 | C-P11 | Selling cost and carrying costs for real estate? | **(a) sellingCostRate essential + a no-costs warning**; (b) a warning only |
| Q11 | C-P17 | Which deflator do set-level real goals use? | (a) each scenario's own; **(b) a set-level deflator** |

### Phase 3: ADR additions with no decision needed (main)
| # | Resolves | Item |
|---|---|---|
| 3.1 | C-P12 | ADR-0025: PurchaseEvent.closingCosts (cost basis only) |
| 3.2 | C-M5 | ADR-0024: existing loan with a current balance, no advance |
| 3.3 | C-P10 | ADR-0049: RRIF-minimum age preset; warning after 71 |
| 3.4 | C-P16 | ADR-0033: one-off percentage Revaluation on Accounts |
| 3.5 | C-P15 | ADR-0024/0029: fixed-payment variable mortgage (trigger rate) and interest-only loan |
| 3.6 | C-P20 | ADR-0047: termAt() warning for an in-term closure with no penalty |
| 3.7 | — | Record the answers to Q1–Q11 |

### Phase 4: PoC features
Ordered by impact on rent vs buy (RvB) and retirement readiness (Ret).

| # | Resolves | Feature | Depends on |
|---|---|---|---|
| 4.1 | C-P1 | Return split with cost basis and deferred gains (RvB, L) | Q1 |
| 4.2 | C-P2 | Refund credit (M) | Q2 |
| 4.3 | C-P3 | New drawdown method (Ret, M) | Q3 |
| 4.4 | C-P5 | Pension early/late adjustment (Ret, M) | Q5 |
| 4.5 | C-M8, C-P6, C-P13 | Capital-gains tax on sale, principal-residence years, rate overrides (L) | Q7, Q8, 3.1 |
| 4.6 | C-P8 | Room cap with overflow (M) | Q9, 4.1 |
| 4.7 | C-P4 | Pension discount and label (S) | Q4 |
| 4.8 | C-P14 | amountAsOf (S) | Q6 |
| 4.9 | C-P11 | sellingCostRate essential + warning (S) | Q10 |
| 4.10 | C-M5 | Existing loans (M) | 3.2 |
| 4.11 | C-P12 | closingCosts (S) | — |
| 4.12 | C-P10 | RRIF preset (S) | — |
| 4.13 | C-P16 | Account revaluation (S) | — |
| 4.14 | C-P15 | Trigger-rate and interest-only loans (M) | — |
| 4.15 | C-P17 | Set-level deflator (S) | Q11 |
| 4.16 | C-P20 | In-term closure warning (S) | — |

**Sequencing:**
1. Phases 0 and 1 can run in parallel.
2. Phase 2 goes one question at a time.
3. Each recorded answer (3.7) unlocks its Phase 4 item.

## Walkthrough decisions
The user's answers, one finding at a time, are kept in CRITIQUE_RESPONSES.md.
