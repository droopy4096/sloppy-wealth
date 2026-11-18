# Glossary (draft)

These are the exact terms the diagrams and ADRs use. Decisions behind these terms: ADR-0011 to ADR-0053.

## Planning concepts

| Term | Definition |
|---|---|
| **Enabled (item switch)** | Every item can be switched off in the builder; an off item, and every item that refers to it, is left out of the run but kept in the file. Used to keep several variations in one file (ADR-0064). |
| **Associated expense / cost** | An item that belongs to a parent item and lives exactly as long as it: a recurring expense (e.g. property tax, vehicle maintenance, account fees) or a one-off cost at the parent's start, end or a date (e.g. closing or selling costs); a fixed amount or a yearly percentage of a value looked up from the parent (ADR-0067, proposed). |
| **Associated income** | An income that belongs to a parent income or pension and lives exactly as long as it: recurring (e.g. a bonus, a 13th-month pension; paid monthly or as a lump at the end of each full quarter or year) or one-off at the parent's start, end or a date (signing bonus, severance); a fixed amount or a yearly percentage of the parent's yearly amount; taxed and owned as its parent (ADR-0068, proposed). |
| **Trigger** | Ties a date of one item (its start or end) to the date of another item, the event, e.g. a salary ends at retirement, a sale happens at retirement. `on: end` uses the event's end instead (an income's end, an asset's sale), e.g. property tax ends with the house. Resolved before the run (ADR-0065, proposed). |
| **Timeline** | The builder's picture of a scenario over time: lasting items as lanes branching off their host and merging back where they end, one-off items as dots, triggers as arrows (ADR-0066, proposed). |
| **Economic Unit** | The single entity being planned for: an individual or a family treated as one (ADR-0002). Owns everything in a scenario. |
| **Cash Balance Event** | States the actual cash balance at the end of a month; the engine sets cash to it and records the difference as a reconciliation from or to outside, not taxed (ADR-0063). |
| **Cash Flow Adjustment** | A new amount for a cash flow from a date, in dollars of that date; the flow's indexing continues from it (ADR-0062). E.g. a property tax reassessment. |
| **Person** | A member of the economic unit with their own income, accounts, pensions, contribution room, retirement date, tax rates and deduction pool (ADR-0061). Money outcomes stay household-level. A file without persons has one implicit person. |
| **Owner** | The person an income, account, pension, contribution room or retirement event belongs to; blank = the first person. Flows into or out of an account take the account's owner (ADR-0061). |
| **Contributor** | On a spousal RRSP: the person whose room and deduction a contribution uses; withdrawals are taxed to the owner (ADR-0061). |
| **retirementOf** | On a household item tied to retirement (sale, payoff, transfer, expense end): whose retirement it follows; blank = the first person (ADR-0061). |
| **Scenario** | A named, self-contained description of one strategy: the economic unit's accounts, assets, liabilities, cash flows, events, assumptions, goals and horizon (ADR-0006). The unit of input to the engine. |
| **Horizon** | The start and end dates of a scenario's projection. Defined per scenario. |
| **Goal** | A condition over one or more tallies, evaluated every month (ADR-0027), e.g. "retirement funds ≥ $1M" or "monthly pension income ≥ $3k". Observed only, never solved for (ADR-0006). |
| **Global Goal** | A goal evaluated against the whole economic unit (net worth). Real dollars by default (ADR-0014). |
| **Local Goal** | A goal attached to one holding, stating a condition that holding should reach (e.g. mortgage paid off). Nominal by default (ADR-0014). |
| **Goal Kind** | REACH (reports when first met) or MAINTAIN (must hold throughout; reports when first violated) (ADR-0014). |
| **Shortfall** | The unpaid part of a debit that exceeded the funds available in its source account in a period (ADR-0015). |
| **Reference Birth Date** | Optional. The birth date the plan's ages are framed around; ages are only a way of entering dates (ADR-0016). |
| **Scenario Set** | One or more scenarios plus set-level goals, run together in lockstep; the engine's unit of invocation (ADR-0028). |
| **Tally** | A named running quantity updated every month after the month closes: holding metric, net worth, tag sum, or derived formula (ADR-0027). |
| **Set-level Goal** | A goal in a scenario set whose condition reads tallies from any of its scenarios, e.g. rent vs buy break-even (ADR-0028). |
| **Active Window** | Optional activeFrom and activeUntil on a goal; the goal is evaluated only inside it (ADR-0037). |
| **Comparison** | Two or more projection results of different scenarios, set side by side for evaluation. |

## Things that hold or owe value

| Term | Definition |
|---|---|
| **Holding** | Anything the economic unit owns or owes whose value changes over time. The common base type of Account, Asset and Liability. Net worth is the sum of all holdings, with liabilities counted as negative (ADR-0011). |
| **Account** | A holding: a container of money with a tax treatment, e.g. TFSA, RRSP, non-registered investments, cash. Its balance changes through cash flows and returns. |
| **Break-even** (property) | Each month, the net proceeds of a hypothetical sale (market value − selling costs − mortgage balance − early-closure penalty) minus the net investment: everything paid for the property so far (from the horizon start for a property bought before it). Positive = ahead. Two variants: ownership costs, and all linked costs (ADR-0073). |
| **Rent equivalent** | (net investment − net proceeds) / months owned: what owning cost per month so far, i.e. the rent that would have cost the same; negative once owning is ahead (ADR-0073). |
| **Cost of ownership** (vehicle) | Each month: (everything paid for the vehicle so far − its value net of selling costs) / months owned (ADR-0074). |
| **RESP** | Registered Education Savings Plan (Canada): an account for a child's education; contributions not deductible, growth sheltered, withdrawals untaxed in the model. Contributions bring the **CESG** grant (20%, at most $500 a year or $1,000 with carried-forward room, $7,200 lifetime); lifetime contributions are limited to $50,000. One account per beneficiary (ADR-0072). |
| **Asset** | A holding: a non-cash item whose value changes over time, e.g. real estate or a vehicle. Grows (appreciation) or shrinks (depreciation) according to a rate generator, and may carry costs. |
| **Liability** | A holding with negative value: an amount owed that is paid down over time, e.g. a mortgage. Has an interest rate generator and a payment schedule, and may have prepayment options and early closure penalties. |
| **Acquisition Price** | What it cost to acquire an asset (purchase price). A fixed input, and the basis for variable costs (ADR-0022). |
| **Cost Basis** | Running metric: acquisition price + costs paid on the asset. Used for capital gains and "value exceeds amount invested" goals (ADR-0014, ADR-0017). |
| **Loan** | An amortising liability with an interest rate generator, optionally secured by an asset (e.g. a car loan). Settled when its securing asset is sold (ADR-0024). |
| **Mortgage** | A loan secured against a real-estate asset, with amortisation, a payment schedule, prepayment options and early closure penalties. |
| **Scheduled Payment** | A loan's regular payment, derived by the engine and recalculated whenever the rate changes (ADR-0029). |
| **Prepayment** | An extra payment against a liability beyond its schedule: one-off (lump sum) or recurring (e.g. doubled payments). Limited by the mortgage's prepayment options. |
| **Early Closure Penalty** | The cost of paying a liability off or breaking it before its term ends. Entered by hand on the event that breaks the loan (sale, switch inside a term, prepayment beyond privileges), in dollars of that date (ADR-0047). |

## Movements of money

| Term | Definition |
|---|---|
| **Cash Flow** | A recurring **monthly** movement of money (amounts may be stated per month, quarter or year; quarterly and yearly amounts are spread evenly, ADR-0021) with a start date, an optional end date and an amount: income (salary, pension), expense (rent, living costs) or transfer (contribution to an account). Has an **indexing** (ADR-0013). Recurring changes, such as doubled payments from a date, are cash flows (ADR-0012). |
| **Cost** | A cash flow attached to an asset or liability. **Fixed cost**: a set amount, e.g. property tax or insurance. **Variable cost**: an annual percentage of the asset's **acquisition price**, spread monthly and then indexed (ADR-0022). |
| **Event** | A one-off, dated occurrence that changes the scenario's state, e.g. buying a property, selling a vehicle, a lump-sum prepayment, retirement. Has an absolute date (ADR-0007). Can be authored directly or generated by an event generator (ADR-0012). |
| **Event Generator** | A rule that produces a series of concrete one-off events following a pattern, e.g. "salary +2% every 1 April from 2027". Expanded into events during event placement (ADR-0012). |
| **One-off Transfer** | An event moving a single amount from an account (or from outside) to a holding (or outside), e.g. a down payment or a gift (ADR-0025). |
| **Improvement** | An event that adds to an asset already owned, e.g. building a house on a parcel or a renovation: its cost is paid (possibly financed by a loan), the cost basis rises by the cost and the value by the value added (ADR-0046). |
| **Owned / not owned** | A holding that is not owned (e.g. a leased vehicle) is projected but excluded from net worth and costs. A purchase event makes it owned at its current value (ADR-0026). |
| **Sweep Rule** | Moves anything above a buffer from one account to another each month, after tax (ADR-0030). |
| **Selling Cost Rate** | Percentage of the sale price lost to selling an asset (realtor, legal). Reduces proceeds and the capital gain (ADR-0031). |
| **Liquidation Net Worth** | Net worth minus the selling costs and taxes that liquidating everything would trigger (ADR-0031). |
| **Revaluation** | A one-off dated event that changes an asset's value by a % or to a set value, e.g. a market shock (ADR-0033). |
| **Negative Equity** | A sale whose proceeds do not cover its secured loans. The deficit is debited from the proceeds account, and any unpaid part becomes a shortfall (ADR-0034). |
| **Pension** | A guaranteed income cash flow until the end of the horizon, usually inflation-indexed and taxable; it has no holding or value in net worth (ADR-0036). |
| **Drawdown Cash Flow** | Draws a pot to zero at the end of the draw (`method: annuity`) as an annuity at the account's expected return, recomputed each year; with `indexing` it keeps its purchasing power. A fixed `amount` can be indexed too but runs until the pot is empty; `even` is the retired name of the unindexed annuity (ADR-0039). |
| **Operating Account** | The implicit "cash" account in every scenario; the default for income, payments, proceeds and tax (ADR-0040). |
| **Neutral Default** | The value used for an omitted optional field, chosen so it contributes nothing (e.g. rate 0) (ADR-0040). |
| **Variant Sweep** | Authoring tooling that generates a scenario set by shifting tagged objects over a range of offsets, to find the earliest variant whose goals hold (ADR-0038). |
| **Movement** | A single money transaction computed in one period (an interest accrual, payment, cost, transfer). Each one is rounded to 2 dp, half-even (ADR-0009). |

## Assumptions

| Term | Definition |
|---|---|
| **Rate Generator** | Anything that gives a rate for a period, `rateFor(period)`: constant, segmented (dated segments), term schedule (mortgage terms and renewals), or probabilistic later (ADR-0019). |
| **Term Schedule** | A rate generator made of consecutive terms (start, length, rate), e.g. a 2y term then 5y then 3y. Also tells which term a period falls in, for penalties (ADR-0019). |
| **Renewal** | The start of a new mortgage term, with a new rate and optionally a new amortisation. The scheduled payment is recalculated. Switching to another institution is a renewal with a new rate and amortisation (ADR-0043). |
| **Compounding Convention** | How a holding turns an annual rate into a monthly one: MONTHLY, SEMI_ANNUAL (Canadian fixed mortgages), ANNUAL (ADR-0019). |
| **Rate Source** | Whatever supplies rate generators to the engine. It is deterministic today; it is the place where Monte Carlo would plug in (ADR-0005). |
| **Inflation** | A rate generator describing the general rise in prices. Used to index cash flows that choose it, and to report values in real dollars (ADR-0013). |
| **Base Date** | Scenario input: the date whose dollars "today's dollars" inputs (pension amounts, REAL goals) are in. Defaults to the scenario start; usually set to today. Changing it restates those inputs (ADR-0013). |
| **Display Dollars Of** | View setting: the date whose dollars real columns are shown in; default the base date. Changes display only (ADR-0013). |
| **Indexing** | How a cash flow's amount changes over time: **fixed nominal** (never changes, e.g. a mortgage payment), **inflation-indexed** (e.g. living costs), or a **custom rate generator** (e.g. salary growth) (ADR-0013). |
| **Nominal / Real values** | Nominal: amounts in the dollars of each period. Real: amounts deflated by inflation to the dollars of a reference date (by default the scenario start) (ADR-0013). |
| **Appreciation / Depreciation** | A rate generator applied to an asset's value, positive or negative. |
| **Return** | A rate generator applied to an account balance (investment growth or interest). |
| **Tax Treatment** | The tax category of an account: **tax-free** (TFSA), **tax-deferred** (RRSP), **taxable** (non-registered, cash). |
| **Deduction** | Money the member pays into a tax-deferred account (e.g. an RRSP contribution; not the employer match) reduces taxable income in the same month, never below zero (ADR-0048). |
| **Contribution** | A cash flow into an account (RRSP, TFSA, investments), optionally with an employer match: the employer adds a share of each contribution from outside (ADR-0051). |
| **Percent Withdrawal** | A withdrawal of a percentage of a fund: on its start and each anniversary, rate × the balance then, paid as 1/12 each month (ADR-0049). |
| **Pension Entitlement** | A guaranteed (defined-benefit) pension held as a holding: it pays from the retirement date to the horizon end, and its amount is in today's dollars and its value is the present value of the payments still to come at a real discount rate (default 2%), in today's dollars; after tax in liquidation net worth (ADR-0052). |
| **Retirement Date** | The month of a person's Retirement Event (ADR-0059, ADR-0061; formerly a scenario field, ADR-0052). |
| **Assets Net Worth** | Everything except the operating cash account, net of debts: investments (including the value of guaranteed pensions) + property & vehicles − debts. Shown in base-date dollars (ADR-0050). |
| **Taxable Flag** | An optional flag on an income cash flow. Income is entered net (after tax) by default; flagged income is taxed at the effective rate (ADR-0020). |
| **Capital Gain** | Sale price minus cost basis on an asset sale. Taxed at inclusion rate × effective tax rate; principal residences are exempt (ADR-0017). |
| **Effective Tax Rate** | A scenario assumption (rate generator) used by the simple tax model (ADR-0017). |
| **Withdrawal Tax Rate** | An optional rate on a tax-deferred account that overrides the effective tax rate for its withdrawals (ADR-0035). |
| **Tax Paid From** | The account that pays every tax the engine computes (ADR-0035). |
| **Tax Rules** | The interface the engine queries for the tax effect of a movement, given a tax treatment and a date. Implemented per **jurisdiction** (Canada first) (ADR-0004). |
| **Jurisdiction** | The tax country a scenario targets (`jurisdiction`: ISO code, default CA; one per scenario). A plug-in package (`state_machine/jurisdictions/<code>/`) declaring its account types with their **treatment**, its own item types, labels, contribution limits and hooks (ADR-0071). |
| **Treatment** | How an account type is taxed, as three flags: contributions deductible, returns taxed, withdrawals taxed (RRSP and traditional 401(k): deductible and withdrawals taxed; TFSA and Roth: none; non-registered and brokerage: returns taxed) (ADR-0071). |

## Time

| Term | Definition |
|---|---|
| **Calendar** | The ordered sequence of periods covering a scenario's horizon. |
| **Period** | One calendar month, identified by year and month. The engine's unit of time (ADR-0007). |
| **Tag** | A label on holdings, cash flows, events and generators. Used to attribute movements (e.g. the total cost of `vehicle`) and to select objects for a time shift (ADR-0023). |
| **Time Shift** | An operation that moves one or more dated objects (of any type) by an offset. Dates are independent, so a shift only moves what is selected (ADR-0007). |
| **Shift Mode** | START, END or BOTH: which dates of the selected objects a time shift moves (ADR-0041). |
| **Time-shiftable** | The property shared by every object with a date that a time shift can move. |

## Engine

| Term | Definition |
|---|---|
| **Engine** | The stateless, platform-agnostic core that turns a scenario into a projection result (ADR-0003). |
| **State** | The complete JSON document passed through the pipeline. It is enriched by each stage and never modified in place (ADR-0010). |
| **Stage** | A pure function from one state to a new, enriched state. Either a whole-timeline stage or the monthly stepping stage (ADR-0010). |
| **Step** | One operation inside the monthly stepping stage, applied to one period (e.g. accrue interest). The order of steps is open (Q-08). |
| **Closed Period** | A period whose steps have all run. Its state is final and is read by the next period. |
| **Projection Result** | The final state, or the part of it a consumer needs: the timeline of balances and values, the movements, and goal observations. Built so results can be compared. |
| **Goal Observation** | A record of whether and when (in which period) a goal was first met. |
| **Residence Switch** | Event that moves the principal-residence designation to another owned property from its month; a sale's exempt share is (1 + designated years) ÷ owned years (ADR-0056). |
| **Retirement Event** | The event whose month is retirement: salaries tied to it end, pensions and withdrawals without own start dates begin, and the tax rate switches to the retirement tax rate (ADR-0059). |
