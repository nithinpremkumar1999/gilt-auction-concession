"""Stage 5: regimes, regressions and robustness (build spec §8, decisions #13-#17).

Dataset: one row per auction = auction panel + measures (M1, M1b, M2 B-beta/B, M3) + control C.

Regressors (spec §8; decision #15 main definitions; proposed details marked [P], listed at the gate)
  dv01          auction DV01 from the allotment excluding PAOF, £m per bp
  medium, long  bucket dummies (short is the base)
  cover_surprise  bid-to-cover minus the mean of the previous 5 auctions in the same bucket [P: 5]
  tail          tail (bp), with 4 Mar 2009 set missing (tail_bp_regression)
  new_issue     1 if the auction launched the gilt
  qt_week, qe_week   BoE QT sale / APF QE purchase within +-5 business days
  synd_week, tender_week   syndication / tender (incl. linker operations) within +-5 business days
                           [P: dummies rather than counts]
  vol           20-day realised volatility of the spot rate at the gilt's maturity (bp)
  QE, LDI, active_QT   regime dummies (pre-crisis is the base); post-QT-decision auctions (2) are
                       descriptive only and leave every regression
  long_x_post2022 (H4, open in the spec) long x (auction on or after 1 Nov 2022) [P: start of active
                  QT], run as an extra specification
Note: cover, tail and PAOF are auction outcomes. They are in the regressions because spec §8 lists
them; for the pre-auction window they are not known in advance.

Specifications
  M1b          1999-2017 (wherever M1b exists), no fixed effects
  M1 (FE)      2018 onwards with gilt fixed effects (decision #17); M1 levels are not concessions then
  M1 pooled    the M1b sample, no fixed effects (robustness: M1b vs M1, like for like)
  M2 pre/day/post (B-beta)   all years
  M3 pre/day/post            wherever M3 exists (reference prices, Nov 1998 - Jul 2017)
Standard errors: clustered by auction week; Newey-West in calendar time as a check (inference.py).
"""
import datetime as dt

import numpy as np
import pandas as pd

from . import auctions as au, measures as ms
from .inference import auction_week, days_since, mean_test, ols

OUT_DIR = ms.paths.PROCESSED / "stage5"
COVER_LOOKBACK = 5
POST2022 = dt.date(2022, 11, 1)
M1_FE_START = dt.date(2018, 1, 1)
REF_END = dt.date(2017, 7, 21)
REGIME_ORDER = ["pre-crisis", "QE", "LDI stress", "active QT", "post-QT-decision"]
BUCKETS = ["short", "medium", "long"]
WINDOWS = ["pre", "day", "post"]
REGRESSORS = ["dv01", "medium", "long", "cover_surprise", "tail", "new_issue", "qt_week", "qe_week",
              "synd_week", "tender_week", "vol", "QE", "LDI", "active_QT"]


def cover_surprise(P: pd.DataFrame, lookback: int = COVER_LOOKBACK) -> pd.Series:
    """Bid-to-cover minus the mean of the previous `lookback` auctions in the same bucket (strictly
    earlier dates; fewer if the history is shorter; missing for the first auction of a bucket)."""
    out = pd.Series(np.nan, index=P.index)
    for b, g in P.sort_values("auction_date").groupby("bucket"):
        prev = g["bid_to_cover"].shift(1).rolling(lookback, min_periods=1).mean()
        out.loc[g.index] = g["bid_to_cover"] - prev
    return out


def dataset() -> pd.DataFrame:
    """Auction-level analysis dataset."""
    P = au.load_auction_panel()
    P["auction_id"] = [f"{d}_{i}" for d, i in zip(P["auction_date"], P["isin"])]
    M = ms.load_measures()
    keep = [c for c in M.columns if c not in P.columns or c == "auction_id"]
    A = P.merge(M[keep], on="auction_id", how="left").copy()
    try:
        C = pd.read_csv(ms.OUT_DIR / "m2c.csv")
        A = A.merge(C[["auction_id", "ois_days", "ois_beyond_25y", "m2_pre_c_bp", "m2_day_c_bp", "m2_post_c_bp"]],
                    on="auction_id", how="left")
    except FileNotFoundError:
        pass
    new = {
        "dv01": A["dv01_gbp_per_bp_auction"] / 1e6,
        "dv01_total": A["dv01_gbp_per_bp_total"] / 1e6,
        "medium": (A["bucket"] == "medium").astype(int),
        "long": (A["bucket"] == "long").astype(int),
        "cover_surprise": cover_surprise(A),
        "tail": A["tail_bp_regression"],
        "qt_week": A["qt_sale_week"].astype(int),
        "qe_week": A["qe_purchase_week"].astype(int),
        "synd_week": (A["synd_n_pm5bd"] > 0).astype(int),
        "tender_week": (A["tender_n_pm5bd"] > 0).astype(int),
        "synd_conv_week": (A["synd_conv_n_pm5bd"] > 0).astype(int),
        "tender_conv_week": (A["tender_conv_n_pm5bd"] > 0).astype(int),
        "vol": A["vol_own_maturity_20d_bp"],
        "vol10": A["vol_10y_20d_bp"],
        "QE": (A["regime"] == "QE").astype(int),
        "LDI": (A["regime"] == "LDI stress").astype(int),
        "active_QT": (A["regime"] == "active QT").astype(int),
        "post2022": (A["auction_date"] >= POST2022).astype(int),
        "week": auction_week(A["auction_date"]),
        "days": days_since(A["auction_date"]),
        "in_regressions": A["regime"] != "post-QT-decision",
        "to_2017": A["auction_date"] <= REF_END,
    }
    A = pd.concat([A.drop(columns=[c for c in new if c in A.columns]), pd.DataFrame(new, index=A.index)], axis=1)
    A["new_issue"] = A["new_issue"].astype(int)
    A["long_x_post2022"] = A["long"] * A["post2022"]
    A["m1_bp_where_m1b"] = A["m1_bp"].where(A["m1b_bp"].notna())
    return A


# ============================================================================ means
def means_table(A: pd.DataFrame, cols: dict, by: str | None = None, order=None) -> pd.DataFrame:
    """Mean of each measure (overall or by group) with clustered and Newey-West SEs."""
    rows = []
    groups = [("all", A)] if by is None else [(g, A[A[by] == g]) for g in (order or sorted(A[by].unique()))]
    for gname, sub in groups:
        for label, col in cols.items():
            s = sub[[col, "week", "days"]].dropna()
            if len(s) < 3:
                continue
            r = mean_test(s[col], s["week"], s["days"], label="mean_bp")
            rows.append(dict(group=gname, measure=label, **r.to_dict()))
    return pd.DataFrame(rows)


def three_numbers(A: pd.DataFrame, prefix: str, suffix: str, by=None, order=None) -> pd.DataFrame:
    return means_table(A, {w: f"{prefix}_{w}_{suffix}" for w in WINDOWS}, by=by, order=order)


# ============================================================================ regressions
def _design(A, regressors, fe=None):
    X = A[regressors].astype(float).copy()
    X.insert(0, "const", 1.0)
    if fe is not None:
        D = pd.get_dummies(A[fe], prefix="fe", drop_first=True, dtype=float)
        X = pd.concat([X, D], axis=1)
    return X


def regress(A, y, regressors=REGRESSORS, fe=None) -> dict:
    d = A.dropna(subset=[y] + [r for r in regressors])
    X = _design(d, regressors, fe)
    r = ols(d[y], X, clusters=d["week"], days=d["days"], report=["const"] + list(regressors))
    r["y"] = y
    r["fe"] = fe
    return r


SPECS = {
    # name: (dependent variable, sample filter, fixed effect)
    "M1b (1999-2017)": ("m1b_bp", lambda A: A["in_regressions"], None),
    "M1, gilt FE (2018-2026)": ("m1_bp", lambda A: A["in_regressions"] & (A["auction_date"] >= M1_FE_START), "isin"),
    "M2 pre (B-β)": ("m2_pre_bbeta_bp", lambda A: A["in_regressions"], None),
    "M2 day (B-β)": ("m2_day_bbeta_bp", lambda A: A["in_regressions"], None),
    "M2 post (B-β)": ("m2_post_bbeta_bp", lambda A: A["in_regressions"], None),
    "M3 pre": ("m3_pre_bp", lambda A: A["in_regressions"], None),
    "M3 day": ("m3_day_bp", lambda A: A["in_regressions"], None),
    "M3 post": ("m3_post_bp", lambda A: A["in_regressions"], None),
    "M1 pooled, M1b sample": ("m1_bp_where_m1b", lambda A: A["in_regressions"], None),
}


REGIMES_DUMMIES = ["QE", "LDI", "active_QT"]


def usable_regressors(sub: pd.DataFrame, y: str, regressors) -> list:
    """Drop regressors with no variation in the estimation sample, and one regime dummy when the
    base regime (pre-crisis) is absent (e.g. 2018-2026, where QE becomes the base)."""
    d = sub.dropna(subset=[y])
    regs = [r for r in regressors if d[r].std() > 0]
    reg_d = [r for r in REGIMES_DUMMIES if r in regs]
    if reg_d and (d[reg_d].sum(axis=1) == 1).all():
        regs.remove(reg_d[0])
    return regs


def run_specs(A: pd.DataFrame, regressors=REGRESSORS, specs=SPECS) -> dict:
    out = {}
    for name, (y, filt, fe) in specs.items():
        sub = A[filt(A)]
        out[name] = regress(sub, y, usable_regressors(sub, y, regressors), fe)
    return out


H4_SPECS = {k: v for k, v in SPECS.items() if k.startswith(("M1, gilt FE", "M2"))}


# ============================================================================ headline means
MEASURE_SETS = {  # label: (column prefix, suffix, sample filter)
    "M2 (B-β), all years": ("m2", "bbeta_bp", lambda A: A.index == A.index),
    "M3, 1999-2017": ("m3", "bp", lambda A: A.index == A.index),
}


def headline(A: pd.DataFrame) -> dict:
    """The PM's three numbers by bucket and by regime, plus M1b/M1 levels to 2017."""
    out = {}
    for label, (pre, suf, filt) in MEASURE_SETS.items():
        sub = A[filt(A)]
        out[(label, "all")] = three_numbers(sub, pre, suf)
        out[(label, "bucket")] = three_numbers(sub, pre, suf, by="bucket", order=BUCKETS)
        out[(label, "regime")] = three_numbers(sub, pre, suf, by="regime", order=[r for r in REGIME_ORDER if r in set(sub["regime"])])
    lv = A
    out[("Levels to 2017", "bucket")] = means_table(lv, {"M1b": "m1b_bp", "M1 (same auctions)": "m1_bp_where_m1b"},
                                                     by="bucket", order=BUCKETS)
    out[("Levels to 2017", "all")] = means_table(lv, {"M1b": "m1b_bp", "M1 (same auctions)": "m1_bp_where_m1b"})
    return out


def flat(tables: dict) -> pd.DataFrame:
    rows = []
    for (label, by), t in tables.items():
        rows.append(t.assign(set=label, by=by))
    return pd.concat(rows, ignore_index=True)[["set", "by", "group", "measure", "n", "mean_bp", "se_cluster",
                                               "p_cluster", "se_nw", "p_nw", "clusters"]]


# ============================================================================ robustness
def m1b_variant(A: pd.DataFrame, exclude_bdays: int, min_days: int) -> pd.Series:
    """M1b recomputed from the stored daily residuals under another exclusion rule."""
    R = pd.read_csv(ms.RESIDUALS_FILE)
    R["date"] = pd.to_datetime(R["date"]).dt.date
    from .curve import load_panel
    pos = {d: i for i, d in enumerate(load_panel().index.date)}
    by_isin = A.groupby("isin")["auction_date"].apply(sorted).to_dict()
    R["isin"] = R["auction_id"].str.split("_").str[1]
    R["T"] = pd.to_datetime(R["auction_id"].str.split("_").str[0]).dt.date
    R["dist"] = [min([abs(pos[d] - pos[x]) for x in by_isin[i] if x < t] or [999])
                 for d, i, t in zip(R["date"], R["isin"], R["T"])]
    other = R["excluded"].notna() & ~R["excluded"].fillna("").str.startswith("within 5")
    ok = R["residual_bp"].notna() & ~other & (R["dist"] > exclude_bdays)
    b = R[ok].groupby("auction_id")["residual_bp"].agg(["mean", "size"])
    b = b[b["size"] >= min_days]["mean"]
    m1 = A.set_index("auction_id")["m1_bp"]
    return (m1 - b).reindex(A["auction_id"]).set_axis(A.index)


ROBUST_SAMPLES = {
    "main": lambda A: A.index == A.index,
    "drop LDI window": lambda A: A["regime"] != "LDI stress",
    "drop Feb-Oct 2022 (passive QT)": lambda A: ~A["passive_qt_2022"].astype(bool),
    "drop > 5y beyond the curve": lambda A: ~A["drop_extrapolation_robustness"].astype(bool),
}


def robustness_means(A: pd.DataFrame) -> pd.DataFrame:
    """Means of the three numbers (overall and by bucket) under each robustness variant."""
    rows = []
    def add(label, sub, pre, suf):
        for by, order in [(None, None), ("bucket", BUCKETS)]:
            t = three_numbers(sub, pre, suf, by=by, order=order)
            rows.append(t.assign(variant=label))
    for label, f in ROBUST_SAMPLES.items():
        add(f"M2 B-β: {label}", A[f(A)], "m2", "bbeta_bp")
    add("M2 control B (β = 1)", A, "m2", "b_bp")
    c = A[A["m2_day_c_bp"].notna()]
    add("M2 B-β on the control-C sample (Dec 2021+)", c, "m2", "bbeta_bp")
    add("M2 control C (gilt - OIS, Dec 2021+)", c, "m2", "c_bp")
    add("M3: main", A, "m3", "bp")
    add("M3: drop > 5y beyond the curve", A[~A["drop_extrapolation_robustness"].astype(bool)], "m3", "bp")
    # M1b under looser exclusion rules (decision #16 keeps the strict rule as main)
    for (ex, md) in [(5, 10), (5, 5), (0, 5)]:
        B = A.assign(m1b_var=m1b_variant(A, ex, md))
        for by, order in [(None, None), ("bucket", BUCKETS)]:
            t = means_table(B, {"level": "m1b_var"}, by=by, order=order)
            rows.append(t.assign(variant=f"M1b: exclude ±{ex} days, min {md} days" + (" (main)" if (ex, md) == (5, 10) else "")))
    return pd.concat(rows, ignore_index=True)


ROBUST_REGRESSIONS = {
    # label: (replacement map for regressors, sample filter)
    "main": ({}, lambda A: A.index == A.index),
    "DV01 incl. PAOF": ({"dv01": "dv01_total"}, lambda A: A.index == A.index),
    "volatility at 10y": ({"vol": "vol10"}, lambda A: A.index == A.index),
    "conventional-only syndications/tenders": ({"synd_week": "synd_conv_week", "tender_week": "tender_conv_week"},
                                               lambda A: A.index == A.index),
    "drop LDI window": ({}, lambda A: A["regime"] != "LDI stress"),
    "drop Feb-Oct 2022": ({}, lambda A: ~A["passive_qt_2022"].astype(bool)),
    "drop > 5y beyond the curve": ({}, lambda A: ~A["drop_extrapolation_robustness"].astype(bool)),
}


def robustness_regressions(A: pd.DataFrame, specs=SPECS) -> pd.DataFrame:
    rows = []
    for label, (repl, f) in ROBUST_REGRESSIONS.items():
        regs = [repl.get(r, r) for r in REGRESSORS]
        B = A[f(A)]
        for name, (y, filt, fe) in specs.items():
            sub = B[filt(B)]
            r = regress(sub, y, usable_regressors(sub, y, regs), fe)
            t = r["table"].reset_index(names="variable")
            t["variable"] = t["variable"].map({v: k for k, v in repl.items()}).fillna(t["variable"])
            rows.append(t.assign(variant=label, spec=name, n=r["n"]))
    return pd.concat(rows, ignore_index=True)


def coef_table(results: dict, stat="coef", star=True) -> pd.DataFrame:
    """Side-by-side table: coefficient with stars from the clustered p-value; SE in brackets."""
    cols = {}
    for name, r in results.items():
        t = r["table"]
        col = {}
        for v in t.index:
            c, se, p = t.at[v, "coef"], t.at[v, "se_cluster"], t.at[v, "p_cluster"]
            s = "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < 0.10 else ""
            col[v] = f"{c:+.3f}{s if star else ''} ({se:.3f})"
        col["N"] = str(r["n"])
        col["clusters (weeks)"] = str(r.get("clusters"))
        col["R²"] = f"{r['r2']:.3f}"
        col["fixed effects"] = "gilt" if r["fe"] else "-"
        cols[name] = col
    order = ["const"] + REGRESSORS + ["long_x_post2022", "N", "clusters (weeks)", "R²", "fixed effects"]
    T = pd.DataFrame(cols)
    return T.loc[[o for o in order if o in T.index]].fillna("")


def long_table(results: dict) -> pd.DataFrame:
    rows = []
    for name, r in results.items():
        t = r["table"].copy()
        t["spec"] = name
        t["n"] = r["n"]
        t["r2"] = r["r2"]
        rows.append(t.reset_index(names="variable"))
    return pd.concat(rows, ignore_index=True)


# ============================================================================ outputs
def main(write: bool = True) -> dict:
    """All Stage 5 tables; written to data/processed_data/stage5/ (CSV)."""
    A = dataset()
    R = run_specs(A)
    H = run_specs(A, REGRESSORS + ["long_x_post2022"], H4_SPECS)
    out = dict(
        headline=flat(headline(A)),
        regressions=long_table(R),
        regressions_wide=coef_table(R),
        h4=long_table(H),
        h4_wide=coef_table(H),
        robust_means=robustness_means(A),
        robust_regressions=robustness_regressions(A),
        dataset=A,
    )
    if write:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        for k, v in out.items():
            if k == "dataset":
                cols = ["auction_id", "auction_date", "gilt_name", "isin", "bucket", "regime", "passive_qt_2022",
                        "m1_bp", "m1b_bp", "m2_pre_bbeta_bp", "m2_day_bbeta_bp", "m2_post_bbeta_bp",
                        "m2_pre_b_bp", "m2_day_b_bp", "m2_post_b_bp", "m2_pre_c_bp", "m2_day_c_bp", "m2_post_c_bp",
                        "m3_pre_bp", "m3_day_bp", "m3_post_bp"] + REGRESSORS + ["long_x_post2022", "dv01_total",
                        "vol10", "synd_conv_week", "tender_conv_week", "week", "in_regressions"]
                v[cols].to_csv(OUT_DIR / "analysis_dataset.csv", index=False)
            else:
                v.to_csv(OUT_DIR / f"{k}.csv", index=k.endswith("_wide"))
    return out


if __name__ == "__main__":
    o = main()
    pd.set_option("display.width", 250)
    print(o["regressions_wide"].to_string())
