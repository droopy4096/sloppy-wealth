"""Associated income and associated one-off income (ADR-0068).

    cd webapp && .venv/bin/python -m unittest state_machine.tests.test_associated_income
"""
import copy
import unittest
from decimal import Decimal

from state_machine import engine


def scenario(*items, **over):
    s = {"schemaVersion": 1, "name": "associated income",
         "horizon": {"start": "2027-01-01", "end": "2030-12-01"},
         "openingCash": "1000", "effectiveTaxRate": "0.3", "items": list(items)}
    s.update(over)
    return s


JOB = {"type": "income", "id": "job", "name": "Job", "startDate": "2027-02-01",
       "endDate": "2029-10-01", "amount": "120000", "per": "year", "taxable": True}
PENSION = {"type": "pension", "id": "p", "name": "DB", "startDate": "2028-01-01",
           "amount": "24000", "per": "year", "taxable": True}


def bonus(**kw):
    return dict({"type": "associatedIncome", "id": "b", "name": "Bonus", "parent": "job"}, **kw)


def one_off(**kw):
    return dict({"type": "associatedOneOff", "id": "o", "name": "Once", "parent": "job"}, **kw)


def run(s):
    return engine.run_detailed(copy.deepcopy(s))


def paid(result, source):
    return {x["month"]: x["amount"] for x in result["ledger"] if x["source"] == source}


class AssociatedIncome(unittest.TestCase):
    def test_monthly_percentage_lives_with_the_job(self):
        months = paid(run(scenario(JOB, bonus(annualRate="0.1"))), "b")
        self.assertEqual((min(months), max(months)), ("2027-02", "2029-10"))
        self.assertEqual(set(months.values()), {Decimal("1000.00")})      # 10% / 12

    def test_percentage_follows_raises_on_anniversaries(self):
        raise_ = {"type": "adjustment", "id": "r", "flow": "job", "adjustmentDate": "2027-07-01",
                  "amount": "180000"}
        months = paid(run(scenario(JOB, raise_, bonus(annualRate="0.1"))), "b")
        # The raise in 2027-07 counts from the job's next anniversary (2028-02).
        self.assertEqual((months["2028-01"], months["2028-02"]),
                         (Decimal("1000.00"), Decimal("1500.00")))

    def test_yearly_lump_in_arrears_partial_year_forfeited(self):
        months = paid(run(scenario(JOB, bonus(annualRate="0.1", per="year", paid="lump"))), "b")
        # Job 2027-02 .. 2029-10: full years end 2028-01 and 2029-01; 2029-02.. is forfeited.
        self.assertEqual(months, {"2028-02": Decimal("12000.00"), "2029-02": Decimal("12000.00")})

    def test_a_full_last_period_is_paid_the_month_after(self):
        exact = dict(JOB, endDate="2028-01-01")             # exactly one year
        months = paid(run(scenario(exact, bonus(amount="12000", per="year", paid="lump"))), "b")
        self.assertEqual(months, {"2028-02": Decimal("12000.00")})
        monthly = paid(run(scenario(exact, bonus(amount="12000", per="year"))), "b")
        self.assertEqual(max(monthly), "2028-01")
        at_horizon = dict(JOB, startDate="2029-12-01", endDate="2030-11-01")
        months = paid(run(scenario(at_horizon, bonus(amount="12000", per="year",
                                                     paid="lump"))), "b")
        self.assertEqual(months, {"2030-12": Decimal("12000.00")})

    def test_quarterly_fixed_lump(self):
        months = paid(run(scenario(JOB, bonus(amount="2000", per="quarter", paid="lump"))), "b")
        self.assertEqual(min(months), "2027-05")
        self.assertEqual(months["2027-05"], Decimal("2000.00"))
        self.assertEqual(max(months), "2029-11")            # 2029-08..10, the last full one

    def test_taxed_and_owned_as_its_parent(self):
        # With the job's own tax flag: the bonus is taxed only when the job is.
        job_only = run(scenario(JOB))["rows"][-1]["cash"]
        untaxed_job = run(scenario(dict(JOB, taxable=False)))["rows"][-1]["cash"]
        taxed = run(scenario(JOB, bonus(amount="1200", per="year")))
        untaxed = run(scenario(dict(JOB, taxable=False), bonus(amount="1200", per="year")))
        gain_taxed = taxed["rows"][-1]["cash"] - job_only
        gain_untaxed = untaxed["rows"][-1]["cash"] - untaxed_job
        self.assertLess(gain_taxed, gain_untaxed)
        self.assertEqual(gain_untaxed, Decimal("3300.00"))      # 33 months x 100, no tax

    def test_new_rate_by_adjustment(self):
        adj = {"type": "adjustment", "id": "a", "flow": "b", "adjustmentDate": "2028-02-01",
               "annualRate": "0.15"}
        months = paid(run(scenario(JOB, bonus(annualRate="0.1"), adj)), "b")
        self.assertEqual((months["2028-01"], months["2028-02"]),
                         (Decimal("1000.00"), Decimal("1500.00")))

    def test_thirteenth_month_pension(self):
        extra = {"type": "associatedIncome", "id": "x", "name": "13th", "parent": "p",
                 "annualRate": str(Decimal(1) / 12), "per": "year", "paid": "lump"}
        months = paid(run(scenario(PENSION, extra)), "x")
        self.assertEqual(months, {"2029-01": Decimal("2000.00"), "2030-01": Decimal("2000.00")})

    def test_off_with_its_parent(self):
        self.assertEqual(paid(run(scenario(dict(JOB, enabled=False), bonus(amount="1"))), "b"),
                         {})


class AssociatedOneOff(unittest.TestCase):
    def test_signing_bonus_severance_and_dated(self):
        r = run(scenario(JOB, one_off(at="start", amount="5000"),
                         one_off(id="s", at="end", rate="0.5"),
                         one_off(id="d", at="date", paymentDate="2028-06-01", amount="700")))
        self.assertEqual(paid(r, "o"), {"2027-02": Decimal("5000.00")})
        self.assertEqual(paid(r, "s"), {"2029-10": Decimal("60000.00")})
        self.assertEqual(paid(r, "d"), {"2028-06": Decimal("700.00")})

    def test_no_end_no_severance_and_dates_outside_the_parent_dropped(self):
        endless = dict(JOB, endDate="")
        self.assertEqual(paid(run(scenario(endless, one_off(at="end", amount="1"))), "o"), {})
        late = one_off(at="date", paymentDate="2030-03-01", amount="1")
        self.assertEqual(paid(run(scenario(JOB, late)), "o"), {})


class Validation(unittest.TestCase):
    def check(self, item, message):
        with self.assertRaisesRegex(ValueError, message):
            engine.validate(scenario(JOB, PENSION, {"type": "expense", "id": "e",
                                                    "startDate": "2027-01-01", "amount": "1"},
                                     item))

    def test_messages(self):
        self.check(bonus(parent="e", amount="1"), "parent refers to unknown item 'e' "
                   r"\(an income or a pension\)")
        self.check(bonus(amount="1", annualRate="0.1"), "give either an amount or a annualRate")
        self.check(bonus(annualRate="-0.1"), "annualRate must be a positive fraction")
        self.check(bonus(amount="1", paid="weekly"), "paid must be monthly or lump")
        self.check(bonus(amount="1", paid="lump"), "a lump is paid per quarter or per year")
        self.check(one_off(at="later", amount="1"), "at must be start, end or date")
        self.check(one_off(at="date", amount="1"), "missing field 'paymentDate'")
        self.check(one_off(at="date", paymentDate="2040-01-01", amount="1"),
                   "paymentDate must be within the horizon")
        engine.validate(scenario(JOB, bonus(annualRate="0.1", per="year", paid="lump"),
                                 one_off(at="end", rate="0.5")))


if __name__ == "__main__":
    unittest.main()
