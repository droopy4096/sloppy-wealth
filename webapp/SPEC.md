# Python PoC: shared spec

A barebones proof of concept to test the mechanics of the planning model (ADRs in
`docs/adr/`). **Keep it simple.** No JS framework, no database, no auth. This is PoC
**iteration 2** (event-emitter engine); iteration 1 (retired) survives only as the golden
results it produced.

## Layout (all under `webapp/`)
```
webapp/
  app.py             # the server: registers the JSON API and the web pages (ADR-0069)
  api.py             # the JSON API (/api/...): the only part that uses the engine
  schema.py          # the item-type schema (fields, choices, hints) served by /api/schema
  timeline.py        # the timeline model (ADR-0066), served by /api/timeline
  web/               # the pages: a client of the API (pages.py, client.py,
                     #   timeline_draw.py, templates/, static/web.js); no engine imports
  state_machine/     # the engine (iteration 2): api.py/engine.py facade, compiler, runner,
                     #   emitters, household, holdings/, events/, flows/, rules/, results,
                     #   ops.py (scenario commands), views.py (derived views),
                     #   jurisdictions/ (tax jurisdictions as packages: ca/, ADR-0071)
  browser.py         # test stand-in for a browser tab (keeps and posts the scenario)
  samples/           # sample scenario JSON files
  build_docs.py      # pre-compiles the Help tab (docs/user) and the developer docs into static/docs/
  test_*.py          # app/engine tests; state_machine/tests/ holds the engine + golden suite
  requirements.txt   # flask
  .venv/             # local virtualenv (not committed)
```
Run: `cd webapp && .venv/bin/python app.py` (port 5000).
Python 3.14. Standard library + Flask only. Engine API: `validate`, `run`,
`run_detailed` (see "Engine output").

## Scenario JSON (schemaVersion 1)
All money values and rates are **strings** (Decimal-safe, ADR-0009). Dates are ISO
`YYYY-MM-DD` strings; the engine uses only the year and month (ADR-0007).

Older files still load with the same results: their forms are converted on input in one
place (`state_machine/upgrade.py`, also used when the UI loads a file): `monthlyAmount`
becomes `amount` per month; withdrawal method `even` becomes `annuity`; the scenario's
`retirementDate` becomes a retirement event (marked `outsideHorizon` when it lies outside
the horizon, which older files allowed); a property's own `saleDate` (with `salePrice`,
`sellingCostRate`, `salePenalty`) becomes a sale item right after the property.
With ADR-0067 also: a vehicle's `annualMaintenance` (+
`maintenanceIncrease`) and a sale's `sellingCostRate` become associated items (below), and
an expense's `attachedTo` becomes an associated expense (with own dates: triggers). Rows,
holdings and tax are unchanged; the ledger shows `EXPENSE` / `COST` lines of the new items
instead of `MAINTENANCE` / `SELLING_COST`.
```json
{
  "schemaVersion": 1,
  "name": "Single house",
  "horizon": {"start": "2027-01-01", "end": "2056-12-01"},
  "openingCash": "150000",
  "items": [
    {"type": "property", "id": "house", "name": "House",
     "purchaseDate": "2027-01-01", "price": "700000", "annualAppreciation": "0.05"},
    {"type": "mortgage", "id": "mtg", "name": "House mortgage",
     "startDate": "2027-01-01", "principal": "560000", "annualRate": "0.0379",
     "amortizationYears": "25"},
    {"type": "vehicle", "id": "car", "name": "Car",
     "purchaseDate": "2027-01-01", "price": "30000", "annualDepreciation": "0.15",
     "annualMaintenance": "2000"},
    {"type": "income", "id": "salary", "name": "Free income",
     "startDate": "2027-01-01", "endDate": "2040-12-01", "monthlyAmount": "4000"},
    {"type": "expense", "id": "living", "name": "Living",
     "startDate": "2027-01-01", "endDate": "", "monthlyAmount": "1500"}
  ]
}
```
Mortgage prepayments (added later) refer to a mortgage by its `id`:
```json
{"type": "extraPayment", "id": "x", "name": "Extra 500", "mortgage": "mtg",
 "startDate": "2027-02-01", "endDate": "2031-12-01", "monthlyAmount": "500"},
{"type": "lumpSum", "id": "l", "name": "Bonus", "mortgage": "mtg",
 "paymentDate": "2030-06-01", "amount": "20000"}
```
- Mortgage and property link (added later): a mortgage may have `"property": "<id>"`
  (secured by, ADR-0024). Its `startDate` may then be blank: it starts in the property's
  purchase month (financed purchase, ADR-0025). The `property` may also be a vehicle (a car
  loan, ADR-0074 amendment): the loan starts with the vehicle's purchase, is paid off if the
  vehicle is sold, and its interest counts in the vehicle's cost of ownership. A property
  may have `marketValue`: cash
  pays `price`, but the property starts at `marketValue` (e.g. a house built for less than
  it is worth). A property may have `saleDate` and
  `sellingCostRate` (fraction). In the sale month (events step) cash receives the
  property's opening value less selling costs, the property value becomes 0, and every
  mortgage secured by it is paid off from cash at its opening balance: no payment,
  interest or prepayment that month (ADR-0031, ADR-0034). Cash may go negative if the
  proceeds do not cover the mortgage. An unlinked mortgage is not affected by a sale.
- Alignment (added later): `per` may also be `quarter` (1/3 a month, ADR-0021); a
  mortgage may set `firstPaymentDate` (default: the month after the advance). Before a
  later first payment, interest on the principal accrues and is paid in cash on the
  first payment date as an INTEREST_ADJUSTMENT, not capitalised; the amortisation starts
  at the first payment (ADR-0029 amendment, C-M6); penalties are optional amounts in dollars of the event
  date (ADR-0047): property `salePenalty` (for the loans settled by the sale), renewal
  `penalty` (switch inside a term), lump sum `penalty`. A mortgage, and each renewal for
  its own term, may also give a term and a penalty formula (ADR-0073): `termMonths` (from
  its start) with `penaltyMethod` `flat` (`penaltyAmount`), `interestLeft` (`penaltyRate`,
  a fraction of the schedule's interest left in the term) or `monthsInterest`
  (`penaltyMonths` months of interest on the balance); none after the term. A sale
  without `salePenalty`, or a lump-sum payoff without `penalty`, uses it (a manual
  amount wins); the holdings points of such a loan carry `closingPenalty` (the penalty if
  closed after that month). Rate ranges follow ADR-0045:
  interest rates 0 <= r < 1, value and indexing rates -1 < r < 1.
- Accounts (added later): `{"type": "account", "accountType": "rrsp" | "tfsa" |
  "nonRegistered", "openingBalance", "openedDate" (blank = horizon start), "annualReturn",
  "withdrawalTaxRate" (RRSP, optional), "openingFrom"}`. Returns on the opening balance
  each month; non-registered returns are taxable income (Q-09), a negative return gives
  no credit against other income (ADR-0017, C-M9).
  - Opening balance (ADR-0057): for an account opened at or before the horizon start,
    `openingBalance` is its balance at the horizon start (a statement balance), not
    grown from `openedDate`. An account opened inside the horizon with a balance must
    set `openingFrom`: `cash` (moved from cash, OPENING_TRANSFER) or `outside` (an
    existing balance not modelled before, OPENING_BALANCE; net worth jumps by it).
  - `contribution`: account, start/end, amount/per, indexing, optional `employerMatch`
    (share added from outside), `endsAtRetirement`. RRSP contributions are deductions in
    the same month (ADR-0048); the match is neither income nor a deduction.
  - `withdrawal`: account, start/end, `method` = `amount` (amount/per, indexing),
    `percent` (`annualRate` × the balance at the start and each anniversary, paid 1/12 a
    month, ADR-0049) or `annuity` (spends the account down by the end of the draw: an
    annuity at the account's `annualReturn` over the months left to min(endDate, horizon
    end), set from the current balance in the first month with a balance and recomputed
    each anniversary; the final month withdraws the whole balance, so about one month's
    return is left; ADR-0039 amendments). Indexing applies to `amount` and `annuity`:
    with it an annuity grows each anniversary by the indexing rate (constant purchasing
    power). `even` in older files is read as an unindexed `annuity`. Percent and annuity
    withdrawals cannot start before their account opens; percent takes no indexing
    (C-M1, C-M16); a percent withdrawal whose account is empty at the
    start or an anniversary pays 0 that year. Capped at the balance; RRSP withdrawals are taxed at the account's
    withdrawalTaxRate or the income tax rate (ADR-0035).
  - Income-less mode (ADR-0044): contributions covered from outside and not deducted;
    withdrawals still move money to cash and are taxed.
  - Rows gain `investments` (all accounts); `assetsNetWorth` = investments + property &
    vehicles − debts; `netWorth` = cash + assetsNetWorth (ADR-0050).
- Sale (added later, the SaleEvent of the domain model): `{"type": "sale", "property":
  "<id>", "saleDate", "sellingCostRate" (optional), "salePenalty" (optional)}`. Same effect
  as the property's own saleDate fields, which older files may still use; a property can
  be sold only once. The same item sells a **vehicle** (`"property": "<vehicle id>"`):
  cash receives its opening value less sellingCostRate (e.g. a trade-in discount); its
  depreciation and maintenance stop. A replacement is a new vehicle bought that month.
  Optional `salePrice` (SaleEvent.price): the asset is sold at that price instead of its
  current value; the difference shows as a gain or loss (SALE_PRICE_DIFFERENCE) and
  selling costs are a share of the price.
- Bought before the horizon (added later): a property or vehicle with a purchaseDate
  before the horizon start is carried in at its value at the start: (marketValue or
  price) grown or depreciated monthly from the purchase month. No cash moves (the
  purchase predates the opening cash). It changes from the first month; vehicle
  maintenance increases count from the real purchase date. Improvements and market
  adjustments must fall inside the horizon; mortgages must still start inside it.
  **Known gap (C-M5):** a mortgage that started before the horizon cannot be entered yet
  (planned: ADR-0058 replay). Do not fake it with a new mortgage at the horizon start:
  its LOAN_ADVANCE adds the principal to cash and overstates net worth by that amount.
  A sale dated before the horizon start is rejected (C-M2).
- Vehicle maintenance increase (added later; **older form**, see
  associated items): optional `maintenanceIncrease` (fraction);
  annualMaintenance steps up by it once a year on the purchase anniversary (ADR-0013
  cadence), paid as 1/12 a month. Blank = flat, as before.
- Market adjustment (added later, ADR-0033): `{"type": "marketAdjustment", "property",
  "adjustmentDate", "percent" | "newValue"}`. A percent (fraction, may be negative) is
  applied to the value before the month's growth; a newValue is the month's closing
  value exactly (no growth that month). Value only: cash, debts and cost are unchanged.
  `property` may also name a vehicle (ADR-0033 amendment 2026-11-11): depreciation
  continues from the adjusted value.
- Cash balance (added later, ADR-0063): `{"type": "cashBalance", "balanceDate", "balance"}`
  sets cash to the stated balance at the end of that month (after the tax step, so the
  month's row shows it). The difference is a `CASH_RECONCILIATION` movement from or to
  outside: not income, not taxable. Several follow each other; in one month the last in
  item order wins. The date must be within the horizon.
- Item switch (added later, ADR-0064): any item may have `"enabled": false` (JSON boolean;
  default true). The item is then left out of the run (not validated, not compiled), and
  so is every item that refers to an off item through `property`, `mortgage`, `account`,
  `flow`, `event`, `target`, `owner`, `contributor` or `retirementOf` (transitively), and
  every item started by a trigger whose event is off (it never starts). The file
  keeps them; switching the item on brings its dependents back. Items with a blank owner
  belong to the first person that is on.
- Trigger (added later, ADR-0065): `{"type": "trigger",
  "event": "<item id>", "target": "<item id>", "action": "start" | "end" |
  "startAndEnd"}` sets a date of the target from the event item's date (its
  `retirementDate`, `saleDate`, `purchaseDate`, `openedDate`, `transferDate`,
  `paymentDate`, `startDate`, …), before validation and compilation:
  `start`: the target starts (or happens) in the event's month, replacing its own date;
  `end` (recurring items: income, expense, contribution, withdrawal, pension,
  extraPayment): its last month is the month before the event (the earlier of that and
  its own endDate); `startAndEnd` (recurring items): only in the event's month. An event
  dated by another trigger is resolved first; a cycle, two triggers setting the same
  date, or an event without a date is an error. A target ended before its own startDate
  never runs (left out with its dependents). Each trigger is logged in its month. It
  follows its event and target when either is switched off (ADR-0064).
  Optional `"on": "start" | "end"` (default start; ADR-0065 amendment 2026-11-13) says
  which date of the event counts: `end` = the month after its last month (recurring
  items: their endDate) or its sale month (property, vehicle: their sale item), so
  `action: end` with `on: end` makes the target's last month the event's last. An event
  that never ends (no endDate, no sale) never fires: an end trigger leaves the target as
  it is, a start trigger makes it never run.
  **Older forms:** `startsAtRetirement`, `endsAtRetirement` and `atRetirement` (below)
  are converted on load to triggers on the retirement event of the item's person; the
  engine no longer reads them. In the builder an item added without its date is kept
  switched off until a trigger sets it (adding the trigger switches it on).
- Cash flow adjustment (added later, ADR-0062): `{"type": "adjustment", "flow",
  "adjustmentDate", "amount", "per"}` gives an income, expense, contribution or
  fixed-amount withdrawal a new amount from that month (`per` defaults to the flow's). The
  amount is in dollars of the adjustment date and is indexed with the flow's own rate in
  yearly steps counted from that date. Several adjustments of one flow follow each other;
  in one month the last in item order wins. The date must be within the horizon; before
  the flow starts it applies once the flow runs. Each adjustment is logged in its month.
  For a withdrawal with method percent, give `"annualRate"` (fraction) instead of an
  amount (ADR-0062 amendment): from that month its monthly amount is re-set from the
  balance at the new rate, and again on each anniversary of the adjustment date.
  Not for pensions, annuity withdrawals or vehicle maintenance.
- Guaranteed pension (added later, ADR-0052): `{"type": "pension", "amount", "per",
  "startDate" (blank = retirementDate), "endDate" (blank = horizon end), "taxable"
  (default true, ADR-0036), "indexing", "indexRate"}`. The amount is in base-date
  (today's) dollars and steps up yearly on the base date's anniversary. Payments move
  from the pension's value into cash (also in income-less mode). Its value, in
  Investments, is the payments still to come in base-date dollars, undiscounted,
  expressed in each month's dollars. A contribution may target a pension: deductible,
  value unchanged, booked as PENSION_CONTRIBUTION from cash to outside (C-M14).
- Retirement date (added later, ADR-0052; older form, converted to triggers, ADR-0065): optional scenario field `retirementDate`.
  An income or expense item with `"endsAtRetirement": true` stops in the month before it
  (unless its own endDate is earlier); with `"startsAtRetirement": true` it starts in the
  retirement month (its startDate may then be blank, and is used only when there is no
  retirement date). Not both. Indexing counts from the effective start. JSON defaults
  false; the builder offers one choice (not tied / ends / starts), income defaulting to
  "ends". E.g. living expenses before and after retirement as two items.
- Retirement event (added later, ADR-0059): `{"type": "retirement", "retirementDate"}`,
  at most one. It replaces the scenario's `retirementDate` (older files: read as the
  event; the UI converts on load; having both is an error). From its month: items tied
  to retirement switch as above, pensions without a startDate begin, **withdrawals
  without a startDate begin**, and the tax rate switches to the scenario's
  `retirementTaxRate` (fraction; blank = no switch). An account's own
  `withdrawalTaxRate` still applies to its withdrawals.
- Contribution room (added later, ADR-0060): `{"type": "contributionRoom", "accountType":
  "rrsp" | "tfsa", "room", "roomAsOfDate", "yearlyMax", "maxYear" (optional, default the
  as-of year), "incomeRate" (RRSP, fraction, default 0.18), "indexing", "indexRate"}`, at
  most one per type, shared by all accounts of that type. `room` is available from the
  as-of month (inside the horizon); earlier movements are not checked. Each January after
  it adds new room: RRSP min(incomeRate × the previous calendar year's earned income, the
  year's maximum); TFSA the year's maximum plus the previous year's TFSA withdrawals. The
  year's maximum is `yearlyMax` indexed from `maxYear` and rounded to $10 (RRSP) or $500
  (TFSA). Contributions (own share, then the match on the share paid) and transfers into
  an account of that type are capped at the room (an opening balance, from cash or from
  outside, is the account's current state: never capped, uses no room);
  the excess stays in cash (a match beyond it is not paid) and only the amount
  contributed is deducted. Income items count as earned income when `earnedIncome`
  (default: `taxable`). Rows gain `rrspRoom` / `tfsaRoom` (room left at month end; null
  before the as-of month) when the item exists. Not modelled: pension adjustment,
  age-71 deadline, the $2,000 buffer, the first-60-days rule.
- Expense attached to an asset (added later, ADR-0040 amendment 2026-11-11; **older form**
  converted on load to a start trigger on the asset or income,
  omitted when the expense's own startDate is not earlier, and an end trigger with
  `on: end`, ADR-0065 amendment 2026-11-13): an expense
  may set `"attachedTo": <property or vehicle id>`. It is paid only while that asset is
  owned: not before its purchase, and not from the month it is sold (on a date or at
  retirement). A blank startDate then means the purchase date (indexing counts from it).
  E.g. property tax, home insurance, condo fees. `attachedTo` may also name an income:
  the expense then runs only in the months that income runs (its dates, including "ends
  at retirement"), a blank startDate meaning the income's start; e.g. job-related
  insurance.
- Associated items (added later, ADR-0067): items that live with a
  `parent` (property, vehicle, account, mortgage, or a recurring item: income, expense,
  contribution, withdrawal, pension, extraPayment, associatedExpense). A `basis` for a
  percentage, per parent type: property/vehicle `value` (its value at the start of the
  month; at its sale, the sale price) or `price`; account `balance`; mortgage
  `principal` or `balance`; income `amount` (its yearly amount that month).
  - `{"type": "associatedExpense", "parent", "amount", "per", "indexing", "indexRate"}` or
    `{..., "annualRate", "basis"}` (exactly one of amount / annualRate): paid every month
    from the parent's start to its end (a holding: while it exists, is not sold, and a
    mortgage while owed). An amount is indexed from the parent's start (also before the
    horizon); a percentage is basis x annualRate / 12, re-set on the first month and each
    anniversary of the parent's start, not indexed. Adjustments: a new `amount`, or a new
    `annualRate` for a percentage. Not paid in income-less mode. Ledger `EXPENSE`.
  - `{"type": "associatedCost", "parent", "at": "start" | "end" | "date", "costDate",
    "amount" | "rate" + "basis"}`: one-off, at the parent's start (a purchase, an opening,
    a first month), its end (an asset's or a mortgage's property's sale month; a
    recurring item's last month; never for an account or an item without an end), or on
    `costDate` while the parent exists (a trigger may set it). A rate is applied to the
    basis that month (at a sale: the sale price). Paid also in income-less mode. Ledger
    `COST`, after the month's sales and purchases (Order.EXPENSE).
  - Not tax-deductible, not added to the asset's value (no cost basis: C-M8).
- Associated income (added later, ADR-0068): income that lives with
  a `parent` income or pension; taxable, earned income and owner are the parent's. Not
  paid in income-less mode for an income parent; paid for a pension parent. Ledger
  `INCOME`, source = the associated item (Order.INCOME).
  - `{"type": "associatedIncome", "parent", "amount", "per", "indexing", "indexRate",
    "amountIn"}` or `{..., "annualRate", "per"}` (exactly one of amount / annualRate), and
    `"paid": "monthly" | "lump"` (default monthly). Its monthly share: an amount indexed
    from the parent's start, or the parent's yearly amount on its start and each
    anniversary x annualRate / 12 (a new rate from an adjustment re-anchors at its month).
    `monthly` pays the share every month from the parent's first to its last month.
    `lump` (per quarter or year) pays the rounded sum of a period's shares on each
    quarterly / yearly anniversary of the parent's start, in arrears (the last full
    period's in the month after the parent's last month, if within the horizon); a
    partial last period is not paid. Adjustments: a new `amount`, or a new `annualRate`.
  - `{"type": "associatedOneOff", "parent", "at": "start" | "end" | "date",
    "paymentDate", "amount" | "rate"}`: one-off, at the parent's first month, its last
    month (only with an endDate within the horizon), or on `paymentDate` while the parent
    runs (a trigger may set it). A rate is applied to the parent's yearly amount that month.
- Persons (added later, ADR-0061): `{"type": "person", "id", "name", "birthDate",
  "effectiveTaxRate", "retirementTaxRate"}` (rates optional fractions; blank = the
  scenario's; a blank retired rate falls back to the scenario's retirementTaxRate, then
  the person's working rate; `birthDate` optional, for age rules, ADR-0071).
  Without person items the scenario has one implicit person (results unchanged).
  `"owner": <person id>` on income, account, pension, contributionRoom and retirement
  (blank = the first person); contributions and withdrawals take their account's owner.
  An rrsp account may name a `"contributor"` (spousal RRSP): movements into it use the
  contributor's room and deduction; withdrawals are taxed to the owner (attribution rule
  not modelled). Household items tied to retirement (expense, extraPayment, lumpSum, sale,
  transfer) may name `"retirementOf"` (blank = the first person). Per person: at most one
  retirement event; the tax rate switches at their own retirement; taxable income,
  deductions and the deduction pool are their own and each pays a TAX movement (source =
  person id when there are several). Contribution room is per (person, type), at most one
  room item each; RRSP room grows from the person's own earned income. Rows stay
  household-level (room columns = the total over persons); `tax` of `run_detailed` is the
  household sum with `persons` (id -> detail) when there are several. Not modelled:
  pension income splitting, joint-account splits, CPP/OAS per person.
- Sale at retirement (added later, ADR-0059 amendment; older form, converted to a trigger, ADR-0065): a sale item may set
  `"atRetirement": true` instead of a saleDate (not both); it happens in the retirement
  event's month and moves with it. Needs a retirement event.
- Lump sum at retirement / payoff (added later, ADR-0059 amendment; at retirement is an older form, converted to a trigger, ADR-0065): a lumpSum may set
  `"atRetirement": true` instead of a paymentDate, and `"payOff": true` instead of an
  amount (pays the whole balance left after that month's scheduled payment). Not both of
  either pair.
- One-off transfer (added later, ADR-0025, ADR-0059): `{"type": "transfer", "account",
  "amount", "transferDate" | "atRetirement": true}` moves the amount from cash into the
  account in the events step, after that month's sales. Into an RRSP it is a deduction
  in that month (ADR-0048).
- Deduction carry-forward (C-P2 revisited, ADR-0048): deductions the month's taxable
  income cannot absorb go into a pool used by later months' tax steps against taxable
  income from any source, down to 0. Tax is never negative; no cash credit.
  `run_detailed()["tax"]` gives each month's tax step (taxable income, deductions, pool
  in, used, pool out, rate, tax); the ledger page shows it under the movements.
- Amount in today's dollars (added later, ADR-0013 amendment): income and expenses may
  set `amountIn`: `start` (default, dollars of the item's start date) or `base` (dollars
  of the base date, "dollarsOf"). With `base`, the amount at the start is amount ×
  (1 + annualInflation)^((start − base) / 12) (fractional years); the item's indexing
  then applies from its start. E.g. retirement living costs known in today's money.
- End choices (added later, ADR-0059 amendment; at retirement is an older form, converted to a trigger, ADR-0065; the builder now has only endDate, blank = never): every item with an end (income,
  expense, contribution, withdrawal, extraPayment, pension) ends **on a date**
  (`endDate`), **never** (both blank: horizon end, or until exhausted) or **at
  retirement** (`endsAtRetirement`: the month before the retirement event). The builder
  offers this as one choice per item (`ends`), plus `starts` (on a date / at retirement)
  for income and expenses; defaults: income and contributions end at retirement, the rest
  never. JSON stays lenient: with both endDate and endsAtRetirement the earlier applies;
  without a retirement event endsAtRetirement has no effect. A pension that starts at
  retirement cannot end at it.
- Improvement (added later, ADR-0046): `{"type": "improvement", "property": "<id>",
  "improvementDate": "...", "cost": "300000", "valueAdded": "450000"}`. Cash pays the
  cost (a mortgage linked to the property and starting that month can fund it); the value
  rises by `valueAdded` (default: the cost). Growth is always on the month's opening
  balance, so an improvement starts appreciating the following month.
- Mortgage renewal or lender switch (added later, ADR-0043):
  `{"type": "renewal", "mortgage": "mtg", "startDate": "2032-01-01", "annualRate": "0.045",
  "amortizationYears": ""}`. From that month the new rate applies and the payment is
  recalculated from the opening balance over the remaining amortization, or over
  `amortizationYears` when given (a new lender with a new amortization). Must start after
  the mortgage start; at most one per mortgage per month.
  Optional `"keepPayment": true` (JSON bool, default false; ADR-0043 amendment, C-M7):
  the scheduled payment before the renewal (without extra monthly prepayments) is kept,
  the new rate applies, and the remaining amortization is derived instead (see Engine
  semantics). Mutually exclusive with `amortizationYears`; any value other than
  true/false is rejected. The builder offers it as "no: lower the payment" (default) /
  "yes: keep the payment, shorten the amortization".
- Rates are **fractions** in JSON (`0.0379`); the builder form takes percentages
  (`3.79`) and converts them. The engine rejects rates outside (−1, 1), except the
  shares of a parent income's yearly amount (`associatedIncome.annualRate`,
  `associatedOneOff.rate`): 0 < rate ≤ 10, since a one-off such as severance can exceed a
  year's pay.
- Income and expense items (added later) give `amount` with `per`: `month` (default) or
  `year`; a yearly amount is spread evenly, amount / 12 each month. Older files with
  `monthlyAmount` still load (per month).
- Jurisdiction (added later, ADR-0071): scenario field `jurisdiction`, an ISO code of a
  registered jurisdiction (`state_machine/jurisdictions/<code>/`): `"CA"` (Canada). Files
  without it are Canadian (`upgrade` adds it after `name`). The jurisdiction decides the
  account types (`accountType`; Canada: `tfsa`, `rrsp`, `nonRegistered`, `resp`), its own item
  types (Canada: `contributionRoom`; another jurisdiction's are refused by name), how
  each account type is taxed (flags: contributions deductible, returns taxed,
  withdrawals taxed) and its contribution limits with their result columns (Canada:
  `rrspRoom`, `tfsaRoom`). Changing it (settings) is refused while items need the old one;
  the message names them.
- RESP (Canada, ADR-0072): `accountType` `resp`, one account per beneficiary;
  contributions not deductible, growth and withdrawals untaxed. Optional fields
  `unusedGrantRoom`, `grantReceived`, `contributedSoFar` (only on an RESP; amounts before
  the horizon, default 0). Each contribution or transfer into it brings the CESG, a
  `GRANT` movement from outside into the account: 20% of the amount, limited by the grant
  room ($500 a calendar year from the horizon's first year, plus `unusedGrantRoom`),
  $1,000 a year and $7,200 lifetime (less `grantReceived`). Lifetime contributions are
  capped at $50,000 (less `contributedSoFar`); the excess stays in cash. An opening
  balance from outside gets no grant and does not count.
- United States (`"jurisdiction": "US"`, ADR-0071): account types `traditional401k`,
  `traditionalIra` (contributions deducted, withdrawals taxed), `roth401k`, `rothIra`
  (neither), `hsa` (deducted; growth and withdrawals untaxed), `brokerage` (returns
  taxed). Yearly limits: `{"type": "contributionLimit", "limitType": "401k" | "ira" |
  "hsa", "yearlyLimit", "limitYear", "catchUp", "contributedSoFar", "indexing",
  "indexRate", "owner"}`, one per person and type. 401k covers traditional and Roth
  401(k) together, ira both IRAs. Each calendar year from `limitYear` (default: the
  horizon's first year) movements into the group's accounts are capped at the limit
  (indexed, rounded down to $500, HSA $50) plus `catchUp` from the year the owner turns
  50 (HSA 55; needs `birthDate`); nothing carries over; `contributedSoFar` counts in the
  first year; the employer match is not capped. Result columns `k401Limit`, `iraLimit`,
  `hsaLimit` (left this year). Social Security is a pension item; federal and state tax
  and FICA are in the flat effective rate.
- Income-less mode (added later, ADR-0044): optional scenario field `incomeMode`,
  `modelled` (default) or `expensesCovered`. In `expensesCovered` income items are
  ignored, and recurring outgoings (scheduled and extra monthly mortgage payments,
  expenses, vehicle maintenance) are assumed paid from outside the model with nothing left
  over: they still amortise the mortgage but do not touch cash. Cash moves only on one-off
  events: purchases, mortgage advances, lump sums and sales.
- A lump sum has optional `paidFrom`: `cash` (default) or `outside` (money from outside
  the model, e.g. a gift: it reduces the mortgage but not cash), in either income mode.
- Simplified income tax (added later): optional scenario field `effectiveTaxRate`
  (fraction, default 0). Income items with `"taxable": true` are credited gross and
  their amount is added to the month's taxable income; the month's **tax step** then
  takes rate × max(0, taxable − deductions − carried-forward pool) from cash as one TAX
  movement (ADR-0018 step 7, ADR-0048). `taxable` defaults to false (amount already
  after tax, ADR-0020); the builder form defaults it to yes. One flat rate (ADR-0017),
  switching to `retirementTaxRate` from the retirement event (ADR-0059).
- Income and expense items take optional `indexing` (added later): `none` (default,
  fixed), `inflation` (the scenario's `annualInflation`) or `custom` with `indexRate`
  (fraction). The amount is in dollars of the item's start month and steps up once a year
  on the anniversary of its start date: amount × (1 + rate)^(full years since start),
  recalculated from the base each year and rounded (ADR-0013).
- `endDate` empty or missing means "until the horizon end".
- `id` is unique within a scenario (the app can generate it from a counter or uuid4 hex).
- Validation: just enough to show a readable error (bad date, missing field), no more.

## Engine semantics (simplified from ADR-0018)
- One implicit **cash** account (ADR-0040) starting at `openingCash`. No return on cash.
- Periods are calendar months from horizon start to end, inclusive.
- Each scenario item becomes one or more **emitters** (`state_machine/`); each month the
  runner walks them in **order** (`state_machine/clock.py` `Order`, ties by item index)
  and applies their events at once. The order, i.e. the steps of a month:
  `INITIAL` (once, before the first month: holdings that exist at the start) ·
  OPEN (retirement) · INCOME · PENSION_PAY · ACQUIRE (purchases, loan advances, account
  openings) · IMPROVE · ADJUST (market adjustments) · SELL (sales, then each secured
  loan's payoff and the penalty) · TRANSFER · SERVICE_DEBT (renewal, interest, scheduled
  payment, prepayments) · EXPENSE · MAINTAIN · CONTRIBUTE · WITHDRAW · GROW (appreciation
  and account returns on the month's **opening** balances) · REVALUE_PENSIONS · TAX ·
  CLOSE (results). Full contract: `state_machine/INTERFACES.md` §10.
- Monthly rates: property `(1 + annualAppreciation)^(1/12) − 1`; vehicle
  `(1 − annualDepreciation)^(1/12) − 1`; mortgage `(1 + annualRate/2)^(1/6) − 1`
  (Canadian semi-annual compounding, ADR-0019); accounts `(1 + annualReturn)^(1/12) − 1`.
- Pension value in real (base-date) columns drifts by up to one year's inflation within
  each year and steps back at the anniversary, because payments step yearly while
  deflation is monthly (ADR-0052 amendment, C-M13); intended.
- Mortgage payment (ADR-0029): standard annuity P = L·r / (1 − (1+r)^−n), with
  n = amortizationYears × 12 and r = the monthly rate above. Fixed for the life of the
  loan; prepayments do not change it, they end the loan earlier (ADR-0029). The last
  scheduled payment clears the rounding remainder; any payment is capped at what is owed.
  A lump sum must fall after the mortgage start month.
- Renewal (ADR-0043): by default the payment is recalculated over the remaining
  amortization, so time saved by prepayments becomes a lower payment (ADR-0029
  amendment). With `keepPayment` (C-M7) the current scheduled payment P is kept and the
  remaining months n are derived from the opening balance B and the new monthly rate r:
  the smallest whole n with annuity(B, r, n) ≤ P, i.e.
  n = ⌈−ln(1 − r·B/P) / ln(1 + r)⌉ (n = ⌈B/P⌉ at r = 0), checked against the
  cent-rounded annuity; the last payment clears the smaller remainder. **Fallback**: if
  P ≤ B·r (the payment does not cover the interest) or n exceeds the remaining
  amortization, the payment is recalculated as by default. In an accruing month (renewal
  before a late first payment) the kept payment is the loan's original scheduled payment
  and B includes the accrued interest, as for the default recalculation.
- **Rounding**: every money movement is rounded to 2 dp with ROUND_HALF_EVEN as it is
  computed (ADR-0009). Use `decimal.Decimal` throughout; fractional powers can go through
  `Decimal.ln()/exp()` or a float with the result quantized. Rates are not rounded.
- **Validation (Phase 0)**: amortizationYears × 12 is a whole number ≥ 1 (C-M11); a
  renewal may not fall in or after the month its property is sold (C-M10); a pension may
  not end before its effective start (C-M15).
- **Known gap (C-M8)**: no capital-gains tax on sales yet. An asset sale pays the full
  proceeds; a property that is not the principal residence is overstated by the tax
  (planned: ADR-0017 with ADR-0056 exemption share and per-sale rate).
- **Known gap**: warnings (e.g. the keepPayment fallback) are not reported in the
  result; the new engine notes the fallback only in the Renew event's log `detail`.
- **PoC simplification**: cash **may go negative** (no shortfall capping, unlike
  ADR-0015). The UI highlights negative cash.

## Engine output
`run(scenario) -> list[dict]`, one row per month:
```
{"month": "2027-01", "cash": Decimal, "investments": Decimal, "assets": Decimal,
 "debts": Decimal, "assetsNetWorth": Decimal, "netWorth": Decimal,
 "realNetWorth": Decimal, "realAssetsNetWorth": Decimal}
```
`run_detailed(scenario)` returns `{"rows", "holdings", "ledger", "tax", "events"}`
(ADR-0053, D-E4): the rows above; per holding its monthly points (opening, closing,
rate; loans also interest, paid, principalPaid); every money movement (month, kind,
from, to, amount, source); each month's tax step; and the applied events (month, order
key, emitter, event, kind, source, cause, ledger range, detail).
`realNetWorth` (added later) = netWorth deflated to horizon-start dollars by the optional
scenario field `annualInflation` (fraction, default 0): netWorth / (1 + i)^(k/12) for the
k-th month after the start (ADR-0013, reporting only; movements stay nominal).
The optional scenario field `dollarsOf` (ISO date, the **base date**; default the horizon
start) sets whose dollars these are: month m is divided by (1 + i)^((m − base)/12), so
months before the base date are inflated and the base month is unchanged.
assets = sum of property and vehicle values; debts = sum of mortgage balances;
assetsNetWorth = assets − debts (added later: wealth held outside cash, i.e. equity in
properties and vehicles, later investments and retirement funds). The tables show it in
base-date dollars (realAssetsNetWorth, deflated like realNetWorth);
netWorth = cash + assets − debts (the "cumulative wealth").
Values are the state at the **end** of the month.

## JSON API (ADR-0069)
The server keeps nothing between requests: every POST carries the present scenario and
gets JSON back; every response has `schemaVersion`. Money and rates are decimal strings.
Scenarios are upgraded from older forms on arrival (`upgrade.py`).
- Commands (`state_machine/ops.py`) answer `{scenario, ok, messages}`: the new scenario;
  or, refused, the scenario as sent and why. `messages` may also note an accepted change.
  - `POST /api/load {data}`: a file's JSON, checked, upgraded, every item given an id.
  - `POST /api/validate {scenario}`; `POST /api/settings {scenario, settings}` (name,
    horizon {start, end}, openingCash, incomeMode, dollarsOf, annualInflation,
    effectiveTaxRate, retirementTaxRate, jurisdiction: refused while items need the old
    one, ADR-0071). `GET /api/new?jurisdiction=CA`: an empty scenario (default Canada).
  - `POST /api/items/update {scenario, id, item, clear}` (ADR-0070 amendment): the new
    values replace the item's fields, the fields in `clear` are removed; id and type
    stay (links kept); refused if invalid or if the type would change.
  - `POST /api/items/add {scenario, item}` (JSON values; an id and a name are given if
    missing; an item waiting for a trigger's date is added switched off, with a note; a
    trigger switches its waiting target on); `POST /api/items/toggle {scenario, id}`;
    `POST /api/items/delete {scenario, id}` (with the cascade, see the builder).
- `GET /api/schema?jurisdiction=CA`: item types, fields, choices, hints, legends, form
  groups, the fields shown when blank, percent fields (`schema.py`), for one jurisdiction
  (default Canada; ADR-0071): the core types plus its own, its account types as the
  `accountType` choices, its wording (`jurisdiction`: code, name, labels, limit columns),
  and every registered jurisdiction (`jurisdictions`).
- Views (`state_machine/views.py`) answer `{ok, messages, ...}`: `POST /api/view/builder
  {scenario}` (starts, display order, off items, trigger-set dates, choices);
  `POST /api/run {scenario}` -> `{scenario (as sent), result: {rows, holdings, ledger,
  tax, events}}`; `POST /api/view/ledger {scenario, month}`; `POST /api/timeline
  {scenario}` (the model, ADR-0066); `POST /api/compare {a, b}` (rows of both, same
  horizon).
- Limits: a body over 1 MB is refused (413); a scenario with more than 1,000 items or a
  horizon over 100 years is refused with a message (400). Responses are gzip-compressed
  when the client accepts it.

## UI pages
0. The scenario lives in the browser tab's sessionStorage (ADR-0069): it survives a
   refresh, not closing the tab; the server keeps nothing. A page's GET returns a shell;
   `web/static/web.js` posts the stored scenario (form field `scenario`) to the same URL
   and swaps in the page that comes back, which carries the new scenario
   (`<script id="scenario-state">`); forms are sent the same way. In-app links do not
   reload the page; closing or reloading a tab with changes since the last save or
   load asks first.
1. `/` builder (ADR-0070): one section per person (Income, Accounts, Pensions; a person
   card with their retirement and contribution room), then Household (the Scenario
   card with the settings and cash balances; Properties, Vehicles, Expenses; Other).
   Each item is a card with an estimated monthly figure for the base month (greyed, a
   hint: own amounts indexed to that month, percentages of their stated basis, mortgage
   payments from their terms; no run); an open card lists its linked items (modifiers,
   associated items, adjustments, triggers) with their figures, switches and delete.
   Items are added with "+ Add" buttons in each category and on each card, which fill
   in the owner or the link. Sections, categories and cards collapse. Taxable inflows
   (income, taxable pensions, their associated income, RRSP withdrawals) are estimated
   after tax at the person's rate in the base month (an RRSP withdrawal at its account's
   withdrawalTaxRate if set). A flow that starts later (e.g. a pension at retirement)
   shows "from YYYY-MM: X/mo", its first month in base-month dollars, outside the totals.
   A withdrawal is listed in its account's card and again under its person's Pensions
   ("from <account>"), counted once. Cards and rows have icons: "+" (show the card's
   "+ Add" buttons), a pencil (edit the item in its form, prefilled) and a trash can
   (delete, after a confirmation).
1a. `/flat` "Builder (flat)": the same items, figures and controls as one table in order
   of their start, modifiers and triggers indented under their host, with a "+ Add" bar
   at the top grouped by category (People & settings, Income & pensions, Accounts,
   Properties & mortgages, Vehicles, Expenses, Triggers). Actions return to the view they were sent from. Both views share their
   building blocks (`web/templates/_items.html`).
2. `/run`: plays the current scenario, showing a table with one row per month and the
   columns Month | Cash | Assets | Debts | Net worth. Negative values in red.
   `/run/break-even?property=<id>` (ADR-0073; `POST /api/view/break-even {scenario,
   property}`, linked from each property card): per month owned, a hypothetical sale's
   net proceeds (value − selling costs from the associated costs at the end − mortgage
   balance − closingPenalty) against the net investment (cash put in: the equity at the
   horizon start for a property bought before it, purchase less advances, mortgage
   payments, prepayments, penalties, improvements, associated expenses and costs), in
   two variants (ownership: without associated expenses flagged `alsoWhenRenting`; all);
   break-even = proceeds − investment, rent equivalent = (investment − proceeds) /
   months owned. Summary and monthly table; stops before a real sale.
   `/run/vehicle-cost?vehicle=<id>` (ADR-0074; `POST /api/view/vehicle-cost {scenario,
   vehicle}`, linked from each vehicle card): per month owned, cost of ownership =
   (paid so far: the purchase or the value at the horizon start, plus the vehicle's
   associated expenses and costs − (value − selling costs)) / months owned.
3. Save / Load: Save downloads the stored scenario as `<name>.json` (in the browser, no
   request); `/load` uploads a JSON file and replaces the current scenario. `/new`
   (ADR-0071) starts an empty scenario for the jurisdiction chosen (warning first if the
   current one has unsaved changes). The Scenario settings show the jurisdiction as a
   dropdown (switching refused while items need the current one); the nav shows it; the
   forms, account choices, limit items, run columns and ledger wording follow it.
4. `/compare`: upload two scenario files, run both, and show the two tables side by side.
   If the horizons differ, show an error (ADR-0028: compared scenarios share a horizon).

## Commits
One commit per change, on a branch for a pull request against `main` (see `CLAUDE.md` at
the repo root), gates passing, message ending with:
```
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```
Do not commit `.venv/` or `diagrams/svg/`.
