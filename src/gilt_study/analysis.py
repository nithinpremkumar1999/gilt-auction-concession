"""Stage 5: regimes, regressions and robustness (build spec §8, decisions #13-#20).

Dataset: one row per auction = auction panel + measures (M1, M1b, M2 B-beta/B, M3) + control C.

Regressors (spec §8; decisions #15, #18)
  dv01          auction DV01 from the allotment excluding PAOF, £m per bp, priced at the T-1 model
                yield for the auction settlement date (chart gate, 21 Oct 2026: strictly ex-ante;
                Stage 3's DV01 was priced at the AAY, an auction outcome, kept as dv01_aay)
  vol           20-day realised volatility to T-1 of the spot rate at the gilt's maturity (bp)
  medium, long  bucket dummies (short is the base)
  new_issue     1 if the auction launched the gilt
  synd_week, tender_week   syndication / tender (incl. linker operations) within +-5 business days,
                           as dummies (counts as robustness, decision #18)
  qt_week, qe_week   BoE QT sale / APF QE purchase within +-5 business days
  QE, LDI, active_QT   regime dummies (pre-crisis is the base); post-QT-decision auctions (2) are
                       descriptive only and leave every regression. The LDI dummy (3 auctions in 2
                       weeks) is reported, not interpreted (decision #20)
  cover_surprise  bid-to-cover minus the mean of the previous 5 auctions in the same bucket
                  (10 as robustness, decision #18)
  tail          tail (bp), with 4 Mar 2009 set missing (tail_bp_regression)
  long_x_post2022 (H4) long x (auction on or after 1 Nov 2022, decision #18), an extra specification

Two specifications (decision #19)
  ex-ante          variables known before bidding: dv01, vol, buckets, new issue, supply and QE/QT
                   weeks, regime. For the PM's prediction; every dependent variable.
  auction-outcome  ex-ante + cover surprise + tail, for explanation. Cover and tail are realised at
                   the auction, so they never enter the pre-window regressions (M2 pre, M3 pre).

Dependent variables
  M1b          1999-2017 (wherever M1b exists), no fixed effects
  M1 (FE)      2018 onwards with gilt fixed effects (decision #17); M1 levels are not concessions then
  M1 pooled    the M1b sample, no fixed effects (robustness: M1b vs M1, like for like)
  M2 pre/day/post (B-beta)   all years
  M3 pre/day/post            wherever M3 exists (reference prices, Nov 1998 - Jul 2017)
Inference (decision #20): the three numbers lead with the placebo-centred p-value (placebo.py),
with standard errors clustered by auction week alongside; regressions use the clustered SEs, with
Newey-West in calendar time as a check (inference.py).
"""
import datetime as dt

import numpy as np
import pandas as pd

from . import auctions as au, measures as ms
from .inference import auction_week, days_since, mean_test, ols
from .pricing import gilt_price

OUT_DIR = ms.paths.PROCESSED / "stage5"
COVER_LOOKBACK = 5
COVER_LOOKBACK_ROBUST = 10
POST2022 = dt.date(2022, 11, 1)
M1_FE_START = dt.date(2018, 1, 1)
REF_END = dt.date(2017, 7, 21)
REGIME_ORDER = ["pre-crisis", "QE", "LDI stress", "active QT", "post-QT-decision"]
BUCKETS = ["short", "medium", "long"]
WINDOWS = ["pre", "day", "post"]
EX_ANTE = ["dv01", "vol", "medium", "long", "new_issue", "synd_week", "tender_week", "qt_week", "qe_week",
           "QE", "LDI", "active_QT"]
OUTCOME_VARS = ["cover_surprise", "tail"]
AUCTION_OUTCOME = EX_ANTE + OUTCOME_VARS
REGRESSORS = AUCTION_OUTCOME                  # every main regressor (dataset export, tables)
SPECIFICATIONS = {"ex-ante": EX_ANTE, "auction-outcome": AUCTION_OUTCOME}
LDI_NOTE = "reported, not interpreted (3 auctions in 2 weeks)"


def cover_surprise(P: pd.DataFrame, lookback: int = COVER_LOOKBACK) -> pd.Series:
    """Bid-to-cover minus the mean of the previous `lookback` auctions in the same bucket (strictly
    earlier dates; fewer if the history is shorter; missing for the first auction of a bucket)."""
    out = pd.Series(np.nan, index=P.index)
    for b, g in P.sort_values("auction_date").groupby("bucket"):
        prev = g["bid_to_cover"].shift(1).rolling(lookback, min_periods=1).mean()
        out.loc[g.index] = g["bid_to_cover"] - prev
    return out


def dv01_per_100_t1(A: pd.DataFrame) -> np.ndarray:
    """DV01 per £100 nominal at the T-1 model yield (the yield M1 is measured against), for the
    auction's settlement date: known before bidding."""
    dd = lambda v: v if isinstance(v, dt.date) else None
    return np.array([gilt_price(s, m, c, y / 100.0, dd(fi), dd(fc))["dv01"] for s, m, c, y, fi, fc in
                     zip(A["settlement_date"], A["maturity"], A["coupon"], A["model_yield_t1"], A["first_issue"],
                         A["first_coupon"])])


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
    dv01_t1 = dv01_per_100_t1(A)
    new = {
        "dv01": dv01_t1 * A["nominal_auction"] / 100.0,            # £m per bp (nominal in £m)
        "dv01_total": dv01_t1 * A["nominal_total"] / 100.0,
        "dv01_aay": A["dv01_gbp_per_bp_auction"] / 1e6,
        "dv01_total_aay": A["dv01_gbp_per_bp_total"] / 1e6,
        "medium": (A["bucket"] == "medium").astype(int),
        "long": (A["bucket"] == "long").astype(int),
        "cover_surprise": cover_surprise(A),
        "cover_surprise10": cover_surprise(A, COVER_LOOKBACK_ROBUST),
        "tail": A["tail_bp_regression"],
        "qt_week": A["qt_sale_week"].astype(int),
        "qe_week": A["qe_purchase_week"].astype(int),
        "synd_week": (A["synd_n_pm5bd"] > 0).astype(int),
        "tender_week": (A["tender_n_pm5bd"] > 0).astype(int),
        "synd_conv_week": (A["synd_conv_n_pm5bd"] > 0).astype(int),
        "tender_conv_week": (A["tender_conv_n_pm5bd"] > 0).astype(int),
        "synd_n": A["synd_n_pm5bd"].astype(int),
        "tender_n": A["tender_n_pm5bd"].astype(int),
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
PRE_WINDOW_SPECS = {"M2 pre (B-β)", "M3 pre"}     # cover and tail never enter these (decision #19)


def specs_for(specification: str, specs: dict = SPECS) -> dict:
    """The dependent variables run under a specification (no pre windows for auction-outcome)."""
    return {k: v for k, v in specs.items() if not (specification == "auction-outcome" and k in PRE_WINDOW_SPECS)}


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


def run_specs(A: pd.DataFrame, specification: str = "ex-ante", extra=(), specs: dict = SPECS,
              replace: dict | None = None) -> dict:
    """Regressions of every dependent variable allowed under `specification`. `replace` swaps
    regressors for robustness variants (e.g. dv01 -> dv01_total)."""
    regs = [(replace or {}).get(r, r) for r in SPECIFICATIONS[specification]] + list(extra)
    out = {}
    for name, (y, filt, fe) in specs_for(specification, specs).items():
        sub = A[filt(A)]
        out[name] = regress(sub, y, usable_regressors(sub, y, regs), fe)
        out[name]["specification"] = specification
    return out


H4_SPECS = {k: v for k, v in SPECS.items() if k.startswith(("M1, gilt FE", "M2"))}


# ============================================================================ headline means
MEASURE_SETS = {  # label: (column prefix, suffix, sample filter, placebo measure name)
    "M2 (B-β), all years": ("m2", "bbeta_bp", lambda A: A.index == A.index, "M2 (B-β)"),
    "M3, 1999-2017": ("m3", "bp", lambda A: A.index == A.index, "M3"),
}


# Chart gate, 21 Oct 2026, added after seeing chart 1 (measures.M2_EXTRA_WINDOWS / M3_EXTRA_WINDOWS)
EXTRA_WINDOWS = {"M2 (B-β), all years": list(ms.M2_EXTRA_WINDOWS), "M3, 1999-2017": list(ms.M3_EXTRA_WINDOWS)}
WINDOW_NOTES = {"pre10": "robustness pre-auction window T-10 -> T-1, added after seeing chart 1 (21 Oct 2026)",
                "total": "M3 total move T-10 -> T+1, added after seeing chart 1 (21 Oct 2026)"}
SAME_REGIME_NOTE = "robustness: placebo dates in the auction's own regime, added after seeing results (21 Oct 2026)"


def headline(A: pd.DataFrame) -> dict:
    """The PM's three numbers by bucket and by regime, plus M1b/M1 levels to 2017."""
    out = {}
    for label, (pre, suf, filt, _) in MEASURE_SETS.items():
        sub = A[filt(A)]
        out[(label, "all")] = three_numbers(sub, pre, suf)
        out[(label, "bucket")] = three_numbers(sub, pre, suf, by="bucket", order=BUCKETS)
        out[(label, "regime")] = three_numbers(sub, pre, suf, by="regime", order=[r for r in REGIME_ORDER if r in set(sub["regime"])])
        cols = {w: f"{pre}_{w}_{suf}" for w in EXTRA_WINDOWS[label]}
        out[(label, "all")] = pd.concat([out[(label, "all")], means_table(sub, cols)], ignore_index=True)
        out[(label, "bucket")] = pd.concat([out[(label, "bucket")], means_table(sub, cols, by="bucket", order=BUCKETS)],
                                           ignore_index=True)
        out[(label, "regime")] = pd.concat([out[(label, "regime")], means_table(
            sub, cols, by="regime", order=[r for r in REGIME_ORDER if r in set(sub["regime"])])], ignore_index=True)
    lv = A
    out[("Levels to 2017", "bucket")] = means_table(lv, {"M1b": "m1b_bp", "M1 (same auctions)": "m1_bp_where_m1b"},
                                                     by="bucket", order=BUCKETS)
    out[("Levels to 2017", "regime")] = means_table(lv, {"M1b": "m1b_bp", "M1 (same auctions)": "m1_bp_where_m1b"},
                                                     by="regime", order=REGIME_ORDER)
    out[("Levels to 2017", "all")] = means_table(lv, {"M1b": "m1b_bp", "M1 (same auctions)": "m1_bp_where_m1b"})
    return out


def flat(tables: dict) -> pd.DataFrame:
    rows = []
    for (label, by), t in tables.items():
        rows.append(t.assign(set=label, by=by))
    return pd.concat(rows, ignore_index=True)[["set", "by", "group", "measure", "n", "mean_bp", "se_cluster",
                                               "p_cluster", "se_nw", "p_nw", "clusters"]]


def add_placebo(H: pd.DataFrame) -> pd.DataFrame:
    """Attach the placebo-centred p-values (decision #20) to the headline means.

    p_placebo / placebo_mean_bp / n_placebo: main design (decision #18), events grouped by the real
    auction's bucket or regime. p_placebo_same_regime: the robustness design (placebo dates in the
    auction's own regime; added after seeing results), on every row. lead_p is the p-value the report
    leads with: the placebo p where a placebo exists (M2, M3), else the clustered p (M1b, M1 levels)."""
    from . import placebo as pl
    try:
        R = pd.read_csv(pl.OUT_DIR / "placebo_results.csv")
    except FileNotFoundError:
        R = None
    H = H.copy()
    for c in ["p_placebo", "placebo_mean_bp", "n_placebo", "p_placebo_same_regime"]:
        H[c] = np.nan
    if R is not None and "design" in R.columns:
        name = {label: v[3] for label, v in MEASURE_SETS.items()}
        for i, r in H.iterrows():
            if r["set"] not in name:
                continue
            m = R[(R["measure"] == name[r["set"]]) & (R["group"] == r["group"]) & (R["window"] == r["measure"])]
            main = m[m["design"] == "main"]
            if len(main):
                H.loc[i, ["p_placebo", "placebo_mean_bp", "n_placebo"]] = main.iloc[0][["p_value", "placebo_mean_bp", "n_events"]].to_numpy()
            alt = m[m["design"] == "same regime"]
            if len(alt):
                H.loc[i, "p_placebo_same_regime"] = alt.iloc[0]["p_value"]
    H["lead_p"] = H["p_placebo"].fillna(H["p_cluster"])
    H["lead_p_source"] = np.where(H["p_placebo"].notna(), "placebo-centred", "clustered")
    H["note"] = np.where(H["group"] == "LDI stress", LDI_NOTE, "")
    H["window_note"] = H["measure"].map(WINDOW_NOTES).fillna("")
    H["p_placebo_same_regime_note"] = np.where(H["p_placebo_same_regime"].notna(), SAME_REGIME_NOTE, "")
    return H


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
    "supply counts (not dummies)": ({"synd_week": "synd_n", "tender_week": "tender_n"}, lambda A: A.index == A.index),
    "cover surprise vs previous 10": ({"cover_surprise": "cover_surprise10"}, lambda A: A.index == A.index),
    "drop LDI window": ({}, lambda A: A["regime"] != "LDI stress"),
    "drop Feb-Oct 2022": ({}, lambda A: ~A["passive_qt_2022"].astype(bool)),
    "drop > 5y beyond the curve": ({}, lambda A: ~A["drop_extrapolation_robustness"].astype(bool)),
}


def robustness_regressions(A: pd.DataFrame, specs=SPECS) -> pd.DataFrame:
    """Every robustness variant under both specifications (variants that only touch cover or tail
    run under auction-outcome only)."""
    rows = []
    for specification in SPECIFICATIONS:
        for label, (repl, f) in ROBUST_REGRESSIONS.items():
            if specification == "ex-ante" and repl and all(k in OUTCOME_VARS for k in repl):
                continue
            R = run_specs(A[f(A)], specification, specs=specs, replace=repl)
            for name, r in R.items():
                t = r["table"].reset_index(names="variable")
                t["variable"] = t["variable"].map({v: k for k, v in repl.items()}).fillna(t["variable"])
                rows.append(t.assign(variant=label, specification=specification, spec=name, n=r["n"]))
    return pd.concat(rows, ignore_index=True)


LABELS = {"LDI": "LDI: " + LDI_NOTE}


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
    T = T.loc[[o for o in order if o in T.index]].fillna("")
    return T.rename(index=LABELS)


def long_table(results: dict) -> pd.DataFrame:
    rows = []
    for name, r in results.items():
        t = r["table"].copy()
        t["specification"] = r.get("specification")
        t["spec"] = name
        t["n"] = r["n"]
        t["r2"] = r["r2"]
        t["clusters"] = r.get("clusters")
        rows.append(t.reset_index(names="variable"))
    return pd.concat(rows, ignore_index=True)


# ============================================================================ outputs
def main(write: bool = True) -> dict:
    """All Stage 5 tables; written to data/processed_data/stage5/ (CSV)."""
    A = dataset()
    R = {s: run_specs(A, s) for s in SPECIFICATIONS}
    H = {s: run_specs(A, s, ["long_x_post2022"], H4_SPECS) for s in SPECIFICATIONS}
    out = dict(
        headline=add_placebo(flat(headline(A))),
        regressions=pd.concat([long_table(R[s]) for s in SPECIFICATIONS], ignore_index=True),
        regressions_ex_ante=coef_table(R["ex-ante"]),
        regressions_outcome=coef_table(R["auction-outcome"]),
        h4=pd.concat([long_table(H[s]) for s in SPECIFICATIONS], ignore_index=True),
        h4_wide=pd.concat({s: coef_table(H[s]) for s in SPECIFICATIONS}, axis=1)
                  .reindex(coef_table(H["auction-outcome"]).index).fillna(""),
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
                        "vol10", "synd_conv_week", "tender_conv_week", "synd_n", "tender_n", "cover_surprise10",
                        "dv01_aay", "dv01_total_aay", "m2_pre10_bbeta_bp", "m3_pre10_bp", "m3_total_bp",
                        "week", "in_regressions"]
                v[cols].to_csv(OUT_DIR / "analysis_dataset.csv", index=False)
            else:
                v.to_csv(OUT_DIR / f"{k}.csv", index=k.startswith(("regressions_", "h4_wide")))
    return out


if __name__ == "__main__":
    o = main()
    pd.set_option("display.width", 250)
    print(o["regressions_ex_ante"].to_string())
    print(o["regressions_outcome"].to_string())
