"""Month arithmetic and scenario date look-ups, copied verbatim from iteration 1's
engine.py (tag poc-iteration-1).

retirement_date, property_sales and mortgage_start live here (not in validation.py)
because both validation (WP1) and the compiler / item factories (WP3, WP4, WP7) need
them; WP1 imports them from here and must not redefine them.
"""
from .persons import owner_of, person_ids


def month_index(value, where):
    """'YYYY-MM-DD' -> absolute month number (year * 12 + month - 1)."""
    try:
        y, m, _d = (int(p) for p in str(value).split("-"))
        if not 1 <= m <= 12:
            raise ValueError
    except ValueError:
        raise ValueError(f"{where}: bad date {value!r}, expected YYYY-MM-DD")
    return y * 12 + m - 1


def month_label(idx):
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def base_month(scenario):
    """The base date of real values ("dollars of"), default the horizon start (ADR-0013)."""
    return month_index(scenario.get("dollarsOf") or scenario["horizon"]["start"], "dollarsOf")


def retirement_date(scenario):
    """'YYYY-MM-DD' of the first person's retirement month, or '' (ADR-0059, ADR-0061)."""
    return retirement_dates(scenario)[person_ids(scenario)[0]]


def retirement_dates(scenario):
    """{person id: 'YYYY-MM-DD' or ''} (ADR-0061): each person's retirement event (its
    owner; blank = the first person). Older files' retirementDate setting is converted
    to an event first (upgrade.py)."""
    from .triggers import prepared
    scenario = prepared(scenario)
    ids = person_ids(scenario)
    out = dict.fromkeys(ids, "")
    events = [i for i in scenario.get("items", []) if i.get("type") == "retirement"]
    seen = set()
    for event in events:
        pid = owner_of(event, scenario)
        if pid not in seen:
            seen.add(pid)
            out[pid] = event.get("retirementDate") or ""
    return out


def flow_window(item, env, first=None):
    """(first, last) month of a recurring item (reference prepare() L656-662): ``first``
    is the given one, else its startDate, else the retirement it follows (a pension or
    withdrawal with a blank start, ADR-0059, ADR-0061); ``last`` is its endDate, else the
    horizon end. Dates set by triggers are already in place (ADR-0065)."""
    if first is None:
        first = (month_index(item["startDate"], "startDate") if item.get("startDate")
                 else env.retirement_for(item))
    last = month_index(item["endDate"], "endDate") if item.get("endDate") else env.end
    return first, last


def property_sales(items):
    """asset id -> the sale item that sells it (older files' property saleDate is converted
    to a sale item by upgrade.py; a sale's date may come from a trigger, ADR-0065)."""
    sales = {}
    for item in items:
        if item.get("type") != "sale" or not item.get("saleDate"):
            continue        # no date yet: reported when the sale item is validated
        pid = item.get("property")
        if pid in sales:
            raise ValueError(f"item {item.get('name') or item.get('id')}: property "
                             f"{pid!r} is sold more than once")
        sales[pid] = item
    return sales


def mortgage_start(item, properties, where=""):
    """Month index a mortgage starts: its startDate, or the purchase date of the property
    (or vehicle, ADR-0074 amendment) it is tied to; ``properties`` maps ids to those."""
    if item.get("startDate"):
        return month_index(item["startDate"], f"{where}.startDate")
    if item.get("property"):
        return month_index(properties[item["property"]]["purchaseDate"], f"{where}.purchaseDate")
    raise ValueError(f"{where}: missing field 'startDate' (or link it to a property)")
