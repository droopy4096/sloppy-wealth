# ADR-0018: Order of steps within a month

- **Status:** Accepted
- **Date:** 2026-11-04

## Context
The monthly stepping stage (ADR-0010) runs a fixed sequence of steps for each period. The
order defines the accounting semantics: what earns interest, which debits fall short first
(ADR-0015), and whether a property sold this month still incurs this month's costs.

## Decision (revision 2)
For each period P:
1. **Open**: carry closed balances and values from P−1.
2. **Resolve**: rates for P (rate generators, ADR-0019) and cash flow amounts for P.
3. **Inflows first**: credit income cash flows, so there are no false shortfalls.
4. **Events**: sales, purchases and lump-sum prepayments, applied after income.
5. **Debits** in fixed priority: liability payments, then costs, then expenses, then
   transfers and contributions, then withdrawals. Each is capped at available funds;
   shortfalls are recorded.
6. **Growth and interest**: revalue assets, apply account returns, accrue liability interest.
   Interest and returns are computed **on the opening balance** (interest in arrears, as banks
   do). A payment or lump sum made in P reduces interest from P+1. This keeps the projection
   reconcilable with real statements and the standard amortisation formula.
7. **Tax** at the flat effective rate (same capping rule).
8. **Close**: snapshot balances, values, cost basis and cumulative shortfall.

Every money movement is rounded to 2 dp, half-even, as it happens (ADR-0009).

Revision 1 (rejected) applied events at the start of the month and credited income after
them. The user found that counter-intuitive: a payment made in a month must show on the
mortgage in that month, and income must arrive first so that no false shortfalls appear.

## Alternatives considered
- Events at the end of the month: a sold property would incur that month's costs and
  interest, which makes settlement more complicated.
- Interest on the balance after payments: feels more natural, but understates interest
  by about a month on every payment compared with the bank.
- User-defined debit priority: more flexible, but more to configure. Could be added later.

## Consequences
- Inflows come before events and debits, so this month's income can pay this month's
  purchase, bills and payments.
- Payments made in P always show in P's closing balance.
- Rates are converted to monthly using each holding's compounding convention (ADR-0019).

## Amendments (2026-11-04)
- **Step 5:** scheduled loan payments are derived by the engine (ADR-0029) and paid
  first within the liability-payments group.
- **Step 7a (new):** sweep rules run after tax and before close (ADR-0030).
- **Steps 9–10 (new):** update tallies, then evaluate scenario-level and set-level goals,
  after every scenario in the set has closed the period (ADR-0027, ADR-0028).
- **Step 4:** sale settlement deducts selling costs (ADR-0031).
- **Step 4 (2026-11-05):** revaluation events (ADR-0033), and the full sale settlement
  order including negative equity (ADR-0034).
