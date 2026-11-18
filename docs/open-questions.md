# Open questions

Running list. Each item moves into an ADR once it is decided.

| # | Question | Origin | Status |
|---|---|---|---|
| Q-01 | Where does the engine run: client-side, local, stateless serverless function? | ADR-0003 | **Deferred.** For now, the engine is stateless per invocation (ADR-0003 amendment) |
| Q-02 | Implementation language | ADR-0003 | **Deferred** until requirements are clear |
| Q-03 | Goals: only evaluated, or solved for? | ADR-0006 | **Resolved:** observed and reported only; solving is out of scope (ADR-0006 amendment) |
| Q-04 | How are results compared across scenarios with different horizons (align, truncate)? | ADR-0006 | **Resolved:** not supported; scenarios in a set share a horizon (ADR-0028) |
| Q-05 | Rounding: mode and precision | ADR-0009 | **Resolved:** half-even, 2 dp, every money movement rounded when computed; rates at full precision (ADR-0009) |
| Q-06 | Per-person Canadian rules (contribution room, income splitting) vs single economic unit | ADR-0002 | Watch item |
| Q-07 | JSON schema versioning | ADR-0008 | **Partly resolved:** every payload is versioned. Open: version format, compatibility, migration |
| Q-08 | Order of steps within a month in the stepping stage (accounting semantics) | ADR-0010 | **Resolved:** ADR-0018 |
| Q-09 | Simple tax model: is one flat effective tax rate used for every taxable effect (capital gains, taxable account income, RRSP withdrawals)? | ADR-0017 | **Resolved:** one flat effective tax rate for all effects (ADR-0017 amendment) |
| Q-10 | Converting rates to a monthly rate: annual/12 or (1+r)^(1/12)−1? Canadian fixed-rate mortgages compound semi-annually by law | ADR-0018 | **Resolved:** compounding convention per holding, mortgages semi-annual (ADR-0019) |
| Q-11 | CompositeRate (market rate + property spread) and a market-level shock object; also partial or capped indexing (share of inflation, cap) once inflation varies over time (Q-33c) | ADR-0033 | Later |
| Q-12 | Reporting REACH goals as last met or met at horizon end, as well as first met | ADR-0014 | Later |
| Q-13 | RRSP to RRIF conversion and minimum withdrawals | ADR-0036 | Watch item |
| Q-14 | Commuted value of a pension in net worth | ADR-0036 | **Resolved:** ADR-0052 |
| Q-15 | Annuity purchase: converting an RRSP lump sum into guaranteed income | ADR-0036 | Later |

## Agenda from the PoC review (docs/poc-review-2026-11-07.md)
Worked through **one at a time, in this order**. Status is updated as each is decided.

| # | Question | Origin | Status |
|---|---|---|---|
| Q-16 | P1: rates as fractions in JSON, percentages in the UI; implausible rates rejected | PoC review | **Resolved:** ADR-0045 |
| Q-17 | P2: last scheduled payment clears the rounding remainder | ADR-0029 | **Resolved:** ADR-0029 amendment |
| Q-18 | P3: first loan payment in the month after the advance | ADR-0029 | **Resolved:** ADR-0029 amendment |
| Q-19 | P4: income gross vs net default (JSON vs authoring), tax timing | ADR-0020 | **Resolved:** ADR-0020 amendment |
| Q-20 | P5: per-year amounts: engine attribute or authoring-only | ADR-0021 | **Resolved:** ADR-0021 amendment (month, quarter, year; spread evenly) |
| Q-21 | P6: indexed amounts step up yearly on the item's anniversary | ADR-0013 | **Resolved:** ADR-0013 amendment |
| Q-22 | P7: market value ≠ price at purchase (cost basis vs value; Revaluation) | ADR-0033 | **Resolved:** ADR-0025 amendment (PurchaseEvent.marketValue) |
| Q-23 | P8: capital improvement (construction) event | PoC review | **Resolved:** ADR-0046 |
| Q-24 | P9: Scenario gains incomeMode and baseDate in the domain model | ADR-0013, ADR-0044 | **Resolved:** domain model v0.21; ADR-0013 amendment (base date is scenario input) |
| Q-25 | P12: early closure penalty formula | ADR-0043 | **Resolved:** ADR-0047 (manual amount) |
| Q-26 | R1: RRSP contribution tax deduction | ADR-0035 | **Resolved:** ADR-0048 (same month) |
| Q-27 | R2: withdrawal as a rate of the balance | ADR-0039 | **Resolved:** ADR-0049 |
| Q-28 | R4: registered funds in the output (investments within assets net worth) | Output model | **Resolved:** ADR-0050 |
| Q-29 | R6: contributions and withdrawals in income-less mode | ADR-0044 | **Resolved:** ADR-0044 amendment |
| Q-30 | R3/R5: contribution form, employer matching | Authoring | **Resolved:** ADR-0051; ADR-0048 amendment |
| Q-31 | D2: pension value in net worth (see Q-14) | ADR-0036 | **Resolved:** ADR-0052 (in net worth; retirement date) |
| Q-36 | Discount rate for the pension value | ADR-0052 | **Resolved:** ADR-0052 amendment (no discounting; amount in today's dollars) |
| Q-37 | Does employment income end at the retirement date? | ADR-0052 | **Resolved:** ADR-0052 amendment (endsAtRetirement) |
| Q-38 | Pension value in the result columns and in liquidation net worth | ADR-0050, ADR-0052 | **Resolved:** ADR-0050 amendment (inside Investments; excluded from liquidation) |
| Q-32 | D3: income-less mode drops pensions; which income it ignores | ADR-0044 | **Resolved:** ADR-0044 amendment (pension payments are moves between holdings) |
| Q-33 | D1/D4/D5: pension form, member contributions, bridge benefit, capped indexing | ADR-0036 | **Resolved:** D1 form → Q-35; member contributions (Q-33a) and start/end dates (Q-33b) → ADR-0052 amendments; capped or partial indexing (Q-33c) **deferred** to Q-11: use a custom rate while inflation is constant |
| Q-34 | Output model class diagram (P10, R4) | Planning | **Resolved (provisional):** ADR-0053, diagram 05; review after the PoC shows real results |
| Q-35 | Add accounts (RRSP/TFSA) and pensions to the PoC | PoC | **Done** on `poc/python-flask` (30ce2d5..9c02dbf): PoC aligned with Q-16..Q-38 decisions, plus accounts, pensions, detail and ledger pages |
