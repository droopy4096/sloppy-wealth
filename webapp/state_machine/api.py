"""Public API of the state-machine engine: the same symbols as iteration 1's engine.py
(tag poc-iteration-1) that webapp/app.py and webapp/test_engine.py use (FEASIBILITY §5, OBJECTS §7.5)."""
from . import compiler, results, validation
from .upgrade import upgrade
from .arith import CENT, ONE, PER, annuity, dec, flow_amount, indexed, monthly_rate, \
    money, mortgage_terms, power
from .dates import base_month, month_index, month_label, mortgage_start, property_sales, \
    retirement_date

__all__ = ["validate", "run", "run_detailed", "simulate", "upgrade", "retirement_date", "month_label",
           "month_index", "base_month", "annuity", "monthly_rate", "mortgage_terms", "money",
           "power", "indexed", "dec", "flow_amount", "mortgage_start", "property_sales",
           "CENT", "ONE", "PER"]


def validate(scenario):
    """Raise ValueError with a readable message if the scenario is malformed."""
    return validation.validate(scenario)


def simulate(scenario):
    """Compile and run without validating or assembling results: the household after the
    last month (for unit tests of WP3-WP7 and the harness)."""
    household, runner = compiler.compile_scenario(scenario)
    runner.run(household)
    return household


def run_detailed(scenario):
    """Rows (main table), per-holding detail, the movement ledger and tax (ADR-0053),
    then the applied events (D-E4, after the reference's keys)."""
    validate(scenario)
    household = simulate(scenario)
    result = results.assemble(household)
    result["events"] = household.events.records
    return result


def run(scenario):
    return run_detailed(scenario)["rows"]
