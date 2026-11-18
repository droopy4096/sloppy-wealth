"""Result assembly (WP8): rows, holdings detail, ledger and tax (OBJECTS §7).

- ``setup_results`` (``@scenario_setup("results", order=90)``) records, at compile time,
  every holding item in slot order (D1: holdings that are never created still get an
  entry) and yields the CLOSE recorder (ordinal SCENARIO, sub 0).
- ``Recorder`` (a ScenarioEmitter at Order.CLOSE) appends, each month after every other
  emitter, the row (``Simulation.row``) and one point per existing aggregate
  (``Simulation.run`` L1055-1062). Recording is bookkeeping, not a change of the
  household, so it is **not** an event: ``emit`` writes the results state directly and
  returns no events, and the public event log (D-E4) holds domain events only. The
  results state is the only thing an emitter writes outside an event.
- ``assemble(household)`` adds the loan flows from the ledger, builds the holdings list,
  applies ``add_real_net_worth`` and returns ``{"rows", "holdings", "ledger", "tax"}``.
State lives in ``household.ext["results"]``.
"""
from decimal import Decimal

from .arith import ONE, money, power
from .base import GROUPS, LIABILITIES
from .clock import Order
from .compiler import scenario_setup
from .dates import base_month, month_index, month_label
from .emitters import ScenarioEmitter

KEY = "results"
LOAN_PAID_KINDS = ("LOAN_PAYMENT", "PREPAYMENT", "LOAN_PAYOFF", "INTEREST_ADJUSTMENT")


class ResultsState:
    """Per-run recorder state: ``slots`` {id: (slot, name, kind)} of every holding (cash
    and each holding item, from the owning item), ``rows`` and ``points`` {id: [point]}."""

    def __init__(self, slots):
        self.slots = slots
        self.rows = []
        self.points = {}


def holding_slots(env):
    """{id: (slot, name, kind)}: cash, then each holding id at its first item's slot with
    the name and type of its last item (reference ``self.holdings`` dict semantics)."""
    slots = {"cash": (-1, "Cash", "cash")}
    for iid, slot in env.slot.items():
        item = env.items[env.owner[iid]]
        slots.setdefault(iid, (slot, item.get("name") or iid, item["type"]))
    return slots


@scenario_setup(KEY, order=90)
def setup_results(env):
    env.household.ext[KEY] = ResultsState(holding_slots(env))
    yield Recorder()


class Recorder(ScenarioEmitter):
    """CLOSE: the month's row and a point per existing aggregate. Emits no events."""
    ORDER = Order.CLOSE
    SUB = 0

    def emit(self, month, household):
        self.record(household, month)
        return None

    @staticmethod
    def record(household, month):
        state = household.ext[KEY]
        state.rows.append(row(household, month))
        label = month_label(month)
        for a in household.aggregates():
            point = {"month": label, "opening": household.points_opening.get(a.id),
                     "closing": a.balance, "rate": a.report_rate}
            point.update(a.report_extra(month) or {})
            state.points.setdefault(a.id, []).append(point)


def row(household, m):
    """Verbatim ``Simulation.row``: totals by kind, holdings order, start ``0.00``."""
    aggregates = household.aggregates()

    def total(kinds):
        return sum((a.balance for a in aggregates
                    if a.kind in kinds and a.balance is not None), Decimal("0.00"))
    cash = household.cash.balance
    investments = total(("account", "pension"))
    assets, debts = total(("property", "vehicle")), total(LIABILITIES)
    anw = investments + assets - debts
    out = {"month": month_label(m), "cash": cash, "investments": investments,
           "assets": assets, "debts": debts, "assetsNetWorth": anw,
           "netWorth": cash + anw}
    # Remaining contribution room or limits, columns named by the jurisdiction (ADR-0060,
    # ADR-0071); none without a limits item.
    out.update(household.jurisdiction.limits.remaining(household))
    return out


def loan_flows(ledger):
    """{(month, loan id): [interest, paid]} from the ledger (verbatim reference scan)."""
    flows = {}
    for x in ledger:
        if x["kind"] == "LOAN_INTEREST":
            flows.setdefault((x["month"], x["from"]), [Decimal(0), Decimal(0)])[0] += x["amount"]
        elif x["kind"] in LOAN_PAID_KINDS:
            flows.setdefault((x["month"], x["to"]), [Decimal(0), Decimal(0)])[1] += x["amount"]
    return flows


def holdings_list(household, state):
    """One entry per holding in slot order, incl. holdings never created (empty points).
    An existing aggregate supplies its own name/kind; otherwise the owning item does."""
    meta = dict(state.slots)
    for a in household.aggregates():
        meta[a.id] = (a.item_index, a.name, a.kind)
    order = sorted(meta, key=lambda hid: (meta[hid][0], hid))
    return [{"id": hid, "name": meta[hid][1], "kind": meta[hid][2],
             "group": GROUPS[meta[hid][2]], "points": state.points.get(hid, [])}
            for hid in order]


def assemble(household):
    """The ``run_detailed`` result: {"rows", "holdings", "ledger", "tax"}."""
    state = household.ext.get(KEY)
    if state is None:
        raise RuntimeError("results.assemble: the results recorder was not registered "
                           "(compile with the 'results' scenario setup)")
    ledger = household.ledger.entries
    holdings = holdings_list(household, state)
    flows = loan_flows(ledger)
    for h in holdings:
        if h["kind"] in LIABILITIES:
            for p in h["points"]:
                interest, paid = flows.get((p["month"], h["id"]), (Decimal(0), Decimal(0)))
                p.update(interest=interest, paid=paid, principalPaid=paid - interest)
    return {"rows": add_real_net_worth(state.rows, household.scenario), "holdings": holdings,
            "ledger": ledger, "tax": household.tax_detail}


def add_real_net_worth(rows, scenario):
    """Verbatim reference: net worth in dollars of the base date (ADR-0013)."""
    inflation = Decimal(str(scenario.get("annualInflation") or "0"))
    start = month_index(scenario["horizon"]["start"], "horizon.start")
    offset = start - base_month(scenario)
    for k, r in enumerate(rows):
        factor = power(ONE + inflation, Decimal(offset + k) / 12) if inflation else ONE
        r["realNetWorth"] = money(r["netWorth"] / factor)
        r["realAssetsNetWorth"] = money(r["assetsNetWorth"] / factor)
    return rows
