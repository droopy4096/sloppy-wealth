# ADR-0061: Second earner — persons in the household

- **Status:** Accepted
- **Date:** 2026-11-11
- **Relates to:** ADR-0002 (single economic unit), ADR-0059 (retirement event and
  retirement tax rate), ADR-0060 (contribution room), ADR-0048 (RRSP deduction pool),
  ADR-0017 (tax)
- **Resolves (when accepted):** Q-06 (per-person rules), Q-39

## Context
The household has one earner. A second family income needs its own RRSP/TFSA
accounts and contribution room, retirement date and tax. Canadian rules that are
per individual (tax brackets, RRSP room from own earned income, TFSA room) cannot be
expressed while the whole household is one taxpayer.

The household stays one economic unit for money (ADR-0002): cash, properties,
mortgages, vehicles, expenses, sales and net worth remain shared. Only the rules that
are per individual move to a person. Scenario files without persons behave as one
implicit person using the scenario's tax rates, so their results are unchanged.

The last single-earner implementation is tagged `single-earner` (`poc/state-machine`,
e12a902).

## Decision
1. **A person is a `person` item** (id, name, optional `effectiveTaxRate` and
   `retirementTaxRate`; blank rates use the scenario's). It appears in the builder
   like other items and gives the `owner` field a list to choose from. Rejected: a
   free-text `owner` only (nowhere for per-person rates, typos unnoticed); a list of
   persons in the scenario settings (outside the item list and builder forms).

2. **Items with an `owner` field:** income, accounts (rrsp, tfsa and
   nonRegistered), pensions, contributionRoom and the retirement event.
   Contributions, withdrawals and transfers take the owner of the account they
   touch (no field of their own). Properties, mortgages, vehicles and expenses stay
   household-level. Rejected: owners on properties as well (work for a capital-gains
   split that is not modelled); non-registered accounts household-level (their
   investment income could not be taxed to one person).

3. **A blank owner means the first person** (in item order). Files without persons
   use one implicit person. Adding a partner only needs the owner set on the
   partner's own items. Rejected: blank owner an error once persons exist (every
   existing item must be edited); a separate "household" owner with the first
   person's rules (same effect, less clear).

4. **Household items tied to retirement name the person: `retirementOf`** (a person
   id; blank = the first person). Applies to every household item whose date can be
   "at retirement" (e.g. a sale, a payoff, an expense end). Owned items follow their
   owner's retirement. Rejected: always the first person (no sale at the partner's
   retirement); household-wide first/last retirement (no per-item control, surprising
   when dates change).

5. **Tax rates per person:** optional `effectiveTaxRate` and `retirementTaxRate` on
   the person; blank = the scenario's rate. Each person's taxable income is taxed at
   their own rate, switching to the retired rate at their own retirement (ADR-0059).
   Rejected: one household rate with only the switch per person (cannot show different
   brackets); per-person brackets (large new feature, against flat rates of ADR-0017).

6. **The carried-forward deduction pool (ADR-0048) is per person.** An RRSP deduction
   reduces only its owner's taxable income; the unused part carries forward in that
   person's pool. Canada has no joint filing and RRSP deductions are not transferable
   between spouses. Rejected: one household pool (overstates savings when incomes or
   rates differ). The legal route to a similar effect is a spousal RRSP (decision 7).

7. **Spousal RRSP is built now:** an rrsp account may name a `contributor` (a person
   id, different from its `owner`; blank = the owner). Contributions, transfers and
   openings from cash into it use the contributor's RRSP room and reduce the
   contributor's taxable income (contributor's deduction pool). Withdrawals are taxed
   to the owner. Not modelled at first: the attribution rule (withdrawals within about
   three calendar years of a contribution taxed to the contributor). Rejected:
   deferring it.

8. **Pension income splitting: deferred** (watch item). Pension income is taxed to
   its owner only; results overstate tax when one partner holds the pension. Possible
   later form: a `splitToSpouse` fraction (0–50%) on pensions. Rejected for now: the
   fixed fraction and an automatic best split each year.

9. **One owner per account.** RRSPs and TFSAs are individual by law; a joint
   non-registered account is assigned to one person, whose rate taxes its investment
   income. A 50/50 split is approximated by entering two accounts. Rejected: an
   `ownerShare` split on non-registered accounts (a split in every tax step).

10. **Results stay household-level.** Monthly rows keep their columns: cash,
    investments, net worth, total tax. The room columns show the household total per
    type (the sum over persons; unchanged with one person). Per-person figures (tax,
    deductions, room movements) are visible in the tax and ledger pages and the event
    log. The plan is judged on household outcomes. Rejected: per-person room and tax
    columns; per-person investments and net worth.

### Mechanics (defaults; not separate owner decisions)
- **Implicit person:** a file without `person` items has one person (id `self`) with
  the scenario's rates; results are identical to before (golden suite unchanged).
- **Owner inheritance:** contributions, withdrawals, transfers and drawdowns take the
  owner of their account; an employer match goes with its contribution.
- **Retirement:** one retirement event per person (ADR-0059); a salary ending at
  retirement uses its owner's date; every consumer of the retirement month asks for a
  named person's retirement.
- **Tax:** one tax accumulator per person: own taxable income, own rate (switching at
  own retirement), own deduction pool; one TAX movement per person per month.
  Investment income of an account is taxed to its owner.
- **Room:** contribution room is per (person, type): a `contributionRoom` item has an
  owner; RRSP room grows from that person's earned income; TFSA withdrawals add back
  to the owner's room. A spousal RRSP uses its contributor's room.
- **Not modelled:** pension income splitting (decision 8), the spousal RRSP
  attribution rule (decision 7), joint ownership splits (decision 9), CPP/OAS per
  person (ADR-0055 unchanged), transfer of credits between spouses.

## Alternatives considered
Listed with each decision above.

## Consequences
- A household with two earners gets realistic room, deductions and tax per person
  while every money outcome stays household-level (ADR-0002 holds for money).
- Existing scenario files and the golden suite are unchanged.
- About eleven engine parts read the retirement month; all must go through one lookup
  by person, with a test each, or they silently use the first person's date.
- Results understate available savings options (no pension splitting) and overstate
  tax when one partner holds most retirement income.
- The last single-earner implementation is tagged `single-earner`.
