"""Tax jurisdictions as plug-in packages (ADR-0071).

A scenario targets one jurisdiction (``"jurisdiction": "CA"``; files without the field
are Canadian). Each jurisdiction is a package under ``jurisdictions/<code>/`` whose class
is registered with ``@jurisdiction("<code>")``; packages are found automatically.

A jurisdiction declares:

- ``account_types``: code -> ``AccountType`` (label, ``Treatment``, extra form fields).
  The three ``Treatment`` flags say how money in the account is taxed; the hooks below
  follow them by default.
- ``item_types``: item types only this jurisdiction offers (Canada: ``contributionRoom``),
  with their ``required`` fields and ``validate_item`` checks. Their factories are
  registered with ``@item_type`` like any other.
- ``limits``: a ``ContributionLimits`` (contribution room, yearly limits), or none.
- ``labels``: wording the pages use (e.g. the ledger's deductions line).

The hooks ``on_contribute``, ``on_return`` and ``on_withdraw`` are called by the account
events with the rounded amount ``household.move`` returned; a jurisdiction overrides one
for anything the flags do not cover.
"""
import importlib
import pkgutil
from dataclasses import dataclass
from decimal import Decimal

DEFAULT = "CA"


@dataclass(frozen=True)
class Treatment:
    deductible: bool          # money put in reduces the contributor's taxable income
    returns_taxed: bool       # the account's return is taxable income (a loss: no credit)
    withdrawal_taxed: bool    # money taken out is taxable income


DEFERRED = Treatment(deductible=True, returns_taxed=False, withdrawal_taxed=True)
EXEMPT = Treatment(deductible=False, returns_taxed=False, withdrawal_taxed=False)
TAXABLE = Treatment(deductible=False, returns_taxed=True, withdrawal_taxed=False)


@dataclass(frozen=True)
class AccountType:
    code: str                 # stored in the scenario's accountType
    label: str                # shown in forms and cards
    treatment: Treatment
    short: str = ""           # card label (default: the code)
    fields: tuple = ()        # optional fields only this type takes ("contributor", ...)


class ContributionLimits:
    """No limits: everything is allowed (the interface Canada's room rule implements)."""

    columns = {}              # result column -> heading on the run page (see remaining)

    def cap(self, household, account, amount, match=False):
        """The part of ``amount`` the account may receive now (and use it up);
        ``match``: an employer match on a contribution."""
        return amount

    def note_earned(self, household, amount, person=None):
        """Earned income of ``person`` this month (limits that depend on it)."""

    def note_withdrawal(self, household, account, amount):
        """A withdrawal from ``account`` (limits that give room back)."""

    def remaining(self, household):
        """{result column: remaining amount or None} for the result rows."""
        return {}


NO_LIMITS = ContributionLimits()


def capped_note(requested, allowed):
    """The event note when a limit capped a movement."""
    from ..arith import money
    return "" if allowed == requested else f" (capped at room: {money(allowed)} of {requested})"


class Jurisdiction:
    code = ""
    name = ""
    account_types = {}
    item_types = ()
    required = {}             # own item type -> required fields (numbers or dates...)
    choice_fields = ()        # ... except these choices, checked by validate_item
    owned_types = ()          # own item types that have an owner (a person)
    labels = {}
    limits = NO_LIMITS
    # Forms (schema.describe): own item types' fields, legends and hints; hints and
    # legends of core fields it words differently; where its types are added.
    form_fields = {}          # own item type -> fields in JSON key order
    legends = {}
    hints = {}                # (type, field) or field -> hint
    percent_fields = ()
    selects = {}              # choices of its own fields: field -> [(value, label)]
    add_groups = {}           # group title -> own item types added to that group
    head_adds = {}            # "person" / "scenario" -> own item types added there

    def treatment(self, account):
        kind = self.account_types.get(getattr(account, "account_type", None))
        return kind.treatment if kind else None

    # ---------------------------------------------------------------- hooks
    def on_contribute(self, household, account, amount, source=None):
        """Money put in (contribution, one-off transfer; ``source`` its item id): a
        deduction of the contributor when the type is deductible, except in income-less
        mode (ADR-0044, ADR-0048)."""
        treatment = self.treatment(account)
        if treatment and treatment.deductible and not household.covered:
            household.tax_of(account.contributor).add_deduction(amount)

    def on_return(self, household, account, ret):
        """The month's return: taxable income of the owner when returns are taxed; a
        loss gives no credit."""
        treatment = self.treatment(account)
        if treatment and treatment.returns_taxed:
            household.tax_of(account.owner).add_taxable(max(Decimal(0), ret))

    def on_withdraw(self, household, account, amount):
        """Money taken out: taxable income of the owner (ADR-0061) when withdrawals are
        taxed, or tax at the account's own rate if it has one (kept unrounded, ADR-0035)."""
        treatment = self.treatment(account)
        if treatment and treatment.withdrawal_taxed:
            tax = household.tax_of(account.owner)
            if getattr(account, "withdrawal_tax_rate", None) is not None:
                tax.add_own_rate_tax(amount * account.withdrawal_tax_rate)
            else:
                tax.add_taxable(amount)

    # ---------------------------------------------------------------- validation
    def validate_item(self, item, where, check):
        """Checks of this jurisdiction's own item types; ``check`` gives the scenario
        context (see validation.ItemCheck)."""

    def label(self, key, default=""):
        return self.labels.get(key, default)


REGISTRY = {}
_discovered = False


def jurisdiction(code):
    """Register a Jurisdiction subclass under its ISO code (one instance)."""
    def register(cls):
        if code in REGISTRY and type(REGISTRY[code]) is not cls:
            raise ValueError(f"jurisdiction {code!r} is already registered")
        cls.code = code
        REGISTRY[code] = cls()
        return cls
    return register


def discover():
    """Import every jurisdiction package once so their decorators run."""
    global _discovered
    if _discovered:
        return
    _discovered = True
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda i: i.name):
        if info.ispkg:
            package = importlib.import_module(f"{__name__}.{info.name}")
            for sub in sorted(pkgutil.iter_modules(package.__path__), key=lambda i: i.name):
                importlib.import_module(f"{package.__name__}.{sub.name}")


def registered():
    discover()
    return dict(REGISTRY)


def code_of(scenario):
    return (scenario.get("jurisdiction") if isinstance(scenario, dict) else None) or DEFAULT


def get(code):
    """The registered jurisdiction ``code``; ValueError if there is none."""
    discover()
    if code not in REGISTRY:
        raise ValueError(f"scenario: jurisdiction must be one of {', '.join(sorted(REGISTRY))}; "
                         f"got {code!r}")
    return REGISTRY[code]


def of(scenario):
    """The scenario's jurisdiction (Canada when the field is missing)."""
    return get(code_of(scenario))


def of_or_default(scenario):
    """The scenario's jurisdiction, or Canada when its code is unknown (for views that
    must render a scenario validation will refuse)."""
    try:
        return of(scenario)
    except ValueError:
        return get(DEFAULT)


def own_item_types():
    """{item type: code of the jurisdiction that offers it} over every jurisdiction."""
    return {t: code for code, j in registered().items() for t in j.item_types}
