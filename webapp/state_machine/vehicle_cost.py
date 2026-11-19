"""Vehicle cost of ownership per month (ADR-0074), read from a run like the property
break-even (``break_even.py``, ADR-0073).

For one vehicle, every month it is owned at the month's end (from its purchase, or from
the horizon start for a vehicle bought before it):

- **paid so far**: the purchase price (or its value at the horizon start), plus every
  associated expense and cost of the vehicle (fuel, insurance, maintenance, repairs),
  penalties of its sale / market adjustment items, and the interest (and penalties) of
  the loans that finance it (a mortgage whose ``property`` is the vehicle, ADR-0074
  amendment; the principal is already the purchase price);
- **value**: its market value at the month's end less its selling costs (associated
  costs at its end, ADR-0067);
- **cost per month** = (paid so far − value) / months owned.

Amounts are nominal (the ledger's). The run is not changed.
"""
from decimal import Decimal

from .break_even import CENT, ZERO, selling_costs
from .dates import base_month, month_index, month_label
from .triggers import prepared


def vehicles(scenario):
    """[(id, name)] of the scenario's vehicles (switched-off ones left out)."""
    return [(i["id"], i.get("name") or i["id"]) for i in prepared(scenario)["items"]
            if i.get("type") == "vehicle" and i.get("id")]


def cost_of_ownership(scenario, result, vid):
    """{"vehicle", "name", "rows": [...], "summary": {...}, "notes": [...]} for ``vid``."""
    s = prepared(scenario)
    item = next((i for i in s["items"] if i.get("type") == "vehicle" and i.get("id") == vid),
                None)
    if item is None:
        raise ValueError(f"unknown vehicle {vid!r}")
    sources, selling = {vid}, []
    loans = {i.get("id") for i in s["items"] if i.get("type") == "mortgage"
             and i.get("property") == vid}
    sources |= loans
    for i in s["items"]:
        kind = i.get("type")
        if kind in ("renewal", "extraPayment", "lumpSum") and i.get("mortgage") in loans:
            sources.add(i.get("id"))
        if kind in ("sale", "marketAdjustment") and i.get("property") == vid:
            sources.add(i.get("id"))
        elif kind in ("associatedExpense", "associatedCost") and i.get("parent") == vid:
            sources.add(i.get("id"))
            if kind == "associatedCost" and i.get("at") == "end":
                selling.append(i)
    points = next((h for h in result["holdings"] if h["id"] == vid), {"points": []})["points"]
    start = month_index(s["horizon"]["start"], "horizon.start")
    sold = [x["month"] for x in result["ledger"] if x["kind"] == "SALE" and x["from"] == vid]
    sale_month = min(sold) if sold else None
    by_month = {}
    for x in result["ledger"]:
        by_month.setdefault(x["month"], []).append(x)

    rows, paid, interest, first, before = [], Decimal(0), Decimal(0), None, False
    for point in points:
        label = point["month"]
        if sale_month is not None and label >= sale_month:
            break                               # sold: the real sale ends the table
        if first is None:
            first = month_index(label + "-01", "month")
            before = point.get("opening") is not None and month_index(
                item["purchaseDate"], "purchaseDate") < start
            if before:                          # bought before the horizon
                paid = point["opening"]
        for x in by_month.get(label, []):
            if (x["kind"] == "PURCHASE" and x["to"] == vid) or (
                    x["kind"] in ("EXPENSE", "COST", "PENALTY") and x["source"] in sources):
                paid += x["amount"]
            elif x["kind"] == "LOAN_INTEREST" and x["from"] in loans:
                paid += x["amount"]
                interest += x["amount"]
        costs = selling_costs(selling, point["closing"])
        value = point["closing"] - costs
        months = month_index(label + "-01", "month") - first + 1
        rows.append({"month": label, "monthsOwned": months, "value": point["closing"],
                     "sellingCosts": costs, "netValue": value, "paidSoFar": paid,
                     "interestSoFar": interest,
                     "costPerMonth": ((paid - value) / months).quantize(CENT)})

    try:
        today = month_label(base_month(scenario))
    except (KeyError, ValueError):
        today = None
    summary = {"current": next((r for r in rows if r["month"] == today), None),
               "last": rows[-1] if rows else None}
    notes = []
    if sale_month:
        notes.append(f"Sold in {sale_month}: the table stops the month before.")
    if before and rows:
        notes.append(f"Bought before the horizon: its value at the horizon start "
                     f"({points[0]['opening']}) counts as already paid; months owned count "
                     "from the horizon start.")
    if not any(i.get("type") == "associatedExpense" and i.get("parent") == vid
               for i in s["items"]):
        notes.append("No running costs: add associated expenses (fuel, insurance, "
                     "maintenance) to the vehicle to include them.")
    return {"vehicle": vid, "name": item.get("name") or vid, "rows": rows,
            "summary": summary, "notes": notes, "financed": bool(loans)}
