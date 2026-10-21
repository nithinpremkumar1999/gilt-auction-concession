"""Stage 5: control C for M2 (build spec §7): the gilt's model yield minus the OIS rate at the same
maturity, from December 2021.

* OIS curve: BoE daily OIS spot curves (data #7), the 2016-2024 and 2025-to-present workbooks, which
  have the same layout as the nominal ones (sheet 2 forward curve, 3 spot short end, 4 spot curve,
  maturities to 25 years). The same splice, spline and flat-forward rule as the nominal curve
  (`curve.Curve`) is used, so ultra-long gilts are compared with a flat-forward OIS beyond 25y
  (listed at the Stage 5 gate). The archive ends on 30 Sep 2026 (no current-month OIS file).
* Control C: AR^C_k = dy_k - do_k, where o_k is the OIS spot rate (% cont. comp.) on day T+k at the
  gilt's own remaining maturity (maturity minus that day's next-day settlement), i.e. the change in
  the gilt-OIS spread. beta = 1 by construction. CAR and the three numbers as for M2.
* Sample: auctions dated 1 Dec 2021 or later. A window number is missing if any of its days lies
  after the end of the OIS data (30 Sep 2026). One OIS date inside the data has no long-end curve
  (only the short end was published); as for the nominal curve (spec §5), the previous OIS curve is
  used and the auction's `ois_fallback_days` counts it.

Output: data/processed_data/curves/boe_ois_spot_daily.csv.gz (panel),
        data/processed_data/measures/m2c.csv (one row per auction in the sample)
"""
import datetime as dt

import numpy as np
import pandas as pd

from . import measures as ms, paths
from .curve import Curve, META_COLUMNS, _read_sheet, _splice_spot, effective_settlement, maturity_columns
from .pricing import next_business_day

OIS_PANEL_FILE = paths.PROCESSED / "curves" / "boe_ois_spot_daily.csv.gz"
M2C_FILE = ms.OUT_DIR / "m2c.csv"
C_START = dt.date(2021, 12, 1)
OIS_WORKBOOKS = ("2016 to 2024", "2025 to present")


def build_ois_panel(write: bool = True) -> pd.DataFrame:
    """Daily OIS spot panel (2016 onwards), same columns as the nominal panel. Rows where the long
    sheet is empty (only the short end published) are dropped and counted."""
    parts = []
    for lab in OIS_WORKBOOKS:
        xls = pd.ExcelFile(paths.OIS_DIR / f"OIS daily data_{lab}.xlsx")
        spot = _splice_spot(xls)
        long_ = _read_sheet(xls, 4).reindex(spot.index)
        fwd = _read_sheet(xls, 2).reindex(spot.index)
        has_long = long_.notna().any(axis=1)
        spot, long_, fwd = spot[has_long], long_[has_long], fwd[has_long]
        t_max = long_.apply(lambda r: r.last_valid_index(), axis=1).astype(float)
        meta = pd.DataFrame(index=spot.index)
        meta["source"] = f"OIS {lab}"
        meta["t_min"] = spot.apply(lambda r: r.first_valid_index(), axis=1).astype(float)
        meta["t_max"] = t_max
        meta["z_tmax"] = [spot.at[d, t] for d, t in zip(spot.index, t_max)]
        meta["f_tmax"] = [fwd.at[d, t] for d, t in zip(fwd.index, t_max)]
        meta["short_end_only_rows_dropped"] = int((~has_long).sum())
        parts.append(pd.concat([meta, spot], axis=1))
    P = pd.concat(parts).sort_index()
    mats = sorted(c for c in P.columns if not isinstance(c, str))
    P = P[["source", "t_min", "t_max", "z_tmax", "f_tmax", "short_end_only_rows_dropped"] + mats]
    P = P[~P.index.duplicated(keep="first")]
    P.index.name = "date"
    if write:
        out = P.copy()
        out.columns = [c if isinstance(c, str) else f"{c:.6f}" for c in out.columns]
        OIS_PANEL_FILE.parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(OIS_PANEL_FILE, date_format="%Y-%m-%d")
    return P


def load_ois_panel() -> pd.DataFrame:
    if not OIS_PANEL_FILE.exists():
        build_ois_panel()
    P = pd.read_csv(OIS_PANEL_FILE, index_col="date", parse_dates=["date"], float_precision="round_trip")
    P.columns = [c if (c in META_COLUMNS or c == "short_end_only_rows_dropped") else float(c) for c in P.columns]
    return P


def m2c(write: bool = True) -> pd.DataFrame:
    """Control C path T-10..T+10 and three numbers for auctions from 1 Dec 2021."""
    from . import auctions as au
    from .curve import load_panel
    P = au.load_auction_panel()
    cp = load_panel()
    O = load_ois_panel()
    mats = maturity_columns(O)
    Y = ms.load_model_yields().set_index(["isin", "curve_date"])["model_yield"]
    rows = []
    for r in P[P["auction_date"] >= C_START].itertuples(index=False):
        days = ms.event_days(cp.index, r.auction_date, ms.M2_WINDOW[0] - 1, ms.M2_WINDOW[1])
        aid = f"{r.auction_date}_{r.isin}"
        fi = r.first_issue if isinstance(r.first_issue, dt.date) else None
        o, y, fallback = {}, {}, 0
        for k, ts in zip(range(ms.M2_WINDOW[0] - 1, ms.M2_WINDOW[1] + 1), days):
            y[k] = Y[(r.isin, ts.date())]
            if O.index[0] <= ts <= O.index[-1]:
                # spec §5 rule, as for the nominal curve: a missing date takes the previous OIS curve
                used = O.index[O.index.searchsorted(ts, side="right") - 1]
                fallback += int(used != ts)
                row = O.loc[used]
                crv = Curve(ts.date(), mats, row[mats].to_numpy(float), row["f_tmax"])
                eff = effective_settlement(next_business_day(ts.date()), fi)
                o[k] = float(crv((r.maturity - eff).days / 365.25))
            else:
                o[k] = np.nan
        ks = list(range(ms.M2_WINDOW[0], ms.M2_WINDOW[1] + 1))
        ar = pd.Series({k: 100 * (y[k] - y[k - 1]) - 100 * (o[k] - o[k - 1]) for k in ks})
        car = ms.cumulate(ar)
        rec = dict(auction_id=aid, auction_date=r.auction_date, bucket=r.bucket, regime=r.regime,
                   ois_days=int(np.sum(~np.isnan([o[k] for k in ks]))), ois_fallback_days=fallback,
                   ois_beyond_25y=(r.maturity - r.settlement_date).days / 365.25 > 25)
        for label, (a, b) in ms.PM_NUMBERS.items():
            seg = ar.loc[a + 1:b]                      # the daily changes inside the window
            rec[f"m2_{label}_c_bp"] = seg.sum() if seg.notna().all() else np.nan
        rows.append(rec)
    C = pd.DataFrame(rows)
    if write:
        C.to_csv(M2C_FILE, index=False)
    return C


if __name__ == "__main__":
    O = build_ois_panel()
    print(f"OIS panel: {len(O)} days {O.index[0].date()} to {O.index[-1].date()}; t_max {sorted(set(O['t_max']))}")
    C = m2c()
    print(C.describe().round(3).T)
