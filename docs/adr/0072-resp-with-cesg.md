# ADR-0072: RESP accounts with the Canada Education Savings Grant (Canada)

- **Status:** Proposed (owner's decision 2026-11-18, Q-48)
- **Date:** 2026-11-18
- **Relates to:** ADR-0011 (investment accounts), ADR-0060 (contribution room), ADR-0071
  (jurisdictions: Canada's package)

## Context
Canadian households save for children's education in a Registered Education Savings Plan
(RESP). The owner's scenario held its RESP as a TFSA-like account, which leaves out the
federal grant, a sizeable part of an RESP's growth. The RESP rules (CRA, ESDC):
contributions are not deductible; growth is sheltered; on withdrawal the contributions
come back tax-free and the growth and grants are taxed to the student (usually nil). The
Canada Education Savings Grant (CESG) adds 20% of contributions, at most $500 of grant a
year, or $1,000 when unused grant room from earlier years is caught up, and $7,200 over
the beneficiary's lifetime. Lifetime contributions are limited to $50,000 per beneficiary.

## Decision (Q-48, owner 2026-11-18: "RESP + CESG grant")
1. Canada gets an account type `resp`: contributions not deductible, growth sheltered,
   withdrawals untaxed (the student's tax, usually nil, is not modelled).
2. One RESP account per beneficiary; a family plan is entered as one account per child.
3. **CESG**: every contribution or one-off transfer into an RESP brings a grant paid into
   the account from outside (movement `GRANT`), 20% of the amount, limited by:
   - the grant room: $500 for each calendar year from the horizon's first year, plus
     the unused room at the start (field `unusedGrantRoom`, default 0);
   - at most $1,000 of grant in a calendar year;
   - $7,200 over the account's life, less the grant already received before the horizon
     (field `grantReceived`, default 0).
4. **Lifetime contribution limit** $50,000 per account, less the contributions made
   before the horizon (field `contributedSoFar`, default 0): a contribution or transfer
   beyond it is capped, the excess stays in cash (as with contribution room, ADR-0060).
   An opening balance from outside is the existing balance: no grant, no limit.
5. The employer match does not apply to an RESP in practice; if entered, it gets no
   grant.

## Alternatives considered
- RESP as an account type only (TFSA-like, no grant or limit): the scenario's current
  workaround, without the grant.
- Full rules (withdrawals split into returned contributions and educational assistance
  payments taxed to the student, grant only until the beneficiary is 17, grant
  repayment if the child does not study): much more to enter and to test; deferred.

## Consequences
- Account items take type-specific fields (`unusedGrantRoom`, `grantReceived`,
  `contributedSoFar`) declared by the account type (`AccountType.fields`, ADR-0071).
- Canada's sample (conformance, ADR-0071) gains an RESP, so its golden result changes.
- Implemented 2026-11-18 on `poc/sm-resp`: `jurisdictions/ca/resp.py`. The grant is
  paid in `Canada.on_contribute` (which now gets the movement's source); the lifetime
  cap is in Canada's limits (`RoomLimits.cap`). A yearly amount is paid monthly, so
  its grant is 20% of each month's share (e.g. 12 x 83.33 = 999.96 for $5,000 a year).
- Not modelled: the Canada Learning Bond, provincial grants, additional CESG for
  lower-income families, the grant age limit, grant repayment, and tax on educational
  assistance payments.
