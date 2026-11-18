"""ScenarioRunner: the month loop over sorted emitters (DECISIONS D-E2, D-E3, D-E4).

    runner.register(emitter, ordinal, source=None, index=None)
    runner.run(household)

- INITIAL step: emitters with a negative order, in key order, asked with ``month`` None.
- Each month ``m`` of the horizon: ``household.begin_month(m)`` (core OPEN step), then
  every emitter with order >= 0 in key order ``(order, ordinal, sub)``; a due emitter is
  asked ``emit(m, household)`` and each event is applied as soon as it is produced, its
  follow-ups depth-first before the next event (D-E3). Every applied event is appended
  to ``household.events`` (an EventLog) with the ledger index range it produced.
- Keys are unique (ValueError on a duplicate).

Only ``emitters.Emitter`` objects can be registered (TypeError otherwise).
"""
from .emitters import Emitter


class ScenarioRunner:
    """Registry of emitters and the month loop (replaces the old Clock)."""

    def __init__(self):
        self._emitters = []
        self._keys = {}
        self._sorted = True

    # ---------- registration ----------
    def register(self, obj, ordinal, source=None, index=None):
        """Register an Emitter at ``ordinal``. Returns ``obj`` unchanged. ``source``
        fills ``emitter.source`` when it is None; ``index`` is the producing item's
        scenario index (None: scenario level)."""
        if not isinstance(obj, Emitter):
            raise TypeError(f"{obj!r} is not an emitters.Emitter: item factories and "
                            f"scenario setups must return Emitter objects (INTERFACES.md §4)")
        emitter = obj
        if emitter.order is None:
            raise TypeError(f"{emitter!r}: no ORDER (set the class ORDER or pass order=)")
        if emitter.sub is None:
            raise TypeError(f"{emitter!r}: sub is None (modifiers get it from the compiler)")
        emitter.ordinal = ordinal
        emitter.index = index
        if emitter.source is None:
            emitter.source = source
        key = emitter.key
        if key in self._keys:
            raise ValueError(f"order key {key} of {emitter!r} is already taken by "
                             f"{self._keys[key]!r}; use a different sub")
        self._keys[key] = emitter
        self._emitters.append(emitter)
        self._sorted = False
        return obj

    def emitters(self):
        """All emitters in key order (INITIAL ones first)."""
        if not self._sorted:
            self._emitters.sort(key=lambda e: e.key)
            self._sorted = True
        return list(self._emitters)

    def schedule(self):
        """All order keys in firing order: for tests and debugging."""
        return [e.key for e in self.emitters()]

    def steps(self):
        """[(order, [emitters])]: the sorted list split at each distinct order number."""
        out = []
        for e in self.emitters():
            if not out or out[-1][0] != e.key[0]:
                out.append((e.key[0], []))
            out[-1][1].append(e)
        return out

    # ---------- the loop ----------
    def run(self, household):
        emitters = self.emitters()
        initial = [e for e in emitters if e.initial]
        monthly = [e for e in emitters if not e.initial]
        for e in initial:
            if e.due(None):
                self._fire(e, None, household)
        for m in range(household.start, household.end + 1):
            household.begin_month(m)
            for e in monthly:
                if e.due(m):
                    self._fire(e, m, household)

    def _fire(self, emitter, month, household):
        for event in emitter.emit(month, household) or ():
            self._apply(event, emitter, month, household, None, emitter.key, emitter.source)

    def _apply(self, event, emitter, month, household, cause, key, source):
        if event.key is None:
            event.key = key
        if event.source is None:
            event.source = source
        start = len(household.ledger.entries)
        follow = event.apply(household)
        index = household.events.record(event, emitter, month, cause,
                                        (start, len(household.ledger.entries)))
        for f in follow or ():
            self._apply(f, emitter, month, household, index, event.key, event.source)
