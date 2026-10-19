"""
Gilt pricing conventions for the Gilt Auction Concession Study.

Conventions (validated against DMO 2016 reference prices and the D1A ex-dividend column):
  * Settlement: next UK (England) business day after the trade date (T+1).
  * Coupon schedule: nominal (unadjusted) quasi-coupon dates, stepping back from maturity in
    6-month steps, always measured from the maturity date (no cumulative drift).
  * Day count: actual/actual (r/s fractions of the current quasi-coupon period).
  * Ex-dividend date: the 7th UK business day strictly before the coupon date (the coupon date
    itself is never counted, even if it falls on a weekend or holiday).
  * A trade is ex-dividend if settlement is AFTER the ex-dividend date. Settlement ON the
    ex-dividend date is still cum-dividend (the buyer is the holder of record that evening).
  * Irregular first coupon (new issues): accrued interest runs from the first issue date; the first
    coupon is (c/2) x (days from issue to first coupon) / (days in each quasi-period), summed over
    the quasi-periods it spans (handles short and long first coupons).
  * Settlement before the first issue date (when-issued trading): priced for settlement on the
    first issue date, accrued interest = 0 (matches DMO reference prices).
  * Final coupon period, ex-dividend: the DMO reports accrued interest = 0 (observed in the 2016
    reference prices); the dirty price is unaffected.
"""
import datetime as dt
import re
from fractions import Fraction

import holidays
import numpy as np
from dateutil.relativedelta import relativedelta
from scipy.optimize import brentq

_UK_HOLIDAYS = holidays.UK(subdiv="ENG", years=range(1990, 2071))


# ----------------------------------------------------------------------------- calendar
def is_business_day(d: dt.date) -> bool:
    """True if d is a UK (England) business day: a weekday that is not a bank holiday.

    The `holidays` calendar includes one-off closures (e.g. 31 Dec 1999, 29 Apr 2011,
    19 Sep 2022, 8 May 2023); checked against holidays==0.106, so pin that version.
    """
    return d.weekday() < 5 and d not in _UK_HOLIDAYS


def next_business_day(d: dt.date) -> dt.date:
    """The first UK business day strictly after d (standard T+1 gilt settlement)."""
    d += dt.timedelta(days=1)
    while not is_business_day(d):
        d += dt.timedelta(days=1)
    return d


def ex_dividend_date(coupon_date: dt.date, n_bdays: int = 7) -> dt.date:
    """The n-th UK business day strictly before the coupon date."""
    d, k = coupon_date, 0
    while k < n_bdays:
        d -= dt.timedelta(days=1)
        if is_business_day(d):
            k += 1
    return d


# ----------------------------------------------------------------------------- names
_FRACTION_SYMBOLS = {"¼": Fraction(1, 4), "½": Fraction(1, 2), "¾": Fraction(3, 4),
                     "⅛": Fraction(1, 8), "⅜": Fraction(3, 8), "⅝": Fraction(5, 8), "⅞": Fraction(7, 8)}


def parse_coupon(name: str):
    """Coupon (% per year) from a DMO gilt name, e.g. '4¼% Treasury Gilt 2055', '0 3/8% ...',
    '4 1/8% ...', '8% Treasury Stock 2021'. Returns None if no coupon is found."""
    m = re.match(r"\s*(\d+)?\s*([¼½¾⅛⅜⅝⅞]|\d+/\d+)?\s*%", str(name))
    if not m or (m.group(1) is None and m.group(2) is None):
        return None
    whole = Fraction(int(m.group(1))) if m.group(1) else Fraction(0)
    frac = m.group(2)
    if frac:
        whole += _FRACTION_SYMBOLS[frac] if frac in _FRACTION_SYMBOLS else Fraction(frac)
    return float(whole)


# ----------------------------------------------------------------------------- schedule
def _quasi_dates(maturity: dt.date, earliest: dt.date):
    """Regular quasi-coupon dates from the last one <= earliest up to maturity (ascending)."""
    dates, k = [], 0
    while True:
        q = maturity - relativedelta(months=6 * k)
        dates.append(q)
        if q <= earliest:
            break
        k += 1
    return dates[::-1]


def cash_flows(settle, maturity, coupon, first_issue=None, first_coupon=None, ex_div_bdays=7,
               cum_on_ex_date=True):
    """Single source of truth for a conventional gilt's remaining cash flows.

    Returns a dict with:
      dates   : quasi-coupon dates after settlement (nominal, unadjusted)
      amounts : cash paid on each of those dates per £100 nominal (0 on a quasi date with no payment)
      expo    : exponents in half-years for discounting (r/s + k)
      accrued : accrued interest (negative when ex-dividend)
      is_ex   : ex-dividend flag
      r, s    : days to next quasi date, days in current quasi period
    cum_on_ex_date=False reproduces the Module 0 assumption (for comparison only).
    """
    if settle >= maturity:
        raise ValueError(f"settle {settle} must be before maturity {maturity}")
    half = coupon / 2.0
    earliest = min(settle, first_issue) if first_issue else settle
    Q = _quasi_dates(maturity, earliest)

    # payment dates: every quasi date from the first coupon onwards
    if first_issue is not None and first_coupon is None:
        first_coupon = next(q for q in Q if q > first_issue)       # default: short first coupon
    pay_from = first_coupon if first_coupon is not None else Q[0]

    def coupon_amount(pay_date):
        """Coupon paid on pay_date (handles an irregular first coupon)."""
        if first_issue is None or pay_date != first_coupon:
            return half
        amt = 0.0
        for a, b in zip(Q[:-1], Q[1:]):                             # quasi periods spanned
            lo, hi = max(a, first_issue), min(b, first_coupon)
            if hi > lo:
                amt += half * (hi - lo).days / (b - a).days
        return amt

    # when-issued trading (settlement before first issue): the DMO prices for settlement on the
    # issue date, with zero accrued interest
    if first_issue is not None and settle < first_issue:
        settle = first_issue

    future = [q for q in Q if q > settle]
    q1 = future[0]
    q0 = Q[Q.index(q1) - 1]
    r, s = (q1 - settle).days, (q1 - q0).days

    amounts = np.array([coupon_amount(q) if q >= pay_from else 0.0 for q in future])
    amounts[-1] += 100.0

    # accrued interest (cum): from max(last payment, first issue) to settlement
    last_pay = max([q for q in Q if q <= settle and q >= pay_from], default=None)
    start = max(d for d in [last_pay, first_issue, Q[0]] if d is not None)
    accrued = 0.0
    if settle > start:
        for a, b in zip(Q[:-1], Q[1:]):
            lo, hi = max(a, start), min(b, settle)
            if hi > lo:
                accrued += half * (hi - lo).days / (b - a).days

    # ex-dividend: relative to the next actual payment date
    next_pay = next(q for q in future if q >= pay_from)
    xd = ex_dividend_date(next_pay, ex_div_bdays)
    is_ex = settle > xd if cum_on_ex_date else settle >= xd   # True = DMO convention
    if is_ex:
        j = future.index(next_pay)
        c_next = coupon_amount(next_pay)
        amounts[j] -= c_next
        accrued = 0.0 if next_pay == maturity else accrued - c_next

    expo = r / s + np.arange(len(future))
    return dict(dates=future, amounts=amounts, expo=expo, accrued=accrued, is_ex=is_ex, r=r, s=s)


# ----------------------------------------------------------------------------- price / yield
def gilt_price(settle, maturity, coupon, ytm, first_issue=None, first_coupon=None, ex_div_bdays=7,
               cum_on_ex_date=True):
    """Price per £100 nominal from a semi-annual gross redemption yield (decimal)."""
    cf = cash_flows(settle, maturity, coupon, first_issue, first_coupon, ex_div_bdays, cum_on_ex_date)
    v = 1.0 / (1.0 + ytm / 2.0)
    pv = cf["amounts"] * v ** cf["expo"]
    dirty = pv.sum()
    dv01 = 1e-4 * 0.5 * np.sum(cf["expo"] * cf["amounts"] * v ** (cf["expo"] + 1))
    mac = np.sum(cf["expo"] / 2.0 * pv) / dirty
    return dict(dirty=dirty, accrued=cf["accrued"], clean=dirty - cf["accrued"], dv01=dv01,
                mod_duration=mac / (1 + ytm / 2.0), is_ex=cf["is_ex"])


def yield_from_dirty(settle, maturity, coupon, dirty, first_issue=None, first_coupon=None,
                     lo=-0.05, hi=0.40):
    """Semi-annual GRY (decimal) that reproduces a dirty price."""
    f = lambda y: gilt_price(settle, maturity, coupon, y, first_issue, first_coupon)["dirty"] - dirty
    return brentq(f, lo, hi, xtol=1e-12)
