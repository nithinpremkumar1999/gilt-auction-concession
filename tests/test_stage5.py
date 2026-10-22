"""Stage 4b/5/6: market yields, M3, extended M1b, control C, inference, specifications (#19), placebo
(#18, #20), and the data behind the report charts.

Run:  pytest tests/test_stage5.py   (reads the built outputs; see the README for the build commands)
"""
import datetime as dt

import numpy as np
import pandas as pd
import pytest

from gilt_study import analysis as an, inference as inf, measures as ms, ois, placebo as pl


# ---------------------------------------------------------------- inference vs statsmodels
def test_cluster_and_newey_west_match_statsmodels():
    """Reference values from statsmodels 0.15.0 (cluster CR1; HAC maxlags=4 with correction) on the
    same simulated data; the calendar-time kernel with d_i = i is the textbook Newey-West."""
    rng = np.random.default_rng(7)
    n = 200
    X = pd.DataFrame({"const": 1.0, "x1": rng.normal(size=n), "x2": rng.normal(size=n)})
    g = rng.integers(0, 40, size=n)
    y = 0.5 + 1.2 * X.x1 - 0.7 * X.x2 + rng.normal(size=n) + 0.8 * rng.normal(size=40)[g]
    t = inf.ols(y, X, clusters=g, days=np.arange(n), hac_bandwidth=4)["table"]
    assert np.allclose(t["coef"], [0.438280786731, 1.188583925472, -0.740086584765], atol=1e-10)
    assert np.allclose(t["se_cluster"], [0.167545733915, 0.070173381104, 0.074346164569], atol=1e-10)
    assert np.allclose(t["se_nw"], [0.093288440661, 0.097229898722, 0.090763250346], atol=1e-10)


def test_auction_week_clusters():
    w = inf.auction_week([dt.date(2020, 1, 6), dt.date(2020, 1, 10), dt.date(2020, 1, 13)])
    assert w[0] == w[1] != w[2]


# ---------------------------------------------------------------- market yields, M1b, M3
@pytest.fixture(scope="module")
def M():
    return ms.load_measures()


def test_market_yields_sources():
    """DMO yields where published; yields from the DMO clean price only before 25 Nov 2002."""
    MY = ms.load_market_yields()
    fc = MY[MY["yield_source"] == ms.SRC_FROM_CLEAN]
    assert len(fc) > 4000 and fc["date"].max() < dt.date(2002, 11, 25)
    assert MY["date"].min() >= dt.date(1998, 11, 1) and MY["date"].max() <= dt.date(2017, 7, 21)


def test_m1b_extended_to_1999(M):
    """Decision #17: M1b now also covers 1999-2002 (319 auctions, from 309)."""
    has = M["m1b_bp"].notna()
    assert int(has.sum()) == 319
    assert M.loc[has, "auction_date"].min() == dt.date(1999, 5, 26)


def test_m3_three_numbers_are_residual_changes(M):
    P = pd.read_csv(ms.M3_PATHS_FILE)
    w = P.pivot(index="auction_id", columns="k", values="residual_bp")
    m = M.set_index("auction_id")
    for name, (a, b) in ms.PM_NUMBERS.items():
        got = m[f"m3_{name}_bp"]
        want = (w[b] - w[a]).reindex(m.index)
        assert np.allclose(got.dropna(), want[got.notna()])
        assert got.isna().equals(want.isna())
    assert (pd.to_datetime(M.loc[M["m3_day_bp"].notna(), "auction_date"]) <= "2017-07-21").all()


# ---------------------------------------------------------------- control C
def test_control_c_sample_and_missing_rule():
    C = pd.read_csv(ois.M2C_FILE)
    assert (pd.to_datetime(C["auction_date"]) >= pd.Timestamp(ois.C_START)).all()
    late = C[C["auction_id"].str.startswith("2026-09-29")]
    assert late["m2_post_c_bp"].isna().all() and late["m2_day_c_bp"].notna().all()   # OIS ends 30 Sep 2026


# ---------------------------------------------------------------- analysis dataset
def test_cover_surprise_uses_only_earlier_auctions():
    A = an.dataset()
    s = A.sort_values("auction_date")
    for b in an.BUCKETS:
        g = s[s["bucket"] == b]
        i = 10
        want = g["bid_to_cover"].iloc[i] - g["bid_to_cover"].iloc[i - 5:i].mean()
        assert abs(g["cover_surprise"].iloc[i] - want) < 1e-12
        assert np.isnan(g["cover_surprise"].iloc[0])


def test_regime_base_is_dropped_when_absent():
    """In the 2018-2026 fixed-effects sample (post-QT-decision auctions excluded) every auction is in
    QE, LDI or active QT, so the first of those dummies is dropped and QE becomes the base."""
    A = an.dataset()
    y, filt, _ = an.SPECS["M1, gilt FE (2018-2026)"]
    sub = A[filt(A)]
    regs = an.usable_regressors(sub, y, an.REGRESSORS)
    assert "QE" not in regs and "LDI" in regs and "active_QT" in regs


# ---------------------------------------------------------------- specifications (decision #19)
def test_ex_ante_and_outcome_specifications():
    """Cover and tail are never in the ex-ante specification nor in any pre-window regression."""
    assert not set(an.OUTCOME_VARS) & set(an.EX_ANTE)
    assert set(an.specs_for("auction-outcome")) == set(an.SPECS) - an.PRE_WINDOW_SPECS
    R = pd.read_csv(an.OUT_DIR / "regressions.csv")
    pre = R["spec"].isin(an.PRE_WINDOW_SPECS) | (R["specification"] == "ex-ante")
    assert not R.loc[pre, "variable"].isin(an.OUTCOME_VARS).any()
    out = R[R["specification"] == "auction-outcome"]
    assert set(out["spec"]) == set(an.SPECS) - an.PRE_WINDOW_SPECS
    assert out["variable"].isin(an.OUTCOME_VARS).any()
    RR = pd.read_csv(an.OUT_DIR / "robust_regressions.csv")
    assert not RR.loc[RR["spec"].isin(an.PRE_WINDOW_SPECS), "variable"].isin(an.OUTCOME_VARS).any()
    assert {"supply counts (not dummies)", "cover surprise vs previous 10"} <= set(RR["variant"])


def test_headline_leads_with_the_placebo_p():
    """Decision #20: M2/M3 rows carry the placebo-centred p as lead_p; M1b rows the clustered p."""
    H = pd.read_csv(an.OUT_DIR / "headline.csv")
    m = H["set"].isin(an.MEASURE_SETS) & H["group"].isin(["all", "short", "medium", "long", "pre-crisis", "QE", "active QT"])
    assert H.loc[m, "p_placebo"].notna().all()
    assert np.allclose(H.loc[m, "lead_p"], H.loc[m, "p_placebo"])
    lv = H["set"] == "Levels to 2017"
    assert (H.loc[lv, "lead_p_source"] == "clustered").all() and np.allclose(H.loc[lv, "lead_p"], H.loc[lv, "p_cluster"])
    assert (H.loc[H["group"] == "LDI stress", "note"] == an.LDI_NOTE).all()


# ---------------------------------------------------------------- placebo
def test_placebo_engine_reproduces_the_real_auctions_and_has_1000_draws():
    R = pd.read_csv(pl.OUT_DIR / "placebo_results.csv")
    assert set(R["design"]) == set(pl.DESIGNS)
    assert (R["engine_check_max_abs"] < 1e-8).all()
    D = pd.read_csv(pl.OUT_DIR / "placebo_draws.csv.gz")
    assert D.groupby(["design", "measure", "group", "window"]).size().eq(pl.N_DRAWS).all()
    # M3: each window on its own sample (the headline's), less the auctions without a placebo date
    M = ms.load_measures()
    main = R[(R["design"] == "main") & (R["measure"] == "M3") & (R["group"] == "all")].set_index("window")
    for w in pl.WINDOWS:
        assert main.at[w, "n_events"] + main.at[w, "no_placebo_date"] == M[f"m3_{w}_bp"].notna().sum()


def test_placebo_paths():
    P = pd.read_csv(pl.OUT_DIR / "placebo_paths.csv.gz")
    assert P.groupby(["measure", "k"]).size().eq(pl.N_DRAWS).all() and P["k"].nunique() == 21
    assert (P.groupby("measure")["engine_check"].max() < 1e-8).all()
    assert np.allclose(P.loc[P["k"] == -6, "mean_bp"], 0)


# ---------------------------------------------------------------- report charts (Stage 6)
def test_report_chart_data():
    from gilt_study import report_charts as rc
    D = rc.path_data()
    assert np.allclose(D.loc[D["k"] == -6, ["mean", "se"]], 0)
    assert (D.loc[D["measure"] == "M2 (B-β)", "n"] == 912).all()
    B = rc.bucket_data()
    H = pd.read_csv(an.OUT_DIR / "headline.csv")
    a = B[(B["panel"] == "M2 (B-β)") & (B["group"] == "all auctions") & (B["window"] == "pre")].iloc[0]
    h = H[(H["set"] == "M2 (B-β), all years") & (H["group"] == "all") & (H["measure"] == "pre")].iloc[0]
    assert np.isclose(a["mean_bp"], h["mean_bp"]) and a["significant"] == (h["p_placebo"] < 0.05)
    assert "LDI stress" not in set(rc.regime_data()["group"])
    C = rc.coef_data()
    assert set(C["specification"]) == {"ex-ante"} and not C["variable"].isin(an.OUTCOME_VARS).any()


# ---------------------------------------------------------------- chart gate (21 Oct 2026)
def test_dv01_is_priced_at_the_t1_model_yield():
    """DV01 is known before bidding: priced at the T-1 model yield, not the AAY."""
    A = an.dataset()
    d = an.dv01_per_100_t1(A.iloc[:25])
    assert np.allclose(A["dv01"].iloc[:25], d * A["nominal_auction"].iloc[:25] / 100.0)
    assert not np.allclose(A["dv01"], A["dv01_aay"]) and np.corrcoef(A["dv01"], A["dv01_aay"])[0, 1] > 0.999


def test_extra_windows_are_path_differences(M):
    """pre10 = T-10 -> T-1 (M2 CAR, M3 residual); M3 total = T-10 -> T+1."""
    car = pd.read_csv(ms.OUT_DIR / "m2_paths.csv.gz").pivot(index="auction_id", columns="k", values="car_bbeta")
    r3 = pd.read_csv(ms.M3_PATHS_FILE).pivot(index="auction_id", columns="k", values="residual_bp")
    m = M.set_index("auction_id")
    assert np.allclose(m["m2_pre10_bbeta_bp"], (car[-1] - car[-10]).reindex(m.index))
    for col, (a, b) in [("m3_pre10_bp", (-10, -1)), ("m3_total_bp", (-10, 1))]:
        want = (r3[b] - r3[a]).reindex(m.index)
        assert m[col].isna().equals(want.isna()) and np.allclose(m[col].dropna(), want.dropna())


def test_robustness_rows_are_labelled():
    R = pd.read_csv(pl.OUT_DIR / "placebo_results.csv")
    assert {"pre10", "total"} <= set(R["window"])
    assert (R.loc[R["window"].isin(["pre10", "total"]), "window_note"] == pl.EXTRA_NOTE).all()
    assert (R.loc[R["design"] == "same regime", "design_note"] == pl.DESIGN_NOTES["same regime"]).all()
    H = pd.read_csv(an.OUT_DIR / "headline.csv")
    x = H[H["measure"].isin(["pre10", "total"])]
    assert set(x.loc[x["set"] == "M3, 1999-2017", "measure"]) == {"pre10", "total"}
    assert set(x.loc[x["set"] == "M2 (B-β), all years", "measure"]) == {"pre10"}
    assert x["window_note"].str.contains("added after seeing chart 1").all() and x["p_placebo"].notna().all()
    s = H[H["p_placebo_same_regime"].notna()]
    assert (s["p_placebo_same_regime_note"] == an.SAME_REGIME_NOTE).all() and set(s["by"]) == {"all", "bucket", "regime"}


def test_appendix_covers_every_charted_point():
    from gilt_study import report_charts as rc
    T = rc.appendix_table()
    B, G, C = rc.bucket_data(), rc.regime_data(), rc.coef_data()
    assert (T["chart"] == "2").sum() == len(B) and (T["chart"] == "3").sum() == len(G)
    assert (T["chart"] == "4").sum() == len(C)
    assert (T.loc[T["group"] == "LDI stress", "chart"] == "table only").all()
    means = T[T["section"] == "Means"]
    assert np.allclose(means["lead_p"], means["p_placebo"].fillna(means["p_clustered"]))
