"""Event-emitter core (DECISIONS D-E1..D-E4, INTERFACES.md §10).

- ``Schedule`` values say in which months an emitter is due: ``Initial``, ``Once``,
  ``Window`` (``EVERY_MONTH`` = unbounded), ``Anniversary``, ``Never``. ``due(None)`` is
  the INITIAL step; only ``Initial`` answers True there.
- ``Emitter``: built by an item factory (one form input -> 1..n emitters). Class-level
  ``ORDER`` (a ``clock.Order`` number), instance ``order`` override, ``ordinal`` (set at
  registration), ``sub``; ``emit(month, household)`` returns/yields Events. It may read
  household state, never write it.
- ``Event``: one change of the household. ``apply(household)`` resolves state-dependent
  amounts *at apply time*, mutates (``household.move`` ...) and returns follow-up events
  (D-E3), applied depth-first right after it. ``KIND``: lifecycle | flow | valuation |
  state.
- ``EventLog``: every applied event, in application order (D-E4 ``events`` output).

The runner (runner.py) walks emitters by key ``(order, ordinal, sub)``; a generator
``emit`` sees the effect of each event it yielded before (the runner applies each event
as soon as it is yielded).
"""
from abc import ABC, abstractmethod

from .clock import is_initial
from .dates import month_label

# Sub-order of a modifier and its host at one (order, ordinal): sub_order(stage, index).
SUB_STRIDE = 1_000_000


def sub_order(stage, index=0):
    """``sub`` for an emitter at ``stage`` (0, 1, 2, ...) of its host's position,
    tie-broken by scenario item ``index`` (item order within a stage)."""
    return stage * SUB_STRIDE + index


# ---------------------------------------------------------------- schedules
class Schedule:
    """When an emitter is due. ``due(None)`` asks about the INITIAL step."""

    def due(self, month):
        raise NotImplementedError

    def __repr__(self):
        args = ", ".join(f"{k}={v!r}" for k, v in vars(self).items())
        return f"{type(self).__name__}({args})"


class Never(Schedule):
    def due(self, month):
        return False


class Initial(Schedule):
    """Once, in the INITIAL step before the first month (``household.month`` None)."""

    def due(self, month):
        return month is None


class Once(Schedule):
    """Exactly one month (``month`` None = never)."""

    def __init__(self, month):
        self.month = month

    def due(self, month):
        return month is not None and month == self.month


class Window(Schedule):
    """Every month ``first <= m <= last`` (None = unbounded). Retirement anchoring
    (dates set by triggers, ADR-0065) is resolved before the factory runs."""

    def __init__(self, first=None, last=None):
        self.first = first
        self.last = last

    def due(self, month):
        return (month is not None
                and (self.first is None or self.first <= month)
                and (self.last is None or month <= self.last))


class Anniversary(Window):
    """Every ``every`` months from ``first`` (12 = yearly anniversary), up to ``last``."""

    def __init__(self, first, every=12, last=None):
        super().__init__(first, last)
        self.every = every

    def due(self, month):
        return super().due(month) and (month - self.first) % self.every == 0


EVERY_MONTH = Window()
NEVER = Never()
INITIAL = Initial()


# ---------------------------------------------------------------- events
class Event(ABC):
    """One change of the household, emitted by an emitter.

    ``key`` and ``source`` default to the emitter's (a follow-up: its parent's); set them
    in ``__init__`` only to override. ``apply`` returns follow-up events or None.
    """
    KIND = "event"
    key = None          # (order, ordinal, sub), filled in by the runner
    source = None       # scenario item id (ledger attribution), filled in by the runner

    @abstractmethod
    def apply(self, household):
        """Resolve amounts from the current state, mutate, return follow-ups (or None)."""

    @property
    def name(self):
        return type(self).__name__

    def describe(self):
        """Compact one-line description for the event log (no Decimals needed)."""
        return self.name

    def __repr__(self):
        return f"<{self.name} {self.key} {self.source!r}>"


class LifecycleEvent(Event):
    """Creates or closes an aggregate (purchase, loan advance, opening, sale, payoff)."""
    KIND = "lifecycle"


class FlowEvent(Event):
    """Moves money (income, expense, payment, contribution, withdrawal, transfer, penalty)."""
    KIND = "flow"


class ValuationEvent(Event):
    """Changes a value without cash (growth, interest, revaluation, market adjustment)."""
    KIND = "valuation"


class StateEvent(Event):
    """Changes household state (retirement, tax step, month record)."""
    KIND = "state"


# ---------------------------------------------------------------- emitters
class Emitter(ABC):
    """Event-producing rule of one form input (or of the scenario).

    Class attributes: ``ORDER`` (required, a ``clock.Order`` number or any int), ``SUB``
    (default 0). Instance: ``order``/``sub`` (override via ``__init__``), ``schedule``,
    ``source`` (item id; the compiler fills it with ``ctx.id`` when None), ``ordinal``
    (set by the runner at registration; never set it yourself), ``index`` (the producing
    item's scenario index, None for scenario level; set at registration).
    """
    ORDER = None
    SUB = 0
    CATEGORY = "emitter"

    def __init__(self, schedule=None, *, order=None, sub=None, source=None):
        self.schedule = EVERY_MONTH if schedule is None else schedule
        self.order = self.ORDER if order is None else order
        self.sub = self.SUB if sub is None else sub
        self.source = source
        self.ordinal = None
        self.index = None

    @property
    def key(self):
        return (int(self.order), self.ordinal, self.sub)

    @property
    def name(self):
        return type(self).__name__

    @property
    def initial(self):
        return is_initial(self.order)

    def due(self, month):
        """True if the emitter is asked in ``month`` (None = the INITIAL step)."""
        return self.schedule.due(month)

    @abstractmethod
    def emit(self, month, household):
        """Events of this month (list, iterable or generator; None = nothing)."""

    def prepare(self, env):
        """Called once after every factory has run (compiler.CompileContext ``env``), in
        key order: resolve cross-item facts (e.g. "last renewal in a month wins")."""

    def __repr__(self):
        return f"<{self.name} {self.key} {self.source!r}>"


class OneShotEmitter(Emitter):
    """Due in exactly one month (``month`` None = never): purchase, opening, transfer,
    improvement, market adjustment."""
    CATEGORY = "one-shot"

    def __init__(self, month, **kw):
        super().__init__(Once(month), **kw)

    @property
    def month(self):
        return self.schedule.month


class InitialEmitter(Emitter):
    """The INITIAL step: holdings that exist at the start. ``ORDER`` must be negative."""
    CATEGORY = "initial"

    def __init__(self, **kw):
        super().__init__(INITIAL, **kw)


class RecurringEmitter(Emitter):
    """Due every month of a window (or a custom Schedule): income, expense, contribution,
    withdrawal, loan servicing, growth, maintenance, pension."""
    CATEGORY = "recurring"

    def __init__(self, first=None, last=None, schedule=None, **kw):
        super().__init__(schedule if schedule is not None else Window(first, last), **kw)


class ModifierEmitter(Emitter):
    """A modifier of a host item (D-E1): renewal, extraPayment, lumpSum on a mortgage;
    sale, improvement, marketAdjustment on an asset.

    ``host`` is the host's item id. With ``AT_HOST`` (default) the compiler gives it the
    host's ordinal (holding slot) instead of its own item index; ``sub`` defaults to
    ``sub_order(stage, own item index)``, so modifiers of one host sort by stage, then
    item order. ``ORDER`` is the host action's order (e.g. Order.SERVICE_DEBT).
    """
    CATEGORY = "modifier"
    AT_HOST = True
    STAGE = 0

    def __init__(self, host, schedule=None, *, stage=None, **kw):
        super().__init__(schedule, **kw)
        self.host = host
        self.stage = self.STAGE if stage is None else stage
        self.sub = kw.get("sub")    # None: filled in by the compiler from stage + index


class ScenarioEmitter(Emitter):
    """Scenario-level emitter (no item): retirement, tax step, results recorder. Ordinal
    SCENARIO; give each a distinct ``sub`` at one order."""
    CATEGORY = "scenario"


# ---------------------------------------------------------------- event log
class EventLog:
    """Applied events in application order (D-E4). ``records`` is the public list."""

    def __init__(self):
        self.records = []

    def record(self, event, emitter, month, cause, ledger_range):
        """Append one applied event; returns its index (a follow-up's ``cause``)."""
        self.records.append({
            "month": None if month is None else month_label(month),
            "key": tuple(event.key),
            "emitter": emitter.name,
            "event": event.name,
            "kind": event.KIND,
            "source": event.source,
            "cause": cause,
            "ledger": ledger_range,
            "detail": event.describe(),
        })
        return len(self.records) - 1

    def __len__(self):
        return len(self.records)

    def __iter__(self):
        return iter(self.records)
