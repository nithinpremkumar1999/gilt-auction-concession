"""Gilt terms (P3, P4): first issue and first coupon dates, and tranche settlement for WI lines.

Run:  pytest tests/test_gilt_terms.py   (reads data/interim_data/gilt_terms.csv; builds it in ~4 min
      if missing)
"""
import datetime as dt

import pytest

from gilt_study import config, gilt_terms
from gilt_study.data_io import load_d1a
from gilt_study import paths


@pytest.fixture(scope="module")
def terms():
    return gilt_terms.load_terms()


@pytest.mark.parametrize("gap, label, kind", [
    (45, gilt_terms.SRC_RULE_LONG, "long"), (1, gilt_terms.SRC_RULE_LONG, "long"),
    (46, gilt_terms.SRC_MANUAL, None), (60, gilt_terms.SRC_MANUAL, None),
    (61, gilt_terms.SRC_RULE_SHORT, "short"), (180, gilt_terms.SRC_RULE_SHORT, "short")])
def test_first_coupon_rule_thresholds(gap, label, kind):
    """Spec §4 fallback: <= 45 days to the next quasi date -> long; >= 61 -> short; 46-60 -> manual."""
    maturity = dt.date(2040, 3, 7)
    quasi = dt.date(2026, 3, 7)
    first_issue = quasi - dt.timedelta(days=gap)
    date, got_label, got_gap = gilt_terms.first_coupon_rule(first_issue, maturity)
    assert got_label == label and got_gap == gap
    if kind == "long":
        assert date == dt.date(2026, 9, 7)
    elif kind == "short":
        assert date == quasi


def test_first_issue_dates_follow_p4(terms):
    """D1A for every gilt in issue; otherwise the first D2.1E launch row; never a later event."""
    d1a = load_d1a(paths.D1A).set_index("isin")["first_issue"]
    t = terms.set_index("isin")
    assert (t.loc[d1a.index, "first_issue"] == d1a).all()
    assert (t.loc[d1a.index, "first_issue_source"] == "D1A").all()
    rest = t.drop(d1a.index)
    assert set(rest["first_issue_source"]) <= {"D2.1E launch row", "none: launched before D2.1E starts"}
    assert rest.loc[rest["first_issue"].isna(), "first_issue_source"].str.startswith("none").all()


def test_first_coupon_dates_from_dmo_wherever_possible(terms):
    """Every DMO notice is matched; no gilt is left for a manual check; the flagged rule is only used
    for gilts launched after the reference-price series ends (no DMO accrued to read)."""
    assert (terms["first_coupon_source"] == gilt_terms.SRC_DMO_NOTICE).sum() == len(gilt_terms.DMO_NOTICES)
    assert not terms["flag_first_coupon_manual_check"].any()
    ruled = terms[terms["flag_first_coupon_rule"]]
    assert (ruled["first_issue"] > config.PRICER_TEST_WINDOW[1]).all()
    has_issue = terms["first_issue"].notna()
    assert terms.loc[has_issue, "first_coupon"].notna().all()
    assert (terms.loc[has_issue, "first_coupon"] > terms.loc[has_issue, "first_issue"]).all()


def test_next_tranche_date_window():
    """WI lines settle on the next priced tranche within 45 days of the trade date (P2)."""
    tranches = {"X": [dt.date(2010, 1, 5), dt.date(2010, 3, 1)]}
    assert gilt_terms.next_tranche_date(tranches, "X", dt.date(2010, 1, 4)) == dt.date(2010, 1, 5)
    assert gilt_terms.next_tranche_date(tranches, "X", dt.date(2010, 1, 5)) is None   # strictly after
    assert gilt_terms.next_tranche_date(tranches, "X", dt.date(2010, 1, 15)) == dt.date(2010, 3, 1)
    assert gilt_terms.next_tranche_date(tranches, "X", dt.date(2010, 1, 14)) is None  # 46 days
    assert gilt_terms.next_tranche_date(tranches, "Y", dt.date(2010, 1, 4)) is None
