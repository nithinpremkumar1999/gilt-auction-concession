"""
Exercise B: price every conventional gilt off the BoE nominal spot curve on one date and compare the
model yield with the DMO reference yield.

Run:  python -m gilt_study.exercises.exercise_b
Outputs: printed table + data/processed_data/exercises/exercise_b_residuals.csv
         + reports/figures/exercise_b_residuals.png (matplotlib; replaced by the seaborn/Plotly
         pair in Stage 2, decision #8)
"""
import datetime as dt

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from .. import paths
from ..curve import curve_function, load_spot_workbook, model_yield
from ..data_io import conventional_only, load_d1a, load_reference_prices
from ..pricing import next_business_day
from .exercise_a import FIRST_ISSUE_OVERRIDES, REF_FILE, D1A_FILE, OUT_DIR

# ---------------------------------------------------------------- CONFIG
CURVE_FILE = paths.curve_workbook("2016 to 2024")   # extracted from glcnominalddata.zip
DATE = dt.date(2016, 3, 15)
MIN_YEARS = 1.0

TARGETS_BP = {"1½% Treasury Gilt 2026": 2.70, "4¼% Treasury Gilt 2055": -1.91,
              "4½% Treasury Gilt 2034": 1.38}


def main():
    curves = load_spot_workbook(CURVE_FILE)
    z = curve_function(curves, DATE)
    settle = next_business_day(DATE)

    ref, _ = conventional_only(load_reference_prices(REF_FILE))
    d1a = load_d1a(D1A_FILE)
    first_issue = dict(zip(d1a["isin"], d1a["first_issue"]))
    first_issue.update(FIRST_ISSUE_OVERRIDES)

    day = ref[ref["date"] == DATE]
    day = day[[(r - DATE).days / 365.25 > MIN_YEARS for r in day["redemption"]]]

    rows = []
    for g in day.itertuples(index=False):
        y = model_yield(settle, g.redemption, g.coupon, z, first_issue.get(g.isin))
        rows.append(dict(gilt=g.name, coupon=g.coupon, redemption=g.redemption,
                         years=round((g.redemption - DATE).days / 365.25, 2),
                         dmo_yield=g._7, model_yield=round(100 * y, 4),
                         residual_bp=round((g._7 - 100 * y) * 100, 2)))
    R = pd.DataFrame(rows).sort_values("years").reset_index(drop=True)
    print(R.to_string(index=False))
    print(f"\nGilts: {len(R)}   mean |residual|: {R.residual_bp.abs().mean():.2f} bp")

    # check against the targets given in the lesson
    for name, target in TARGETS_BP.items():
        got = R.loc[R.gilt == name, "residual_bp"].item()
        status = "OK " if abs(got - target) < 0.05 else "CHECK"
        print(f"  [{status}] {name:28s} residual {got:+.2f} bp (target {target:+.2f})")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    R.to_csv(OUT_DIR / "exercise_b_residuals.csv", index=False)

    fig, ax = plt.subplots(figsize=(9, 5))
    sc = ax.scatter(R.years, R.residual_bp, c=R.coupon, cmap="viridis", s=45, edgecolor="k", lw=0.3)
    ax.axhline(0, color="grey", lw=0.8)
    ax.set_xlabel("Years to maturity")
    ax.set_ylabel("DMO yield − model yield (bp)\n(positive = cheap to curve)")
    ax.set_title(f"Gilt residuals vs BoE nominal curve, {DATE:%d %b %Y}")
    fig.colorbar(sc, ax=ax, label="Coupon (%)")
    fig.tight_layout()
    paths.FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(paths.FIGURES / "exercise_b_residuals.png", dpi=150)
    print(f"\nSaved {OUT_DIR / 'exercise_b_residuals.csv'} and "
          f"{paths.FIGURES / 'exercise_b_residuals.png'}")


if __name__ == "__main__":
    main()
