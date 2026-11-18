"""Decimal arithmetic, copied verbatim from iteration 1's engine.py
(tag poc-iteration-1; FEASIBILITY §4.1).

Never rearrange these expressions and never touch the Decimal context: Decimal at
precision 28 gives different last digits when the algebra is rearranged. Integer powers
use ``**`` (exact); fractional powers use ``power`` -- the two must not be swapped.
"""
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_EVEN, InvalidOperation

CENT = Decimal("0.01")
ONE = Decimal(1)
PER = {"month": 1, "quarter": 3, "year": 12}


def D(x):
    """A JSON number or string as Decimal: always through str, never Decimal(float)."""
    return Decimal(str(x))


def money(x):
    return x.quantize(CENT, rounding=ROUND_HALF_EVEN)


def power(base, exp):
    """base ** exp for a positive Decimal base and fractional exponent."""
    return (base.ln() * exp).exp()


def dec(item, field, where):
    try:
        return Decimal(str(item[field]))
    except KeyError:
        raise ValueError(f"{where}: missing field {field!r}")
    except InvalidOperation:
        raise ValueError(f"{where}: {field!r} is not a number: {item[field]!r}")


def flow_amount(item, where=""):
    """(amount, per) of a flow. per is 'month', 'quarter' or 'year' (older files'
    monthlyAmount is converted by upgrade.py)."""
    if "amount" in item:
        per = item.get("per") or "month"
        if per not in ("month", "quarter", "year"):
            raise ValueError(f"{where}: per must be month, quarter or year; got {per!r}")
        return dec(item, "amount", where), per
    raise ValueError(f"{where}: missing field 'amount'")


def monthly_rate(annual):
    """Monthly rate equivalent to an annual rate compounded semi-annually (ADR-0019)."""
    return power(ONE + Decimal(str(annual)) / 2, ONE / 6) - 1


def annuity(balance, r, n):
    """Level monthly payment that repays balance over n months at monthly rate r."""
    if r == 0:
        return money(balance / n)
    return money(balance * r / (1 - (1 + r) ** -n))


def keep_payment_months(balance, r, payment, limit):
    """Remaining amortisation when a renewal keeps the payment (ADR-0043 amendment, C-M7):
    the smallest whole n with annuity(balance, r, n) <= payment, i.e.
    n = ceil(-ln(1 - r*balance/payment) / ln(1 + r)), or ceil(balance/payment) at r = 0.
    None (the caller falls back to recomputing the payment) when the payment does not cover
    the monthly interest or n exceeds ``limit``, the remaining amortisation."""
    if payment <= 0 or (r > 0 and payment <= balance * r):
        return None
    if r == 0:
        x = balance / payment
    else:
        x = -(ONE - r * balance / payment).ln() / (ONE + r).ln()
    if x > limit:
        return None
    n = max(1, int(x.to_integral_value(rounding=ROUND_CEILING)))
    # ln and the cent rounding of annuity can put n one off: settle on the smallest that fits.
    while annuity(balance, r, n) > payment:
        n += 1
        if n > limit:
            return None
    while n > 1 and annuity(balance, r, n - 1) <= payment:
        n -= 1
    return n


def mortgage_terms(item):
    """Monthly rate (semi-annual compounding), fixed annuity payment, number of payments."""
    principal = Decimal(str(item["principal"]))
    n = int(Decimal(str(item["amortizationYears"])) * 12)
    r = monthly_rate(item["annualRate"])
    return r, annuity(principal, r, n), n


def indexed(base, rate, months_since_start, divisor=1):
    """Monthly amount after indexing (ADR-0013): steps up once a year on the anniversary
    of the item's start date. The base amount is in dollars of the item's start month.
    An annual amount (divisor 12) is spread evenly over the months (ADR-0021)."""
    return money(base * (ONE + rate) ** (months_since_start // 12) / divisor)


def indexing_rate(item, inflation):
    """Annual indexing rate of a flow or pension: the expression the reference repeats in
    prepare() for income/expense, contribution/withdrawal and pension (verbatim)."""
    indexing = item.get("indexing") or "none"
    return (inflation if indexing == "inflation" else
            Decimal(str(item["indexRate"])) if indexing == "custom" else Decimal(0))
