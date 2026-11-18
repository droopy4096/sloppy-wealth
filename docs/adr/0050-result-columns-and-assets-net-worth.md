# ADR-0050: Result columns group holdings as cash, investments, property, debts

- **Status:** Accepted
- **Date:** 2026-11-07
- **Relates to:** ADR-0011 (holding hierarchy), ADR-0013 (real values, base date),
  ADR-0031 (liquidation net worth); input to the output model (Q-34)

## Context
Users think of RRSP, TFSA and investments as "assets". In the model they are accounts,
next to the operating cash account, while `Asset` means real estate and vehicles. The PoC
added an "assets net worth" column (assets − debts) before any investment accounts existed.

## Decision
The main monthly result table has these columns:

| Column | Contents |
|---|---|
| Cash | the operating account only |
| Investments | every other account (RRSP, TFSA, non-registered) |
| Property & vehicles | all `Asset` holdings |
| Debts | all liabilities |
| Assets net worth | investments + property & vehicles − debts: everything except cash, net of debts. Shown in base-date dollars |
| Net worth | cash + assets net worth (nominal), plus its base-date-dollar version |

- A **per-holding breakdown** (each account, asset and loan) is available as detail, not in
  the main table.
- Investment balances are **gross**: tax still owed on tax-deferred balances appears only
  in liquidation net worth (ADR-0031), which remains a separate figure.

## Alternatives considered
- Treat investment accounts as assets in the domain model: blurs the tax treatment and
  return behaviour that make them accounts.
- Show one column per account: the main table would grow with every account added.

## Consequences
- The output model (Q-34) defines these columns as tallies (ADR-0027) over holding groups.
- In the PoC, "Assets net worth" already means everything except cash, net of debts; it
  will include accounts once they are added (Q-35).

## Amendment (2026-11-08): pension value goes into Investments (Q-38)
- The value of a guaranteed pension (ADR-0052) is included in the **Investments** column,
  with RRSP, TFSA and other accounts. No extra column: fewer columns keep side-by-side
  comparisons readable.
- The per-holding detail lists the pension separately.
- **Liquidation net worth excludes the pension value**: a guaranteed pension cannot
  normally be sold or cashed in.

## Amendment (2026-11-09): pension in liquidation net worth (C-P4)
- The previous amendment's exclusion is withdrawn. Liquidation net worth includes the
  pension's discounted value after tax at the effective rate (ADR-0052 amendment
  2026-11-09).
