"""Regression checks: the Module 2 exercises still reproduce their validated results after the
Stage 0 restructure (and after any later change to pricing.py or curve.py).

Run:  pytest -m slow      (about a minute)
"""
import pandas as pd
import pytest

from gilt_study.exercises import exercise_a, exercise_b


@pytest.mark.slow
def test_exercise_a_reproduces_dmo_2016(capsys):
    """Spec §4: 0 of 10,508 conventional gilt-days outside 1e-4 on dirty price, accrued and clean."""
    exercise_a.main()
    capsys.readouterr()
    E = pd.read_csv(exercise_a.OUT_DIR / "exercise_a_errors.csv")
    assert len(E) == 10_508
    assert int(E["bad"].sum()) == 0
    assert E["dirty_err"].abs().max() < 1e-4


@pytest.mark.slow
def test_exercise_b_reproduces_module2_targets(capsys):
    """Spec §5 curve acceptance test: three residual targets and the mean |residual| over 39 gilts."""
    exercise_b.main()
    capsys.readouterr()
    R = pd.read_csv(exercise_b.OUT_DIR / "exercise_b_residuals.csv")
    assert len(R) == 39
    got = R.set_index("gilt")["residual_bp"]
    for name, target in exercise_b.TARGETS_BP.items():
        assert abs(got[name] - target) < 0.05, name
    assert abs(R["residual_bp"].abs().mean() - 2.64) < 0.01
