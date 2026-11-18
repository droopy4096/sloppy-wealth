# Object inventory of the reference engine (`webapp/engine.py`)

> References to `engine.py` / "the reference" point to iteration 1 on branch
> poc/python-flask (tag poc-iteration-1).

Purpose: everything a re-implementation must reproduce to give byte-identical
`repr(run_detailed(s))` and identical `validate()` errors. Line numbers (`L123`) refer to
`webapp/engine.py` at the branch point. Where `webapp/SPEC.md` disagrees with the code (e.g.
"sale at opening value", "taxable income credited net"), **the code is the reference**.

Conventions used below:
- `D(x)` = `Decimal(str(x))`. All JSON numbers go through `Decimal(str(raw))`; never
  `Decimal(float)`. Default context (precision 28, never changed).
- `money(x)` = `x.quantize(Decimal("0.01"), ROUND_HALF_EVEN)` (L80).
- `power(b, e)` = `(b.ln() * e).exp()` (L106). Used for every fractional power. Integer
  powers use `**` (exact Decimal power) — the two must not be swapped.
- `month_index("YYYY-MM-DD")` = `y*12 + m - 1` (L111); `month_label(i)` =
  `f"{i//12:04d}-{i%12+1:02d}"` (L122).
- `PER = {"month": 1, "quarter": 3, "year": 12}` (L1082) is the `divisor`.
- **Truthiness on raw JSON values** decides "given / not given" almost everywhere
  (`item.get(x)`): `""`, missing, `0`, `0.0`, `false` are "absent"; the *string* `"0"` is
  present. Ports must test the raw value, not the parsed Decimal.
- Ledger `move(kind, src, dst, amount, source)` (L580): `amount = money(amount)`; if 0 →
  **no line, returns Decimal 0.00**; else apply `-amount` to src, `+amount` to dst, and
  append `{"month", "kind", "from", "to", "amount", "source"}` (that key order). `_apply`
  (L576): for kind in `LIABILITIES=("mortgage",)` the delta is negated (money *from* a loan
  raises its balance). `None` = outside the model. Negative amounts are recorded.

**Names in the state-machine engine (since E7).** This inventory predates the emitter
model; the "phases" below are the reference `step` stages, now the `clock.Order` numbers
(phase × 100, INTERFACES.md §10.2). The planned handler classes became emitters and
events: a dated event (§3) → a `OneShotEmitter` (or `ModifierEmitter` for improvement,
market adjustment, sale, renewal, lump sum) emitting an `Event`; a recurring process
(§4) → a `RecurringEmitter`; holdings at the start → an `InitialEmitter`; the runtime
`RetirementEvent` (§3.10) → `RetirementEmitter` emitting a `Retirement` state event; the
tax step (§4.9) → `TaxEmitter` / `TaxStepEvent`; the results recorder (§7) → `Recorder`.
`base.Handler/Event/Process/InitialEvent` and `clock.Phase` no longer exist.

---

## 1. Main object: Household (today `Simulation`, L546) — WP0 (core), WP7 (tax), WP8 (results)

| Field | Init (line) | Meaning / notes |
|---|---|---|
| `scenario` | L551 | raw dict |
| `start`, `end` | L552–553 | month indexes of horizon (inclusive) |
| `inflation` | L554 | `D(annualInflation or "0")` |
| `tax_rate` | L555 | `D(effectiveTaxRate or "0")` |
| `retirement` | L556–557 | month index of `retirement_date(scenario)` or `None` |
| `retirement_tax_rate` | L559–560 | `D(rtr) if rtr else tax_rate` (raw truthiness: number `0` = no switch, `"0"` = 0%) |
| `base` | L561 | `base_month(s)`: `dollarsOf or horizon.start` (L1095) |
| `covered` | L564 | `incomeMode == "expensesCovered"` |
| `holdings` | L565 + prepare | **dict, insertion order = output order**: `"cash"` first, then one entry per `account`, `pension`, `mortgage`, `property`, `vehicle` item **in scenario item order** (kinds interleaved). Key = `item.id or f"item{n}"` (n = item index). Duplicate id overwrites the value but keeps the first slot. |
| `ledger` | L567 | list of movement dicts |
| `month` | L568 | current month index (`None` before first step) |
| `taxable`, `deductions` | L569–570, reset L777–778 | per-month accumulators (Decimal 0) |
| `extra_tax` | L779 only | per-month own-rate withdrawal tax, **unrounded**; attribute exists only after first `step` |
| `pool` | L571 | carried-forward unused deductions (never reset) |
| `tax_detail` | L572 | `month_label -> dict` (see §4.9) |
| `opening` | L782 | `{id: balance}` of `opened` holdings at start of month |
| `flows` | prepare | income+expense dicts, item order (§4.1) |
| `extras` | prepare | extraPayment+lumpSum dicts, **one list, item order** (§3.8, §4.3) |
| `renewals` | prepare | dict `(mortgageId, month) -> (r, resetMonths|None, penalty, rid)` |
| `improvements`, `adjustments`, `transfers`, `contributions`, `withdrawals` | prepare | lists in item order |

Cash holding (L565): `{"id": "cash", "name": "Cash", "kind": "cash", "balance": money(D(openingCash))}`.
No `rate` key (points show `rate: None`), no return, may go negative. Aggregate class: **Cash** (WP0).

`step(m)` (L775): sets month, resets taxable/deductions/extra_tax, freezes
`opened = [h for h in holdings.values() if kind != "cash" and balance is not None]`
(holdings order) and `opening`, then calls the phases (§6).

---

## 2. Aggregates

Common holding keys: `id`, `name` (`item.name or id`), `kind`, `balance` (`None` = not yet
existing; points are only emitted when not None), `rate` (reported in points).
`GROUPS` (L542): cash→cash, property→property, vehicle→property, mortgage→debts,
account→investments, pension→investments.

### 2.1 RealEstate (`type: "property"`) — WP3
JSON: `id`, `name`, `purchaseDate`*, `price`*, `annualAppreciation`* (-1<r<1),
`marketValue` (opt, ≥0), legacy sale fields `saleDate`, `sellingCostRate`, `salePenalty`
(the property itself acts as its sale item, §3.6).

Internal (L744–772):
| key | value |
|---|---|
| `at` | `month_index(purchaseDate)` (kept even if < start) |
| `amount` | `money(D(price))` |
| `value` | `money(D(marketValue)) if marketValue else None` |
| `rate` | `power(ONE + D(annualAppreciation), ONE/12) - 1` (monthly) |
| `upkeep` | `Decimal(0)`; `upkeepRate` = `D(maintenanceIncrease or "0")` (unused) |
| `saleAt`, `sellingCost`, `salePenalty`, `salePrice`, `saleId` | from `property_sales` (§3.6) |
| `fixedAt` | set to m by a newValue market adjustment (L869) |
| `sold` | `True` after sale (L879) |

Lifecycle: PLANNED (`balance None`) → ACTIVE → SOLD (`balance 0`, `sold True`, stays in
`opened` forever after, points continue with closing 0.00).
- Pre-horizon (`at < start`, L767–772): `balance = money(base * (ONE + rate) ** (start - at))`,
  `base = value or amount`; integer power; no ledger line; ACTIVE from month 1 (in `opened`).
- `at >= start`: activated by Purchase in ACQUIRE of month `at` (§3.1). Not in `opened`
  that month → no growth in purchase month.
Growth (L1011–1013): if `balance` truthy (current) and `fixedAt != month`:
`APPRECIATION None→id, opening[id] * rate, src=id`.
Points: `opening`, `closing`, `rate` (monthly rate).

### 2.2 Vehicle (`type: "vehicle"`) — WP3
JSON: `purchaseDate`*, `price`*, `annualDepreciation`* (-1<r<1), `annualMaintenance`*,
`maintenanceIncrease` (opt, -1<r<1). No `marketValue` (always `value None`). Can be sold
by a `sale` item whose `property` = vehicle id (not by legacy saleDate).
Internal as property except: `rate = power(ONE - D(annualDepreciation), ONE/12) - 1`
(negative), `upkeep = D(annualMaintenance)` (annual, unrounded), `upkeepRate =
D(maintenanceIncrease or "0")`.
Lifecycle/pre-horizon/growth identical to property (growth kind is still `APPRECIATION`,
negative amounts).
Maintenance (L906–911, holdings order, all holdings): if `balance is not None` and not
`sold` and not `covered`: `MAINTENANCE cash→None, indexed(upkeep, upkeepRate, m - at, 12),
src=id`. Includes purchase month; anniversaries from real purchase (also pre-horizon).

### 2.3 Mortgage (`type: "mortgage"`) — WP4
JSON: `principal`*, `annualRate`* (0≤r<1), `amortizationYears`* (×12 whole, ≥1),
`startDate` (opt if `property` given), `property` (securedBy), `firstPaymentDate` (opt).

Internal (L732–743):
| key | value |
|---|---|
| `securedBy` | `property or None` |
| `at` | `mortgage_start` (L84): `startDate`, else linked property's `purchaseDate` |
| `firstPay` | `month_index(firstPaymentDate)` if given else `at + 1` |
| `amount` | `money(D(principal))` (advance and accrual base) |
| `rate` | `monthly_rate(annualRate)` = `power(ONE + D(annual)/2, ONE/6) - 1` (L514) |
| `payment` | `annuity(D(principal) /*unrounded*/, r, n)` via `mortgage_terms` (L526) |
| `left` | `n = int(D(amortizationYears) * 12)` remaining scheduled payments |
| `term` | set by renewal: renewal id (source of later interest/payments) |
| `accrued` | interest accrued before `firstPay` (unrounded sum of rounded moves) |

`annuity(balance, r, n)` (L519): `money(balance / n)` if `r == 0` else
`money(balance * r / (1 - (1 + r) ** -n))`.

Balance sign: positive = owed. Lifecycle: PLANNED → (LoanAdvance at `at`) → ACCRUING
(`at < m < firstPay`) → AMORTIZING → PAID_OFF (balance 0.00; never serviced again).
Serviced only if in `opened` **and** `balance > 0` at SERVICE_DEBT time (L899–901), so
not in the advance month, and not in a month a sale paid it off.

Per serviced month `pay_mortgage(h, m)` (L969–1005), in order:
1. Renewal if `(id, m) in renewals` (§3.7).
2. `term = h.get("term") or id`.
3. If `m < firstPay` (ACCRUING): `interest = move(LOAN_INTEREST, id→None, amount * rate, term)`
   (on the rounded principal, simple, raises the balance); `accrued += interest`; **return**
   (no payment, `left` unchanged, extras skipped).
4. If `accrued` truthy: `INTEREST_ADJUSTMENT (None if covered else cash)→id, accrued, term`; `accrued = 0`.
5. `LOAN_INTEREST id→None, balance * rate, term`.
6. `left -= 1`; `owed = balance`; `payment = owed if left <= 0 else min(payment, owed)`;
   `LOAN_PAYMENT (None if covered else cash)→id, payment, term`.
7. Extras for this loan, `extras` list order (§3.8 lump sums, §4.3 extra payments).
Points: `opening`, `closing`, `rate` (current monthly rate, changes at renewal), plus
`interest`, `paid`, `principalPaid` (§7.2).

### 2.4 InvestmentAccount (`type: "account"`) — WP5
JSON: `accountType`* ∈ (`tfsa`,`rrsp`,`nonRegistered`), `annualReturn`* (-1<r<1),
`openingBalance` (opt ≥0), `openedDate` (opt, blank = horizon start), `openingFrom`
(`""`/`cash`/`outside`), `withdrawalTaxRate` (opt 0≤r<1, used for rrsp).

Internal (L624–638): `accountType`; `rate = power(ONE + D(annualReturn), ONE/12) - 1`;
`withdrawalTaxRate = D(w) if w else None` (raw truthiness: number 0 → None → taxed as
income); `openingBalance = money(D(openingBalance or "0"))`; `openingFrom = openingFrom or
"outside"`; with `at0 = month_index(openedDate) if openedDate else start`:
`at = at0 if at0 > start else None`; `balance = openingBalance if at0 <= start else None`.

Lifecycle: OPEN from month 1 (at0 ≤ start, statement balance, no ledger line) or PLANNED →
OPEN by AccountOpening in month `at` (§3.3). Not in `opened` in its opening month.
Growth (L1014–1019, every `opened` account, no balance check):
`ret = move(RETURN, None→id, opening[id] * rate, id)`; if `nonRegistered`:
`taxable += max(Decimal(0), ret)` (`ret` is the rounded result, 0.00 if dropped).
Points: `opening`, `closing`, `rate` (monthly return).

### 2.5 Pension (`type: "pension"`) — WP6
JSON: `amount`+`per` (or legacy `monthlyAmount`), `startDate` (blank = retirement),
`endDate`, `endsAtRetirement`, `taxable` (default **true**), `indexing`
(`none`/`inflation`/`custom`), `indexRate`.

Internal (L639–655):
| key | value |
|---|---|
| `base`, `divisor` | `flow_amount` (L93): `D(amount), per or "month"`; or `D(monthlyAmount), "month"`; divisor = PER |
| `first` | `month_index(startDate)` if given else `retirement` |
| `last` | `min(month_index(endDate) if endDate else end, retirement - 1 if endsAtRetirement and retirement is not None else end)` (always ≤ end) |
| `rate` | annual indexing: `inflation` / `D(indexRate)` / `Decimal(0)` |
| `taxable` | `item.get("taxable", True)` |
| `balance` | `pension_value(h, start - 1)` at prepare (exists from month 1, always in `opened`) |

`pension_payment(h, m)` (L795): `years = (m - base) // 12`;
`money(base * (ONE + rate) ** years / divisor)` (indexing from **base date**, not from `first`).
`pension_value(h, m)` (L801):
```
real = Decimal(0)
for k in range(max(m + 1, first), last + 1):
    years = (k - self.base) // 12
    real += base * ((ONE + rate) / (ONE + inflation)) ** years / divisor
factor = power(ONE + inflation, Decimal(m - self.base) / 12) if inflation else ONE
return money(real * factor)
```
Payment (PENSION_PAY phase, L811–821, holdings order): if `first <= m <= last`:
`paid = move(PENSION_PAYMENT, id→cash, pension_payment(h, m), id)`; if `taxable`:
`taxable += paid`. Runs in covered mode too.
Revaluation (L823–827, every pension, every month, holdings order):
`REVALUATION None→id, pension_value(h, m) - balance, id` (may be negative; zero dropped).
Contribution target: §4.4. Points: `opening`, `closing`, `rate` = **annual indexing rate**.

---

## 3. Events (discrete, dated)

### 3.1 Purchase (property / vehicle) — WP3
Trigger: `h["at"] == m`, ACQUIRE phase (L840–854), loop over `list(holdings.values())`
(mixed kinds with LoanAdvance and AccountOpening). Effects: `balance = Decimal("0.00")`;
`PURCHASE cash→id, amount, id`; if `value` truthy: `REVALUATION None→id, value - amount, id`.
Pre-horizon purchases never fire (at < start).

### 3.2 LoanAdvance (mortgage) — WP4
Same loop, kind mortgage: `balance = 0.00`; `LOAN_ADVANCE id→cash, amount, id`
(balance becomes +amount). A mortgage item listed before its property advances first.

### 3.3 AccountOpening — WP5
Same loop, kind account with `at == m` (only when opened after start): `balance = 0.00`;
`openingFrom == "cash"` → `OPENING_TRANSFER cash→id, openingBalance, id`; else
`OPENING_BALANCE None→id, openingBalance, id`. Zero balance → no line, but account exists.

### 3.4 Improvement — WP3
JSON: `property`*, `improvementDate`*, `cost`*, `valueAdded` (opt). Internal (L680–686):
`cost = money(D(cost))`, `at`, `valueAdded = money(D(valueAdded)) if valueAdded else cost`
(raw truthiness: number `0` → cost). IMPROVE phase (L856–859), item order, `at == m`:
`IMPROVEMENT cash→property, cost, iid`; `REVALUATION None→property, valueAdded - cost, iid`.
Properties only (validated).

### 3.5 MarketAdjustment — WP3
JSON: `property`*, `adjustmentDate`*, exactly one of `percent` (-1<p<1) / `newValue` (≥0).
Internal (L616–623): `percent = D(percent) if percent else None`, `newValue =
money(D(newValue)) if newValue else None`. ADJUST phase (L862–870), item order, `at == m`:
percent → `change = balance * percent` (balance after this month's improvements);
else `change = newValue - balance`, `h["fixedAt"] = m` (no APPRECIATION this month).
`MARKET_ADJUSTMENT None→property, change, iid`.

### 3.6 Sale — WP3
Sources: `sale` item (`property` = property or vehicle id, `saleDate` or `atRetirement`,
`sellingCostRate`, `salePenalty`, `salePrice`) or legacy property with `saleDate`
(then sale fields are read from the property; `saleId` = property id).
`property_sales(items, retirement)` (L58): dict asset id → sale item, in item order;
`atRetirement` sale copied with `saleDate = retirement` (when retirement set); dateless
sale items skipped; second sale of same id → ValueError "is sold more than once".
Attached to the asset at prepare (L760–765): `saleAt`, `sellingCost = D(sellingCostRate
or "0")`, `salePenalty = D(salePenalty or "0")` (unrounded), `salePrice =
money(D(salePrice)) if sale and salePrice else None` (raw `0` → None → sells at value),
`saleId = sale.id or asset iid`.
SELL phase (L871–887), loop `list(holdings.values())`, `saleAt == m`:
1. if `salePrice is not None`: `SALE_PRICE_DIFFERENCE None→id, salePrice - balance, saleId`.
2. `price = balance`; `sold = True`; `SALE id→cash, price, saleId`.
3. `SELLING_COST cash→None, price * sellingCost, saleId`.
4. for `loan in holdings.values()` (holdings order) with `securedBy == id` and `balance`
   truthy: `LOAN_PAYOFF cash→loan, loan.balance, saleId` (includes any accrued interest).
5. `PENALTY cash→None, salePenalty, saleId`.
Effect on same month: paid-off loan skipped in SERVICE_DEBT; asset gets no maintenance
(`sold`) and no growth (balance 0). No capital-gains tax (C-M8).

### 3.7 Renewal — WP4
JSON: `mortgage`*, `startDate`*, `annualRate`*, `amortizationYears` (opt), `penalty` (opt).
Internal (L687–692): key `(mortgage, month_index(startDate))` →
`(monthly_rate(annualRate), int(D(amort) * 12) if amort else None, D(penalty or "0"), iid)`.
Fires inside `pay_mortgage` step 1 (only if the loan is serviced that month; else silently
lost, incl. penalty): `rate = r`; `term = rid`; `left = reset or left`;
`payment = annuity(balance, rate, left)` (current balance, before this month's interest;
in ACCRUING months this includes accrued interest); `PENALTY cash→None, penalty, rid`.

### 3.8 LumpSum — WP4
JSON: `mortgage`*, `paymentDate` or `atRetirement`, `amount` or `payOff: true`,
`paidFrom` (`cash` default / `outside`), `penalty`.
Internal (L701–710): `first = last = retirement if atRetirement else month_index(paymentDate)`;
`amount = None if payOff else money(D(amount))`; `recurring False`; `fromCash = (paidFrom
or "cash") == "cash"`; `penalty = D(penalty or "0")`.
Fires in `pay_mortgage` step 7 (after the scheduled payment, in `extras` order):
`src = "cash" if fromCash else None` (independent of covered);
`amt = balance if amount is None else min(amount, balance)`; `PREPAYMENT src→loan, amt, iid`;
then `PENALTY cash→None, penalty, iid` (charged even if PREPAYMENT was 0). Skipped
entirely in ACCRUING months or when the loan is not serviced.

### 3.9 Transfer — WP5
JSON: `account`*, `amount`* (>0), `transferDate` or `atRetirement`.
Internal (L609–615): `at = retirement if atRetirement else month_index(transferDate)`,
`amount = money(D(amount))`. TRANSFER phase (L890–895), item order, after sales:
`TRANSFER cash→account, amount, iid` (from cash even when covered); if account is `rrsp`
and not covered: `deductions += amount`.

### 3.10 Retirement — WP7 (per D2: runtime retirement event; code: `RetirementEmitter`)
JSON: `{"type": "retirement", "retirementDate"}` (≤1); legacy scenario `retirementDate`.
`retirement_date(s)` (L49): first retirement item's `retirementDate or ""`, else
`s.retirementDate or ""`. Today: no ledger line, skipped in prepare (L607). Effects to
reproduce: tax rate switch `month >= retirement` (§4.9); anchors resolved at prepare:
income/expense `startsAtRetirement` first (§4.1), `endsAtRetirement` last = `retirement-1`
(income, expense, contribution, withdrawal, extraPayment, pension), pension/withdrawal
blank start = retirement, sale/lumpSum/transfer `atRetirement` month = retirement.
Look-ahead required: pension initial value at `start-1` and every `pension_value` need
`first`/`last`; even drawdown divisor needs `last`; `amountIn: base` needs `first`.

---

## 4. Recurring processes / flows

`active(f, m)` = `f["first"] <= m <= f["last"]` (L791). `indexed(base, rate, k, divisor=1)`
(L534) = `money(base * (ONE + rate) ** (k // 12) / divisor)` (integer power, anniversary step).
Indexing rate resolution (all flows): `inflation` → `self.inflation`; `custom` →
`D(indexRate)`; else `Decimal(0)`.

### 4.1 Income / Expense — WP7
JSON: `amount`+`per` / legacy `monthlyAmount`; `startDate` (blank allowed with
`startsAtRetirement`); `endDate`; `startsAtRetirement`/`endsAtRetirement`; `indexing`,
`indexRate`; `amountIn` (`start` default / `base`); `taxable` (income only, default false).
Internal (L711–731): `first = retirement if startsAtRetirement and retirement is not None
else month_index(startDate)`; `last = month_index(endDate) if endDate else end`, then
`min(last, retirement - 1)` if endsAtRetirement and retirement set; `base = amount`, and if
`amountIn == "base" and inflation` (truthy): `base = amount * power(ONE + inflation,
Decimal(first - self.base) / 12)` (**unrounded**); `divisor = PER[per]`;
`taxable = kind == "income" and item.get("taxable", False)`.
- INCOME phase (L829–836), `flows` order, active and not covered:
  `gross = indexed(base, rate, m - first, divisor)`; `INCOME None→cash, gross, iid`; if
  taxable: `taxable += gross`.
- EXPENSE phase (L902–905), `flows` order, active and not covered:
  `EXPENSE cash→None, indexed(base, rate, m - first, divisor), iid`.
Covered mode: no line at all.

### 4.2 Mortgage service (payment, interest, accrual) — WP4
See §2.3 `pay_mortgage`. Interest source/payment source tagged with `term`.

### 4.3 ExtraPayment — WP4
JSON: `mortgage`*, `startDate`*, `endDate`, `endsAtRetirement`, `monthlyAmount`* (>0).
Internal (L693–700): `first`, `last` (endDate or end; endsAtRetirement cap),
`amount = money(D(monthlyAmount))`, `recurring True`.
In `pay_mortgage` step 7 when `first <= m <= last`: `src = None if covered else "cash"`;
`PREPAYMENT src→loan, min(amount, balance), iid`. Does not change `payment` or `left`.

### 4.4 Contribution — WP5 (account) / WP6 (pension target)
JSON: `account`* (account **or pension** id), `startDate`*, `endDate`, `endsAtRetirement`,
`amount`/`per`, `indexing`, `employerMatch` (0..1).
Internal (L656–671): `first = startDate`, `last`, `rate`, `base`, `divisor`,
`match = D(employerMatch or "0")`.
CONTRIBUTE phase (L915–936), item order; skip unless active and target `balance is not None`:
`amount = indexed(base, rate, m - first, divisor)`.
- Pension target: if not covered: `amount = move(PENSION_CONTRIBUTION, cash→None, amount, iid)`;
  `deductions += amount`. Covered: nothing. Pension value unchanged.
- Account: `CONTRIBUTION (None if covered else cash)→acct, amount, iid`; if `rrsp` and not
  covered: `deductions += amount`; then `EMPLOYER_MATCH None→acct, amount * match, iid`
  (always outside; not income, not deduction).

### 4.5 Withdrawal — WP5
JSON: `account`*, `method`* ∈ (`amount`,`percent`,`annuity`; `even` = unindexed annuity), `startDate` (blank =
retirement), `endDate`, `endsAtRetirement`, `amount`/`per`+`indexing` (amount),
`annualRate` (percent, 0<r<1), `indexing` (amount, annuity).
Internal (L656–679): `first = startDate or retirement`, `last`, `rate`, `method`;
amount → `base`, `divisor`; percent → `annualRate = D(annualRate)`; mutable `monthly`.
WITHDRAW phase (L938–967), item order; skip if not active:
1. percent and `(m - first) % 12 == 0`: `bal = opening.get(acct.id, acct.balance) or
   Decimal(0)`; `monthly = money(bal * annualRate / 12)` (runs even if balance is 0/None).
2. `if not acct.balance: continue` (None or 0).
3. amount: `indexed(base, rate, m - first, divisor)`; percent: `f.get("monthly", Decimal(0))`;
   annuity (ADR-0039 am. 2026-11-11): `final = min(last, end)`; in `final` request the
   whole balance; else if `monthly` unset or `(m - first) % 12 == 0`:
   `monthly = money(balance / annuity_factor(acct.rate, rate, final - m + 1))` (growing
   annuity, g = indexing rate; closed form in `flows/withdrawal.py`), use it.
4. `amt = move(WITHDRAWAL, acct→cash, min(amount, balance), iid)`.
5. rrsp: `withdrawalTaxRate is not None` → `extra_tax += amt * withdrawalTaxRate`
   (unrounded); else `taxable += amt`. tfsa/nonRegistered: untaxed.
Covered mode: unchanged (still into cash, still taxed).

### 4.6 Vehicle maintenance — WP3: §2.2.
### 4.7 Growth (APPRECIATION / RETURN) — WP3/WP5: §2.1, §2.4. On `opening`, over `opened`.
### 4.8 Pension payment and revaluation — WP6: §2.5.

### 4.9 Tax step — WP7 (L1021–1036)
```
retired = self.retirement is not None and self.month >= self.retirement
rate = self.retirement_tax_rate if retired else self.tax_rate
pool_in = self.pool
available = self.deductions + self.pool
used = min(available, max(Decimal(0), self.taxable))
self.pool = available - used
due = money(rate * (max(Decimal(0), self.taxable) - used))
tax_detail[label] = {"taxable": money(taxable), "deductions": money(deductions),
  "poolIn": money(pool_in), "used": money(used), "poolOut": money(pool),
  "rate": rate /*unrounded*/, "retired": retired, "incomeTax": due,
  "ownRateTax": money(extra_tax), "total": due + money(extra_tax)}
move("TAX", "cash", None, due + money(extra_tax), None)   # source None; 0 → no line
```
Always paid from cash (also covered). Detail written every month.

---

## 5. Rules (to be Rule objects)

| Rule | Inputs | Formula (line) | Referenced by |
|---|---|---|---|
| MonetaryRounding | x | `money` L80; applied in `move`, `annuity`, `indexed`, `pension_payment`, `pension_value`, prepare amounts, percent/even `monthly`, tax `due`, real net worth | all |
| CompoundingRule.semiAnnual | annual | `power(ONE + D(annual)/2, ONE/6) - 1` L514 | Mortgage, Renewal |
| CompoundingRule.annualToMonthly | annual | `power(ONE + D(a), ONE/12) - 1` (appreciation, return), `power(ONE - D(d), ONE/12) - 1` (depreciation) L631, L746, L749 | RealEstate, Vehicle, InvestmentAccount |
| CompoundingRule.preHorizon | value, monthly r, months | `money(base * (ONE + rate) ** (start - at))` L772 | RealEstate, Vehicle |
| AmortizationRule | balance, r, n | `annuity` L519; last payment `owed if left <= 0`, cap `min(payment, owed)` L994 | Mortgage, Renewal |
| IndexingRule | base, rate, months since anchor, divisor | `indexed` L534; anchor = flow `first` (income, expense, contribution, withdrawal-amount), vehicle `at` (maintenance, divisor 12); pension uses **base date** anchor in its own formula L798 | Income, Expense, Contribution, Withdrawal(amount), Vehicle, Pension |
| AmountInBaseRule | amount, inflation, first, base | `amount * power(ONE + inflation, Decimal(first - base) / 12)` if `amountIn=="base"` and inflation, L725–728 | Income, Expense |
| IncomeModeRule (`expensesCovered`) | covered | skip INCOME, EXPENSE, MAINTENANCE, pension contribution; source `None` for LOAN_PAYMENT, INTEREST_ADJUSTMENT, recurring PREPAYMENT, CONTRIBUTION; no RRSP deduction (contribution, transfer). Unaffected: purchases, advances, openings, improvements, sales, penalties, transfers, lump sums (paidFrom), pension payments, withdrawals, match, tax | Household, all flows, Mortgage |
| Jurisdiction.on_return (ADR-0071) | treatment, ret | `returns_taxed` (CA nonRegistered): `taxable += max(0, ret)` L1016–1019; else untaxed | InvestmentAccount |
| Jurisdiction.on_withdraw (ADR-0071) | treatment, withdrawalTaxRate, amt | `withdrawal_taxed` (CA rrsp): own rate → `extra_tax += amt * rate`, else `taxable += amt` L963–967 | InvestmentAccount |
| Jurisdiction.on_contribute (ADR-0071) | treatment | `deductible` (CA rrsp) contribution or transfer, not covered: the contributor's `deductions += amount`; pension contributions: in `holdings/pension.py` | InvestmentAccount |
| TaxRule | taxable, deductions, pool, extra_tax, retired — per person (ADR-0061) | §4.9, once per person: own accumulator, rate (`person.current_tax_rate`) and pool; one TAX movement each (source = person id with several persons); `household.tax_detail` = the person's detail (one person) or the sums + `persons` | Household, Person |
| PensionValuationRule | base, rate, inflation, first, last, base month | `pension_value` L801 | Pension |
| RoomLimits: Canada's `jurisdiction.limits` (ADR-0060, `jurisdictions/ca/room.py`) | account type, amount; earned income, TFSA withdrawals per year | `cap`: min(amount, room) and uses it up (before the as-of month or without a room item: unchanged); new room each January: RRSP min(money(rate × earned[y−1]), max(y)), TFSA max(y) + withdrawn[y−1]; max(y) = yearlyMax·(1+g)^(y−maxYear) rounded half-up to $10 / $500 | Contribution, Transfer, AccountOpening, Income, Withdrawal; keyed by (person, type) (ADR-0061): the account's contributor's room, the income owner's earned income, the account owner's TFSA withdrawals; rows show the total per type |
| CapitalGainsRule | — | **no-op** (C-M8) | RealEstate, Vehicle, InvestmentAccount |
| RealValueRule | netWorth, inflation, offset | §7.1 | Results |

---

## 6. Exact intra-month ordering (`step`, L775–789)

0. OPEN: `month = m`; `taxable = deductions = extra_tax = Decimal(0)`; `opened` (holdings
   order, non-cash, balance not None); `opening = {id: balance}`. (`run` separately
   snapshots every holding incl. cash for points, L1055.)
1. INCOME: `flows` in item order, kind income → INCOME.
2. PENSION_PAY: `holdings` order, pensions → PENSION_PAYMENT.
3. ACQUIRE: `list(holdings.values())` order, `at == m`: per holding PURCHASE[, REVALUATION]
   | LOAN_ADVANCE | OPENING_TRANSFER/OPENING_BALANCE.
4. IMPROVE: `improvements` item order: IMPROVEMENT, REVALUATION.
5. ADJUST: `adjustments` item order: MARKET_ADJUSTMENT.
6. SELL: `list(holdings.values())` order, `saleAt == m`: [SALE_PRICE_DIFFERENCE], SALE,
   SELLING_COST, LOAN_PAYOFF × (holdings order of secured loans), PENALTY.
7. TRANSFER: `transfers` item order: TRANSFER.
8. SERVICE_DEBT: `opened` order (holdings order), mortgages with current balance > 0;
   per loan: [renewal PENALTY]; ACCRUING: LOAN_INTEREST, stop; else [INTEREST_ADJUSTMENT],
   LOAN_INTEREST, LOAN_PAYMENT, then `extras` in item order filtered to this loan and
   active: extraPayment → PREPAYMENT; lumpSum → PREPAYMENT, PENALTY.
9. EXPENSE: `flows` item order, kind expense → EXPENSE.
10. MAINTAIN: `holdings` order, vehicles → MAINTENANCE.
11. CONTRIBUTE: `contributions` item order: PENSION_CONTRIBUTION | CONTRIBUTION, EMPLOYER_MATCH.
12. WITHDRAW: `withdrawals` item order: WITHDRAWAL.
13. GROW: `opened` order: property/vehicle APPRECIATION; account RETURN.
14. REVALUE_PENSIONS: `holdings` order: REVALUATION.
15. TAX: TAX.
16. CLOSE (in `run`): row + points.
Every line above is suppressed when its rounded amount is 0.

Ledger kinds summary (from → to; source):
| kind | from | to | source |
|---|---|---|---|
| INCOME | None | cash | flow id |
| PENSION_PAYMENT | pension | cash | pension id |
| PURCHASE | cash | asset | asset id |
| REVALUATION | None | asset/pension | asset id / improvement id / pension id |
| LOAN_ADVANCE | loan | cash | loan id |
| OPENING_TRANSFER / OPENING_BALANCE | cash / None | account | account id |
| IMPROVEMENT | cash | property | improvement id |
| MARKET_ADJUSTMENT | None | property | adjustment id |
| SALE_PRICE_DIFFERENCE | None | asset | saleId |
| SALE | asset | cash | saleId |
| SELLING_COST | cash | None | saleId |
| LOAN_PAYOFF | cash | loan | saleId |
| PENALTY | cash | None | saleId / renewal id / lumpSum id |
| TRANSFER | cash | account | transfer id |
| LOAN_INTEREST | loan | None | term (renewal id or loan id) |
| INTEREST_ADJUSTMENT, LOAN_PAYMENT | cash or None | loan | term |
| PREPAYMENT | cash or None | loan | extra/lumpSum id |
| EXPENSE, MAINTENANCE | cash | None | flow id / vehicle id |
| PENSION_CONTRIBUTION | cash | None | contribution id |
| CONTRIBUTION | cash or None | account | contribution id |
| EMPLOYER_MATCH | None | account | contribution id |
| WITHDRAWAL | account | cash | withdrawal id |
| APPRECIATION, RETURN | None | asset/account | holding id |
| TAX | cash | None | None |

---

## 7. Results — WP8

### 7.1 Rows (`row`, L1039; `add_real_net_worth`, L1100)
`total(kinds)` = `sum(balance for holdings in kinds if balance is not None, Decimal("0.00"))`.
Key order: `month`, `cash`, `investments` (account+pension), `assets` (property+vehicle),
`debts` (mortgage), `assetsNetWorth = investments + assets - debts`,
`netWorth = cash + anw`, then appended `realNetWorth`, `realAssetsNetWorth`:
`offset = start - base`; for row k: `factor = power(ONE + inflation, Decimal(offset + k) / 12)
if inflation else ONE`; `money(netWorth / factor)`, `money(assetsNetWorth / factor)`.
(Inflation re-read from the scenario: `D(annualInflation or "0")`.)

### 7.2 Holdings detail (`run`, L1052–1077)
- `detail = {hid: [] for hid in holdings}` built **before** the loop (all holdings exist
  after prepare; D1: the new engine must emit an entry for every holding item, in this
  order, even before creation).
- Per month, after `step`: for each holding with `balance is not None`, append
  `{"month", "opening": balance before step (None in creation month), "closing": balance,
  "rate": h.get("rate")}`.
- Loans: scan ledger once: `LOAN_INTEREST` → `flows[(month, from)][0] += amount`;
  `LOAN_PAYMENT`, `PREPAYMENT`, `LOAN_PAYOFF`, `INTEREST_ADJUSTMENT` →
  `flows[(month, to)][1] += amount` (accumulators start at `Decimal(0)`). Each mortgage point
  gets `interest`, `paid`, `principalPaid = paid - interest`; default
  `(Decimal(0), Decimal(0))` → reprs `Decimal('0')`, not `0.00`. ACCRUING months give
  negative `principalPaid`; the first-payment month counts INTEREST_ADJUSTMENT as paid.
- Entry: `{"id", "name", "kind", "group": GROUPS[kind], "points"}`.
### 7.3 Tax detail: `tax_detail` (§4.9), month order.
### 7.4 Return: `{"rows", "holdings", "ledger", "tax"}` (L1078).

### 7.5 Public API (facade must export)
- `app.py`: `validate`, `run`, `run_detailed`, `retirement_date`, `month_label`,
  `month_index`, `base_month`.
- `test_engine.py`: `run` (168×), `run_detailed` (33×), `retirement_date`, `annuity`,
  `monthly_rate`, `mortgage_terms`, `from engine import money`.
- `run_detailed(s)` = `validate(s)` then `Simulation(s).run()`; `run(s)` = its `rows`.

---

## 8. Validation (`validate`, L135–503; port verbatim — WP1)
Order matters (first error wins). Messages start with `scenario:`, `horizon:` or
`item {name or id or index}:` (`where`).

Scenario level (L137–175), in order: missing `horizon`/`openingCash`/`items`; bad
`horizon.start`/`end` date; "end is before start"; `openingCash` number; `annualInflation`
-1<x<1; `dollarsOf` date; "only one retirement event is allowed"; "has both a retirement
event and a retirementDate setting"; `retirementDate` date; `retirementTaxRate` 0≤x<1;
`incomeMode` ∈ modelled/expensesCovered; `effectiveTaxRate` 0≤x<1; then
`property_sales` ("is sold more than once") — before the item loop.

Per item, in order (L176–503):
1. "unknown type"; REQUIRED loop (L181–203): skip `property`/`accountType`/`method`;
   `account` → "refers to unknown account" (contribution: accounts+pensions); `mortgage` →
   "refers to unknown mortgage"; `*Date` → "missing field", bad date, property/vehicle
   "{field} is after the horizon end"; else `dec` ("missing field" / "is not a number").
2. mortgage: unknown property; `mortgage_start` ("missing field 'startDate' (or link it to a
   property)"); "startDate is outside the horizon"; "starts before its property is
   purchased"; "starts after its property is sold".
3. property `marketValue` ≥0; sale `salePrice` ≥0.
4. property/sale: `sellingCostRate` 0≤x<1; sale target property **or vehicle** ("refers to
   unknown property"; `item["property"]` missing → **KeyError**); sale: atRetirement bool;
   "give a saleDate or atRetirement, not both"; "sells at retirement, but the scenario has no
   retirement event"; "missing field 'saleDate' (or sell at retirement)"; saleDate: "is before
   the horizon start {label}; remove the asset, or move the horizon"; "saleDate must be after
   the purchase and within the horizon".
5. income/expense: `flow_amount` ("per must be month, quarter or year", "missing field
   'amount'"); taxable bool; ends/startsAtRetirement bool; "cannot both start and end at
   retirement"; "starts at retirement, but the scenario has no retirement event"; "missing
   field 'startDate'"; startDate date; indexing ∈ none/inflation/custom; amountIn ∈
   start/base; custom `indexRate` -1<x<1.
6. any type with endDate and startDate: "endDate is before startDate".
7. rate ranges for REQUIRED `annualAppreciation`/`annualDepreciation` (-1<r<1) and
   `annualRate` (0≤r<1): "must be a fraction between ... e.g. 0.0379 for 3.79%".
8. any type `salePenalty`/`penalty` ≥0.
9. renewal: "startDate must be after the mortgage start"; `check_amortization`
   (L506: "amortizationYears must be a whole number of months, at least 1"); renewal at/after
   securing property's sale ("is in the same month as"/"after" "the sale of ... remove the
   renewal, or put the penalty on the sale"); "another renewal of this mortgage starts in the
   same month".
10. lumpSum: atRetirement/payOff bool; paymentDate+atRetirement not both; at retirement
    needs event; "missing field 'paymentDate' (or pay at retirement)"; "give an amount or
    payOff, not both"; "paymentDate must be after the mortgage start"; then paidFrom ∈
    cash/outside.
11. extraPayment `monthlyAmount` / lumpSum (not payOff) `amount`: "amount must be positive".
12. account: accountType in list (missing → **KeyError**); annualReturn -1<x<1;
    withdrawalTaxRate 0≤x<1; openingBalance ≥0; "openedDate is after the horizon";
    openingFrom ∈ ""/cash/outside; inside-horizon opening with balance needs openingFrom.
13. pension: flow_amount; "needs a startDate or a retirement event"; start/end dates; "ends
    {..}, before its effective start"; "ends at retirement, but starts .. not before it";
    taxable bool; indexing; custom indexRate.
14. contribution: flow_amount; employerMatch 0≤x≤1.
15. contribution/withdrawal/extraPayment/pension: endsAtRetirement bool.
16. contribution/withdrawal: indexing ∈ none/inflation/custom.
17. withdrawal: "needs a startDate or a retirement event"; begin date; percent/even "starts
    .., before its account .. opens"; method in list (missing → **KeyError** at L405);
    "indexing applies only to method 'amount'"; amount method without amount (hint about
    percent); percent without annualRate (hint about amount); amount → flow_amount; percent
    0<annualRate<1.
18. transfer: amount >0; atRetirement bool; not both; needs event; "missing field
    'transferDate'"; "transferDate must be within the horizon"; "transfers .., before its
    account .. opens".
19. retirement: "retirementDate must be within the horizon".
20. marketAdjustment: unknown property (properties only; missing key → KeyError);
    "adjustmentDate is before the horizon start; include it in the property's marketValue
    instead"; on/after purchase and within horizon; "must be before the sale"; "give either
    percent or newValue, not both" (`bool(percent) == bool(newValue)`, so neither also fails);
    percent -1<x<1; newValue ≥0.
21. improvement: unknown property (KeyError if missing); "improvementDate is before the
    horizon start"; on/after purchase and within horizon; "must be before the sale"; "cost
    and valueAdded must not be negative".
22. vehicle maintenanceIncrease -1<x<1.
23. mortgage firstPaymentDate "must be after the mortgage start"; `check_amortization`.

---

## 9. Parity hazards found (surprising or fragile)

1. Raw-truthiness defaults: numeric `0` (not `"0"`) for `marketValue`, `salePrice`,
   `valueAdded` (→ cost), `withdrawalTaxRate` (→ taxed as income), `retirementTaxRate`
   (→ no switch), `amortizationYears` on renewal (→ keep remaining term).
2. Validation raises **KeyError** (not ValueError) for a sale/improvement/marketAdjustment
   without `property`, an account without `accountType`, a withdrawal without `method`.
3. Holdings order = item order across kinds; duplicate ids keep the first slot; items without
   id become `item{n}` and cannot be referenced.
4. ACCRUING mortgage: interest is simple on the rounded principal but **raises the
   balance**; `left` only counts from `firstPay`; a renewal in that window annuitises
   principal + accrued; lump sums / extras (and their penalty) in that window are dropped.
5. Renewal or lump sum on a loan already at 0 (e.g. prepaid off) is silently lost with its
   penalty; a lump-sum PENALTY is charged even when its PREPAYMENT rounds to 0.
6. Payment is annuitised on the **unrounded** principal; the advance uses the rounded one.
7. Points: `interest`/`paid`/`principalPaid` default `Decimal('0')` (exponent 0) while
   ledger sums carry `0.00`; pension `rate` is the annual indexing rate, others monthly.
8. Sold assets keep `balance 0.00` (not None): they stay in `opened`, keep emitting points,
   and growth is suppressed only by the zero balance.
9. Covered mode drops EXPENSE/MAINTENANCE/pension contribution lines entirely but keeps
   loan-payment and contribution lines with `from None`; TAX is still taken from cash.
10. `extra_tax` and `amountIn: base` amounts stay unrounded until their final use.
11. Percent withdrawal re-bases on `opening.get(id, balance)` (current balance in the
    account's opening month); the annuity is set from the *current* balance at the first
    non-zero month and re-set on each anniversary of `first`.
12. Pension indexing counts years from the **base date**; flows count from their `first`.
13. `pension_value` uses `power` for the inflation factor but an integer `**` for the
    real ratio; preserve both expressions exactly.
