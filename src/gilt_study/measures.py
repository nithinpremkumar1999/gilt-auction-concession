"""Stage 4: the concession measures M1, M1b and M2 (build spec §7).

Event time is counted in UK business days, which are exactly the BoE curve dates (Stage 2: no
business day is missing). Day 0 (T) is the auction date; T-1 is the previous curve date.

M1, primary concession (bp)
---------------------------
  M1 = 100 x (AAY - model yield), where the model yield is the auctioned gilt priced off the T-1
  close curve. The model yield is computed for the auction's own settlement date (the DMO issue
  date, spec §4), so it is compared with the AAY like for like. As in the whole curve pricer, t is
  measured from that settlement date (from the first issue date for a new gilt, decision #10).
  Positive = the auction cleared cheap to the curve.

M1b, baseline-adjusted concession, 1998-2017 (decision #4)
-------------------------------------------------------------
  M1b = M1 - the gilt's mean residual over T-25 to T-6, where residual_d = 100 x (DMO reference
  yield_d - model yield_d), both for settlement on the next business day after d.
  Proposed defaults (not set by the spec; listed at the Stage 4 gate):
    * 'any earlier auction of the same gilt inside it' -> drop days within +-5 business days of an
      earlier auction of the same gilt (the same +-5 used for the pre/post windows);
    * at least 10 valid days of the 20, else M1b is missing.
  M1b is missing for new issues (no prices before launch) and outside the reference-price data
  (1 Nov 1998 - 21 Jul 2017). Market yield = the DMO yield where published (from 25 Nov 2002); before
  that, the yield our pricer gives for the DMO clean price plus our accrued interest (spec §7, v0.5).

M3, bond residual path (spec §7, decision #17)
-----------------------------------------------
  r_k = 100 x (market yield - model yield) of the auctioned gilt on day T+k, k = -10..+10, from the
  DMO reference prices (own ISIN line; market yield as for M1b). The three numbers are changes in
  r over the same windows as M2: pre = r_-1 - r_-6, day = r_0 - r_-1, post = r_5 - r_0 (missing if
  an end point is missing). Available 1 Nov 1998 - 21 Jul 2017.

M2, event path with control B-beta (decision #13)
-------------------------------------------------
  y_k = model yield of the auctioned gilt off curve T+k, for settlement on the next business day
        after T+k (the first issue date for a new gilt before launch, decision #10).
  dy_k = 100 x (y_k - y_{k-1}) in bp.
  dc_k = mean over the control maturities of 100 x (z_m(T+k) - z_m(T+k-1)), where the control
         maturities are the BoE spot points 2.0, 2.5, ..., 30.0 years that lie more than 3 years
         from the gilt's years to maturity (|m - ytm| > 3) and exist on every day used (so the
         range stops at 25y before 2016).
  beta  = OLS slope of dy on dc (with an intercept, which is not used) over k = -120..-21.
  AR_k  = dy_k - beta x dc_k  (no alpha subtracted);  CAR_k cumulates AR from the base T-6:
          CAR_-6 = 0, CAR_k = sum_{j=-5..k} AR_j for k > -6, and -sum_{j=k+1..-6} AR_j for k < -6.
  Robustness B: beta = 1 (AR_B). The raw path (no control) is kept too.
  beta outliers (spec): beta < 0 or beta > 3 are flagged.

The PM's three numbers (spec §7), as read here (listed at the gate):
  pre-auction cheapening (T-5 -> T-1) = CAR_-1 - CAR_-6  (the daily changes of days T-5..T-1)
  auction-day concession             = CAR_0 - CAR_-1    (close T-1 to close T)
  post-auction reversal (T -> T+5)   = CAR_5 - CAR_0     (the daily changes of days T+1..T+5)
  Positive = the gilt cheapened relative to the control (its yield rose more).

Extra windows (Stage 6 chart gate, 21 Oct 2026; added after seeing chart 1, where M3 rises from T-8)
  pre10 (T-10 -> T-1)   robustness pre-auction window, M2 (B-beta) and M3: CAR_-1 - CAR_-10, r_-1 - r_-10
  total (T-10 -> T+1)   the M3 total move: r_1 - r_-10

Outputs
-------
  data/interim_data/auction_gilt_model_yields.csv.gz  model yield of every auctioned gilt on every
                                                      curve date used (cache; regenerable)
  data/processed_data/measures/auction_measures.csv   one row per auction: M1, M1b, beta, PM numbers
  data/processed_data/measures/m2_paths.csv.gz        T-10..T+10 path per auction
  data/processed_data/measures/m1b_residuals.csv.gz   T-25..T-6 residuals per auction
  data/processed_data/measures/m3_paths.csv.gz        T-10..T+10 bond residual path per auction
  data/interim_data/auctioned_gilts_market_yields.csv.gz  market yields of the auctioned gilts,
                                                      1 Nov 1998 - 21 Jul 2017 (DMO, or from clean)

Run:  python -m gilt_study.measures            (about 10 minutes on 2 cores the first time)
"""
import datetime as dt
import os
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from . import auctions as au, config, paths
from .curve import Curve, curve_on, effective_settlement, load_panel, maturity_columns, model_yield
from .data_io import load_reference_prices
from .pricing import cash_flows, next_business_day, yield_from_dirty

OUT_DIR = paths.PROCESSED / "measures"
MEASURES_FILE = OUT_DIR / "auction_measures.csv"
PATHS_FILE = OUT_DIR / "m2_paths.csv.gz"
RESIDUALS_FILE = OUT_DIR / "m1b_residuals.csv.gz"
M3_PATHS_FILE = OUT_DIR / "m3_paths.csv.gz"
MARKET_YIELDS_FILE = paths.INTERIM / "auctioned_gilts_market_yields.csv.gz"
REF_DATA_WINDOW = (dt.date(1998, 11, 1), config.PRICER_TEST_WINDOW[1])   # actual/actual era .. last file
SRC_DMO_YIELD, SRC_FROM_CLEAN = "DMO yield", "from DMO clean price"
MODEL_YIELDS_FILE = paths.INTERIM / "auction_gilt_model_yields.csv.gz"

M2_WINDOW = (-10, 10)            # spec §7
M2_BASE = -6                     # cumulative change from T-6
BETA_WINDOW = (-120, -21)        # decision #13
BETA_OUTLIER = (0.0, 3.0)        # flag beta < 0 or > 3
CONTROL_GRID = np.round(np.arange(2.0, 30.0 + 1e-9, 0.5), 6)   # 2-30y, half-yearly BoE points
CONTROL_EXCLUSION_YEARS = 3.0    # outside +-3 years of the gilt's maturity
M1B_WINDOW = (-25, -6)           # decision #4
M1B_EXCLUDE_BDAYS = 5            # proposed default: +-5 business days around an earlier auction
M1B_MIN_DAYS = 10                # proposed default
FIRST_K = BETA_WINDOW[0] - 1     # earliest day whose model yield is needed (-121)
PM_NUMBERS = {"pre": (-6, -1), "day": (-1, 0), "post": (0, 5)}
# Added at the Stage 6 chart gate (21 Oct 2026), after seeing chart 1
M2_EXTRA_WINDOWS = {"pre10": (-10, -1)}                       # robustness pre-auction window
M3_EXTRA_WINDOWS = {"pre10": (-10, -1), "total": (-10, 1)}    # robustness window; M3 total move


# ============================================================================ event-time helpers
def event_days(index: pd.DatetimeIndex, auction_date: dt.date, k_from: int, k_to: int) -> pd.DatetimeIndex:
    """Curve dates T+k_from .. T+k_to (UK business days) around an auction date."""
    pos = index.get_loc(pd.Timestamp(auction_date))
    return index[pos + k_from: pos + k_to + 1]


def control_maturities(years_to_maturity: float, available) -> np.ndarray:
    """BoE grid points 2-30y more than 3 years from the gilt's maturity, among `available`."""
    avail = set(np.round(np.asarray(available, float), 6))
    keep = [m for m in CONTROL_GRID if abs(m - years_to_maturity) > CONTROL_EXCLUSION_YEARS and m in avail]
    return np.array(keep)


def ols(y: np.ndarray, x: np.ndarray) -> dict:
    """OLS of y on x with an intercept: alpha, beta, se(beta), R^2, n."""
    X = np.column_stack([np.ones_like(x), x])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ coef
    n = len(y)
    s2 = resid @ resid / (n - 2)
    se_beta = np.sqrt(s2 / np.sum((x - x.mean()) ** 2))
    r2 = 1 - (resid @ resid) / np.sum((y - y.mean()) ** 2)
    return dict(alpha=coef[0], beta=coef[1], se_beta=se_beta, r2=r2, n=n)


def cumulate(ar: pd.Series, base: int = M2_BASE) -> pd.Series:
    """CAR from abnormal returns indexed by k: 0 at the base, cumulated forwards and backwards."""
    car = pd.Series(0.0, index=ar.index)
    for k in ar.index:
        if k > base:
            car[k] = ar.loc[base + 1:k].sum()
        elif k < base:
            car[k] = -ar.loc[k + 1:base].sum()
    return car


# ============================================================================ model-yield cache
def _model_yields_for_dates(args):
    """Worker: model yields for a list of (curve date, [(isin, maturity, coupon, fi, fc), ...])."""
    items, = args
    cp = load_panel()
    mats = maturity_columns(cp)
    out = []
    for ts, gilts in items:
        row = cp.loc[ts]
        crv = Curve(ts.date(), mats, row[mats].to_numpy(float), row["f_tmax"])
        settle = next_business_day(ts.date())
        for isin, mat, cpn, fi, fc in gilts:
            eff = effective_settlement(settle, fi)
            out.append((isin, ts.date(), eff, 100.0 * model_yield(settle, mat, cpn, crv, fi, fc)))
    return out


def build_model_yields(P: pd.DataFrame, cp: pd.DataFrame, write: bool = True) -> pd.DataFrame:
    """Model yield (%) of each auctioned gilt on every curve date from T-121 to T+10 of each of its
    auctions, for settlement on the next business day (decision #10 before launch)."""
    need = {}
    terms = {}
    for r in P.itertuples(index=False):
        terms[r.isin] = (r.maturity, r.coupon, r.first_issue, r.first_coupon)
        for ts in event_days(cp.index, r.auction_date, FIRST_K, M2_WINDOW[1]):
            need.setdefault(ts, set()).add(r.isin)
    dates = sorted(need)
    items = [(ts, [(i, *terms[i]) for i in sorted(need[ts])]) for ts in dates]
    n_workers = os.cpu_count() or 1
    chunks = [items[i::n_workers * 8] for i in range(n_workers * 8)]
    with ProcessPoolExecutor(max_workers=n_workers) as pool:
        res = [x for part in pool.map(_model_yields_for_dates, [(c,) for c in chunks]) for x in part]
    Y = pd.DataFrame(res, columns=["isin", "curve_date", "settle", "model_yield"]).sort_values(["isin", "curve_date"])
    if write:
        paths.INTERIM.mkdir(parents=True, exist_ok=True)
        Y.to_csv(MODEL_YIELDS_FILE, index=False, float_format="%.12g")
    return Y.reset_index(drop=True)


def load_model_yields() -> pd.DataFrame:
    Y = pd.read_csv(MODEL_YIELDS_FILE, float_precision="round_trip")
    Y["curve_date"] = [dt.date.fromisoformat(v) for v in Y["curve_date"]]
    Y["settle"] = [dt.date.fromisoformat(v) for v in Y["settle"]]
    return Y


# ============================================================================ M1
def m1(P: pd.DataFrame, cp: pd.DataFrame) -> pd.DataFrame:
    """Model yield off the T-1 curve for the auction settlement date, and M1 (bp)."""
    rows = []
    for r in P.itertuples(index=False):
        crv, used, fb = curve_on(cp, r.t_minus_1)
        y = 100.0 * model_yield(r.settlement_date, r.maturity, r.coupon, crv, r.first_issue, r.first_coupon)
        rows.append(dict(model_yield_t1=y, m1_bp=100.0 * (r.aay - y), m1_curve_date=used, m1_curve_fallback=fb))
    return pd.DataFrame(rows, index=P.index)


# ============================================================================ M2
def m2(P: pd.DataFrame, cp: pd.DataFrame, Y: pd.DataFrame):
    """Beta estimation and the T-10..T+10 path for every auction. Returns (summary, paths)."""
    ylook = Y.set_index(["isin", "curve_date"])["model_yield"]
    mats = maturity_columns(cp)
    summary, paths_ = [], []
    for r in P.itertuples(index=False):
        days = event_days(cp.index, r.auction_date, FIRST_K, M2_WINDOW[1])
        ks = np.arange(FIRST_K, M2_WINDOW[1] + 1)
        Z = cp.loc[days, mats]
        avail = [m for m in mats if Z[m].notna().all()]
        cm = control_maturities(r.years_to_maturity, avail)
        zc = Z[list(cm)].to_numpy(float)
        dc = pd.Series(np.r_[np.nan, 100.0 * np.diff(zc, axis=0).mean(axis=1)], index=ks)
        y = pd.Series([ylook[(r.isin, ts.date())] for ts in days], index=ks)
        dy = 100.0 * y.diff()
        est = ols(dy.loc[BETA_WINDOW[0]:BETA_WINDOW[1]].to_numpy(), dc.loc[BETA_WINDOW[0]:BETA_WINDOW[1]].to_numpy())
        win = np.arange(M2_WINDOW[0], M2_WINDOW[1] + 1)
        ar = (dy - est["beta"] * dc).loc[M2_WINDOW[0]:]
        ar_b = (dy - dc).loc[M2_WINDOW[0]:]
        car, car_b, car_raw = cumulate(ar), cumulate(ar_b), cumulate(dy.loc[M2_WINDOW[0]:])
        aid = f"{r.auction_date}_{r.isin}"
        for k in win:
            paths_.append(dict(auction_id=aid, k=int(k), curve_date=days[k - FIRST_K].date(), model_yield=y[k],
                               dy_bp=dy[k], dc_bp=dc[k], ar_bbeta=ar[k], car_bbeta=car[k],
                               ar_b=ar_b[k], car_b=car_b[k], car_raw=car_raw[k]))
        s = dict(auction_id=aid, beta=est["beta"], alpha_bp=est["alpha"], se_beta=est["se_beta"], r2=est["r2"],
                 n_beta=est["n"], beta_outlier=not (BETA_OUTLIER[0] <= est["beta"] <= BETA_OUTLIER[1]),
                 n_control_maturities=len(cm), control_min=cm.min(), control_max=cm.max(),
                 m2_window_start=days[M2_WINDOW[0] - FIRST_K].date(), m2_window_end=days[-1].date())
        for label, (a, b) in PM_NUMBERS.items():
            s[f"m2_{label}_bbeta_bp"] = car[b] - car[a]
            s[f"m2_{label}_b_bp"] = car_b[b] - car_b[a]
            s[f"m2_{label}_raw_bp"] = car_raw[b] - car_raw[a]
        for label, (a, b) in M2_EXTRA_WINDOWS.items():
            s[f"m2_{label}_bbeta_bp"] = car[b] - car[a]
        summary.append(s)
    return pd.DataFrame(summary, index=P.index), pd.DataFrame(paths_)


# ============================================================================ M1b
def _yields_from_clean(rows):
    """Worker: yield (%) for each (isin, date, clean, maturity, coupon, fi, fc) from the DMO clean price
    plus our accrued interest, for settlement on the next business day."""
    rows, = rows
    out = []
    for isin, d, clean, mat, cpn, fi, fc in rows:
        settle = next_business_day(d)
        eff = effective_settlement(settle, fi)
        if eff >= mat:
            out.append((isin, d, np.nan)); continue
        acc = cash_flows(eff, mat, cpn, fi, fc)["accrued"]
        out.append((isin, d, 100.0 * yield_from_dirty(eff, mat, cpn, clean + acc, fi, fc)))
    return out


def build_market_yields(P: pd.DataFrame, write: bool = True) -> pd.DataFrame:
    """Market yields of the auctioned gilts on every reference-price day 1 Nov 1998 - 21 Jul 2017:
    the DMO yield where published, else the yield from the DMO clean price (our pricer)."""
    lo, hi = REF_DATA_WINDOW
    isins = set(P["isin"])
    parts = []
    for y in range(lo.year, hi.year + 1):
        ref = load_reference_prices(paths.ref_prices_file(y))
        ref = ref[ref["isin"].isin(isins) & (ref["date"] >= lo) & (ref["date"] <= hi)]
        parts.append(ref[["isin", "date", "clean", "yield"]])
    R = pd.concat(parts, ignore_index=True).drop_duplicates(["isin", "date"]).rename(columns={"yield": "dmo_yield"})
    T = P.groupby("isin").agg(maturity=("maturity", "first"), coupon=("coupon", "first"),
                              fi=("first_issue", "first"), fc=("first_coupon", "first"))
    need = R[R["dmo_yield"].isna() & R["clean"].notna()]
    rows = [(i, d, float(c), T.at[i, "maturity"], T.at[i, "coupon"],
             T.at[i, "fi"] if isinstance(T.at[i, "fi"], dt.date) else None,
             T.at[i, "fc"] if isinstance(T.at[i, "fc"], dt.date) else None)
            for i, d, c in zip(need["isin"], need["date"], need["clean"])]
    n_workers = os.cpu_count() or 1
    chunks = [rows[i::n_workers * 4] for i in range(n_workers * 4)]
    with ProcessPoolExecutor(max_workers=n_workers) as pool:
        got = [x for part in pool.map(_yields_from_clean, [(c,) for c in chunks]) for x in part]
    G = pd.DataFrame(got, columns=["isin", "date", "yield_from_clean"])
    R = R.merge(G, on=["isin", "date"], how="left")
    R["market_yield"] = R["dmo_yield"].fillna(R["yield_from_clean"])
    R["yield_source"] = np.where(R["dmo_yield"].notna(), SRC_DMO_YIELD,
                                 np.where(R["yield_from_clean"].notna(), SRC_FROM_CLEAN, None))
    R = R.dropna(subset=["market_yield"]).sort_values(["isin", "date"])
    if write:
        paths.INTERIM.mkdir(parents=True, exist_ok=True)
        R.to_csv(MARKET_YIELDS_FILE, index=False, float_format="%.12g")
    return R.reset_index(drop=True)


def load_market_yields() -> pd.DataFrame:
    R = pd.read_csv(MARKET_YIELDS_FILE, float_precision="round_trip")
    R["date"] = [dt.date.fromisoformat(v) for v in R["date"]]
    return R


def m1b(P: pd.DataFrame, cp: pd.DataFrame, Y: pd.DataFrame, M1: pd.DataFrame, MY: pd.DataFrame):
    """Baseline (mean residual T-25..T-6) and M1b for every auction. Returns (summary, residuals)."""
    lo, hi = REF_DATA_WINDOW
    R = MY.set_index(["isin", "date"])["market_yield"]
    SRC = MY.set_index(["isin", "date"])["yield_source"]
    ylook = Y.set_index(["isin", "curve_date"])["model_yield"]
    pos = {d: i for i, d in enumerate(cp.index.date)}
    auc_by_isin = P.groupby("isin")["auction_date"].apply(sorted).to_dict()
    summary, resid = [], []
    for i, r in zip(P.index, P.itertuples(index=False)):
        aid = f"{r.auction_date}_{r.isin}"
        fi = r.first_issue if isinstance(r.first_issue, dt.date) else None
        days = event_days(cp.index, r.auction_date, *M1B_WINDOW)
        earlier = [pos[d] for d in auc_by_isin[r.isin] if d < r.auction_date]
        vals = []
        for k, ts in zip(range(M1B_WINDOW[0], M1B_WINDOW[1] + 1), days):
            d = ts.date()
            dmo = R.get((r.isin, d), np.nan)
            mod = ylook.get((r.isin, d), np.nan)
            reason = None
            if any(abs(pos[d] - p) <= M1B_EXCLUDE_BDAYS for p in earlier):
                reason = "within 5 business days of an earlier auction of the gilt"
            elif not (lo <= d <= hi):
                reason = "outside the reference-price data (1 Nov 1998 - 21 Jul 2017)"
            elif fi is not None and d < fi:
                reason = "before the gilt's first issue"
            elif np.isnan(dmo):
                reason = "no DMO price for the gilt that day"
            # the residual is kept for every day with a DMO yield (for the hand check and sensitivity
            # analysis); only days with no exclusion reason enter the baseline
            res = 100.0 * (dmo - mod) if (lo <= d <= hi and not np.isnan(dmo) and not np.isnan(mod)) else np.nan
            if reason is None:
                vals.append(res)
            resid.append(dict(auction_id=aid, k=k, date=d, market_yield=dmo, yield_source=SRC.get((r.isin, d)),
                              model_yield=mod, residual_bp=res, excluded=reason))
        n = len(vals)
        base = float(np.mean(vals)) if n else np.nan
        ok = n >= M1B_MIN_DAYS
        why = None if ok else ("new issue: no prices before launch" if r.new_issue else
                               ("outside the reference-price data" if n == 0 else f"only {n} valid days (< {M1B_MIN_DAYS})"))
        summary.append(dict(m1b_baseline_bp=base if ok else np.nan, m1b_days=n,
                            m1b_bp=M1.at[i, "m1_bp"] - base if ok else np.nan, m1b_missing_reason=why))
    return pd.DataFrame(summary, index=P.index), pd.DataFrame(resid)


# ============================================================================ M3
def m3(P: pd.DataFrame, cp: pd.DataFrame, Y: pd.DataFrame, MY: pd.DataFrame):
    """Bond residual path T-10..T+10 and its three numbers. Returns (summary, paths)."""
    R = MY.set_index(["isin", "date"])
    ylook = Y.set_index(["isin", "curve_date"])["model_yield"]
    summary, paths_ = [], []
    for i, r in zip(P.index, P.itertuples(index=False)):
        aid = f"{r.auction_date}_{r.isin}"
        days = event_days(cp.index, r.auction_date, *M2_WINDOW)
        res = {}
        for k, ts in zip(range(M2_WINDOW[0], M2_WINDOW[1] + 1), days):
            d = ts.date()
            key = (r.isin, d)
            mk = R["market_yield"].get(key, np.nan)
            mod = ylook.get(key, np.nan)
            res[k] = 100.0 * (mk - mod)
            paths_.append(dict(auction_id=aid, k=k, date=d, market_yield=mk, yield_source=R["yield_source"].get(key),
                               model_yield=mod, residual_bp=res[k]))
        s_ = dict(m3_days=int(np.sum(~np.isnan(list(res.values())))), m3_residual_t6_bp=res[M2_BASE])
        for label, (a, b) in {**PM_NUMBERS, **M3_EXTRA_WINDOWS}.items():
            s_[f"m3_{label}_bp"] = res[b] - res[a]
        summary.append(s_)
    Pth = pd.DataFrame(paths_)
    base = Pth[Pth["k"] == M2_BASE].set_index("auction_id")["residual_bp"]
    Pth["residual_rel_t6_bp"] = Pth["residual_bp"] - Pth["auction_id"].map(base)
    return pd.DataFrame(summary, index=P.index), Pth


# ============================================================================ build
def build(write: bool = True, rebuild_cache: bool = False):
    """All measures. Returns (measures, m2 paths, m1b residuals)."""
    P = au.load_auction_panel()
    cp = load_panel()
    Y = build_model_yields(P, cp) if (rebuild_cache or not MODEL_YIELDS_FILE.exists()) else load_model_yields()
    MY = build_market_yields(P) if (rebuild_cache or not MARKET_YIELDS_FILE.exists()) else load_market_yields()
    M1 = m1(P, cp)
    S2, paths_ = m2(P, cp, Y)
    S1b, resid = m1b(P, cp, Y, M1, MY)
    S3, paths3 = m3(P, cp, Y, MY)
    keys = P[["auction_date", "settlement_date", "gilt_name", "isin", "bucket", "regime", "passive_qt_2022",
              "new_issue", "years_to_maturity", "years_beyond_curve", "drop_extrapolation_robustness",
              "flag_first_coupon_rule", "aay", "t_minus_1"]].copy()
    keys.insert(0, "auction_id", [f"{d}_{i}" for d, i in zip(P["auction_date"], P["isin"])])
    ylook = Y.set_index(["isin", "curve_date"])["model_yield"]
    M1["model_yield_t1_curve_settle"] = [ylook[(i, d)] for i, d in zip(P["isin"], P["t_minus_1"])]
    M1["m1_alt_curve_settlement_bp"] = 100.0 * (P["aay"] - M1["model_yield_t1_curve_settle"])
    out = pd.concat([keys, M1, S1b, S2.drop(columns="auction_id"), S3], axis=1)
    if write:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        out.to_csv(MEASURES_FILE, index=False)
        paths_.to_csv(PATHS_FILE, index=False, float_format="%.10g")
        resid.to_csv(RESIDUALS_FILE, index=False, float_format="%.10g")
        paths3.to_csv(M3_PATHS_FILE, index=False, float_format="%.10g")
    return out, paths_, resid


def load_measures() -> pd.DataFrame:
    M = pd.read_csv(MEASURES_FILE, float_precision="round_trip")
    for c in ["auction_date", "settlement_date", "t_minus_1", "m1_curve_date", "m2_window_start", "m2_window_end"]:
        M[c] = [dt.date.fromisoformat(str(v)[:10]) for v in M[c]]
    return M


if __name__ == "__main__":
    M, Pth, Res = build(rebuild_cache="--rebuild" in os.sys.argv)
    pd.set_option("display.width", 200)
    print(M[["m1_bp", "m1b_bp", "beta", "m2_pre_bbeta_bp", "m2_day_bbeta_bp", "m2_post_bbeta_bp"]].describe().round(3))
