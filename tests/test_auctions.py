"""Stage 3: the auction panel and its acceptance checks (build spec §6).

Run:  pytest tests/test_auctions.py   (reads data/processed_data/auctions/auction_panel.csv; builds it
      in ~20 s if missing)
"""
import datetime as dt

import pytest

from gilt_study import auctions as au, config, curve
from gilt_study.data_io import is_index_linked


@pytest.fixture(scope="module")
def panel():
    return au.load_auction_panel()


@pytest.fixture(scope="module")
def checks(panel):
    return au.panel_checks(panel)


# ---------------------------------------------------------------- helpers
def test_business_day_helpers():
    assert au.previous_business_day(dt.date(2016, 3, 29)) == dt.date(2016, 3, 24)   # Easter Monday, Good Friday
    assert au.add_business_days(dt.date(2016, 3, 24), 1) == dt.date(2016, 3, 29)
    assert au.add_business_days(dt.date(2016, 3, 29), -5) == dt.date(2016, 3, 18)
    assert au.financial_year(dt.date(2021, 3, 31)) == "2020-21"
    assert au.financial_year(dt.date(2021, 4, 1)) == "2021-22"


@pytest.mark.parametrize("years, expected", [(6.99, "short"), (7.0, "medium"), (15.0, "medium"),
                                             (15.01, "long")])
def test_bucket_bands(years, expected):
    """Spec §6: short < 7y, medium 7-15y, long > 15y."""
    assert au.bucket(years) == expected


@pytest.mark.parametrize("day, expected", [
    (dt.date(2008, 12, 31), "pre-crisis"), (dt.date(2009, 1, 1), "QE"), (dt.date(2022, 1, 31), "QE"),
    (dt.date(2022, 2, 1), au.REGIME_OPEN), (dt.date(2022, 9, 23), "LDI stress"),
    (dt.date(2022, 10, 14), "LDI stress"), (dt.date(2022, 10, 18), au.REGIME_OPEN),
    (dt.date(2022, 11, 1), "active QT"), (dt.date(2026, 9, 16), "active QT"),
    (dt.date(2026, 9, 17), "post-QT-decision")])
def test_regime_boundaries(day, expected):
    """Spec §8 regimes; Feb-Oct 2022 outside the LDI window stays an explicit open category."""
    assert au.regime(day) == expected


# ---------------------------------------------------------------- spec §6 panel checks
def test_sample_and_linker_exclusion(panel, checks):
    """912 conventional auctions in the window; 328 linkers excluded (5 spelled 'Index-Linked')."""
    assert len(panel) == checks["conventional_in_window"] == 912
    assert panel["auction_date"].min() == dt.date(1999, 5, 26)
    assert panel["auction_date"].min() >= config.STUDY_START and panel["auction_date"].max() <= config.STUDY_END
    assert not panel["gilt_name"].map(is_index_linked).any()
    assert checks["linkers_in_window"] == 328
    assert checks["linkers_missed_by_case_sensitive_filter"] == 5


def test_counts_reconcile_to_dmo(checks):
    """Spec §6 check 1: every financial year's auction count (1998-99 to 2023-24) equals the DMO's;
    the bucket split matches in all five spot-check years."""
    assert checks["fy_all_auctions"]["match"].all()
    assert len(checks["fy_all_auctions"]) == 26
    assert checks["fy_buckets"]["match"].all()
    assert len(checks["fy_buckets"]) >= 5


def test_no_duplicates_and_every_isin_has_terms(checks):
    """Spec §6 checks 2-3."""
    assert checks["duplicates"] == 0
    assert checks["isin_missing"] == 0
    assert checks["terms_missing"] == 0
    assert checks["ambiguous_isin"] == 0


def test_settlement_is_the_dmo_issue_date(panel):
    """Spec §4: settlement from the D2.1E issue date (here always T+1)."""
    assert panel["settlement_is_t_plus_1"].all()
    assert (panel["settlement_date"] > panel["auction_date"]).all()


def test_aay_reprices_to_aap(panel):
    """Every DMO average accepted yield reprices to the published AAP with our terms and settlement;
    the 89 auctions that depend on a rule-based first coupon all reprice within 1e-5."""
    assert set(panel["aap_check"]) <= {"rounded", "truncated"}
    late = panel[(panel["auction_date"] >= dt.date(2003, 7, 29)) & (panel["aay_decimals"] > 3)]
    assert late["aap_check_error"].abs().max() < 5e-5
    ruled = panel[panel["flag_first_coupon_rule"]]
    assert len(ruled) == 89 and ruled["aap_check_error"].abs().max() < 2e-5


@pytest.mark.parametrize("day, offered, cover, aap, aay3, lowest_yield3, tail", [
    (dt.date(2009, 3, 25), 1750, 0.93, 95.24, 4.506, 4.634, 12.8),   # uncovered auction; full amount allotted
    (dt.date(2010, 8, 10), 1750, 1.56, 104.51, 4.200, 4.203, 0.3)])
def test_matches_dmo_result_notices(panel, day, offered, cover, aap, aay3, lowest_yield3, tail):
    """Field-by-field against DMO auction result notices (URLs in SOURCES.md #5b)."""
    r = panel[panel["auction_date"] == day].iloc[0]
    assert r["nominal_offered"] == r["nominal_allotted"] == offered
    assert r["bid_to_cover"] == cover and r["aap"] == aap and r["tail_bp"] == tail
    assert round(r["aay"], 3) == aay3 and round(r["yield_at_lowest_accepted_price"], 3) == lowest_yield3


def test_years_beyond_curve_and_robustness_flag(panel):
    """Decision #12: years beyond the T-1 curve; drop flag above 5 years; only long gilts affected."""
    assert ((panel["years_beyond_curve"] > 0) == panel["beyond_curve"]).all()
    gap = panel["years_to_maturity"] - panel["curve_t_max"]
    assert (abs(panel["years_beyond_curve"] - gap.clip(lower=0)) < 0.01).all()
    assert (panel["drop_extrapolation_robustness"] == (panel["years_beyond_curve"] > config.MAX_YEARS_BEYOND_CURVE)).all()
    assert set(panel.loc[panel["beyond_curve"], "bucket"]) == {"long"}
    assert not panel["curve_fallback"].any()
    assert int(panel["beyond_curve"].sum()) == 101 and int(panel["drop_extrapolation_robustness"].sum()) == 75


def test_new_issues_and_first_coupon_flags(panel):
    """New issue = settles on the first issue date; the rule flag is set only where the rule-based
    first coupon date is still ahead at settlement (spec §4: auctions priced with the fallback)."""
    assert (panel.loc[panel["new_issue"], "settlement_date"] == panel.loc[panel["new_issue"], "first_issue"]).all()
    assert int(panel["new_issue"].sum()) == 80
    assert (panel["flag_first_coupon_rule"] <= panel["gilt_first_coupon_from_rule"]).all()
    assert (panel.loc[panel["flag_first_coupon_rule"], "settlement_date"]
            < panel.loc[panel["flag_first_coupon_rule"], "first_coupon"]).all()
    assert not panel["flag_first_coupon_manual_check"].any()


def test_supply_window_example(panel):
    """The 5⅜% 2056 syndication of 8 Sep 2026 (the only conventional syndication from Jul to Sep 2026)
    counts for exactly the auctions whose +-5 business-day window contains it."""
    s = panel[(panel["auction_date"] >= dt.date(2026, 8, 1)) & (panel["auction_date"] <= dt.date(2026, 9, 30))]
    assert len(s) > 3
    for r in s.itertuples():
        inside = au.add_business_days(r.auction_date, -5) <= dt.date(2026, 9, 8) <= au.add_business_days(r.auction_date, 5)
        assert r.synd_conv_n_pm5bd == (1 if inside else 0), r.auction_date


def test_negative_tail_is_flagged_not_changed(panel):
    """4 Mar 2009 (4¼% 2039): D2.1A tail -5.5bp is impossible in a multiple-price auction; kept as
    published and flagged."""
    r = panel[panel["flag_tail_negative"]]
    assert list(r["auction_date"]) == [dt.date(2009, 3, 4)] and r["tail_bp"].iloc[0] == -5.5
