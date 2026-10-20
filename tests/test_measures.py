"""Stage 4: M1, M1b and M2 (build spec §7).

Run:  pytest tests/test_measures.py   (reads data/processed_data/measures/; `python -m gilt_study.measures`
      builds them in about 10 minutes)
"""
import datetime as dt

import numpy as np
import pandas as pd
import pytest

from gilt_study import config, curve, measures as ms


# ---------------------------------------------------------------- the arithmetic (synthetic)
def test_cumulate_is_zero_at_the_base_and_sums_both_ways():
    ar = pd.Series(1.0, index=range(-10, 11))
    car = ms.cumulate(ar)
    assert car[-6] == 0
    assert car[-1] == 5 and car[0] == 6 and car[5] == 11      # days -5..k
    assert car[-10] == -4                                      # minus the changes of days -9..-6
    pre, day, post = car[-1] - car[-6], car[0] - car[-1], car[5] - car[0]
    assert (pre, day, post) == (5, 1, 5)


def test_ols_recovers_a_known_line():
    rng = np.random.default_rng(0)
    x = rng.normal(size=100)
    est = ms.ols(0.5 + 1.7 * x, x)
    assert abs(est["beta"] - 1.7) < 1e-12 and abs(est["alpha"] - 0.5) < 1e-12 and est["n"] == 100
    assert abs(est["r2"] - 1) < 1e-12


def test_control_maturities_exclude_three_years_either_side():
    grid = ms.CONTROL_GRID
    cm = ms.control_maturities(10.0, grid)
    assert 7.0 not in cm and 13.0 not in cm and 6.5 in cm and 13.5 in cm
    assert cm.min() == 2.0 and cm.max() == 30.0
    cm25 = ms.control_maturities(28.0, grid[grid <= 25.0])          # pre-2016 curve stops at 25y
    assert cm25.max() == 24.5 and 25.0 not in cm25


def test_event_days_are_curve_dates():
    cp = curve.load_panel()
    d = ms.event_days(cp.index, dt.date(2016, 3, 29), -2, 1)        # around Easter 2016
    assert [x.date() for x in d] == [dt.date(2016, 3, 23), dt.date(2016, 3, 24), dt.date(2016, 3, 29),
                                     dt.date(2016, 3, 30)]


# ---------------------------------------------------------------- the built measures
@pytest.fixture(scope="module")
def M():
    return ms.load_measures()


@pytest.fixture(scope="module")
def paths_():
    return pd.read_csv(ms.PATHS_FILE)


def test_m1_for_every_auction(M):
    assert len(M) == 912 and M["m1_bp"].notna().all()
    assert np.allclose(M["m1_bp"], 100 * (M["aay"] - M["model_yield_t1"]))
    assert not M["m1_curve_fallback"].any()
    assert (pd.to_datetime(M["m1_curve_date"]) == pd.to_datetime(M["t_minus_1"])).all()


def test_m1_settlement_choice_is_immaterial(M):
    """M1 prices for the auction settlement (T+1); pricing for the curve's own settlement (T) instead
    moves M1 by well under half a basis point."""
    assert (M["m1_bp"] - M["m1_alt_curve_settlement_bp"]).abs().max() < 0.5


def test_m1b_coverage_and_rules(M):
    """M1b only where the DMO yields exist, never for new issues, always on >= 10 valid days."""
    has = M["m1b_bp"].notna()
    assert not (has & M["new_issue"]).any()
    assert (M.loc[has, "m1b_days"] >= ms.M1B_MIN_DAYS).all()
    d = pd.to_datetime(M.loc[has, "auction_date"])
    assert d.min() > pd.Timestamp(config.PRICER_TEST_WINDOW[0]) and d.max() <= pd.Timestamp("2017-08-31")
    assert np.allclose(M.loc[has, "m1b_bp"], M.loc[has, "m1_bp"] - M.loc[has, "m1b_baseline_bp"])
    assert M.loc[~has, "m1b_missing_reason"].notna().all()


def test_m2_paths_are_consistent(M, paths_):
    """CAR is 0 at T-6 for every auction, steps by AR, and the PM numbers are CAR differences;
    beta always uses 100 daily changes."""
    assert (M["n_beta"] == 100).all()
    assert paths_.groupby("auction_id").size().eq(21).all()
    assert (paths_.loc[paths_["k"] == ms.M2_BASE, ["car_bbeta", "car_b", "car_raw"]] == 0).all().all()
    p = paths_.sort_values(["auction_id", "k"])
    step = p.groupby("auction_id")["car_bbeta"].diff()
    later = p["k"] > ms.M2_WINDOW[0]
    assert np.allclose(step[later], p.loc[later, "ar_bbeta"])
    w = p.pivot(index="auction_id", columns="k", values="car_bbeta")
    m = M.set_index("auction_id")
    assert np.allclose(m["m2_pre_bbeta_bp"], (w[-1] - w[-6]).reindex(m.index))
    assert np.allclose(m["m2_day_bbeta_bp"], (w[0] - w[-1]).reindex(m.index))
    assert np.allclose(m["m2_post_bbeta_bp"], (w[5] - w[0]).reindex(m.index))
    assert (M["beta_outlier"] == ((M["beta"] < 0) | (M["beta"] > 3))).all()


def test_ar_definitions(paths_, M):
    """AR B-beta = dy - beta*dc (no alpha); AR B = dy - dc."""
    p = paths_.merge(M[["auction_id", "beta"]], on="auction_id")
    assert np.allclose(p["ar_bbeta"], p["dy_bp"] - p["beta"] * p["dc_bp"])
    assert np.allclose(p["ar_b"], p["dy_bp"] - p["dc_bp"])


def test_coverage_counts(M):
    """Stage 4 record: M1 and M2 for all 912 auctions; M1b for 309 (defaults: +-5 days, >= 10 days)."""
    assert int(M["m1b_bp"].notna().sum()) == 309
    assert int(M["m1b_missing_reason"].eq("new issue: no prices before launch").sum()) == 80
    assert not M["beta_outlier"].any()


def test_handcheck_auctions_are_the_documented_five(M):
    """The five gate auctions (notebook 04 §5, handcheck workbook) follow from the selection rule."""
    from gilt_study import auctions as au
    from gilt_study.exercises import handcheck_stage4 as hc
    picks = hc.choose(M, au.load_auction_panel())
    assert picks == {"short": "2013-08-06_GB00B8KP6M44", "medium": "2010-10-21_GB00B582JV65",
                     "long": "2012-10-09_GB0004893086", "new issue": "2018-03-15_GB00BFX0ZL78",
                     "Sept-Oct 2022": "2022-10-04_GB00BMBL1D50"}
