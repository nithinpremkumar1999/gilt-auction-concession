"""
Exercise B, the Stage 2 curve acceptance test (build spec §5): price every single-dated conventional
gilt off the BoE nominal spot curve on 15 Mar 2016 and compare the model yield with the DMO
reference yield.

Targets (spec §5, restated 20 Oct 2026, decision #11): 1½% 2026 +2.70bp, 4¼% 2055 −1.91bp, 4½% 2034
+1.38bp reproduced exactly; 39 gilts; mean |residual| 2.70bp for the gilts within the curve's 40y range.
(The original 2.6bp all-gilt target was computed with flat-z extrapolation: 2.64bp.) Residual = DMO yield − model yield (positive = the gilt is cheap to the curve).

The curve comes from the Stage 2 panel (`curve.load_panel`, `curve.curve_on`) with flat-forward
extrapolation beyond 40y (decision #5); first issue and first coupon dates from gilt_terms (P3, P4).
The Module 2 exercise held z flat beyond the last maturity; that version is reported alongside
(`*_flat_z` columns) because three gilts on this date mature beyond 40y.

Run:  python -m gilt_study.exercises.exercise_b
Outputs: printed table, data/processed_data/exercises/exercise_b_residuals.csv,
         reports/figures/exercise_b_residuals.png + reports/interactive/exercise_b_residuals.html
"""
import datetime as dt

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import plotly.graph_objects as go
import seaborn as sns

from .. import gilt_terms, plotting
from ..curve import beyond_curve, curve_on, load_panel, model_yield, years_beyond_curve
from ..data_io import conventional_only, load_reference_prices
from ..pricing import next_business_day
from .exercise_a import OUT_DIR, REF_FILE

# ---------------------------------------------------------------- CONFIG
DATE = dt.date(2016, 3, 15)
MIN_YEARS = 1.0                              # Module 2: gilts with more than 1 year to maturity
TARGETS_BP = {"1½% Treasury Gilt 2026": 2.70, "4¼% Treasury Gilt 2055": -1.91,
              "4½% Treasury Gilt 2034": 1.38}
TARGET_MEAN_ABS_BP_WITHIN_CURVE = 2.70       # spec §5 as restated (decision #11)
MODULE2_MEAN_ABS_BP_FLAT_Z = 2.64            # the original Module 2 result, all 39 gilts, flat z
TARGET_COUNT = 39
CHART = "exercise_b_residuals"


def residuals(date: dt.date = DATE, panel: pd.DataFrame | None = None) -> pd.DataFrame:
    """DMO yield minus model yield (bp) for every single-dated conventional gilt with more than
    MIN_YEARS to maturity on `date`, under flat-forward (study) and flat-z (Module 2) extrapolation."""
    panel = load_panel() if panel is None else panel
    ff, curve_date, fallback = curve_on(panel, date, "flat_forward")
    fz, _, _ = curve_on(panel, date, "flat_z")
    settle = next_business_day(curve_date)
    T = gilt_terms.load_terms().set_index("isin")

    ref, _ = conventional_only(load_reference_prices(REF_FILE if date.year == 2016 else
                                                     gilt_terms.paths.ref_prices_file(date.year)))
    day = ref[ref["date"] == date]
    day = day[[(r - date).days / 365.25 > MIN_YEARS for r in day["redemption"]]]

    rows = []
    for g in day.itertuples(index=False):
        fi = T["first_issue"].get(g.isin)
        fc = T["first_coupon"].get(g.isin)
        y_ff = model_yield(settle, g.redemption, g.coupon, ff, fi, fc)
        y_fz = model_yield(settle, g.redemption, g.coupon, fz, fi, fc)
        rows.append(dict(gilt=g.name, isin=g.isin, coupon=g.coupon, redemption=g.redemption,
                         years=round((g.redemption - date).days / 365.25, 2),
                         dmo_yield=g._7, model_yield=round(100 * y_ff, 4),
                         residual_bp=round((g._7 - 100 * y_ff) * 100, 2),
                         model_yield_flat_z=round(100 * y_fz, 4),
                         residual_bp_flat_z=round((g._7 - 100 * y_fz) * 100, 2),
                         beyond_curve=beyond_curve(settle, g.redemption, ff, fi),
                         years_beyond_curve=round(years_beyond_curve(settle, g.redemption, ff, fi), 2),
                         curve_date=curve_date, curve_fallback=fallback,
                         first_coupon_source=T["first_coupon_source"].get(g.isin)))
    return pd.DataFrame(rows).sort_values("years").reset_index(drop=True)


def charts(R: pd.DataFrame, date: dt.date = DATE):
    """Residual by maturity: seaborn figure and Plotly figure (same data, same look)."""
    plotting.set_seaborn_theme()
    R = R.assign(curve=["beyond 40y: flat forward" if b else "within the BoE curve" for b in R.beyond_curve])
    cmap = plotting.colour_map(["within the BoE curve", "beyond 40y: flat forward"])
    title = f"Gilt yield residuals to the BoE nominal curve, {date:%d %b %Y}"
    ylab = "DMO yield − model yield (bp)"

    fig_s, ax = plt.subplots(figsize=(9, 4.8))
    ax.axhline(0, color=plotting.BASELINE, lw=1)
    ext = R[R.beyond_curve]
    ax.scatter(ext.years, ext.residual_bp_flat_z, s=40, facecolors="none",
               edgecolors=plotting.INK_MUTED, lw=1, label="beyond 40y: flat z (Module 2)", zorder=2)
    sns.scatterplot(data=R, x="years", y="residual_bp", hue="curve", palette=cmap, s=60,
                    edgecolor="white", linewidth=0.5, ax=ax, zorder=3)
    for name in TARGETS_BP:
        r = R[R.gilt == name].iloc[0]
        ax.annotate(f"{name.replace('Treasury Gilt ', '')}  {r.residual_bp:+.2f}", (r.years, r.residual_bp),
                    xytext=(6, 6), textcoords="offset points", fontsize=9, color=plotting.INK_SECONDARY)
    ax.set_xlabel("Years to maturity")
    ax.set_ylabel(ylab)
    ax.set_title(title)
    ax.legend(title=None, loc="upper center", bbox_to_anchor=(0.5, -0.14), ncols=3)
    fig_s.tight_layout()

    fig_p = go.Figure()
    fig_p.add_hline(y=0, line_color=plotting.BASELINE, line_width=1)
    fig_p.add_trace(go.Scatter(x=ext.years, y=ext.residual_bp_flat_z, mode="markers",
                               name="beyond 40y: flat z (Module 2)", text=ext.gilt,
                               marker=dict(size=9, color="rgba(0,0,0,0)",
                                           line=dict(color=plotting.INK_MUTED, width=1.5)),
                               hovertemplate="%{text}<br>%{x:.1f}y<br>flat z: %{y:+.2f} bp<extra></extra>"))
    for label, colour in cmap.items():
        s = R[R.curve == label]
        fig_p.add_trace(go.Scatter(
            x=s.years, y=s.residual_bp, mode="markers", name=label, marker=dict(color=colour, size=10),
            customdata=s[["gilt", "dmo_yield", "model_yield"]].to_numpy(),
            hovertemplate=("%{customdata[0]}<br>%{x:.1f} years<br>residual %{y:+.2f} bp<br>"
                           "DMO %{customdata[1]:.3f}% · model %{customdata[2]:.3f}%<extra></extra>")))
    fig_p.update_layout(template=plotting.PLOTLY_TEMPLATE, title=title, height=460,
                        xaxis_title="Years to maturity", yaxis_title=ylab,
                        legend=dict(orientation="h", y=-0.2))
    return fig_s, fig_p


def main(date: dt.date = DATE, save: bool = True) -> pd.DataFrame:
    R = residuals(date)
    pd.set_option("display.width", 200)
    print(R.drop(columns=["isin", "curve_date", "curve_fallback", "first_coupon_source"]).to_string(index=False))
    n_ext = int(R.beyond_curve.sum())
    print(f"\nGilts: {len(R)} (target {TARGET_COUNT})   curve date {R.curve_date.iloc[0]}"
          f"{' (FALLBACK)' if R.curve_fallback.iloc[0] else ''}")
    within = R.loc[~R.beyond_curve, "residual_bp"].abs().mean()
    print(f"mean |residual| within the curve: {within:.2f} bp (target {TARGET_MEAN_ABS_BP_WITHIN_CURVE:.2f}) "
          f"[{'OK' if abs(within - TARGET_MEAN_ABS_BP_WITHIN_CURVE) < 0.005 else 'CHECK'}]")
    print(f"all {len(R)} gilts: {R.residual_bp.abs().mean():.2f} bp with flat forward (study); "
          f"{R.residual_bp_flat_z.abs().mean():.2f} bp with flat z (Module 2: {MODULE2_MEAN_ABS_BP_FLAT_Z})")
    print(f"gilts beyond the curve's last maturity: {n_ext}")
    for name, target in TARGETS_BP.items():
        got = R.loc[R.gilt == name, "residual_bp"].item()
        status = "OK " if abs(got - target) < 0.05 else "CHECK"
        print(f"  [{status}] {name:28s} residual {got:+.2f} bp (target {target:+.2f})")

    if save:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        R.to_csv(OUT_DIR / "exercise_b_residuals.csv", index=False)
        fig_s, fig_p = charts(R, date)
        png, html = plotting.save_pair(CHART, fig_s, fig_p)
        plotting.close(fig_s)
        print(f"\nSaved {OUT_DIR / 'exercise_b_residuals.csv'}, {png} and {html}")
    return R


if __name__ == "__main__":
    main()
