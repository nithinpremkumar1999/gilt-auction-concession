"""Bank of England nominal spot curve: the daily curve panel and the curve pricer (Stage 2, spec §5).

Conventions (spec §5; decisions #5 and #10 in the spec log)
----------------------------------------------------------
* BoE spot rates z are % per year, continuously compounded: DF(t) = exp(-z(t)/100 * t), with
  t = (cash flow date - settlement).days / 365.25.
* Splice: short-end sheet for maturities <= 5y (monthly grid) + long sheet for maturities > 5y
  (half-yearly grid). Natural cubic spline in z through the day's available maturities.
* Below the first available maturity t_min: z is held flat at z(t_min).
* Beyond the last available maturity T (23y in Jan 1998, 25y from 29 Jan 1998 to end-2015, 40y from
  2016): FLAT FORWARD (spec decision #5). The BoE instantaneous forward at T, f(T), from the forward
  sheet on the same day, is held constant beyond T:
        z(t) * t = z(T) * T + f(T) * (t - T)        for t > T.
  z is continuous at T. Every price that uses this region is flagged (`beyond_curve`).
* Holiday rows (empty) are dropped, never filled. If a curve date is missing, the previous
  available date is used and flagged (`curve_on` returns the flag).
* When-issued (decision #10, "discount only from first issue date"): a gilt that
  settles before its first issue date is priced for settlement on the first issue date. Cash flows
  are discounted from that date, consistent with `cash_flows()` and `yield_from_dirty()`.
* Model yield = the semi-annual GRY at which `gilt_price()` reproduces the curve dirty price
  (brentq, in `pricing.yield_from_dirty`). One `cash_flows()` feeds both.

Workbook layout (checked for all archive workbooks 1979-2026 and the current-month file, 19 Oct
2026): sheet 0 = info, 1 = forwards short end, 2 = forward curve, 3 = spot short end (1 month to 5
years, monthly), 4 = spot curve (0.5 years upwards, half-yearly). Row 3 holds maturities in years,
data start on row 5, column 0 = date. Sheets 2 and 4 share their maturity grid, and on every day
1995-2026 the last available maturity is the same in both (checked in notebook 02).

The panel
---------
`build_panel()` writes data/processed_data/curves/boe_nominal_spot_daily.csv.gz: one row per BoE
curve date from config.CURVE_PANEL_START, spliced spot z by maturity (columns in years), plus
t_min, t_max, z_tmax, f_tmax and the source workbook. `load_panel()` reads it.

Typical use
-----------
    panel = load_panel()
    curve, curve_date, fallback = curve_on(panel, dt.date(2016, 3, 15))
    settle = next_business_day(curve_date)
    y = model_yield(settle, maturity, coupon, curve, first_issue, first_coupon)   # decimal
    flag = beyond_curve(settle, maturity, curve, first_issue)
"""
import datetime as dt
import io
import re
import zipfile
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd
from scipy.interpolate import CubicSpline

from . import config, paths
from .pricing import cash_flows, yield_from_dirty

SPLICE_AT = 5.0                                  # years: short-end sheet up to here, long sheet beyond
CURVE_WORKBOOKS = ("1995 to 1999", "2000 to 2004", "2005 to 2015", "2016 to 2024", "2025 to present")
CURRENT_MONTH_LABEL = "current month"
PANEL_DIR = paths.PROCESSED / "curves"
PANEL_FILE = PANEL_DIR / "boe_nominal_spot_daily.csv.gz"
META_COLUMNS = ["source", "t_min", "t_max", "z_tmax", "f_tmax"]
EXTRAPOLATIONS = ("flat_forward", "flat_z")      # flat_forward = spec decision #5; flat_z for diagnostics


# ============================================================================ reading the workbooks
def _read_sheet(xls, sheet_index):
    """One curve sheet as a DataFrame: index = dates, columns = maturities in years (floats).
    Rows whose first column is not a date (titles, notes) are dropped."""
    raw = pd.read_excel(xls, sheet_name=sheet_index, header=None)
    mats = pd.to_numeric(raw.iloc[3, 1:], errors="coerce")       # row 3: maturities in years
    data = raw.iloc[5:, :].copy()                                  # data start on row 5
    data = data[pd.to_datetime(data.iloc[:, 0], errors="coerce").notna()]
    data.index = pd.to_datetime(data.iloc[:, 0]).dt.normalize()
    data = data.iloc[:, 1:]
    data.columns = mats.values
    data = data.loc[:, data.columns.notna()].apply(pd.to_numeric, errors="coerce")
    data.columns = np.round(data.columns.astype(float), 6)
    return data


_read_spot_sheet = _read_sheet                   # name used before Stage 2


def _splice(short, long_):
    """Short-end columns up to SPLICE_AT + long columns beyond it; empty (holiday) rows dropped."""
    curves = pd.concat([short.loc[:, short.columns <= SPLICE_AT + 1e-6],
                        long_.loc[:, long_.columns > SPLICE_AT + 1e-6]], axis=1)
    curves.columns = np.round(curves.columns.astype(float), 6)
    curves = curves.loc[:, ~curves.columns.duplicated()].sort_index(axis=1)
    return curves.dropna(how="all")


def _splice_spot(xls):
    """Spliced spot curves from sheets 3 (short end) and 4 (long)."""
    return _splice(_read_sheet(xls, 3), _read_sheet(xls, 4))


def load_spot_workbook(path):
    """Spliced daily spot curves (% cont. comp.) from one extracted BoE workbook (.xlsx).
    Index = dates, columns = maturities in years; holiday rows dropped."""
    return _splice_spot(pd.ExcelFile(path))


def load_spot_curves(zip_path, workbook_pattern):
    """As load_spot_workbook(), for a workbook inside the BoE ZIP (pattern e.g. r'2016 to 2024')."""
    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist() if re.search(workbook_pattern, n)]
        if len(names) != 1:
            raise ValueError(f"pattern {workbook_pattern!r} matched {names}")
        xls = pd.ExcelFile(io.BytesIO(z.read(names[0])))
    return _splice_spot(xls)


def _workbook_panel(item):
    """Panel rows from one workbook: spliced spot z plus t_min, t_max, z(t_max), f(t_max), source."""
    label, path = item
    xls = pd.ExcelFile(path)
    spot = _splice_spot(xls)
    fwd = _read_sheet(xls, 2).reindex(spot.index)
    long_ = _read_sheet(xls, 4).reindex(spot.index)
    t_max = long_.apply(lambda r: r.last_valid_index(), axis=1).astype(float)
    t_max_fwd = fwd.apply(lambda r: r.last_valid_index(), axis=1).astype(float)
    if not np.allclose(t_max, t_max_fwd):
        raise ValueError(f"{label}: last maturity differs between the spot and forward sheets")
    meta = pd.DataFrame(index=spot.index)
    meta["source"] = label
    meta["t_min"] = spot.apply(lambda r: r.first_valid_index(), axis=1).astype(float)
    meta["t_max"] = t_max
    meta["z_tmax"] = [spot.at[d, t] for d, t in zip(spot.index, t_max)]
    meta["f_tmax"] = [fwd.at[d, t] for d, t in zip(fwd.index, t_max)]
    if meta[["z_tmax", "f_tmax"]].isna().any().any():
        raise ValueError(f"{label}: missing z or forward at the last maturity")
    return pd.concat([meta, spot], axis=1), len(_read_sheet(xls, 3)) - len(spot)


# ============================================================================ the panel
def build_panel(write: bool = True, start: dt.date = config.CURVE_PANEL_START) -> pd.DataFrame:
    """Daily BoE nominal spot curve panel from `start` to the last date in raw_data.

    Reads the archive workbooks from 1995 and the current-month file. Holiday rows (empty) are
    dropped. Workbooks do not overlap; if they ever did, identical rows are kept once and
    differing rows raise. Writes PANEL_FILE when write=True and returns the panel (index = dates,
    META_COLUMNS then maturity columns as floats)."""
    sources = [(lab, paths.curve_workbook(lab)) for lab in CURVE_WORKBOOKS]
    sources.append((CURRENT_MONTH_LABEL, paths.CURVE_CURRENT_MONTH))
    with ProcessPoolExecutor(max_workers=len(sources)) as pool:
        parts = list(pool.map(_workbook_panel, sources))
    P = pd.concat([p for p, _ in parts], axis=0)
    mats = sorted(c for c in P.columns if not isinstance(c, str))
    P = P[META_COLUMNS + mats].sort_index()
    dup = P.index.duplicated(keep="first")
    if dup.any():
        d = P.index[dup]
        a = P[~dup].loc[d, mats].to_numpy(float)
        b = P[dup].loc[d, mats].to_numpy(float)
        if not np.allclose(np.nan_to_num(a), np.nan_to_num(b), atol=0, rtol=0):
            raise ValueError(f"overlapping workbooks disagree on {len(d)} dates")
        P = P[~dup]
    P = P[P.index >= pd.Timestamp(start)]
    P.index.name = "date"
    if write:
        PANEL_DIR.mkdir(parents=True, exist_ok=True)
        out = P.copy()
        out.columns = [c if isinstance(c, str) else f"{c:.6f}" for c in out.columns]
        out.to_csv(PANEL_FILE, date_format="%Y-%m-%d")
    return P


def load_panel(build_if_missing: bool = True) -> pd.DataFrame:
    """The curve panel from PANEL_FILE (built from raw_data first if missing, ~15 s)."""
    if not PANEL_FILE.exists():
        if not build_if_missing:
            raise FileNotFoundError(PANEL_FILE)
        build_panel()
    P = pd.read_csv(PANEL_FILE, index_col="date", parse_dates=["date"], float_precision="round_trip")
    P.columns = [c if c in META_COLUMNS else float(c) for c in P.columns]
    return P


def maturity_columns(panel: pd.DataFrame) -> list:
    """The maturity (float) columns of the panel, in order."""
    return [c for c in panel.columns if not isinstance(c, str)]


# ============================================================================ one day's curve
class Curve:
    """One day's BoE spot curve as a function z(t) in % (continuously compounded).

    Natural cubic spline through the available maturities; flat z below t_min; beyond t_max flat
    forward (default, spec decision #5) or flat z (`extrapolation='flat_z'`, diagnostics only).
    Calling the object returns z(t), so it can be passed wherever a z-function is expected.
    """

    def __init__(self, date, maturities, rates, f_tmax, extrapolation: str = "flat_forward"):
        if extrapolation not in EXTRAPOLATIONS:
            raise ValueError(f"extrapolation must be one of {EXTRAPOLATIONS}")
        t = np.asarray(maturities, float)
        z = np.asarray(rates, float)
        ok = np.isfinite(z)
        self.date = date
        self.t, self.zs = t[ok], z[ok]
        self.t_min, self.t_max = float(self.t[0]), float(self.t[-1])
        self.z_tmax = float(self.zs[-1])
        self.f_tmax = float(f_tmax)
        self.extrapolation = extrapolation
        self._spline = CubicSpline(self.t, self.zs, bc_type="natural")

    def z(self, t):
        """Spot rate (% cont. comp.) at maturity t (years); scalar or array."""
        t = np.asarray(t, float)
        out = np.empty_like(t)
        lo, hi = t < self.t_min, t > self.t_max
        mid = ~lo & ~hi
        out[mid] = self._spline(t[mid])
        out[lo] = self.zs[0]
        if self.extrapolation == "flat_forward":
            out[hi] = (self.z_tmax * self.t_max + self.f_tmax * (t[hi] - self.t_max)) / t[hi]
        else:
            out[hi] = self.z_tmax
        return out if out.ndim else float(out)

    __call__ = z

    def discount(self, t):
        """Discount factor exp(-z(t)/100 * t)."""
        t = np.asarray(t, float)
        return np.exp(-self.z(t) / 100.0 * t)

    def __repr__(self):
        return (f"Curve({self.date}, {self.t_min:.3f}-{self.t_max:.1f}y, {self.extrapolation}, "
                f"f(T)={self.f_tmax:.3f}%)")


def curve_on(panel: pd.DataFrame, date, extrapolation: str = "flat_forward"):
    """(Curve, curve date used, fallback flag) for `date`.

    If `date` has no curve (a missing date), the previous available date is used and the flag is
    True (spec §5). Dates before the first or after the last curve date raise ValueError: those
    are outside the panel, not missing."""
    ts = pd.Timestamp(date)
    idx = panel.index
    if ts < idx[0] or ts > idx[-1]:
        raise ValueError(f"{ts.date()} is outside the curve panel ({idx[0].date()} to {idx[-1].date()})")
    fallback = ts not in idx
    used = idx[idx.searchsorted(ts, side="right") - 1]
    row = panel.loc[used]
    mats = maturity_columns(panel)
    curve = Curve(used.date(), mats, row[mats].to_numpy(float), row["f_tmax"], extrapolation)
    return curve, used.date(), bool(fallback)


def curve_function(curves, date):
    """Module 2 exercise version, kept for Nithin's notebook: z(t) in % for one date from a
    load_spot_workbook() frame, natural cubic spline, flat z beyond BOTH ends. The study uses
    curve_on() (flat forward beyond the last maturity, decision #5)."""
    row = curves.loc[pd.Timestamp(date)].dropna()
    t, z = row.index.to_numpy(float), row.to_numpy(float)
    spline = CubicSpline(t, z, bc_type="natural")
    return lambda x: spline(np.clip(np.asarray(x, float), t[0], t[-1]))


# ============================================================================ pricing off the curve
def effective_settlement(settle: dt.date, first_issue: dt.date | None = None) -> dt.date:
    """Settlement used for pricing: the first issue date if the trade settles before it (a
    when-issued new gilt), else the settlement date."""
    return settle if first_issue is None or settle >= first_issue else first_issue


def model_dirty(settle, maturity, coupon, zfun, first_issue=None, first_coupon=None) -> float:
    """Dirty price per £100 nominal: the gilt's cash flows discounted on the curve `zfun`
    (a Curve, or any function t -> z in %). DF = exp(-z/100 * t), t from the effective settlement
    date (first issue date for a when-issued new gilt) in days / 365.25."""
    eff = effective_settlement(settle, first_issue)
    cf = cash_flows(eff, maturity, coupon, first_issue, first_coupon)
    t = np.array([(d - eff).days / 365.25 for d in cf["dates"]])
    return float(np.sum(np.asarray(cf["amounts"], float) * np.exp(-np.asarray(zfun(t), float) / 100.0 * t)))


def model_yield(settle, maturity, coupon, zfun, first_issue=None, first_coupon=None) -> float:
    """Semi-annual GRY (decimal) of the gilt priced exactly on the curve, for the same effective
    settlement as model_dirty()."""
    eff = effective_settlement(settle, first_issue)
    d = model_dirty(eff, maturity, coupon, zfun, first_issue, first_coupon)
    return yield_from_dirty(eff, maturity, coupon, d, first_issue, first_coupon)


def years_beyond_curve(settle, maturity, curve: Curve, first_issue=None) -> float:
    """Years of cash flows beyond the curve's last maturity (decision #12): time to maturity from the
    effective settlement date minus t_max, floored at 0. Robustness drops auctions with more than
    config.MAX_YEARS_BEYOND_CURVE years beyond."""
    eff = effective_settlement(settle, first_issue)
    return max(0.0, (maturity - eff).days / 365.25 - curve.t_max)


def beyond_curve(settle, maturity, curve: Curve, first_issue=None) -> bool:
    """True if the gilt's last cash flow lies beyond the curve's last maturity, i.e. its price uses
    the extrapolated region (flag every affected auction, spec §5)."""
    eff = effective_settlement(settle, first_issue)
    return (maturity - eff).days / 365.25 > curve.t_max + 1e-9
