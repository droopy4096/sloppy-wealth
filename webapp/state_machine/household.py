"""Household: the main object (today's ``Simulation``). Holds the aggregates, the ledger,
the scenario settings, the month state and the tax accumulator. See INTERFACES.md §3.
"""
from bisect import insort
from decimal import Decimal

from .arith import money
from .dates import base_month, month_index, month_label, retirement_dates
from .persons import IMPLICIT, person_items
from . import jurisdictions
from .emitters import EventLog
from .holdings.cash import Cash
from .ledger import Ledger


class TaxAccumulator:
    """Per-month tax inputs and the carried-forward pool (OBJECTS §4.9).

    taxable, deductions: Decimal sums of the month (reset in OPEN).
    extra_tax: own-rate withdrawal tax of the month, kept *unrounded* (reset in OPEN).
    pool: unused deductions carried forward; never reset; updated only by TaxRule (WP7).
    detail: month label -> the tax step's working (written by TaxRule, read by WP8).
    """

    def __init__(self):
        self.taxable = Decimal(0)
        self.deductions = Decimal(0)
        self.extra_tax = Decimal(0)
        self.pool = Decimal(0)
        self.detail = {}

    def reset_month(self):
        self.taxable = Decimal(0)
        self.deductions = Decimal(0)
        self.extra_tax = Decimal(0)

    def add_taxable(self, amount):
        """Taxable income: pass the *rounded* amount returned by ``household.move``
        (e.g. a 0.00 from a dropped move adds nothing)."""
        self.taxable += amount

    def add_deduction(self, amount):
        self.deductions += amount

    def add_own_rate_tax(self, amount):
        """Tax at an account's own rate (``amt * withdrawalTaxRate``), unrounded."""
        self.extra_tax += amount


class Person:
    """A person of the household (ADR-0061): own tax rates, retirement and tax
    accumulator. Rates: the person's own, else the scenario's; the retired rate falls back
    to the scenario's retirementTaxRate, then to the person's working rate (raw
    truthiness, as the scenario fields: a JSON number 0 means "not given")."""

    def __init__(self, pid, name, tax_rate, retirement_tax_rate, retirement_date):
        self.id = pid
        self.name = name
        self.tax_rate = tax_rate
        self.retirement_tax_rate = retirement_tax_rate
        # Look-ahead (D2): the retirement month is known up front.
        self.retirement_date = retirement_date
        self.retirement = (month_index(retirement_date, "retirementDate")
                           if retirement_date else None)
        self.retired = False
        self.tax = TaxAccumulator()

    @property
    def current_tax_rate(self):
        return self.retirement_tax_rate if self.retired else self.tax_rate


def build_persons(scenario):
    """{person id: Person} in item order; one implicit person without person items."""
    tax_rate = Decimal(str(scenario.get("effectiveTaxRate") or "0"))
    rtr = scenario.get("retirementTaxRate")
    scenario_retired = Decimal(str(rtr)) if rtr else None
    dates = retirement_dates(scenario)
    items = person_items(scenario) or [{"id": IMPLICIT, "name": ""}]
    persons = {}
    for item in items:
        own = item.get("effectiveTaxRate")
        rate = Decimal(str(own)) if own else tax_rate
        own_retired = item.get("retirementTaxRate")
        retired = (Decimal(str(own_retired)) if own_retired
                   else scenario_retired if scenario_retired is not None else rate)
        pid = item["id"]
        persons[pid] = Person(pid, item.get("name") or pid, rate, retired, dates.get(pid, ""))
    return persons


class Household:
    """Scenario settings (verbatim from ``Simulation.__init__``), aggregates in slot order,
    the ledger and the month state. Built by ``compiler.compile_scenario``."""

    def __init__(self, scenario):
        self.scenario = scenario
        self.start = month_index(scenario["horizon"]["start"], "horizon.start")
        self.end = month_index(scenario["horizon"]["end"], "horizon.end")
        self.inflation = Decimal(str(scenario.get("annualInflation") or "0"))
        # Persons (ADR-0061); ``first`` is the default person (blank owner).
        self.persons = build_persons(scenario)
        self.first = next(iter(self.persons.values()))
        self.base = base_month(scenario)
        self.covered = scenario.get("incomeMode") == "expensesCovered"
        self.jurisdiction = jurisdictions.of(scenario)     # tax rules and limits, ADR-0071
        self.ledger = Ledger()
        self.events = EventLog()     # applied events (D-E4), appended by the runner
        self.tax_detail = {}         # month label -> household tax view (rules/tax.py)
        self.month = None
        self.opened = []             # non-cash aggregates existing at the start of the month
        self.opening = {}            # id -> balance of ``opened`` at the start of the month
        self.points_opening = {}     # id -> balance of every aggregate (incl. cash) at the start
        self.ext = {}                # per-WP private state, keyed by the owning module name
        self._by_id = {}
        self._order = []             # [(item_index, id)] sorted: the holdings order
        self.add(Cash(scenario["openingCash"]))

    # ---------- aggregates ----------
    def add(self, aggregate):
        """Add an aggregate created by an event. Re-adding an id replaces the object and
        keeps the existing slot (reference dict semantics)."""
        if aggregate.id not in self._by_id:
            insort(self._order, (aggregate.item_index, aggregate.id))
        self._by_id[aggregate.id] = aggregate
        return aggregate

    def get(self, hid):
        """The aggregate with id ``hid``, or None if it does not exist (yet)."""
        return self._by_id.get(hid)

    def __getitem__(self, hid):
        return self._by_id[hid]

    def __contains__(self, hid):
        return hid in self._by_id

    @property
    def cash(self):
        return self._by_id["cash"]

    def aggregates(self, *kinds):
        """Existing aggregates in holdings order (cash first, then item order); only the
        given kinds if any are given."""
        return [self._by_id[hid] for _, hid in self._order
                if not kinds or self._by_id[hid].kind in kinds]

    def opened_aggregates(self, *kinds):
        """The ``opened`` list frozen in OPEN (holdings order), optionally by kind."""
        return [a for a in self.opened if not kinds or a.kind in kinds]

    def is_opened(self, hid):
        """True if ``hid`` was in ``opened`` this month (existed, non-cash, at the start)."""
        return hid in self.opening

    def loans_secured_by(self, asset_id):
        """Existing liabilities whose ``secured_by`` is ``asset_id``, in holdings order.
        The caller applies the reference's ``and loan.balance`` truthiness check."""
        return [a for a in self.aggregates() if a.liability and a.secured_by == asset_id]

    # ---------- income mode ----------
    @property
    def recurring_source(self):
        """Source of recurring outgoings (loan payment, interest adjustment, recurring
        prepayment, contribution): None (outside) when expenses are covered, else cash."""
        return None if self.covered else "cash"

    # ---------- persons (ADR-0061) ----------
    def person(self, pid=None):
        """The person ``pid`` (None: the first person)."""
        return self.persons[pid] if pid else self.first

    def tax_of(self, pid=None):
        """The tax accumulator of person ``pid`` (None: the first person)."""
        return self.person(pid).tax

    # ---------- movements ----------
    def move(self, kind, src, dst, amount, source=None):
        """Record a movement of amount from src to dst (None = outside the model).
        A liability grows when money comes from it (advance, interest) and shrinks when
        money goes to it (payments). Returns the rounded amount; an amount that rounds to
        0 records nothing and returns Decimal('0.00') (verbatim reference ``move``)."""
        amount = money(amount)
        if amount == 0:
            return amount
        if src:
            self._by_id[src]._apply(-amount)
        if dst:
            self._by_id[dst]._apply(amount)
        self.ledger.record(month_label(self.month), kind, src, dst, amount, source)
        return amount

    # ---------- the month (core OPEN step, called by the ScenarioRunner) ----------
    def begin_month(self, m):
        self.month = m
        for person in self.persons.values():
            person.tax.reset_month()
        self.points_opening = {a.id: a.balance for a in self.aggregates()}
        self.opened = [a for a in self.aggregates()
                       if a.kind != "cash" and a.balance is not None]
        self.opening = {a.id: a.balance for a in self.opened}
