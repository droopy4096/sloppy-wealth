"""Property break-even and rent equivalent (ADR-0073), read from a run.

For one property, every month it is owned at the month's end (from its purchase, or
from the horizon start for a property bought before it, decision 3):

- **net proceeds** of a hypothetical sale after that month: market value − selling
  costs (the property's, and its mortgages', associated costs at their end, ADR-0067: a
  rate x the value, or the amount) − the mortgages' balances − their early-closure
  penalties (holdings points' ``closingPenalty``, decision 4);
- **net investment**, two variants (decision 2): cash put in so far — the equity at the
  horizon start (bought before it), the purchase less the mortgage advances, mortgage
  payments, interest adjustments, prepayments and payoffs, penalties, improvements, and
  the associated expenses and costs of the property and its mortgages; **ownership**
  leaves out expenses flagged ``alsoWhenRenting`` (a renter pays them too), **all**
  keeps every one;
- **break-even** = net proceeds − net investment (positive: ahead), and **rent
  equivalent** = (net investment − net proceeds) / months owned: what owning cost per
  month, the rent that would have cost the same (negative once ahead).

Amounts are nominal (the ledger's). The run is not changed: the sale is hypothetical.
"""
from decimal import Decimal

from .dates import base_month, month_index, month_label
from .triggers import prepared

ZERO = Decimal("0.00")
CENT = Decimal("0.01")
PAID_TO_LOAN = ("LOAN_PAYMENT", "INTEREST_ADJUSTMENT", "PREPAYMENT", "LOAN_PAYOFF")
VARIANTS = ("ownership", "all")


def properties(scenario):
    """[(id, name)] of the scenario's properties (switched-off ones left out)."""
    return [(i["id"], i.get("name") or i["id"]) for i in prepared(scenario)["items"]
            if i.get("type") == "property" and i.get("id")]


def related(items, pid):
    """The ids around property ``pid``: its mortgages, every item that pays or charges for
    it (modifiers, associated items), the associated items a renter pays too, and its
    selling costs (associated costs at the end of the property or its mortgages)."""
    loans = {i["id"] for i in items if i.get("type") == "mortgage" and i.get("property") == pid}
    hosts = {pid} | loans
    sources = set(hosts)
    renter, selling = set(), []
    for i in items:
        kind, iid = i.get("type"), i.get("id")
        if kind in ("renewal", "extraPayment", "lumpSum") and i.get("mortgage") in loans:
            sources.add(iid)
        elif kind in ("sale", "improvement", "marketAdjustment") and i.get("property") == pid:
            sources.add(iid)
        elif kind in ("associatedExpense", "associatedCost") and i.get("parent") in hosts:
            sources.add(iid)
            if kind == "associatedExpense" and i.get("alsoWhenRenting") is True:
                renter.add(iid)
            if kind == "associatedCost" and i.get("at") == "end":
                selling.append(i)
    return loans, sources, renter, selling


def selling_costs(costs, value):
    total = Decimal(0)
    for c in costs:
        if c.get("rate") not in (None, ""):
            total += value * Decimal(str(c["rate"]))
        elif c.get("amount") not in (None, ""):
            total += Decimal(str(c["amount"]))
    return total.quantize(CENT)


def paid_for(line, pid, loans, sources):
    """Cash put into the property by one ledger line (negative: received), or None."""
    kind, amount = line["kind"], line["amount"]
    if kind == "PURCHASE" and line["to"] == pid:
        return amount
    if kind == "LOAN_ADVANCE" and line["from"] in loans:
        return -amount
    if kind in PAID_TO_LOAN and line["to"] in loans:
        return amount
    if kind == "IMPROVEMENT" and line["to"] == pid:
        return amount
    if kind in ("PENALTY", "EXPENSE", "COST") and line["source"] in sources:
        return amount
    return None


def break_even(scenario, result, pid):
    """{"property", "name", "rows": [...], "summary": {...}, "notes": [...]} for ``pid``."""
    s = prepared(scenario)
    item = next((i for i in s["items"] if i.get("type") == "property" and i.get("id") == pid),
                None)
    if item is None:
        raise ValueError(f"unknown property {pid!r}")
    loans, sources, renter, selling = related(s["items"], pid)
    holdings = {h["id"]: {p["month"]: p for p in h["points"]} for h in result["holdings"]}
    own = holdings.get(pid, {})
    start = month_index(s["horizon"]["start"], "horizon.start")
    sold = {x["month"] for x in result["ledger"] if x["kind"] == "SALE" and x["from"] == pid}
    sale_month = min(sold) if sold else None
    by_month = {}
    for x in result["ledger"]:
        by_month.setdefault(x["month"], []).append(x)

    rows, initial, first = [], None, None
    paid = {v: Decimal(0) for v in VARIANTS}
    for label in sorted(own):
        point = own[label]
        if sale_month is not None and label >= sale_month:
            break                               # sold: the real sale replaces the hypothesis
        if initial is None:
            bought_before = point.get("opening") is not None and month_index(
                item["purchaseDate"], "purchaseDate") < start
            # Bought before the horizon: the equity at its start is the investment so far.
            initial = (point["opening"] - sum(holdings.get(m, {}).get(label, {}).get("opening")
                                              or ZERO for m in loans)) if bought_before else ZERO
            first = month_index(label + "-01", "month")
        for x in by_month.get(label, []):
            amount = paid_for(x, pid, loans, sources)
            if amount is not None:
                paid["all"] += amount
                if x["source"] not in renter:
                    paid["ownership"] += amount
        value = point["closing"]
        balance = sum((holdings.get(m, {}).get(label, {}).get("closing") or ZERO
                       for m in loans), ZERO)
        penalty = sum((holdings.get(m, {}).get(label, {}).get("closingPenalty") or ZERO
                       for m in loans), ZERO)
        costs = selling_costs(selling, value)
        proceeds = value - costs - balance - penalty
        months = month_index(label + "-01", "month") - first + 1
        row = {"month": label, "monthsOwned": months, "value": value, "sellingCosts": costs,
               "balance": balance, "penalty": penalty, "netProceeds": proceeds}
        for v in VARIANTS:
            invested = initial + paid[v]
            gain = proceeds - invested
            row[v] = {"netInvestment": invested, "breakEven": gain,
                      "rentEquivalent": (-gain / months).quantize(CENT)}
        rows.append(row)

    summary = {"breakEvenMonth": {}, "current": None}
    for v in VARIANTS:
        summary["breakEvenMonth"][v] = next((r["month"] for r in rows
                                             if r[v]["breakEven"] >= 0), None)
    try:
        today = month_label(base_month(scenario))
    except (KeyError, ValueError):
        today = None
    summary["current"] = next((r for r in rows if r["month"] == today), rows[-1] if rows else None)
    notes = []
    if not selling:
        notes.append("No selling costs: add an associated cost at the property's end (e.g. a "
                     "realtor's rate of its value) to include them.")
    if loans and not any("closingPenalty" in p for m in loans for p in holdings.get(m, {}).values()):
        notes.append("No early-closure penalty: give the mortgage (or its renewals) a term "
                     "and a penalty method to include it.")
    if sale_month:
        notes.append(f"Sold in {sale_month}: the table stops the month before.")
    if initial and rows:
        notes.append(f"Bought before the horizon: the equity at its start ({initial}) counts "
                     "as already invested; months owned count from the horizon start.")
    return {"property": pid, "name": item.get("name") or pid, "rows": rows,
            "summary": summary, "notes": notes}
