"""
Exercise A: validate the gilt pricer against DMO 2016 reference prices, and check the ex-dividend
convention against the DMO's published ex-dividend dates in D1A.

Run:  python -m gilt_study.exercises.exercise_a
Outputs: printed summary + data/processed_data/exercises/exercise_a_errors.csv
"""
import datetime as dt

import pandas as pd

from .. import paths
from ..data_io import conventional_only, load_d1a, load_reference_prices
from ..pricing import (_UK_HOLIDAYS, cash_flows, ex_dividend_date, gilt_price, is_business_day,
                       next_business_day)

# ---------------------------------------------------------------- CONFIG (paths live in paths.py)
REF_FILE = paths.ref_prices_file(2016)
D1A_FILE = paths.D1A
OUT_DIR = paths.PROCESSED / "exercises"

# First issue dates for 2016 new issues that are no longer in D1A (they have matured).
# ⚠️ Inferred from the DMO's accrued interest on the first day it turns positive.
#    Replace with dates from D2.1E (issuance history) when you build the full panel.
FIRST_ISSUE_OVERRIDES = {
    "GB00BYY5F581": dt.date(2015, 9, 3),    # 1½% Treasury Gilt 2021
    "GB00BYZW3G56": dt.date(2016, 2, 18),   # 1½% Treasury Gilt 2026
    "GB00BD0PCK97": dt.date(2016, 8, 3),    # 0½% Treasury Gilt 2022
}
DIRTY_TOL = CLEAN_TOL = 1e-4                # the DMO yield is computed from its rounded clean price,
                                            # so clean prices from the DMO yield match to ~1e-5


def classify(row, first_issue):
    """Which known convention issue explains a Module-0 mismatch?"""
    cf = cash_flows(row.settle, row.redemption, row.coupon, first_issue)
    nxt = cf["dates"][0]          # next coupon date (no long first coupons in this data)
    labels = []
    if row.settle == ex_dividend_date(nxt):
        labels.append("A: settles ON ex-div date")
    if cf["is_ex"] and nxt == row.redemption:
        labels.append("B: final period, ex-div")
    if first_issue is not None and row.settle <= nxt and (nxt - first_issue).days < 200:
        labels.append("C: new issue (irregular 1st coupon / when-issued)")
    return "; ".join(labels) or "UNEXPLAINED"


def main():
    ref, excluded = conventional_only(load_reference_prices(REF_FILE))
    d1a = load_d1a(D1A_FILE)
    first_issue = dict(zip(d1a["isin"], d1a["first_issue"]))
    first_issue.update(FIRST_ISSUE_OVERRIDES)
    print(f"Conventional gilt-days: {len(ref):,}  gilts: {ref['isin'].nunique()}  "
          f"excluded names: {excluded}")

    rows = []
    for r in ref.itertuples(index=False):
        settle = next_business_day(r.date)
        if settle >= r.redemption:
            continue
        fi = first_issue.get(r.isin)
        y = r._7 / 100.0                                     # 'yield' column
        naive = gilt_price(settle, r.redemption, r.coupon, y, None, None, cum_on_ex_date=False)
        good = gilt_price(settle, r.redemption, r.coupon, y, fi)
        rows.append(dict(name=r.name, isin=r.isin, date=r.date, settle=settle,
                         redemption=r.redemption, coupon=r.coupon, dmo_yield=r._7,
                         dmo_dirty=r.dirty, dmo_accrued=r.accrued, dmo_clean=r.clean,
                         naive_dirty_err=naive["dirty"] - r.dirty,
                         naive_ai_err=naive["accrued"] - r.accrued,
                         dirty_err=good["dirty"] - r.dirty,
                         ai_err=good["accrued"] - r.accrued,
                         clean_err=good["clean"] - r.clean,
                         first_issue=fi))
    E = pd.DataFrame(rows)

    def bad(dirty, ai):
        return (dirty.abs() > DIRTY_TOL) | (ai.abs() > DIRTY_TOL)

    E["naive_bad"] = bad(E.naive_dirty_err, E.naive_ai_err)
    E["bad"] = bad(E.dirty_err, E.ai_err) | (E.clean_err.abs() > CLEAN_TOL)

    print("\n=== Module 0 conventions (settle >= ex-div date is ex; no first-issue handling) ===")
    nb = E[E.naive_bad].copy()
    nb["why"] = [classify(r, r.first_issue) for r in nb.itertuples()]
    print(f"mismatching gilt-days: {len(nb)} of {len(E)}")
    print(nb.groupby("why").agg(days=("name", "size"), gilts=("name", "nunique")).to_string())

    print("\n=== Corrected conventions ===")
    print(f"median |dirty error| : {E.dirty_err.abs().median():.2e}")
    print(f"max    |dirty error| : {E.dirty_err.abs().max():.2e}")
    print(f"max    |accrued err| : {E.ai_err.abs().max():.2e}")
    print(f"max    |clean error| : {E.clean_err.abs().max():.2e}")
    print(f"gilt-days failing tolerance: {E.bad.sum()}")
    if E.bad.any():
        print(E.loc[E.bad, ["name", "date", "dirty_err", "ai_err", "clean_err"]].to_string())

    # final coupon period: Module 0 would report negative accrued; the DMO reports 0
    fin = [r for r in E.itertuples()
           if cash_flows(r.settle, r.redemption, r.coupon)["is_ex"]
           and len(cash_flows(r.settle, r.redemption, r.coupon)["dates"]) == 1]
    print(f"\nB: final-period ex-div gilt-days (DMO accrued = 0, handled): {len(fin)} "
          f"across {len({r.name for r in fin})} gilts")

    # ---------------------------------------------------------- ex-dividend counting conventions
    print("\n=== Ex-dividend date: which business-day counting rule matches the DMO? ===")

    def roll_back_first(coupon_date, n=7):
        """numpy busday_offset(roll='backward') style: roll a non-business coupon date back to the
        previous business day, which then counts as day 0."""
        d = coupon_date
        while not is_business_day(d):
            d -= dt.timedelta(days=1)
        k = 0
        while k < n:
            d -= dt.timedelta(days=1)
            if is_business_day(d):
                k += 1
        return d

    def weekdays_only(coupon_date, n=7):
        """pandas BDay without UK holidays."""
        d, k = coupon_date, 0
        while k < n:
            d -= dt.timedelta(days=1)
            if d.weekday() < 5:
                k += 1
        return d

    rules = {"ours (UK holidays, coupon date not counted)": ex_dividend_date,
             "roll back first (numpy style)": roll_back_first,
             "weekdays only (pandas BDay, no holidays)": weekdays_only}

    # (1) against the DMO's published ex-div dates in D1A
    checks = []
    for g in d1a.itertuples():
        cf = cash_flows(g.dmo_ex_div, g.redemption, g.coupon, g.first_issue)
        nxt = cf["dates"][0]
        checks.append(dict(coupon_date=nxt, weekend=not is_business_day(nxt), dmo=g.dmo_ex_div))
    C = pd.DataFrame(checks)
    print(f"(1) D1A published ex-div dates: {len(C)} gilts, {C.weekend.sum()} with a non-business-day coupon")
    for label, f in rules.items():
        m = C.coupon_date.map(f) == C.dmo
        print(f"    {label:45s}: {m.sum()}/{len(C)} match")

    # (2) against the ex/cum switch implied by DMO accrued interest in 2016 (excl. final periods)
    print("(2) 2016 reference prices: days where the rule's ex/cum flag disagrees with the DMO's")
    sub = E[[len(cash_flows(r.settle, r.redemption, r.coupon, r.first_issue)["dates"]) > 1
             for r in E.itertuples()]]
    dmo_ex = sub.dmo_accrued < 0
    for label, f in rules.items():
        flags = []
        for r in sub.itertuples():
            cf = cash_flows(r.settle, r.redemption, r.coupon, r.first_issue)
            nxt = cf["dates"][0]
            flags.append(r.settle > f(nxt))
        print(f"    {label:45s}: {(pd.Series(flags, index=sub.index) != dmo_ex).sum()} disagreements")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    E.to_csv(OUT_DIR / "exercise_a_errors.csv", index=False)
    print(f"\nSaved {OUT_DIR / 'exercise_a_errors.csv'}")


if __name__ == "__main__":
    main()
