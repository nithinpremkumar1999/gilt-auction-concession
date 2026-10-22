"""Stage 6: the report's four charts (build spec §9; decisions #9, #18-#20).

Each chart is made twice from the same tidy table (decision #9): a seaborn/matplotlib PNG in
reports/figures/ and a Plotly HTML in reports/interactive/, both named report_<n>_<topic>.

  1. report_1_paths              average path T-10..T+10 for M2 (B-beta) and M3, relative to T-6,
                                 with the 95% CI of the mean (clustered by auction week) and the
                                 placebo 95% range (2.5-97.5 percentiles of 1,000 placebo mean paths)
  2. report_2_by_bucket          the PM's three numbers by bucket for M2 and M3, and the M1b level
  3. report_3_by_regime          the same by regime (pre-crisis, QE, active QT); the LDI-stress window
                                 (3 auctions) is in the tables only: reported, not interpreted (#20)
  4. report_4_ex_ante_drivers    ex-ante regression coefficients (decision #19) with 95% CIs

Inference shown (decision #20)
  * Intervals are 95% CIs from standard errors clustered by auction week (t with G-1 df for the
    means is approximated here by +-1.96 SE; the tables carry the exact p-values).
  * Marker fill carries the lead p-value: filled if p < 0.05, hollow otherwise. The lead p is the
    placebo-centred p for M2 and M3 means, and the clustered p for M1b means and all coefficients
    (no placebo exists for them). A CI that excludes zero on a hollow marker is therefore possible:
    the placebo test is stricter there.

Captions (chart gate, 21 Oct 2026): every chart carries a caption under it that explains each band,
bar and marker; exact p-values are in the appendix table (reports/tables/appendix_p_values.csv and
.html; `appendix_table()`), which also carries the robustness rows added at the chart gate after
seeing the results: the placebo with dates in the auction's own regime, the T-10 -> T-1 pre-auction
window (M2, M3) and the M3 total move T-10 -> T+1.

Titles (Stage 7, 22 Oct 2026): `main()` takes each chart's title from the report's caption, i.e. the
first sentence of the image alt text "Chart N. <title>. ..." in reports/report_final.md
(`report_titles()`), so chart and caption cannot drift apart; site/build.py checks the match.
Panel names use the report's words (the curve / the gilt relative to the curve / auction discount).
The explanatory captions under the charts are Plotly annotations named "caption", so the website
(which shows the report's own caption instead) can drop them.

Signs: every number is a yield change or level in bp; positive = the gilt cheapened.
Colours: buckets use categorical slots 1-3 (as in Stages 3-5); regimes use slots 7, 4, 5
(validated 21 Oct 2026 with the dataviz validator: worst CVD Delta E 16.3, normal 19.6; contrast
below 3:1 for two slots, so every series is also named in the legend and the hover, and the tables
sit in notebook 06); "all auctions" is neutral ink; single-series charts use slot 1.

Run:  python -m gilt_study.report_charts      (needs the Stage 5 outputs: analysis + placebo)
"""
import re
import textwrap

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from matplotlib.lines import Line2D
from plotly.subplots import make_subplots

from . import analysis as an, measures as ms, paths, placebo as pl, plotting
from .inference import mean_test
from .plotting import (BASELINE, CATEGORICAL, GRID, INK, INK_MUTED, INK_SECONDARY, NEUTRAL_BAND,
                       PLOTLY_TEMPLATE, SURFACE)

Z95 = 1.96
SIG = 0.05
WINDOWS = an.WINDOWS
BUCKETS = an.BUCKETS
REGIMES = ["pre-crisis", "QE", "active QT"]
GROUP_COLOURS = {"all auctions": INK_SECONDARY, **plotting.colour_map(BUCKETS),
                 "pre-crisis": CATEGORICAL[6], "QE": CATEGORICAL[3], "active QT": CATEGORICAL[4]}
LINE_COLOUR = CATEGORICAL[0]
WINDOW_TICKS = {"pre": "Pre-auction<br>T-6 → T-1", "day": "Auction day<br>T-1 → T", "post": "Post-auction<br>T → T+5",
                "level": "At auction<br>(level)"}
MEASURE_TITLES = {"M2 (B-β)": "The curve at the gilt's maturity (M2), 1999–2026",
                  "M3": "The gilt relative to the curve (M3), 1999–2017",
                  "M1b": "Auction discount (M1b), 1999–2017"}
SIGN_NOTE = "bp; positive = the gilt cheapened"
FILL_NOTE = ("Filled marker: p < 0.05 on the lead test (placebo-centred for M2 and M3, clustered for M1b); hollow "
             "otherwise. Bars: 95% confidence intervals from standard errors clustered by auction week. A hollow "
             "marker can have a bar that clears zero: the placebo test is the stricter one there. Exact p-values: "
             "appendix table.")
PATH_CAPTION = [
    "Blue line and band: the mean of the real auctions on each day, relative to T-6, with its 95% confidence "
    "interval (standard errors clustered by auction week). M2: all 912 auctions; M3: the 367 auctions with a "
    "bond residual on every day from T-10 to T+10, so the line is one fixed set of auctions.",
    "Grey band, dashed edges: the placebo 95% range, i.e. the middle 95% of 1,000 mean paths for the same gilts "
    "on random non-auction dates (same bucket, at least 10 business days from their own auctions). Where the blue "
    "line leaves the grey band, ordinary days rarely produce such a path. The M2 range drifts down after T-6 "
    "because the abnormal change has no intercept; p-values are measured from the placebo centre.",
    "Dotted lines: T-6, T-1, T and T+5, the ends of the PM's three windows (pre, day, post).",
]


def _caption_static(fig, paragraphs, y: float, width: int = 175):
    """Caption under a matplotlib figure (saved with bbox_inches='tight', so it is kept)."""
    text = "\n".join(textwrap.fill(p, width) for p in paragraphs)
    fig.text(0.01, y, text, fontsize=8.5, color=INK_MUTED, ha="left", va="top")


def _caption_plotly(paragraphs, width: int = 150) -> str:
    return "<br>".join("<br>".join(textwrap.wrap(p, width)) for p in paragraphs)


def _rgba(hex_colour: str, alpha: float) -> str:
    r, g, b = (int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{g},{b},{alpha})"


def _static_ticks(labels):
    return [WINDOW_TICKS[w].replace("<br>", "\n") for w in labels]


# =============================================================================== data
def path_data() -> pd.DataFrame:
    """Mean path k = -10..+10 (relative to T-6) with clustered 95% CIs and the placebo 95% range.
    M2: every auction (CAR, B-beta). M3: auctions with a residual on every day T-10..T+10."""
    A = an.dataset()[["auction_id", "week", "days"]]
    p2 = pd.read_csv(ms.OUT_DIR / "m2_paths.csv.gz", usecols=["auction_id", "k", "car_bbeta"]).rename(columns={"car_bbeta": "value"})
    p3 = pd.read_csv(ms.M3_PATHS_FILE, usecols=["auction_id", "k", "residual_rel_t6_bp"]).rename(columns={"residual_rel_t6_bp": "value"})
    full = p3.groupby("auction_id")["value"].apply(lambda s: s.notna().all())
    p3 = p3[p3["auction_id"].isin(full[full].index)]
    PL = pd.read_csv(pl.OUT_DIR / "placebo_paths.csv.gz")
    rows = []
    for measure, P in [("M2 (B-β)", p2), ("M3", p3)]:
        P = P.merge(A, on="auction_id")
        null = PL[PL["measure"] == measure]
        for k, g in P.groupby("k"):
            nk = null[null["k"] == k]["mean_bp"]
            row = dict(measure=measure, k=int(k), n=len(g), placebo_lo=nk.quantile(0.025), placebo_hi=nk.quantile(0.975),
                       placebo_mean=nk.mean(), placebo_n=int(null["n_events"].iloc[0]))
            if k == ms.M2_BASE:
                row.update(mean=0.0, se=0.0)
            else:
                r = mean_test(g["value"], g["week"], g["days"], label="mean")
                row.update(mean=r["mean"], se=r["se_cluster"])
            rows.append(row)
    D = pd.DataFrame(rows)
    D["lo"], D["hi"] = D["mean"] - Z95 * D["se"], D["mean"] + Z95 * D["se"]
    return D


def _headline() -> pd.DataFrame:
    H = pd.read_csv(an.OUT_DIR / "headline.csv")
    names = {"M2 (B-β), all years": "M2 (B-β)", "M3, 1999-2017": "M3", "Levels to 2017": "M1b"}
    H = H[H["set"].isin(names) & ((H["set"] != "Levels to 2017") | (H["measure"] == "M1b"))].copy()
    H["panel"] = H["set"].map(names)
    H["window"] = np.where(H["panel"] == "M1b", "level", H["measure"])
    H["group"] = H["group"].replace({"all": "all auctions"})
    H["lo"], H["hi"] = H["mean_bp"] - Z95 * H["se_cluster"], H["mean_bp"] + Z95 * H["se_cluster"]
    H["significant"] = H["lead_p"] < SIG
    return H[H["window"].isin(WINDOWS + ["level"])]          # charted windows (extra windows: appendix only)


def bucket_data() -> pd.DataFrame:
    H = _headline()
    return H[H["by"].isin(["all", "bucket"])].reset_index(drop=True)


def regime_data() -> pd.DataFrame:
    H = _headline()
    return H[(H["by"] == "regime") & H["group"].isin(REGIMES)].reset_index(drop=True)


COEF_VARS = {
    "dv01": "Auction DV01 (per £1m/bp)",
    "vol": "Volatility to T-1 (per 1bp/day)",
    "medium": "Medium bucket (vs short)",
    "long": "Long bucket (vs short)",
    "new_issue": "New issue (launch)",
    "synd_week": "Syndication within ±5 days",
    "tender_week": "Tender within ±5 days",
    "qt_week": "BoE QT sale within ±5 days",
    "qe_week": "BoE QE purchase within ±5 days",
}
COEF_PANELS = [  # (spec name in analysis.SPECS, panel title, row, col)
    ("M2 pre (B-β)", "M2 pre-auction", 0, 0), ("M2 day (B-β)", "M2 auction day", 0, 1), ("M2 post (B-β)", "M2 post-auction", 0, 2),
    ("M3 pre", "M3 pre-auction", 1, 0), ("M3 day", "M3 auction day", 1, 1), ("M3 post", "M3 post-auction", 1, 2),
    ("M1b (1999-2017)", "M1b level, 1999–2017", 2, 0), ("M1, gilt FE (2018-2026)", "M1 level, gilt FE, 2018–2026", 2, 1),
]


def coef_data() -> pd.DataFrame:
    """Ex-ante coefficients (decision #19) for the chart's variables; regime dummies and the constant
    are in the tables (regimes: chart 3)."""
    R = pd.read_csv(an.OUT_DIR / "regressions.csv")
    R = R[(R["specification"] == "ex-ante") & R["spec"].isin([p[0] for p in COEF_PANELS]) & R["variable"].isin(COEF_VARS)].copy()
    R["label"] = R["variable"].map(COEF_VARS)
    R["lo"], R["hi"] = R["coef"] - Z95 * R["se_cluster"], R["coef"] + Z95 * R["se_cluster"]
    R["significant"] = R["p_cluster"] < SIG
    return R.reset_index(drop=True)


# =============================================================================== chart 1: paths
def chart_paths(D: pd.DataFrame | None = None, title: str | None = None):
    D = path_data() if D is None else D
    title = title or "Average path around the auction, T-10 to T+10 (bp, relative to T-6; positive = the gilt cheapened)"
    windows = [(-6, -1, "pre"), (-1, 0, "day"), (0, 5, "post")]
    fig_s, axes = plt.subplots(1, 2, figsize=(13, 4.8), sharey=True)
    for ax, m in zip(axes, ["M2 (B-β)", "M3"]):
        d = D[D["measure"] == m]
        for x in (-6, -1, 0, 5):
            ax.axvline(x, color=BASELINE, lw=1, ls=":", zorder=0)
        for a, b, lab in windows:
            ax.text((a + b) / 2, 1.0, lab, transform=ax.get_xaxis_transform(), ha="center", va="bottom",
                    color=INK_MUTED, fontsize=9)
        ax.axhline(0, color=BASELINE, lw=1)
        ax.fill_between(d["k"], d["placebo_lo"], d["placebo_hi"], color=NEUTRAL_BAND, lw=0, zorder=1)
        ax.plot(d["k"], d["placebo_lo"], color=INK_MUTED, lw=1, ls="--", zorder=2)
        ax.plot(d["k"], d["placebo_hi"], color=INK_MUTED, lw=1, ls="--", zorder=2)
        ax.fill_between(d["k"], d["lo"], d["hi"], color=LINE_COLOUR, alpha=0.15, lw=0, zorder=3)
        ax.plot(d["k"], d["mean"], color=LINE_COLOUR, marker="o", ms=4, zorder=4)
        ax.set_title(f"{MEASURE_TITLES[m]} (n = {int(d['n'].iloc[0])})", fontsize=11, pad=16)
        ax.set_xticks(range(-10, 11, 2))
        ax.set_xlabel("Business days relative to the auction (T = 0)")
    axes[0].set_ylabel(SIGN_NOTE)
    handles = [Line2D([], [], color=LINE_COLOUR, marker="o", ms=4, label="Mean of the real auctions"),
               plt.Rectangle((0, 0), 1, 1, color=LINE_COLOUR, alpha=0.15, label="95% CI of the mean (clustered by week)"),
               plt.Rectangle((0, 0), 1, 1, facecolor=NEUTRAL_BAND, edgecolor=INK_MUTED, ls="--",
                             label="Placebo 95% range (1,000 sets of non-auction dates)")]
    fig_s.legend(handles=handles, loc="lower center", ncol=3, bbox_to_anchor=(0.5, -0.06), fontsize=9)
    fig_s.suptitle(title, x=0.01, ha="left", fontweight="bold", fontsize=12)
    fig_s.tight_layout(rect=(0, 0.04, 1, 1))
    _caption_static(fig_s, PATH_CAPTION, -0.08)

    fig_p = make_subplots(rows=1, cols=2, shared_yaxes=True, horizontal_spacing=0.06,
                          subplot_titles=[f"{MEASURE_TITLES[m]} (n = {int(D[D.measure == m]['n'].iloc[0])})"
                                          for m in ["M2 (B-β)", "M3"]])
    for c, m in enumerate(["M2 (B-β)", "M3"], start=1):
        d = D[D["measure"] == m]
        show = c == 1
        fig_p.add_trace(go.Scatter(x=np.r_[d.k, d.k[::-1]], y=np.r_[d.placebo_hi, d.placebo_lo[::-1]], fill="toself",
                                   fillcolor=NEUTRAL_BAND, line=dict(width=0),
                                   name="Placebo 95% range (1,000 sets of non-auction dates)", legendgroup="pl",
                                   showlegend=show, hoverinfo="skip"), row=1, col=c)
        for edge in ("placebo_lo", "placebo_hi"):
            fig_p.add_trace(go.Scatter(x=d.k, y=d[edge], mode="lines", line=dict(color=INK_MUTED, width=1, dash="dash"),
                                       legendgroup="pl", showlegend=False, hoverinfo="skip"), row=1, col=c)
        fig_p.add_trace(go.Scatter(x=np.r_[d.k, d.k[::-1]], y=np.r_[d.hi, d.lo[::-1]], fill="toself",
                                   fillcolor=_rgba(LINE_COLOUR, 0.15), line=dict(width=0),
                                   name="95% CI of the mean (clustered by week)", legendgroup="ci", showlegend=show,
                                   hoverinfo="skip"), row=1, col=c)
        fig_p.add_trace(go.Scatter(x=d.k, y=d["mean"], mode="lines+markers", line=dict(color=LINE_COLOUR),
                                   marker=dict(size=7), name="Mean of the real auctions", legendgroup="m", showlegend=show,
                                   customdata=np.stack([d.lo, d.hi, d.placebo_lo, d.placebo_hi, d.n], axis=1),
                                   hovertemplate="T%{x:+d}: %{y:+.2f} bp<br>95% CI [%{customdata[0]:+.2f}, %{customdata[1]:+.2f}]"
                                                 "<br>placebo 95% range [%{customdata[2]:+.2f}, %{customdata[3]:+.2f}]"
                                                 "<br>n %{customdata[4]:.0f}<extra>" + m + "</extra>"), row=1, col=c)
        for x in (-6, -1, 0, 5):
            fig_p.add_vline(x=x, line=dict(color=BASELINE, width=1, dash="dot"), row=1, col=c)
        for a, b, lab in windows:
            fig_p.add_annotation(x=(a + b) / 2, y=1.0, yref="y domain", text=lab, showarrow=False, yanchor="top",
                                 font=dict(color=INK_MUTED, size=11), row=1, col=c)
        fig_p.add_hline(y=0, line_color=BASELINE, row=1, col=c)
        fig_p.update_xaxes(title_text="Business days relative to the auction (T = 0)", dtick=2, row=1, col=c)
    fig_p.update_yaxes(title_text=SIGN_NOTE, row=1, col=1)
    fig_p.add_annotation(name="caption", text=_caption_plotly(PATH_CAPTION, 170), xref="paper", yref="paper", x=0, y=-0.27,
                         showarrow=False, xanchor="left", yanchor="top", align="left", font=dict(size=11, color=INK_MUTED))
    fig_p.update_layout(template=PLOTLY_TEMPLATE, height=720, title=title, hovermode="closest",
                        legend=dict(orientation="h", y=-0.16, x=0), margin=dict(b=270))
    return fig_s, fig_p


# =============================================================================== charts 2-3: dot + CI
def _dot_chart(D: pd.DataFrame, groups: list, title: str, legend_title: str, caption: list | None = None):
    panels = [p for p in ["M2 (B-β)", "M3", "M1b"] if p in set(D["panel"])]
    widths = [3 if p != "M1b" else 1.25 for p in panels]
    nG = len(groups)
    offs = (np.arange(nG) - (nG - 1) / 2) * (0.62 / max(nG - 1, 1))
    fig_s, axes = plt.subplots(1, len(panels), figsize=(14, 5), sharey=True, gridspec_kw=dict(width_ratios=widths))
    for ax, p in zip(np.atleast_1d(axes), panels):
        d = D[D["panel"] == p]
        wins = WINDOWS if p != "M1b" else ["level"]
        ax.axhline(0, color=BASELINE, lw=1)
        for i, g in enumerate(groups):
            u = d[d["group"] == g].set_index("window").reindex(wins)
            col = GROUP_COLOURS[g]
            for j, w in enumerate(wins):
                if pd.isna(u.at[w, "mean_bp"]):
                    continue
                x = j + offs[i]
                ax.plot([x, x], [u.at[w, "lo"], u.at[w, "hi"]], color=col, lw=2, solid_capstyle="round")
                ax.plot(x, u.at[w, "mean_bp"], "o", ms=8, mec=col, mew=2, mfc=col if u.at[w, "significant"] else SURFACE)
        ax.set_xticks(range(len(wins)), _static_ticks(wins))
        ax.set_xlim(-0.6, len(wins) - 0.4)
        ax.set_title(MEASURE_TITLES[p], fontsize=10.5)
    np.atleast_1d(axes)[0].set_ylabel(SIGN_NOTE)
    handles = [Line2D([], [], color=GROUP_COLOURS[g], marker="o", ms=7, lw=2, label=g) for g in groups]
    handles += [Line2D([], [], color=INK_MUTED, marker="o", ms=7, lw=0, label="p < 0.05 (lead test)"),
                Line2D([], [], color=INK_MUTED, marker="o", ms=7, lw=0, mfc=SURFACE, mew=2, label="p ≥ 0.05")]
    fig_s.legend(handles=handles, loc="lower center", ncol=len(handles), bbox_to_anchor=(0.5, -0.07), fontsize=9,
                 title=None)
    caption = [FILL_NOTE] + (caption or [])
    fig_s.suptitle(title, x=0.01, ha="left", fontweight="bold", fontsize=12)
    fig_s.tight_layout(rect=(0, 0.03, 1, 1))
    _caption_static(fig_s, caption, -0.1, width=190)

    fig_p = make_subplots(rows=1, cols=len(panels), shared_yaxes=True, column_widths=widths, horizontal_spacing=0.04,
                          subplot_titles=[MEASURE_TITLES[p] for p in panels])
    for c, p in enumerate(panels, start=1):
        d = D[D["panel"] == p]
        wins = WINDOWS if p != "M1b" else ["level"]
        for i, g in enumerate(groups):
            u = d[d["group"] == g].set_index("window").reindex(wins).reset_index()
            u = u[u["mean_bp"].notna()]
            if u.empty:
                continue
            col = GROUP_COLOURS[g]
            xs = [wins.index(w) + offs[i] for w in u["window"]]
            lead = [f"{v:.3f}" if v >= 0.001 else "< 0.001" for v in u["lead_p"]]
            src = ["placebo-centred" if s == "placebo-centred" else "clustered" for s in u["lead_p_source"]]
            fig_p.add_trace(go.Scatter(
                x=xs, y=u["mean_bp"], mode="markers", name=g, legendgroup=g, showlegend=False,
                marker=dict(color=col, size=10, symbol=["circle" if s else "circle-open" for s in u["significant"]],
                            line=dict(color=col, width=2)),
                error_y=dict(type="data", symmetric=False, array=u["hi"] - u["mean_bp"], arrayminus=u["mean_bp"] - u["lo"],
                             color=col, thickness=2, width=0),
                customdata=np.stack([u["lo"], u["hi"], u["n"], lead, src, u["p_cluster"]], axis=1),
                hovertemplate="<b>" + g + "</b>: %{y:+.2f} bp<br>95% CI [%{customdata[0]:+.2f}, %{customdata[1]:+.2f}]"
                              "<br>p %{customdata[3]} (%{customdata[4]}); clustered p %{customdata[5]:.3f}"
                              "<br>n %{customdata[2]:.0f}<extra></extra>"), row=1, col=c)
        fig_p.update_xaxes(tickvals=list(range(len(wins))), ticktext=[WINDOW_TICKS[w] for w in wins],
                           range=[-0.6, len(wins) - 0.4], row=1, col=c)
        fig_p.add_hline(y=0, line_color=BASELINE, row=1, col=c)
    for g in groups:                                    # legend: identity, always a filled marker
        fig_p.add_trace(go.Scatter(x=[None], y=[None], mode="markers+lines", name=g, legendgroup=g,
                                   marker=dict(color=GROUP_COLOURS[g], size=10), line=dict(color=GROUP_COLOURS[g], width=2)),
                        row=1, col=1)
    for sym, lab in [("circle", "p < 0.05 (lead test)"), ("circle-open", "p ≥ 0.05")]:
        fig_p.add_trace(go.Scatter(x=[None], y=[None], mode="markers", name=lab,
                                   marker=dict(color=INK_MUTED, size=10, symbol=sym, line=dict(color=INK_MUTED, width=2))),
                        row=1, col=1)
    fig_p.update_yaxes(title_text=SIGN_NOTE, row=1, col=1)
    fig_p.add_annotation(name="caption", text=_caption_plotly(caption, 160), xref="paper", yref="paper", x=0, y=-0.3, showarrow=False,
                         xanchor="left", yanchor="top", align="left", font=dict(size=11, color=INK_MUTED))
    fig_p.update_layout(template=PLOTLY_TEMPLATE, height=560 + 16 * len(caption), title=title,
                        legend=dict(orientation="h", y=-0.17, x=0), margin=dict(b=150 + 16 * len(caption)))
    return fig_s, fig_p


def chart_buckets(D: pd.DataFrame | None = None, title: str | None = None):
    D = bucket_data() if D is None else D
    return _dot_chart(D, ["all auctions"] + BUCKETS,
                      title or "The PM's three numbers by bucket, and the M1b level (bp, mean ± 95% CI; positive = cheapened)",
                      "bucket")


def chart_regimes(D: pd.DataFrame | None = None, title: str | None = None):
    D = regime_data() if D is None else D
    pts = D[D["p_placebo_same_regime"].notna()]
    flips = int(((pts["p_placebo_same_regime"] < SIG) != pts["significant"]).sum())
    note = ("Robustness, added after seeing the results: with placebo dates restricted to each auction's own regime, "
            + ("no marker changes fill" if flips == 0 else f"{flips} marker(s) change fill")
            + " (p-values in the appendix table). The LDI-stress window (3 auctions) is in the appendix table only: "
              "reported, not interpreted. M3 and M1b end in Jul 2017, so they have no active-QT point.")
    fig_s, fig_p = _dot_chart(D, REGIMES, title or "By regime (bp, mean ± 95% CI; positive = cheapened)", "regime", [note])
    return fig_s, fig_p


# =============================================================================== chart 4: coefficients
def chart_coefficients(D: pd.DataFrame | None = None, title: str | None = None):
    D = coef_data() if D is None else D
    labels = list(COEF_VARS.values())
    ypos = {l: i for i, l in enumerate(labels[::-1])}
    title = title or "What predicts the numbers, using only what is known before bidding (ex-ante regressions; bp, coefficient ± 95% CI)"
    rng_top = (min(D[D.spec.str.startswith(("M2", "M3"))]["lo"].min(), 0) - 0.2,
               max(D[D.spec.str.startswith(("M2", "M3"))]["hi"].max(), 0) + 0.2)
    fig_s, axes = plt.subplots(3, 3, figsize=(14, 11), sharey=True)
    for spec, ptitle, r, c in COEF_PANELS:
        ax = axes[r, c]
        d = D[D["spec"] == spec]
        ax.axvline(0, color=BASELINE, lw=1)
        for _, u in d.iterrows():
            y = ypos[u["label"]]
            ax.plot([u["lo"], u["hi"]], [y, y], color=LINE_COLOUR, lw=2, solid_capstyle="round")
            ax.plot(u["coef"], y, "o", ms=7, mec=LINE_COLOUR, mew=2, mfc=LINE_COLOUR if u["significant"] else SURFACE)
        n = int(d["n"].iloc[0]) if len(d) else 0
        ax.set_title(f"{ptitle} (n = {n})", fontsize=10)
        if r < 2:
            ax.set_xlim(*rng_top)
        ax.set_yticks(range(len(labels)), labels[::-1])
        ax.tick_params(axis="y", labelsize=9)
    ax = axes[2, 2]
    ax.axis("off")
    ax.text(0, 0.95, "How to read", fontweight="bold", fontsize=10, va="top", transform=ax.transAxes)
    ax.text(0, 0.85, "Each dot: the change in the number (bp) when the\nvariable rises by its unit or the condition holds,\n"
                     "holding the others fixed. DV01 is priced at the\nT-1 model yield (known before bidding).\n\n"
                     "Bars: 95% CI, SEs clustered by auction week.\n"
                     "Filled: clustered p < 0.05; hollow otherwise.\nExact p-values: appendix table.\n\n"
                     "Also in every regression: regime dummies\n"
                     "(chart 3) and a constant. Cover and tail are\nnot used: they are known only after bidding\n"
                     "(decision #19). QT sales start in 2022, so\nM3 and M1b (to 2017) have no QT term; M1b\nexcludes new issues by rule, so it has no\nnew-issue term.",
            fontsize=9, color=INK_SECONDARY, va="top", transform=ax.transAxes)
    for a in axes[1]:
        a.set_xlabel("")
    for a in (axes[2, 0], axes[2, 1]):
        a.set_xlabel("bp")
    fig_s.suptitle(title, x=0.01, ha="left", fontweight="bold", fontsize=12)
    fig_s.tight_layout()

    fig_p = make_subplots(rows=3, cols=3, shared_yaxes=True, horizontal_spacing=0.03, vertical_spacing=0.08,
                          subplot_titles=[f"{t} (n = {int(D[D.spec == s]['n'].iloc[0])})" for s, t, _, _ in COEF_PANELS] + [""])
    for spec, ptitle, r, c in COEF_PANELS:
        d = D[D["spec"] == spec]
        fig_p.add_trace(go.Scatter(
            x=d["coef"], y=d["label"], mode="markers", showlegend=False,
            marker=dict(color=LINE_COLOUR, size=9, symbol=["circle" if s else "circle-open" for s in d["significant"]],
                        line=dict(color=LINE_COLOUR, width=2)),
            error_x=dict(type="data", symmetric=False, array=d["hi"] - d["coef"], arrayminus=d["coef"] - d["lo"],
                         color=LINE_COLOUR, thickness=2, width=0),
            customdata=np.stack([d["lo"], d["hi"], d["p_cluster"], d["p_nw"]], axis=1),
            hovertemplate="%{y}: %{x:+.2f} bp<br>95% CI [%{customdata[0]:+.2f}, %{customdata[1]:+.2f}]"
                          "<br>clustered p %{customdata[2]:.3f}; Newey-West p %{customdata[3]:.3f}<extra>" + ptitle + "</extra>"),
            row=r + 1, col=c + 1)
        fig_p.add_vline(x=0, line_color=BASELINE, row=r + 1, col=c + 1)
        if r < 2:
            fig_p.update_xaxes(range=list(rng_top), row=r + 1, col=c + 1)
    fig_p.update_yaxes(categoryorder="array", categoryarray=labels[::-1])
    fig_p.update_xaxes(visible=False, row=3, col=3)
    fig_p.update_yaxes(visible=False, row=3, col=3)
    cell = fig_p.get_subplot(3, 3)
    fig_p.add_annotation(xref="paper", yref="paper", x=cell.xaxis.domain[0], y=cell.yaxis.domain[1],
                         xanchor="left", yanchor="top", align="left",
                         showarrow=False, font=dict(size=12, color=INK_SECONDARY),
                         text="<b>How to read</b><br>Each dot: the change in the number (bp) when the<br>variable rises by "
                              "its unit or the condition holds,<br>holding the others fixed. DV01 is priced at the<br>T-1 model "
                              "yield (known before bidding).<br><br>Bars: 95% CI, SEs "
                              "clustered by auction week.<br>Filled: clustered p < 0.05; hollow otherwise.<br>Exact p-values: "
                              "appendix table.<br><br>Also in every "
                              "regression: regime dummies<br>(chart 3) and a constant. Cover and tail are not<br>used: they are "
                              "known only after bidding (#19).<br>QT sales start in 2022, so M3 and M1b (to 2017)<br>have no QT term; M1b excludes new issues by rule,<br>so it has no new-issue term.")
    fig_p.update_layout(template=PLOTLY_TEMPLATE, height=1000, title=title)
    return fig_s, fig_p


# =============================================================================== appendix: exact p-values
WINDOW_NAMES = {"pre": "pre-auction T-6 → T-1", "day": "auction day T-1 → T", "post": "post-auction T → T+5",
                "pre10": "pre-auction T-10 → T-1 (robustness)", "total": "total move T-10 → T+1",
                "M1b": "level at auction (M1b)", "M1 (same auctions)": "level at auction (M1, same auctions)"}
SET_NAMES = {"M2 (B-β), all years": "M2 (B-β), 1999–2026", "M3, 1999-2017": "M3, 1999–2017", "Levels to 2017": "Levels, 1999–2017"}


REGIME_VARS = {"QE": "QE regime", "LDI": "LDI-stress regime", "active_QT": "Active-QT regime"}


def appendix_table() -> pd.DataFrame:
    """Every number behind charts 2-4 with exact p-values, plus the rows the charts leave out (LDI
    window, M1 on the M1b sample, regime dummies) and the robustness rows added at the chart gate."""
    H = pd.read_csv(an.OUT_DIR / "headline.csv")
    H["note"] = H["note"].fillna("")
    H["window_note"] = H["window_note"].fillna("")
    rows = []
    for _, r in H.iterrows():
        w = r["measure"]
        charted = (w in WINDOWS or w == "M1b") and r["group"] != "LDI stress"
        chart = ("2" if r["by"] in ("all", "bucket") else "3") if charted else "table only"
        notes = [x for x in [r["note"], r["window_note"]] if x]
        rows.append(dict(section="Means", chart=chart, measure=SET_NAMES[r["set"]],
                         group="all auctions" if r["group"] == "all" else r["group"], window=WINDOW_NAMES.get(w, w),
                         n=int(r["n"]), estimate_bp=r["mean_bp"], ci_low=r["mean_bp"] - Z95 * r["se_cluster"],
                         ci_high=r["mean_bp"] + Z95 * r["se_cluster"], lead_p=r["lead_p"], lead_test=r["lead_p_source"],
                         p_placebo=r["p_placebo"], n_placebo=r["n_placebo"],
                         p_placebo_same_regime=r["p_placebo_same_regime"], p_clustered=r["p_cluster"],
                         p_newey_west=r["p_nw"], note="; ".join(notes)))
    R = pd.read_csv(an.OUT_DIR / "regressions.csv")
    R = R[(R["specification"] == "ex-ante") & (R["variable"] != "const") & R["spec"].isin([c[0] for c in COEF_PANELS])]
    titles = {c[0]: c[1] for c in COEF_PANELS}
    for _, r in R.iterrows():
        base = "QE" if r["spec"].startswith("M1, gilt FE") else "pre-crisis"
        note = an.LDI_NOTE if r["variable"] == "LDI" else ""
        if r["variable"] in REGIME_VARS:
            note = "; ".join(x for x in [f"base regime: {base}", note] if x)
        rows.append(dict(section="Ex-ante regressions", chart="4" if r["variable"] in COEF_VARS else "table only",
                         measure=titles[r["spec"]], group="",
                         window=COEF_VARS.get(r["variable"], REGIME_VARS.get(r["variable"], r["variable"])),
                         n=int(r["n"]), estimate_bp=r["coef"], ci_low=r["coef"] - Z95 * r["se_cluster"],
                         ci_high=r["coef"] + Z95 * r["se_cluster"], lead_p=r["p_cluster"], lead_test="clustered",
                         p_placebo=np.nan, n_placebo=np.nan, p_placebo_same_regime=np.nan, p_clustered=r["p_cluster"],
                         p_newey_west=r["p_nw"], note=note))
    T = pd.DataFrame(rows)
    order = {"2": 0, "3": 1, "4": 0, "table only": 2}
    T["_o"] = T["chart"].map(order)
    T["_s"] = (T["section"] != "Means").astype(int)
    return T.sort_values(["_s", "_o"], kind="stable").drop(columns=["_o", "_s"]).reset_index(drop=True)


APPENDIX_COLUMNS = {  # column: header in the HTML table
    "chart": "Chart", "measure": "Measure", "group": "Group", "window": "Window / variable", "n": "n",
    "estimate_bp": "Estimate (bp)", "ci": "95% CI", "lead_p": "Lead p", "lead_test": "Lead test",
    "p_placebo": "Placebo p (decision #18)", "n_placebo": "n placebo",
    "p_placebo_same_regime": "Placebo p, own-regime dates (robustness, added after seeing results)",
    "p_clustered": "Clustered p", "p_newey_west": "Newey-West p", "note": "Note"}


def _p(v, placebo=False) -> str:
    if pd.isna(v):
        return ""
    if placebo:
        return "< 0.001" if v < 0.001 else f"{v:.3f}"         # 1,000 draws: steps of 0.001
    return f"{v:.3f}" if v >= 0.001 else f"{v:.1e}"


def appendix_html(T: pd.DataFrame) -> str:
    """A self-contained HTML page for the report's appendix (light and dark)."""
    F = T.copy()
    F["estimate_bp"] = F["estimate_bp"].map("{:+.2f}".format)
    F["ci"] = [f"[{a:+.2f}, {b:+.2f}]" for a, b in zip(T["ci_low"], T["ci_high"])]
    F["lead_p"] = [_p(v, s == "placebo-centred") for v, s in zip(T["lead_p"], T["lead_test"])]
    F["p_placebo"] = T["p_placebo"].map(lambda v: _p(v, True))
    F["p_placebo_same_regime"] = T["p_placebo_same_regime"].map(lambda v: _p(v, True))
    F["p_clustered"] = T["p_clustered"].map(_p)
    F["p_newey_west"] = T["p_newey_west"].map(_p)
    F["n_placebo"] = T["n_placebo"].map(lambda v: "" if pd.isna(v) else f"{int(v)}")
    F["lead_test"] = F["lead_test"].replace({"placebo-centred": "placebo-centred", "clustered": "clustered"})
    sections = []
    for sec in ["Means", "Ex-ante regressions"]:
        body = F[F["section"] == sec][list(APPENDIX_COLUMNS)].rename(columns=APPENDIX_COLUMNS)
        sections.append(f"<h2>{sec}</h2>" + body.to_html(index=False, escape=True, border=0, classes="t"))
    notes = (
        "<p>Exact p-values for every point in report charts 2–4, and for the rows the charts leave out. "
        "<b>Lead p</b> (decision #20) is the placebo-centred p for M2 and M3 means: the share of 1,000 placebo means at "
        "least as far from the placebo centre as the real mean (steps of 0.001; “&lt; 0.001” = no draw as extreme). "
        "It is the clustered p (t with G−1 df, clusters = auction weeks) for M1b/M1 levels and for coefficients, which "
        "have no placebo. 95% CI = estimate ± 1.96 clustered SE. Placebo p uses the auctions with an eligible placebo "
        "date (n placebo).</p><p><b>Added after seeing the results (chart gate, 21 Oct 2026):</b> the placebo with dates "
        "in the auction's own regime (robustness column), the pre-auction window T-10 → T-1 for M2 and M3 "
        "(robustness), and the M3 total move T-10 → T+1. The LDI-stress window (3 auctions in 2 weeks) is reported, "
        "not interpreted. Positive = the gilt cheapened.</p>")
    css = """
:root{--bg:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--band:#f0efec}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#161615;--ink:#f2f1ee;--ink2:#c9c7c0;
--muted:#9b998f;--grid:#3a3935;--band:#22211f}}
:root[data-theme="dark"]{--bg:#161615;--ink:#f2f1ee;--ink2:#c9c7c0;--muted:#9b998f;--grid:#3a3935;--band:#22211f}
body{background:var(--bg);color:var(--ink2);font:13px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif;margin:24px 16px}
h1{color:var(--ink);font-size:18px;margin:0 0 8px}h2{color:var(--ink);font-size:15px;margin:24px 0 8px}
p{max-width:980px}.wrap{overflow-x:auto}
table.t{border-collapse:collapse;font-variant-numeric:tabular-nums;white-space:nowrap}
table.t th{color:var(--ink);text-align:left;font-weight:600;border-bottom:1px solid var(--grid);padding:6px 10px;
position:sticky;top:0;background:var(--bg);white-space:normal;max-width:180px;vertical-align:bottom}
table.t td{border-bottom:1px solid var(--grid);padding:4px 10px}
table.t tr:hover td{background:var(--band)}
"""
    return ("<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
            "content='width=device-width,initial-scale=1'><title>Appendix: exact p-values</title>"
            f"<style>{css}</style></head><body><h1>Appendix: exact p-values</h1>{notes}"
            f"<div class='wrap'>{''.join(sections)}</div></body></html>")


def write_appendix() -> tuple:
    T = appendix_table()
    paths.TABLES.mkdir(parents=True, exist_ok=True)
    csv, html = paths.TABLES / "appendix_p_values.csv", paths.TABLES / "appendix_p_values.html"
    T.to_csv(csv, index=False)
    html.write_text(appendix_html(T), encoding="utf-8")
    return csv, html


# =============================================================================== all
CHARTS = {"report_1_paths": chart_paths, "report_2_by_bucket": chart_buckets,
          "report_3_by_regime": chart_regimes, "report_4_ex_ante_drivers": chart_coefficients}


REPORT_FILE = paths.REPORTS / "report_final.md"
CAPTION_RE = re.compile(r"^!\[Chart (\d+)\. (.+?)\]\(figures/(report_\d+_[a-z0-9_]+)\.png\)\s*$", re.M)


def report_titles(path=REPORT_FILE) -> dict:
    """{chart file name: title} from the report's image captions: "Chart N. <title>. <more>" -> <title>
    (the first sentence after "Chart N."). The chart number must match the file's report_N prefix."""
    out = {}
    for n, alt, name in CAPTION_RE.findall(path.read_text(encoding="utf-8")):
        if not name.startswith(f"report_{n}_"):
            raise ValueError(f"caption 'Chart {n}' points at {name}")
        out[name] = re.split(r"\.(?:\s|$)", alt, maxsplit=1)[0]
    return out


def main() -> dict:
    plotting.set_seaborn_theme()
    titles = report_titles() if REPORT_FILE.exists() else {}
    if REPORT_FILE.exists() and set(titles) != set(CHARTS):
        raise ValueError(f"report captions cover {sorted(titles)}, charts are {sorted(CHARTS)}")
    out = {}
    for name, f in CHARTS.items():
        fig_s, fig_p = f(title=titles.get(name))
        out[name] = plotting.save_pair(name, fig_s, fig_p)
        plotting.close(fig_s)
    out["appendix_p_values"] = write_appendix()
    return out


if __name__ == "__main__":
    for name, (png, html) in main().items():
        print(name, png, html)
