"""Regression checks for the Module 2 exercises and the Stage 1 pricer acceptance test.

Run:  pytest -m "not slow"   (first-issue-date checks, seconds)
      pytest -m slow         (re-runs Exercise A for 2016 and the Stage 1 test in both modes)
"""
import datetime as dt

import pandas as pd
import pytest

from gilt_study.data_io import load_d1a
from gilt_study.exercises import exercise_a
from gilt_study import gilt_terms, paths


def test_first_issue_dates_reproduce_deleted_overrides():
    """P4 first issue dates (gilt_terms) give the three dates once inferred from DMO accrued."""
    T = gilt_terms.load_terms().set_index("isin")
    assert T.at["GB00BYY5F581", "first_issue"] == dt.date(2015, 9, 3)    # 1½% Treasury Gilt 2021
    assert T.at["GB00BYZW3G56", "first_issue"] == dt.date(2016, 2, 18)   # 1½% Treasury Gilt 2026
    assert T.at["GB00BD0PCK97", "first_issue"] == dt.date(2016, 8, 3)    # 0½% Treasury Gilt 2022
    assert not hasattr(exercise_a, "FIRST_ISSUE_OVERRIDES")


def test_d1a_and_d2_1e_first_issue_dates_agree():
    """For every conventional gilt still in issue, D1A's first issue date equals D2.1E's earliest."""
    d1a = load_d1a(paths.D1A).set_index("isin")["first_issue"]
    raw = pd.read_excel(paths.D2_1E, header=None).iloc[5:, [1, 2]]
    raw.columns = ["isin", "date"]
    raw = raw[raw["isin"].fillna("").astype(str).str.startswith("GB")]
    earliest = pd.to_datetime(raw["date"]).dt.date.groupby(raw["isin"]).min()
    assert (d1a == earliest.reindex(d1a.index)).all()


@pytest.mark.slow
def test_exercise_a_reproduces_dmo_2016(capsys):
    """Spec §4, 2016: 0 of 10,508 conventional gilt-days outside 1e-4 (dirty, accrued and clean),
    now with first issue dates from D1A/D2.1E instead of the deleted overrides."""
    exercise_a.main([2016])
    capsys.readouterr()
    E = pd.read_csv(exercise_a.OUT_DIR / "exercise_a_errors.csv")
    assert len(E) == 10_508
    assert int(E["bad"].sum()) == 0
    assert E["dirty_err"].abs().max() < 1e-4


@pytest.mark.slow
def test_stage1_final_passes_with_only_dmo_data_errors(capsys):
    """Stage 1 as signed off (P1-P4, decision #6): >= 99.5% of single-dated gilt-days in the test
    window within 1e-4 dirty; every exception has a confirmed cause, and each is a DMO data error."""
    T, G, X, A = exercise_a.main(mode="final")
    capsys.readouterr()
    W = G[G["in_window"]]
    assert len(W) == len(G) == 135_094                  # no testable rows outside the window
    assert W["pass_dirty"].mean() >= exercise_a.SPEC_PASS_RATE
    assert int(W["pass_dirty"].sum()) == int(W["pass_strict"].sum()) == 135_067
    F = G[~G["pass_strict"]]
    assert F["cause"].notna().all()
    assert F["cause"].str.contains("DMO data error").all(), F["cause"].value_counts()
    # every WI line has a tranche of its underlying gilt within 45 days, except '4¾% Treasury Stock
    # 2010 WI' (Jan 2006), which is the WI line of 4¾% 2020 labelled with the wrong maturity
    no_tranche = G[G["wi_line"] & G["tranche_found"].eq(False)]
    assert set(no_tranche["name"]) == {"4¾% Treasury Stock 2010 WI"}
    assert (no_tranche["cause"] == exercise_a.CAUSE_WI_REDEMPTION).all()


@pytest.mark.slow
def test_stage1_as_run_record_is_reproduced(capsys):
    """The as-run record behind the sign-off (19 Oct 2026): 138,685 of 167,608 gilt-days pass and
    every failure has a confirmed cause (nothing UNEXPLAINED)."""
    T, G, X, A = exercise_a.main(mode="as_run")
    capsys.readouterr()
    F = G[~G["pass_strict"]]
    assert F["cause"].notna().all()
    assert (F["cause"] != exercise_a.CAUSE_UNEXPLAINED).all()
    assert int(T["tested"].sum()) == len(G) == 167_608
    assert int(T["pass_strict"].sum()) == 138_685

# The curve acceptance test (Exercise B) moved to tests/test_curve.py in Stage 2.
