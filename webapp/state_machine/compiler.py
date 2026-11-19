"""Scenario compiler: turns scenario items into emitters registered on the ScenarioRunner.

Work packages register in their own modules (auto-discovered, no shared edits):

    from ..compiler import item_type, scenario_setup

    @item_type("property")
    def compile_property(item, ctx):          # ctx: ItemContext
        yield PurchaseEmitter(...)             # any iterable of Emitters (or None)

    @scenario_setup("tax", order=50)
    def setup_tax(env):                        # env: CompileContext
        yield TaxEmitter()                     # registered with ordinal SCENARIO (-1)

Factories return ``emitters.Emitter`` objects only (the runner rejects anything
else with TypeError). A ``ModifierEmitter`` is placed at its host's ordinal (``AT_HOST``) with
``sub = sub_order(stage, item index)`` unless it sets ``sub`` itself (INTERFACES §10).

Every module under ``holdings/``, ``flows/``, ``events/``, ``rules/`` and the top-level
``results`` module is imported by ``discover()`` before the first compile.
"""
import importlib
import pkgutil
from contextlib import contextmanager

from .base import HOLDING_TYPES
from .clock import SCENARIO
from .emitters import ModifierEmitter, sub_order
from .dates import property_sales
from .household import Household
from .persons import contributor_of, items_by_id, owner_of, retirement_person
from .runner import ScenarioRunner
from .triggers import prepared

PLUGIN_PACKAGES = ("holdings", "flows", "events", "rules")
PLUGIN_MODULES = ("results",)

_ITEM_TYPES = {}       # type -> factory(item, ctx)
_SETUP = {}            # name -> (order, hook(env))
_discovered = False


def item_type(name):
    """Register the factory of scenario item type ``name`` (exactly one per type)."""
    def decorate(factory):
        if name in _ITEM_TYPES and _ITEM_TYPES[name] is not factory:
            raise ValueError(f"item type {name!r} is already registered by "
                             f"{_ITEM_TYPES[name].__module__}")
        _ITEM_TYPES[name] = factory
        return factory
    return decorate


def scenario_setup(name, order):
    """Register a scenario-level hook, run before the item factories in (order, name)
    order. Its handlers get ordinal SCENARIO; give them distinct ``sub`` values."""
    def decorate(hook):
        if name in _SETUP and _SETUP[name][1] is not hook:
            raise ValueError(f"scenario setup {name!r} is already registered")
        _SETUP[name] = (order, hook)
        return hook
    return decorate


def discover():
    """Import every plug-in module once so their decorators run."""
    global _discovered
    if _discovered:
        return
    pkg = __package__
    for sub in PLUGIN_PACKAGES:
        package = importlib.import_module(f"{pkg}.{sub}")
        for info in sorted(pkgutil.iter_modules(package.__path__), key=lambda i: i.name):
            importlib.import_module(f"{pkg}.{sub}.{info.name}")
    for name in PLUGIN_MODULES:
        importlib.import_module(f"{pkg}.{name}")
    importlib.import_module(f"{pkg}.jurisdictions").discover()    # ADR-0071
    _discovered = True


def registered_types():
    discover()
    return dict(_ITEM_TYPES)


@contextmanager
def isolated_registry(empty=True):
    """For tests: discover first, then (optionally) start from an empty registry; the
    previous registry is restored on exit."""
    discover()
    saved = dict(_ITEM_TYPES), dict(_SETUP)
    if empty:
        _ITEM_TYPES.clear()
        _SETUP.clear()
    try:
        yield
    finally:
        _ITEM_TYPES.clear()
        _ITEM_TYPES.update(saved[0])
        _SETUP.clear()
        _SETUP.update(saved[1])


class CompileContext:
    """Scenario-level information for factories and setup hooks (read-only except
    ``bucket``). Values that need the scenario but not WP logic are computed here once."""

    def __init__(self, scenario, household, runner):
        items = scenario["items"]
        self.scenario = scenario
        self.items = items
        self.household = household
        self.runner = runner
        self.start, self.end = household.start, household.end
        # Items tied to retirement use retirement_for(item), which picks the person
        # (ADR-0061 decision 4); the months are known up front (look-ahead, D2).
        self._targets = items_by_id(scenario)     # accounts and pensions, for owners
        # Reference prepare(): last property item per id; sales keyed by asset id.
        self.properties = {i.get("id"): i for i in items if i["type"] == "property"}
        # What a loan may be tied to: a property, or a vehicle it finances (ADR-0074 am.).
        self.assets = dict(self.properties, **{i.get("id"): i for i in items
                                               if i["type"] == "vehicle"})
        self.sales = property_sales(items)
        # Holding slots (D1): an id's position is its first holding item; only its last
        # holding item is compiled (the reference dict overwrote earlier ones).
        self.slot, self.owner = {}, {}
        for n, item in enumerate(items):
            if item["type"] in HOLDING_TYPES:
                iid = item_id(item, n)
                self.slot.setdefault(iid, n)
                self.owner[iid] = n
        self._buckets = {}

    # Persons (ADR-0061).
    def person_of(self, item):
        """Person id an item belongs to (own owner, its account's owner, or the first)."""
        return owner_of(item, self.scenario, self._targets)

    def contributor_of(self, item):
        """Person id whose room and deduction an account item uses (spousal RRSP)."""
        return contributor_of(item, self.scenario)

    def retirement_person(self, item):
        """Person id whose retirement an item tied to retirement follows."""
        return retirement_person(item, self.scenario, self._targets)

    def retirement_for(self, item):
        """Month index of the retirement ``item`` follows, or None (look-ahead)."""
        return self.household.person(self.retirement_person(item)).retirement

    def bucket(self, name, key):
        """A shared list, created on first use, for handing objects from one item's
        factory to another's regardless of item order (items are compiled in item order,
        so appends are in item order). Example: WP4 extras per mortgage:
        ``ctx.env.bucket("mortgage.extras", mortgage_id).append(extra)``.
        Namespace ``name`` with your module/WP."""
        return self._buckets.setdefault((name, key), [])

    # Lookups for Emitter.prepare(env) (valid once every factory has run).
    def emitters_for(self, source):
        """Emitters whose ``source`` is item id ``source``, in key order (e.g. a modifier
        finding its host's emitters)."""
        return [e for e in self.runner.emitters() if e.source == source]

    def modifiers_of(self, host, cls=None):
        """ModifierEmitters attached to ``host`` (optionally of class ``cls``), in
        scenario item order (e.g. "last renewal in a month wins")."""
        found = [e for e in self.runner.emitters() if isinstance(e, ModifierEmitter)
                 and e.host == host and (cls is None or isinstance(e, cls))]
        return sorted(found, key=lambda e: e.index)


class ItemContext:
    """Per-item context passed to an item factory."""

    def __init__(self, env, item, index, id, ordinal):
        self.env = env              # CompileContext
        self.item = item            # the raw scenario item (dict)
        self.index = index          # its position in scenario["items"]
        self.id = id                # item.get("id") or f"item{index}"
        self.ordinal = ordinal      # order key ordinal: slot for holdings, else index

    @property
    def household(self):
        return self.env.household

    @property
    def name(self):
        """Display name of a holding: ``item.name or id``."""
        return self.item.get("name") or self.id


def item_id(item, n):
    return item.get("id") or f"item{n}"


def place_modifier(emitter, env, index):
    """D-E1: a modifier acts at its host's position: ordinal = the host holding's slot
    (``AT_HOST``; else its own item index ``index``), sub = sub_order(stage, index)."""
    if emitter.AT_HOST:
        if emitter.host not in env.slot:
            raise ValueError(f"{emitter!r}: host {emitter.host!r} is not a holding item")
        ordinal = env.slot[emitter.host]
    else:
        ordinal = index
    if emitter.sub is None:
        emitter.sub = sub_order(emitter.stage, index)
    return ordinal


def compile_scenario(scenario):
    """Build the Household and a ScenarioRunner with every emitter registered, then call
    each emitter's ``prepare(env)``. Does not validate (api.run_detailed validates first)
    and does not run."""
    discover()
    scenario = prepared(scenario)           # upgrade, off items left out, triggers resolved
    household = Household(scenario)
    runner = ScenarioRunner()
    env = CompileContext(scenario, household, runner)
    for name, (_order, hook) in sorted(_SETUP.items(), key=lambda kv: (kv[1][0], kv[0])):
        for handler in hook(env) or ():
            runner.register(handler, SCENARIO)
    for n, item in enumerate(env.items):
        kind = item["type"]
        factory = _ITEM_TYPES.get(kind)
        if factory is None:
            raise NotImplementedError(f"no factory registered for item type {kind!r}")
        iid = item_id(item, n)
        if kind in HOLDING_TYPES:
            if env.owner[iid] != n:
                continue
            ordinal = env.slot[iid]
        else:
            ordinal = n
        ctx = ItemContext(env, item, n, iid, ordinal)
        for handler in factory(item, ctx) or ():
            if isinstance(handler, ModifierEmitter):
                runner.register(handler, place_modifier(handler, env, n), iid, n)
            else:
                runner.register(handler, ordinal, iid, n)
    for emitter in runner.emitters():
        emitter.prepare(env)
    return household, runner
