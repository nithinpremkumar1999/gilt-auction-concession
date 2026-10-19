"""Bank of England nominal spot curve: loading and pricing gilts off it.

Layout of every BoE GLC nominal workbook (checked for all archive workbooks 1979-2026 and the
current-month file, 19 Oct 2026): sheet 0 = info, 1-2 = forwards, 3 = spot short end
(1 month to 5 years, monthly), 4 = spot curve (0.5 years upwards, half-yearly; 25y maximum to
end-2015, 40y from 2016). Row 3 holds maturities in years, data start on row 5, column 0 = date.
"""
import io
import re
import zipfile

import numpy as np
import pandas as pd
from scipy.interpolate import CubicSpline

from .pricing import cash_flows, yield_from_dirty


def _read_spot_sheet(xls, sheet_index):
    """One spot sheet as a DataFrame: index = dates, columns = maturities in years (floats)."""
    raw = pd.read_excel(xls, sheet_name=sheet_index, header=None)
    # row 3 (0-based) holds maturities in years; data from row 5; column 0 = dates
    mats = pd.to_numeric(raw.iloc[3, 1:], errors="coerce")
    data = raw.iloc[5:, :].copy()
    data = data[pd.to_datetime(data.iloc[:, 0], errors="coerce").notna()]
    data.index = pd.to_datetime(data.iloc[:, 0]).dt.normalize()
    data = data.iloc[:, 1:]
    data.columns = mats.values
    data = data.loc[:, data.columns.notna()].apply(pd.to_numeric, errors="coerce")
    return data


def load_spot_curves(zip_path, workbook_pattern):
    """Spliced daily spot curves (% cont. comp.) from one workbook inside the BoE ZIP.

    workbook_pattern: regex matching the workbook name, e.g. r'2016 to 2024'.
    Returns DataFrame: index = dates, columns = maturities in years (short end <= 5y, long > 5y).
    Sheets are taken by position: 3 = spot short end, 4 = spot curve (0 = info)."""
    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist() if re.search(workbook_pattern, n)]
        if len(names) != 1:
            raise ValueError(f"pattern {workbook_pattern!r} matched {names}")
        xls = pd.ExcelFile(io.BytesIO(z.read(names[0])))
    return _splice_spot(xls)


def load_spot_workbook(path):
    """Spliced daily spot curves (% cont. comp.) from one extracted BoE workbook (.xlsx).

    Same output as load_spot_curves(); use this for the extracted files in data/raw_data/glc_nominal.
    """
    return _splice_spot(pd.ExcelFile(path))


def _splice_spot(xls):
    """Short-end sheet up to 5y + long sheet beyond 5y; empty (holiday) rows dropped."""
    short = _read_spot_sheet(xls, 3)
    long_ = _read_spot_sheet(xls, 4)
    curves = pd.concat([short.loc[:, short.columns <= 5.0 + 1e-6],
                        long_.loc[:, long_.columns > 5.0 + 1e-6]], axis=1)
    curves.columns = np.round(curves.columns.astype(float), 6)
    curves = curves.loc[:, ~curves.columns.duplicated()].sort_index(axis=1)
    return curves.dropna(how="all")                      # drop holiday rows


def curve_function(curves, date):
    """z(t) in % for one date: natural cubic spline, flat beyond the first/last available maturity."""
    row = curves.loc[pd.Timestamp(date)].dropna()
    t, z = row.index.to_numpy(float), row.to_numpy(float)
    spline = CubicSpline(t, z, bc_type="natural")
    return lambda x: spline(np.clip(np.asarray(x, float), t[0], t[-1]))


def model_dirty(settle, maturity, coupon, zfun, first_issue=None, first_coupon=None):
    """Dirty price per £100 nominal: the gilt's cash flows discounted on the curve zfun.

    DF = exp(-z/100 * t), t = (cash flow date - settle).days / 365.25.
    NOTE (decision #4, to be implemented in Stage 2): when settle < first_issue this still
    discounts from settle, while cash_flows() and yield_from_dirty() price for settlement on
    first_issue. Stage 2 changes this to discount from the first issue date.
    """
    cf = cash_flows(settle, maturity, coupon, first_issue, first_coupon)
    t = np.array([(d - settle).days / 365.25 for d in cf["dates"]])
    return float(np.sum(cf["amounts"] * np.exp(-zfun(t) / 100.0 * t)))


def model_yield(settle, maturity, coupon, zfun, first_issue=None, first_coupon=None):
    """Semi-annual GRY (decimal) of the gilt priced exactly on the curve."""
    d = model_dirty(settle, maturity, coupon, zfun, first_issue, first_coupon)
    return yield_from_dirty(settle, maturity, coupon, d, first_issue, first_coupon)
