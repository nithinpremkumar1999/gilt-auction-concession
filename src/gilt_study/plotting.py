"""One chart, two outputs (decision #8): a seaborn PNG for notebooks and a Plotly HTML for the webpage.

Both libraries draw from the same tidy DataFrame and share one visual system, so the static and
interactive versions of a chart look alike:
  * categorical colours assigned in a fixed order (never cycled, never by rank); the order is
    colour-blind-checked for adjacent series (validated 19 Oct 2026: worst adjacent CVD Delta E 24.7
    for slots 1-2)
  * text in ink colours, never in a series colour
  * hairline solid gridlines, recessive axes, 2px lines, >= 8px markers
  * one y-axis per chart (no dual axes)

Usage
    set_seaborn_theme()
    fig_s = ...seaborn/matplotlib figure...
    fig_p = ...plotly figure (template=PLOTLY_TEMPLATE)...
    save_pair("coverage", fig_s, fig_p)   # -> reports/figures/coverage.png, reports/interactive/coverage.html
"""
from pathlib import Path

import matplotlib.pyplot as plt
import plotly.graph_objects as go
import plotly.io as pio
import seaborn as sns

from . import paths

# ------------------------------------------------------------------ palette (light surface)
SURFACE = "#fcfcfb"
INK = "#0b0b0b"          # titles, values
INK_SECONDARY = "#52514e"  # labels
INK_MUTED = "#898781"    # axis ticks
GRID = "#e1e0d9"         # hairline gridlines
BASELINE = "#c3c2b7"     # axis lines
NEUTRAL_BAND = "#f0efec"  # background bands (e.g. study window, regime shading)

# Categorical slots in fixed order. Three or more series in a scatter/small-multiple context:
# use only the first three (all-pairs safe), fold the rest into "Other".
CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]

FONT_FAMILY = "system-ui, -apple-system, 'Segoe UI', sans-serif"


def colour_map(categories) -> dict:
    """Fixed category -> colour mapping in the order given (pass the full, stable list of categories
    so a filtered chart keeps each survivor's colour)."""
    cats = list(dict.fromkeys(categories))
    if len(cats) > len(CATEGORICAL):
        raise ValueError(f"{len(cats)} categories > {len(CATEGORICAL)} slots: fold the tail into 'Other'")
    return dict(zip(cats, CATEGORICAL))


# ------------------------------------------------------------------ seaborn / matplotlib
def set_seaborn_theme():
    """Apply the shared look to seaborn and matplotlib (call once per notebook or script)."""
    sns.set_theme(style="whitegrid", palette=CATEGORICAL, rc={
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": BASELINE, "axes.linewidth": 0.8, "axes.labelcolor": INK_SECONDARY,
        "axes.titlecolor": INK, "axes.titleweight": "bold", "axes.titlesize": 12,
        "axes.titlelocation": "left", "axes.spines.top": False, "axes.spines.right": False,
        "grid.color": GRID, "grid.linewidth": 0.8, "grid.linestyle": "-",
        "xtick.color": INK_MUTED, "ytick.color": INK_MUTED, "text.color": INK,
        "lines.linewidth": 2, "lines.markersize": 8, "legend.frameon": False,
        "font.family": "sans-serif", "font.sans-serif": ["DejaVu Sans", "Segoe UI", "Arial"],
    })


# ------------------------------------------------------------------ plotly
PLOTLY_TEMPLATE = go.layout.Template(
    layout=dict(
        font=dict(family=FONT_FAMILY, color=INK_SECONDARY, size=13),
        title=dict(font=dict(color=INK, size=16), x=0, xanchor="left"),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE, colorway=CATEGORICAL,
        xaxis=dict(gridcolor=GRID, gridwidth=1, linecolor=BASELINE, zeroline=False, automargin=True,
                   tickfont=dict(color=INK_MUTED), title=dict(font=dict(color=INK_SECONDARY))),
        yaxis=dict(gridcolor=GRID, gridwidth=1, linecolor=BASELINE, zeroline=False, automargin=True,
                   tickfont=dict(color=INK_MUTED), title=dict(font=dict(color=INK_SECONDARY))),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=INK_SECONDARY)),
        hoverlabel=dict(bgcolor="white", bordercolor=BASELINE, align="left",
                        font=dict(color=INK, family=FONT_FAMILY)),
        hovermode="closest", margin=dict(l=60, r=30, t=70, b=50),
    ),
    data=dict(scatter=[go.Scatter(line=dict(width=2), marker=dict(size=8))]),
)
pio.templates["gilt_study"] = PLOTLY_TEMPLATE


# ------------------------------------------------------------------ saving
def save_pair(name: str, fig_static, fig_interactive, dpi: int = 150) -> tuple[Path, Path]:
    """Save the seaborn/matplotlib figure as reports/figures/<name>.png and the Plotly figure as
    reports/interactive/<name>.html. The HTML loads plotly.js from its CDN (small files; needs
    internet to view). Returns both paths."""
    paths.FIGURES.mkdir(parents=True, exist_ok=True)
    paths.INTERACTIVE.mkdir(parents=True, exist_ok=True)
    png = paths.FIGURES / f"{name}.png"
    html = paths.INTERACTIVE / f"{name}.html"
    fig_static.savefig(png, dpi=dpi, bbox_inches="tight")
    fig_interactive.write_html(html, include_plotlyjs="cdn", full_html=True)
    return png, html


def close(fig_static):
    """Close a matplotlib figure after saving (keeps notebook memory flat)."""
    plt.close(fig_static)
