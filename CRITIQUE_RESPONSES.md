# Responses to CRITIQUE.md

The user's answer to each finding, taken one at a time, starting 2026-11-09.
Option letters refer to the options offered at the time; the decision column states the choice in full.

| ID | Date | Choice | Decision | Rationale (user) | Recorded in |
|---|---|---|---|---|---|
| C-P1 | 2026-11-09 | a | Return split: `incomeYield` taxed yearly in full; growth deferred, taxed at inclusion on withdrawal; average cost basis | — | ADR-0054, ADR-0017 amendment, domain model v0.31 |
| C-P2 | 2026-11-09 | a | Refund credit: excess deduction × rate paid to cash in modelled-income mode; still lost in income-less mode | — | ADR-0048 amendment |
| C-P3, C-M3 | 2026-11-09 | a | Annuity at expected return, recomputed yearly, optional `indexed` (growing annuity) | — | ADR-0039 amendment, glossary, domain model v0.32 |
| C-P4 | 2026-11-09 | a | Discount at `pensionDiscountRate` (real, default 2%); include after tax in liquidation net worth | — | ADR-0052 and ADR-0050 amendments, glossary, domain model v0.33 |
| C-P5 | 2026-11-09 | c | Keep constant amount; warning when retirement date or pension start varies across a sweep/set | — | ADR-0052 amendment |
| C-P6 | 2026-11-09 | a | `SaleEvent.taxRate` override; scenario `liquidationTaxRate` for all liquidation-NW taxes except pension; both default to effective rate | — | ADR-0017 and ADR-0031 amendments, domain model v0.34 |
| C-P7 | 2026-11-09 | c | Leave as is; ADR-0020 already states rental deductions are not modelled | — | — (no change) |
| C-P8 | 2026-11-09 | c | Leave as is; contribution room stays out of scope (Q-06 watch item) | — | — (no change) |
| C-P9 | 2026-11-09 | a | Record the bias: OAS before clawback, no GIS, splitting assumed inside the effective rate | — | ADR-0055 |
| C-P10 | 2026-11-09 | c | Keep as is: no RRIF minimums, no warning; ADR-0036 stands | Canada is considering a lifelong RRSP, so RRIF rules may not apply | — (no change) |
| C-P11 | 2026-11-09 | own | `sellingCostRate` essential for RealEstate (explicit 0 allowed); carrying costs not in the property entry, must be in living expenses; no warning | Carrying costs belong in living expenses | ADR-0040 amendment, domain model v0.35 |
| C-P12 | 2026-11-09 | own | No `closingCosts` field; assume closing costs are rolled into the mortgage principal the user enters | Purchase costs are typically rolled into the mortgage, so the mortgage number is the one to go by | ADR-0025 amendment |
| C-P13 | 2026-11-09 | own | New `ResidenceSwitchEvent` moves the principal-residence designation; designated years by year-end rule; exempt share = min(1, (1 + designated) ÷ owned) | Wants an event that switches the principal-residence flag | ADR-0056, ADR-0017 amendment, glossary, domain model v0.36 |
| C-P14 | 2026-11-09 | b | `baseDate` is input only (today's dollars for pensions and REAL goals); new view setting `displayDollarsOf` (default baseDate) for real columns | — | ADR-0013 and ADR-0052 amendments, glossary, domain model v0.37 |
| C-P15 | 2026-11-09 | c | Not modelled; amortising loans only; watch item for loan `paymentMode` (FIXED_PAYMENT, INTEREST_ONLY) | Keep a note of the decision | ADR-0029 amendment |
| C-P16 | 2026-11-09 | a | Market adjustment (Revaluation, percent only) on accounts; cost basis unchanged; no tax effect | — | ADR-0033 amendment, domain model v0.38 |
| C-P17 | 2026-11-09 | c | Keep per-scenario deflator; documented that real figures are purchasing power in each scenario's world | — | ADR-0028 amendment |
| C-P18 | 2026-11-09 | a | Rejection confirmed: no capital-loss credit or carry-forward (ADR-0017 simplification) | — | — (no change) |
| C-P19 | 2026-11-09 | a | Rejection confirmed: variable costs stay on acquisition price; custom indexing for value-tracking costs | — | — (no change) |
| C-P20 | 2026-11-09 | a | Warning when a secured loan closes in-term with no penalty entered; penalty stays manual | — | ADR-0047 amendment |
| C-M1 | 2026-11-09 | a | Validation: percent/even withdrawal cannot start before account opens; engine: zero balance at start/anniversary gives 0 for that year, no crash | — | PoC fix pending (Phase 0) |
| C-M2 | 2026-11-09 | a | Validation error for a sale before the horizon start (remove the asset or move the horizon) | — | PoC fix pending (Phase 0) |
| C-M4 | 2026-11-09 | a | In-horizon account with balance must state `openingFrom` (CASH or OUTSIDE); pre-horizon balance = balance at horizon start, not grown | — | ADR-0057, domain model v0.39; PoC fix pending |
| C-M5 | 2026-11-09 | a | Pre-horizon loans replayed from their own start without cash; optional `balanceAtHorizonStart` override; pre-horizon asset growth recorded | — | ADR-0058, domain model v0.40; PoC feature pending |
| C-M6 | 2026-11-09 | b | Interest adjustment: accrued interest to the first payment paid in cash on that date; amortisation starts at the first payment | — | ADR-0029 amendment; PoC fix pending (Phase 0) |
| C-M7 | 2026-11-09 | b | ADR-0029 wording fixed ("until the next renewal"); renewal option `keepPayment` derives the amortisation from the kept payment | — | ADR-0029 and ADR-0043 amendments, domain model v0.41; PoC feature pending |
| C-M8 | 2026-11-09 | a | Build capital-gains tax on sale in PoC (PR exemption share, per-sale rate); SPEC lists it as a known gap until then | — | PoC feature pending (Phase 4.5); SPEC note pending |
| C-M9 | 2026-11-09 | a | Quick fix: per-account taxable return max(0, ·); replaced later by the return split (ADR-0054) | — | PoC fix pending (Phase 0) |
| C-M10 | 2026-11-09 | a | Validation error for a renewal/switch in the same month as the sale of the securing property; break penalty belongs on the sale | — | PoC fix pending (Phase 0) |
| C-M11 | 2026-11-09 | a | Validation: amortisation must be a whole number of months ≥ 1 (mortgages and renewal terms) | — | PoC fix pending (Phase 0) |
| C-M12 | 2026-11-09 | a | Rejection confirmed; clarifying line: penalty always from the loan's paymentFrom, even for outside lump sums | — | ADR-0047 amendment |
| C-M13 | 2026-11-09 | a | Documented: pension value in real columns drifts up to one year's inflation within each year | — | ADR-0052 amendment |
| C-M14 | 2026-11-09 | a | Pension contribution booked cash → outside ("pension plan contribution"), no revaluation pair | — | PoC fix pending (Phase 0) |
| C-M15 | 2026-11-09 | a | Validation error when a pension ends before its effective start (message names the start's source) | — | PoC fix pending (Phase 0) |
| C-M16 | 2026-11-09 | a | Validation error for generic indexing on percent withdrawals and drawdowns; drawdown uses its own `indexed` flag; form hides the field | — | PoC fix pending (Phase 0) |
| C-M17 | 2026-11-09 | a | Rejection confirmed: negative cash stays a highlighted PoC simplification; ADR-0015 shortfalls built later | — | — (no change) |
| C-P2 (revisited) | 2026-11-09 | a | Refund credit replaced by a carried-forward pool of unused deductions, applied against later taxable income from any source; never negative, nothing paid out | Uncapped credit would refund tax never withheld (e.g. $300k RRSP transfer at retirement) | ADR-0048 amendment |
