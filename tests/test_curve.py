"""Stage 2: curve panel and curve pricer (build spec §5).

Run:  pytest tests/test_curve.py            (reads the panel; builds it from raw_data in ~20 s if missing)
      pytest -m slow tests/test_curve.py    (+ the 15 Mar 2016 curve acceptance test)
"""
import datetime as dt

import numpy as np
import pandas as pd
import pytest

from gilt_study import config, curve
from gilt_study.exercises import exercise_b
from gilt_study.pricing import gilt_price, is_business_day, next_business_day


@pytest.fixture(scope="module")
def panel():
    return curve.load_panel()


def toy_curve(extrapolation="flat_forward"):
    """Upward-sloping toy curve to 25y with a forward of 3% at 25y."""
    t = np.array([0.5, 1, 2, 5, 10, 15, 20, 25])
    z = np.array([1.0, 1.2, 1.5, 2.0, 2.6, 2.9, 3.1, 3.2])
    return curve.Curve(dt.date(2010, 1, 4), t, z, f_tmax=3.0, extrapolation=extrapolation)


# ---------------------------------------------------------------- extrapolation (spec §5)
def test_flat_z_below_first_maturity():
    c = toy_curve()
    assert c(0.0) == c(0.1) == c(0.5) == 1.0


def test_spline_passes_through_the_boe_points():
    c = toy_curve()
    assert np.allclose(c(c.t), c.zs, atol=1e-12)


def test_flat_forward_is_continuous_and_holds_the_forward():
    """z is continuous at T and the instantaneous forward beyond T equals f(T)."""
    c = toy_curve()
    T = c.t_max
    assert abs(c(T + 1e-9) - c(T)) < 1e-8
    for a, b in [(26, 27), (30, 35), (40, 50)]:
        fwd = (c(b) * b - c(a) * a) / (b - a)            # -d ln DF / dt, in %
        assert abs(fwd - 3.0) < 1e-12
    assert abs(c(50) - (3.2 * 25 + 3.0 * 25) / 50) < 1e-12


def test_flat_z_option_for_diagnostics():
    c = toy_curve("flat_z")
    assert c(30) == c(50) == c.z_tmax
    with pytest.raises(ValueError):
        toy_curve("linear")


# ---------------------------------------------------------------- the curve pricer
def test_when_issued_discounts_from_first_issue_date():
    """Chat decision (19 Oct 2026): a gilt settling before its first issue date is priced as if it
    settled on the first issue date, so the price does not depend on the earlier settlement date."""
    c = toy_curve()
    fi, mat, fc = dt.date(2010, 2, 3), dt.date(2030, 9, 7), dt.date(2010, 9, 7)
    p_wi = curve.model_dirty(dt.date(2010, 1, 20), mat, 4.0, c, fi, fc)
    p_issue = curve.model_dirty(fi, mat, 4.0, c, fi, fc)
    assert p_wi == p_issue
    assert curve.model_yield(dt.date(2010, 1, 20), mat, 4.0, c, fi, fc) == curve.model_yield(fi, mat, 4.0, c, fi, fc)


def test_model_yield_reprices_the_curve_price():
    """Model yield is the GRY at which gilt_price() gives the curve dirty price (one cash_flows())."""
    c = toy_curve()
    settle, mat = dt.date(2010, 1, 5), dt.date(2040, 3, 7)
    d = curve.model_dirty(settle, mat, 4.25, c)
    y = curve.model_yield(settle, mat, 4.25, c)
    assert abs(gilt_price(settle, mat, 4.25, y)["dirty"] - d) < 1e-9


def test_beyond_curve_flag_and_years():
    """Flag and years beyond the curve (decision #12), measured from the effective settlement."""
    c = toy_curve()
    settle = dt.date(2010, 1, 5)
    assert not curve.beyond_curve(settle, dt.date(2034, 12, 7), c)      # 24.9y
    assert curve.years_beyond_curve(settle, dt.date(2034, 12, 7), c) == 0.0
    assert curve.beyond_curve(settle, dt.date(2035, 3, 7), c)           # 25.2y
    mat = dt.date(2045, 3, 7)
    assert abs(curve.years_beyond_curve(settle, mat, c) - ((mat - settle).days / 365.25 - 25)) < 1e-12
    # a when-issued new gilt: measured from its first issue date
    fi = dt.date(2010, 2, 3)
    assert curve.years_beyond_curve(settle, mat, c, fi) == (mat - fi).days / 365.25 - 25


# ---------------------------------------------------------------- the panel
def test_panel_covers_every_uk_business_day(panel):
    """Every UK business day from the panel start to the last BoE date has a curve; there are no
    rows on non-business days (holiday rows are dropped)."""
    start, end = panel.index[0].date(), panel.index[-1].date()
    assert start <= config.CURVE_PANEL_START + dt.timedelta(days=4)
    assert end >= config.STUDY_END
    days = pd.date_range(start, end, freq="D")
    bdays = {d for d in days if is_business_day(d.date())}
    assert bdays == set(panel.index)


def test_panel_maximum_maturity_and_forward(panel):
    """Last maturity 25y from 29 Jan 1998 to end-2015, 40y from 2016; forward present at T."""
    tm = panel["t_max"]
    assert set(tm[(panel.index >= "1998-01-29") & (panel.index < "2016-01-01")]) == {25.0}
    assert set(tm[panel.index >= "2016-01-01"]) == {40.0}
    assert panel["f_tmax"].notna().all() and panel["z_tmax"].notna().all()
    assert (panel["t_min"] <= 1.0).all()


def test_missing_date_uses_previous_curve_and_flags(panel):
    """Good Friday 2016 (25 Mar) has no curve: the curve of Thu 24 Mar is used, flagged."""
    c, used, fallback = curve.curve_on(panel, dt.date(2016, 3, 25))
    assert used == dt.date(2016, 3, 24) and fallback
    c, used, fallback = curve.curve_on(panel, dt.date(2016, 3, 24))
    assert used == dt.date(2016, 3, 24) and not fallback
    with pytest.raises(ValueError):
        curve.curve_on(panel, panel.index[-1] + pd.Timedelta(days=1))


def test_panel_rows_match_the_raw_workbook(panel):
    """The panel's 15 Mar 2016 row is the spliced raw workbook row, exactly."""
    raw = curve.load_spot_workbook(curve.paths.curve_workbook("2016 to 2024")).loc["2016-03-15"].dropna()
    row = panel.loc["2016-03-15", raw.index.tolist()]
    assert np.array_equal(row.to_numpy(float), raw.to_numpy(float))


# ---------------------------------------------------------------- acceptance test (spec §5)
@pytest.mark.slow
def test_curve_acceptance_15_mar_2016(capsys, panel):
    """Spec §5 as restated (decision #11): the three Module 2 targets within 0.05bp, 39 gilts, mean
    |residual| 2.70bp for the 36 gilts within the 40y curve. The all-gilt flat-z mean still
    reproduces Module 2 (2.64bp); flat forward moves only the 3 gilts beyond 40y."""
    R = exercise_b.residuals(exercise_b.DATE, panel)
    capsys.readouterr()
    assert len(R) == exercise_b.TARGET_COUNT
    got = R.set_index("gilt")["residual_bp"]
    for name, target in exercise_b.TARGETS_BP.items():
        assert abs(got[name] - target) < 0.05, name
    inside = R[~R["beyond_curve"]]
    assert len(inside) == 36
    assert abs(inside["residual_bp"].abs().mean() - exercise_b.TARGET_MEAN_ABS_BP_WITHIN_CURVE) < 0.005
    assert abs(R["residual_bp_flat_z"].abs().mean() - exercise_b.MODULE2_MEAN_ABS_BP_FLAT_Z) < 0.01
    assert R["beyond_curve"].sum() == 3
    assert (inside["residual_bp"] == inside["residual_bp_flat_z"]).all()
