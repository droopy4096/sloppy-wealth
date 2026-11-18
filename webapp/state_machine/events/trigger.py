"""Trigger (``type: "trigger"``) — ADR-0065 (proposed).

The target's dates are written by ``triggers.resolve`` before compiling; the emitter only
records the trigger in the event log in the event's month (a state event that changes
nothing). A trigger on the end of an event that never ends logs nothing.
"""
from ..clock import Order
from ..compiler import item_type
from ..emitters import OneShotEmitter, StateEvent
from ..triggers import event_month

ORDER_TRIGGER = Order.OPEN + 59        # before adjustments (log only)


class Triggered(StateEvent):
    def __init__(self, event, action, target):
        self.event, self.action, self.target = event, action, target

    def apply(self, household):
        pass        # the target's dates were set at compile time

    def describe(self):
        return f"{self.event}: {self.action} {self.target}"


class TriggerEmitter(OneShotEmitter):
    ORDER = ORDER_TRIGGER

    def __init__(self, month, event, action, target, **kw):
        super().__init__(month, **kw)
        self.event, self.action, self.target = event, action, target

    def emit(self, month, household):
        return (Triggered(self.event, self.action, self.target),)


@item_type("trigger")
def compile_trigger(item, ctx):
    items = {i.get("id"): i for i in ctx.env.items}
    event, target = items[item["event"]], items[item["target"]]
    name = lambda i: i.get("name") or i.get("id")
    sales = {i.get("property"): i for i in ctx.env.items if i.get("type") == "sale"}
    on = item.get("on") or "start"
    month = event_month(event, f"trigger {name(item)}", on, sales)
    if month is None:
        return
    what = name(event) if on == "start" else f"end of {name(event)}"
    yield TriggerEmitter(month, what, item["action"], name(target))
