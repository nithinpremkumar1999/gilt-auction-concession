"""
Stage 2 diagnostics for the curve pricer beyond the acceptance test (spec §5). Validation only:
nothing here changes the curve conventions.

1. monthly_residuals(): DMO yield minus model yield for every single-dated conventional gilt on the
   last reference-price date of each month, 25 Nov 2002 - 21 Jul 2017, under flat-forward (the
   study, decision #5) and flat-z extrapolation. Shows how the residuals of gilts beyond the curve's
   25y maximum (all before 2016) compare with gilts inside it.
2. truncation_test(): from 2016 the BoE publishes the curve to 40y. Cut each month-end curve at 25y,
   extrapolate it (flat forward from the BoE forward at 25y, or flat z), and compare the model
   yields of gilts with 25-40 years to maturity with those from the full curve. This measures the
   extrapolation error that pre-2016 long auctions carry, against the BoE's own longer curve.

Run:  python -m gilt_study.exercises.curve_checks
Outputs: data/processed_data/stage2/monthly_residuals.csv, extrapolation_truncation.csv
"""
import datetime as dt
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from .. import config, gilt_terms, paths
from ..curve import (Curve, _read_sheet, beyond_curve, curve_on, load_panel, maturity_columns,
                     model_yield)
from ..data_io import conventional_only, instrument_type, load_reference_prices
from ..pricing import next_business_day

OUT_DIR = paths.PROCESSED / "stage2"
TRUNCATE_AT = 25.0                       # the BoE's maximum maturity before 2016
TRUNCATION_START = dt.date(2016, 1, 1)


# ---------------------------------------------------------------- 1. monthly residuals 2002-2017
def _month_end_dates(dates) -> list:
    s = pd.Series(sorted(set(dates)))
    return list(s.groupby([d.strftime("%Y-%m") for d in s]).max())


def _residuals_year(year: int) -> pd.DataFrame:
    panel = load_panel()
    T = gilt_terms.load_terms().set_index("isin")
    ref, _ = conventional_only(load_reference_prices(paths.ref_prices_file(year)))
    lo, hi = config.PRICER_TEST_WINDOW
    ref = ref[(ref["date"] >= lo) & (ref["date"] <= hi)]
    # gilts with known terms only: drops WI lines (temporary ISINs or 'WI' names), whose DMO yields
    # are for settlement on the tranche's issue date
    ref = ref[ref["isin"].isin(T.index) & ~ref["name"].str.contains(r"WI$")]
    rows = []
    for date in _month_end_dates(ref["date"]):
        ff, cdate, fb = curve_on(panel, date, "flat_forward")
        fz, _, _ = curve_on(panel, date, "flat_z")
        settle = next_business_day(cdate)
        for g in ref[ref["date"] == date].itertuples(index=False):
            if (g.redemption - date).days / 365.25 <= 1.0:          # as Module 2: > 1 year
                continue
            fi, fc = T.at[g.isin, "first_issue"], T.at[g.isin, "first_coupon"]
            y_ff = model_yield(settle, g.redemption, g.coupon, ff, fi, fc)
            y_fz = model_yield(settle, g.redemption, g.coupon, fz, fi, fc)
            rows.append(dict(date=date, gilt=g.name, isin=g.isin, coupon=g.coupon,
                             redemption=g.redemption, years=(g.redemption - date).days / 365.25,
                             t_max=ff.t_max, beyond_curve=beyond_curve(settle, g.redemption, ff, fi),
                             dmo_yield=g._7, residual_bp=(g._7 - 100 * y_ff) * 100,
                             residual_bp_flat_z=(g._7 - 100 * y_fz) * 100, curve_fallback=fb))
    return pd.DataFrame(rows)


def monthly_residuals(write: bool = True) -> pd.DataFrame:
    years = range(config.PRICER_TEST_WINDOW[0].year, config.PRICER_TEST_WINDOW[1].year + 1)
    load_panel()                                        # build once before the workers start
    with ProcessPoolExecutor(max_workers=os.cpu_count() or 1) as pool:
        R = pd.concat(pool.map(_residuals_year, years), ignore_index=True)
    if write:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        R.to_csv(OUT_DIR / "monthly_residuals.csv", index=False)
    return R


# ---------------------------------------------------------------- 2. truncation test 2016-2026
def forward_at(maturity: float = TRUNCATE_AT) -> pd.Series:
    """The BoE instantaneous forward (%) at `maturity` on every date from 2016 (forward sheet)."""
    files = [paths.curve_workbook("2016 to 2024"), paths.curve_workbook("2025 to present"),
             paths.CURVE_CURRENT_MONTH]
    parts = [_read_sheet(pd.ExcelFile(f), 2)[round(maturity, 6)] for f in files]
    return pd.concat(parts).dropna().sort_index()


def truncation_test(write: bool = True) -> pd.DataFrame:
    panel = load_panel()
    f25 = forward_at(TRUNCATE_AT)
    T = gilt_terms.load_terms()
    T = T[np.array([instrument_type(n) == "single-dated" for n in T["name"]]) & T["maturity"].notna()]
    mats = maturity_columns(panel)
    keep = [m for m in mats if m <= TRUNCATE_AT + 1e-9]
    dates = _month_end_dates([d.date() for d in panel.index if d.date() >= TRUNCATION_START])
    rows = []
    for date in dates:
        full, cdate, _ = curve_on(panel, date, "flat_forward")
        row = panel.loc[pd.Timestamp(cdate)]
        z = row[keep].to_numpy(float)
        cut = {m: Curve(cdate, keep, z, f25.loc[pd.Timestamp(cdate)], m) for m in ("flat_forward", "flat_z")}
        settle = next_business_day(cdate)
        live = T[(T["maturity"] > settle) & np.array([fi is None or fi <= settle for fi in T["first_issue"]])]
        for g in live.itertuples(index=False):
            yrs = (g.maturity - settle).days / 365.25
            if not TRUNCATE_AT < yrs <= full.t_max:
                continue
            y_full = model_yield(settle, g.maturity, g.coupon, full, g.first_issue, g.first_coupon)
            out = dict(date=cdate, gilt=g.name, isin=g.isin, coupon=g.coupon, maturity=g.maturity,
                       years=yrs, years_beyond=yrs - TRUNCATE_AT, model_yield_full=100 * y_full,
                       z_25=float(full(TRUNCATE_AT)), f_25=float(f25.loc[pd.Timestamp(cdate)]))
            for m, c in cut.items():
                y = model_yield(settle, g.maturity, g.coupon, c, g.first_issue, g.first_coupon)
                out[f"error_bp_{m}"] = (100 * y - 100 * y_full) * 100
            rows.append(out)
    R = pd.DataFrame(rows)
    if write:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        R.to_csv(OUT_DIR / "extrapolation_truncation.csv", index=False)
    return R


def summary(M: pd.DataFrame, X: pd.DataFrame):
    """Printed summary of both checks."""
    print("=== 1. Monthly residuals, 25 Nov 2002 - 21 Jul 2017 (DMO yield - model yield, bp) ===")
    g = M.assign(group=np.where(M["beyond_curve"], "beyond the curve's last maturity", "within the curve"))
    print(g.groupby("group").agg(gilt_days=("gilt", "size"), dates=("date", "nunique"),
                                 mean_flat_forward=("residual_bp", "mean"),
                                 mean_abs_flat_forward=("residual_bp", lambda s: s.abs().mean()),
                                 mean_flat_z=("residual_bp_flat_z", "mean"),
                                 mean_abs_flat_z=("residual_bp_flat_z", lambda s: s.abs().mean()))
          .round(2).to_string())
    print("\n=== 2. Truncation test 2016-2026: model yield from a curve cut at 25y minus full curve (bp) ===")
    X = X.assign(beyond=pd.cut(X["years_beyond"], [0, 5, 10, 15], labels=["25-30y", "30-35y", "35-40y"]))
    print(X.groupby("beyond", observed=True).agg(
        gilt_days=("gilt", "size"), mean_flat_forward=("error_bp_flat_forward", "mean"),
        mean_abs_flat_forward=("error_bp_flat_forward", lambda s: s.abs().mean()),
        mean_flat_z=("error_bp_flat_z", "mean"),
        mean_abs_flat_z=("error_bp_flat_z", lambda s: s.abs().mean())).round(2).to_string())


def main():
    M = monthly_residuals()
    X = truncation_test()
    summary(M, X)
    print(f"\nSaved {OUT_DIR / 'monthly_residuals.csv'} and {OUT_DIR / 'extrapolation_truncation.csv'}")
    return M, X


if __name__ == "__main__":
    main()
