"""Persons of the household (``type: "person"``) — ADR-0061.

A person owns income, accounts, pensions, contribution room and a retirement event, and
has their own tax rates, tax accumulator and deduction pool. Everything else (cash,
properties, mortgages, vehicles, expenses, net worth) stays household-level (ADR-0002).

- A scenario without ``person`` items has one implicit person, id ``IMPLICIT``, using
  the scenario's tax rates: results are identical to before.
- A blank ``owner`` means the first person (decision 3).
- Contributions and withdrawals take the owner of their account (or pension); a
  spousal RRSP (an rrsp account with a ``contributor``) uses the contributor's room and
  deduction (decision 7).
- Items tied to retirement follow ``retirementOf`` if given, else their owner (own or
  via their account), else the first person (decision 4).

The helpers here work on the raw scenario dict so validation, the compiler and the
household share one definition (no engine imports). The item type is registered in
``rules/person.py``.
"""
IMPLICIT = "self"
# Items with an owner of their own (decision 2); the retirement event also has one.
# A jurisdiction adds its own (Canada: contributionRoom, ADR-0071): see owned_types().
OWNED_TYPES = ("income", "account", "pension", "retirement")
# Flows that take the owner of the account (or pension) they touch.
ACCOUNT_FLOWS = ("contribution", "withdrawal")


def owned_types():
    """OWNED_TYPES plus every jurisdiction's own owned item types (ADR-0071)."""
    from . import jurisdictions
    return OWNED_TYPES + tuple(t for j in jurisdictions.registered().values()
                               for t in j.owned_types)


def person_items(scenario):
    return [i for i in scenario.get("items", []) if i.get("type") == "person"]


def person_ids(scenario):
    """Person ids in item order; ``[IMPLICIT]`` when the scenario has none."""
    return [p.get("id") for p in person_items(scenario)] or [IMPLICIT]


def first_person(scenario):
    return person_ids(scenario)[0]


def owner_of(item, scenario, by_id=None):
    """The person an item belongs to: its ``owner``; for a contribution or withdrawal the
    owner of its account; else the first person."""
    if item.get("type") in ACCOUNT_FLOWS:
        by_id = by_id if by_id is not None else items_by_id(scenario)
        target = by_id.get(item.get("account"))
        if target is not None:
            return owner_of(target, scenario, by_id)
    return item.get("owner") or first_person(scenario)


def contributor_of(account_item, scenario):
    """Whose room and deduction a movement into the account uses (spousal RRSP)."""
    return account_item.get("contributor") or owner_of(account_item, scenario)


def retirement_person(item, scenario, by_id=None):
    """Whose retirement an item tied to retirement follows (decision 4)."""
    if item.get("retirementOf"):
        return item["retirementOf"]
    if item.get("type") in owned_types() or item.get("type") in ACCOUNT_FLOWS:
        return owner_of(item, scenario, by_id)
    return first_person(scenario)


def items_by_id(scenario):
    return {i.get("id"): i for i in scenario.get("items", [])
            if i.get("type") in ("account", "pension")}

