"""Stage 4b/5: market yields, M3, extended M1b, control C, inference, placebo and the analysis dataset.

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


# ---------------------------------------------------------------- placebo
def test_placebo_engine_reproduces_the_real_auctions_and_has_1000_draws():
    R = pd.read_csv(pl.OUT_DIR / "placebo_results.csv")
    assert (R["engine_check_max_abs"] < 1e-8).all()
    D = pd.read_csv(pl.OUT_DIR / "placebo_draws.csv.gz")
    assert D.groupby(["measure", "group"]).size().eq(pl.N_DRAWS).all()
