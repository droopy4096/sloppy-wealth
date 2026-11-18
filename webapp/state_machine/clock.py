"""The order table of the month (FEASIBILITY §2, OBJECTS §6, DECISIONS D-E2).

Every emitter (emitters.py) has the order key

    (order, ordinal, sub)

- ``order``: an ``Order`` number below (or any int in between). The ScenarioRunner
  (runner.py) walks emitters in key order every month; reordering = changing a number.
  The ``Order`` steps are ``ORDER_STEP`` (100) apart, so new positions can be
  inserted between two steps (e.g. 850 = after debt service, before expenses).
  Negative orders form the INITIAL step (once, before the first month).
- ``ordinal``: the scenario item index of the item that produced the emitter. For a
  holding (base.HOLDING_TYPES) it is the holding's *slot* (index of the first holding
  item with that id), so holdings-order loops of the reference come out right. A
  modifier acting at its host's position (D-E1) gets the host's slot. Scenario level
  emitters (tax, retirement, results recorder) use ``SCENARIO`` (-1).
- ``sub``: a small int chosen by the emitter's class or instance, to order two emitters
  of the same item (or a host and its modifiers) at the same order (default 0).

The key must be unique; ``ScenarioRunner.register`` raises ValueError on a duplicate.
"""
from enum import IntEnum

SCENARIO = -1
ORDER_STEP = 100


class Order(IntEnum):
    """Default emitter order numbers (INTERFACES.md §4). The step positions match the
    reference engine's month order (parity, D-E2); ``ORDER_STEP`` apart."""
    INITIAL = -1 * ORDER_STEP           # once, before the first month: holdings at the start
    OPEN = 0                            # core OPEN step (begin_month); then RetirementEmitter
    INCOME = 1 * ORDER_STEP             # income flows
    PENSION_PAY = 2 * ORDER_STEP        # pension payments
    ACQUIRE = 3 * ORDER_STEP            # purchase | loan advance | account opening
    IMPROVE = 4 * ORDER_STEP            # improvements
    ADJUST = 5 * ORDER_STEP             # market adjustments
    SELL = 6 * ORDER_STEP               # sales incl. loan payoff
    TRANSFER = 7 * ORDER_STEP           # one-off transfers into accounts
    SERVICE_DEBT = 8 * ORDER_STEP       # mortgage service incl. renewal, extras
    EXPENSE = 9 * ORDER_STEP            # expense flows
    MAINTAIN = 10 * ORDER_STEP          # vehicle maintenance
    CONTRIBUTE = 11 * ORDER_STEP        # contributions (account / pension)
    WITHDRAW = 12 * ORDER_STEP          # withdrawals
    GROW = 13 * ORDER_STEP              # appreciation, account return
    REVALUE_PENSIONS = 14 * ORDER_STEP  # pension revaluation
    TAX = 15 * ORDER_STEP               # tax step
    CLOSE = 16 * ORDER_STEP             # results rows and holdings points


def is_initial(order):
    """Negative orders run once in the INITIAL step, with ``month`` None."""
    return order < 0
