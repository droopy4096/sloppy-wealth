# ADR-0060: RRSP and TFSA contribution room limits

- **Status:** Accepted
- **Date:** 2026-11-11
- **Relates to:** ADR-0002 (single economic unit), ADR-0048 (RRSP contribution
  deduction), ADR-0030 (sweeps), ADR-0025 (one-off transfers), ADR-0052 (pensions),
  ADR-0013 (indexing)
- **Resolves:** Q-06 (contribution room part)

## Context
Contributions and transfers into RRSP and TFSA accounts are unlimited today (ADR-0048,
ADR-0030 watch notes). An optimisation run on a real-life scenario (2026-11-11) put several
hundred thousand dollars into the RRSP within a few years, which real contribution room
does not allow,
and every dollar was also deducted from taxable income. Results that rely on such
transfers overstate retirement income.

Canadian rules (to be parameterised, not hard-coded):
- RRSP: new room each January 1 = min(18% of the previous year's earned income, the
  year's dollar maximum) − pension adjustment; unused room carries forward.
- TFSA: new room each January 1 = the year's annual limit; unused room carries
  forward; withdrawals are added back on the following January 1.

## Decision
1. **Over the room: cap.** A contribution or a transfer into an RRSP or TFSA moves
   only the amount within the available room; the excess stays in cash. The capped
   amount is shown (ledger amount and the event's log detail). Only the amount
   actually contributed is an RRSP deduction (ADR-0048).
2. **Inputs: a `contributionRoom` item per account type** (`accountType`: rrsp | tfsa;
   at most one per type). It holds the current room and its as-of date, and the yearly
   rules: RRSP rate (18%) and yearly dollar maximum; TFSA annual limit; with their
   indexing. All accounts of that type share the room. The builder shows it as its own
   form. Without the item, that type has no limit (older files unchanged).
3. **Earned income: an `earnedIncome` flag on income items**, default = the item's
   `taxable` (salaries count automatically). Pensions (their own item type) and account
   withdrawals never count. RRSP room for year Y uses the earned income paid in Y − 1
   (gross, as credited by the engine).
4. **Pension adjustment: not modelled for now.** The current-room input (from the CRA
   notice of assessment) already reflects past pension adjustments. Revisit when a
   modelled job has a workplace pension plan.
5. **Yearly maximums are indexed with the existing `indexing` field** (none | inflation |
   custom, ADR-0013): the item states the maximum and the year it applies to; later
   years grow by the indexing rate from that year. Rounded as CRA does: the TFSA limit
   to the nearest $500, the RRSP dollar maximum to the nearest $10. A custom rate can
   stand in for wage growth (the RRSP maximum follows the average wage).
6. **Every account of type `rrsp` is treated fully as an RRSP**, including the owner's
   "RRSP+401k": room applies to every contribution and transfer into it; no exemption
   for 401(k) rollovers (model a rollover as part of the opening balance).

### Mechanics (defaults following the CRA rules; not separate owner decisions)
- **What uses room:** contributions (the own part first, then the employer match, both
  within the room; a match beyond the room is not paid), one-off transfers into the
  account, and an opening balance moved from cash (`openingFrom: cash`). Opening
  balances at the horizon start or from outside, and returns, do not.
- **Timeline:** the room given is the room available in the month of its as-of date.
  Movements before that month are not checked. Each following January 1 adds the new
  room (RRSP: min(rate × the previous calendar year's earned income, the year's
  maximum); TFSA: the year's annual limit). Earned income before the horizon start is
  not known and counts as 0.
- **TFSA withdrawals** are added back to the room on the following January 1. RRSP
  withdrawals are not.
- **Not modelled:** the age-71 RRSP deadline (C-P10), the $2,000 over-contribution
  buffer, the first-60-days rule, spousal plans.
- **Visible in results:** each January 1 room update and each capped movement is an
  event in the event log with the room before and after; the remaining room per type
  is reported monthly.

## Alternatives considered
- Cap and send the excess to a fallback account: rejected for now (simpler; the owner
  can add a separate contribution to another account).
- Contribute in full and charge the CRA over-contribution penalty (1% a month above
  the $2,000 buffer): rejected, nobody plans for a penalty.
- Validation error: rejected; the room depends on income at run time.

## Consequences
- Plans stay feasible and realistic; money over the room remains in cash (0% return)
  unless the owner directs it elsewhere.

## Amendment (2026-11-11): room per person (ADR-0061)
A `contributionRoom` item has an `owner`; at most one per (person, account type). Room
is used by the owner's accounts, or by the `contributor` of a spousal RRSP. RRSP room
grows from that person's own earned income; TFSA withdrawals add back to the owner's
room. "Spousal plans" are no longer in the not-modelled list. The room columns in the
results show the household total per type.
