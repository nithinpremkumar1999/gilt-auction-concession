"""Stage 3: the auction panel, one row per conventional gilt auction (build spec §6).

Sample: conventional auctions dated 1 Nov 1998 (decision #7) to 30 Sep 2026 (spec §2). The first
auction in the window is 26 May 1999; there are 912.

Where each field comes from
---------------------------
* D2.1A (auction results): auction date, gilt name, nominal issued via auction and via the PAOF,
  total cash raised, bid-to-cover, average accepted price (AAP), yield at the AAP (the average
  accepted yield, AAY) and the tail. D2.1A is the source for prices and yields (D2.1E truncates
  them). Index-linked auctions are excluded by `data_io.is_index_linked` (case-insensitive; the
  DMO spells five 2018-21 linker auctions "Index-Linked").
* D2.1E (issuance history): the ISIN and the settlement date. The auction's D2.1E row is the
  first *priced* conventional row after the auction date (within 5 days) with the same coupon
  and maturity year, and the same total nominal as D2.1A (auction + PAOF). Its issue date is the
  settlement date (spec §4: taken from the DMO, not assumed T+1). Unpriced rows are direct
  issues to the DMO and are never matched.
* gilt_terms (Stage 1, P3-P4): maturity, first issue date, first coupon date and its source.
  New issue = the auction settles on the gilt's first issue date (its launch); otherwise a
  reopening.
* Curve panel (Stage 2): the T-1 close curve (previous UK business day; flagged fallback if
  missing), its last maturity, and years of cash flows beyond it (decision #12).

Derived fields (each stated here so nothing is decided silently)
------------------------------------------------------------------
* nominal_offered = the amount allotted at the auction (D2.1A 'issued via auction'). The DMO
  allots the full amount on offer at conventional auctions, including the one uncovered auction
  (25 Mar 2009, 4¼% 2049: offered £1,750m, bids £1,627m, allotted £1,750m; DMO result notice).
* paof_takeup: D2.1A PAOF column; 0 when blank from 1 Jun 2009 (PAOF start), missing before.
* yield_at_lowest_accepted_price (the highest accepted yield) = AAY + tail / 100 (D2.1A tail is
  the DMO's definition: yield at the lowest accepted price minus the AAY, from unrounded yields).
* years_to_maturity: (maturity - settlement date) / 365.25.
* bucket (spec §6, DMO remit bands): short < 7y, medium 7-15y, long > 15y, on years_to_maturity.
* dv01_per_100: `pricing.gilt_price()` DV01 (dirty, per £100 nominal, per 1bp) at the AAY for
  settlement on the issue date. Auction DV01 (£ per bp) = dv01_per_100 x nominal / 100, given
  for the auction allotment and for the total including the PAOF.
* regime (spec §8, decision #14, by auction date): pre-crisis (to Dec 2008), QE (2009 - 22 Sep
  2022), LDI stress (23 Sep - 14 Oct 2022), active QT (1 Nov 2022 - 16 Sep 2026),
  post-QT-decision (17 Sep 2026 on). The passive-QT months Feb-Oct 2022 outside the LDI window
  (including 15-31 Oct 2022) are in QE and flagged `passive_qt_2022` (robustness: drop them).
* Supply controls (spec §6/§8): operations from 5 UK business days before to 5 after the auction
  date (inclusive): syndications (D10A), tenders (D2.1PROF9), BoE QT sales (days with an
  allocation), BoE APF QE purchases (days with an allocation). `qe_purchase_week` and
  `qt_sale_week` are the dummies. Taps and mini-tender re-sales (other operations file) and the
  2022 financial-stability purchases and sales (#11) are recorded separately, not in the dummies.
* Rate volatility: standard deviation of the daily changes (bp) in the BoE spot rate over the 20
  changes ending at T-1, at the auctioned gilt's own maturity and at 10 years.
* tail_bp_regression = tail_bp, set to missing where the published tail is negative (4 Mar 2009,
  decision #15); tail_bp keeps the published value.

Main and robustness variables (decision #15)
--------------------------------------------
  volatility      main: vol_own_maturity_20d_bp          robustness: vol_10y_20d_bp
  auction DV01    main: dv01_gbp_per_bp_auction (excl.   robustness: dv01_gbp_per_bp_total
                  PAOF)
  syndications    main: synd_n_pm5bd (incl. linkers)     robustness: synd_conv_n_pm5bd
  tenders         main: tender_n_pm5bd (incl. linkers)   robustness: tender_conv_n_pm5bd
  regime sample   main: all                              robustness: drop passive_qt_2022

Checks (spec §6 + one more): `panel_checks()`.

Run:  python -m gilt_study.auctions
Output: data/processed_data/auctions/auction_panel.csv
"""
import datetime as dt
import re
import sys

import numpy as np
import pandas as pd

from . import config, gilt_terms, paths
from .curve import Curve, curve_on, load_panel, maturity_columns, years_beyond_curve
from .data_io import is_index_linked
from .pricing import gilt_price, is_business_day, parse_coupon

OUT_DIR = paths.PROCESSED / "auctions"
PANEL_FILE = OUT_DIR / "auction_panel.csv"
MATCH_WINDOW_DAYS = 5            # D2.1E settlement row: within 5 calendar days after the auction
SUPPLY_WINDOW_BDAYS = 5          # spec §6: supply controls within +-5 business days
VOL_CHANGES = 20                 # rate volatility: daily changes ending at T-1
PAOF_START = dt.date(2009, 6, 1)  # D2.1A notes 5-6

REGIMES = [  # (label, first auction date, last auction date), spec §8, decision #14
    ("pre-crisis", dt.date(1998, 11, 1), dt.date(2008, 12, 31)),
    ("QE", dt.date(2009, 1, 1), dt.date(2022, 9, 22)),
    ("LDI stress", dt.date(2022, 9, 23), dt.date(2022, 10, 14)),
    ("QE", dt.date(2022, 10, 15), dt.date(2022, 10, 31)),      # 'Feb-Oct 2022 in QE' (decision #14)
    ("active QT", dt.date(2022, 11, 1), dt.date(2026, 9, 16)),
    ("post-QT-decision", dt.date(2026, 9, 17), dt.date(2099, 12, 31)),
]
LDI_WINDOW = (dt.date(2022, 9, 23), dt.date(2022, 10, 14))
PASSIVE_QT_2022 = (dt.date(2022, 2, 1), dt.date(2022, 10, 31))   # minus the LDI window


# ============================================================================ calendar helpers
def previous_business_day(d: dt.date) -> dt.date:
    d -= dt.timedelta(days=1)
    while not is_business_day(d):
        d -= dt.timedelta(days=1)
    return d


def add_business_days(d: dt.date, n: int) -> dt.date:
    """d moved by n UK business days (n may be negative); d itself need not be a business day."""
    step = 1 if n >= 0 else -1
    k = 0
    while k < abs(n):
        d += dt.timedelta(days=step)
        if is_business_day(d):
            k += 1
    return d


def financial_year(d: dt.date) -> str:
    """UK financial year label, April to March: 2020-04-01 -> '2020-21'."""
    y = d.year if d.month >= 4 else d.year - 1
    return f"{y}-{str(y + 1)[2:]}"


def bucket(years: float) -> str:
    """DMO remit bands as in spec §6: short < 7y, medium 7-15y, long > 15y."""
    return "short" if years < 7 else ("medium" if years <= 15 else "long")


def regime(d: dt.date) -> str:
    for label, a, b in REGIMES:
        if a <= d <= b:
            return label
    return "before sample"


def passive_qt_2022(d: dt.date) -> bool:
    """Feb-Oct 2022 outside the LDI window: in QE (decision #14), dropped in a robustness check."""
    return PASSIVE_QT_2022[0] <= d <= PASSIVE_QT_2022[1] and not (LDI_WINDOW[0] <= d <= LDI_WINDOW[1])


def _num(s):
    return pd.to_numeric(pd.Series(s).astype(object).map(lambda v: str(v).replace(",", "") if pd.notna(v) else v),
                         errors="coerce").to_numpy()


def _maturity_year(name: str):
    years = re.findall(r"(\d{4})", str(name))
    return int(years[-1]) if years else None


# ============================================================================ readers
def load_d2_1a() -> pd.DataFrame:
    """D2.1A: every outright auction (conventional and index-linked), one row each."""
    raw = pd.read_excel(paths.D2_1A, header=None)
    a = raw.iloc[5:, :10].copy()
    a.columns = ["auction_date", "gilt_name", "nominal_auction", "paof", "nominal_total", "cash_raised",
                 "bid_to_cover", "aap", "aay", "tail_bp"]
    a = a[pd.to_datetime(a["auction_date"], errors="coerce").notna()].copy()
    a["auction_date"] = pd.to_datetime(a["auction_date"]).dt.date
    a["gilt_name"] = a["gilt_name"].astype(str).str.strip()
    for c in ["nominal_auction", "paof", "nominal_total", "cash_raised", "bid_to_cover", "aap", "aay", "tail_bp"]:
        a[c] = _num(a[c])
    a["index_linked"] = a["gilt_name"].map(is_index_linked)
    a["index_linked_case_sensitive"] = a["gilt_name"].str.contains("Index-linked")
    return a.sort_values("auction_date").reset_index(drop=True)


def load_syndications() -> pd.DataFrame:
    s = pd.read_excel(paths.SYNDICATIONS, header=0).iloc[:, :5]
    s.columns = ["date", "gilt_name", "nominal", "price", "yield"]
    s = s[s["date"].notna() & s["gilt_name"].notna()].copy()
    s["date"] = pd.to_datetime(s["date"], format="%d %b %Y").dt.date
    s["nominal"] = _num(s["nominal"])
    s["index_linked"] = s["gilt_name"].map(is_index_linked)
    return s.reset_index(drop=True)


def load_tenders() -> pd.DataFrame:
    raw = pd.read_excel(paths.TENDERS, header=None)
    t = raw.iloc[5:, [0, 1, 2, 8]].copy()
    t.columns = ["date", "gilt_name", "nominal", "issue_date"]
    t = t[pd.to_datetime(t["date"], errors="coerce").notna()].copy()
    t["date"] = pd.to_datetime(t["date"]).dt.date
    t["nominal"] = _num(t["nominal"])
    t["index_linked"] = t["gilt_name"].map(is_index_linked)
    return t.reset_index(drop=True)


def load_other_supply() -> pd.DataFrame:
    """Taps and mini-tender re-sales of existing gilts from the 'other operations' file."""
    raw = pd.read_excel(paths.OTHER_OPERATIONS, header=None)
    out, section = [], None
    for _, r in raw.iterrows():
        first = r.iloc[0]
        if isinstance(first, str) and first.isupper() and first.startswith(("RESULTS", "USE", "ISSUANCE")):
            section = first
            continue
        d = pd.to_datetime(first, errors="coerce")
        if section is None or pd.isna(d) or not isinstance(r.iloc[1], str):
            continue
        if section == "RESULTS OF GILT TAPS":
            out.append(dict(date=d.date(), gilt_name=r.iloc[1], nominal=float(r.iloc[2]), kind="tap"))
        elif section.startswith("RESULTS OF GILT MINI TENDERS"):
            out.append(dict(date=d.date(), gilt_name=r.iloc[1], nominal=float(r.iloc[2]), kind="mini-tender re-sale"))
    o = pd.DataFrame(out)
    o["index_linked"] = o["gilt_name"].map(is_index_linked)
    return o


def _qt_maturity(code: str):
    """'UKT_0.125_300126' -> 30 Jan 2026."""
    m = re.search(r"_(\d{6})$", str(code).strip())
    return dt.datetime.strptime(m.group(1), "%d%m%y").date() if m else None


def _boe_operations(path, sheet=0) -> pd.DataFrame:
    """A BoE APF operations workbook (QE purchases, QT sales, 2022 FS operations): one row per bond
    per operation with operation date, ISIN, bond code and nominal allocated (> 0 only)."""
    raw = pd.read_excel(path, sheet_name=sheet, header=None)
    hdr = next(i for i in range(10) if any(str(v).strip() == "Operation date" for v in raw.iloc[i]))
    names = [" ".join(str(v).split()) for v in raw.iloc[hdr]]
    col = lambda label: names.index(label)
    q = pd.DataFrame({"date": raw.iloc[hdr + 1:, col("Operation date")],
                      "isin": raw.iloc[hdr + 1:, col("ISIN")],
                      "bond": raw.iloc[hdr + 1:, col("Bond")],
                      "nominal": raw.iloc[hdr + 1:, col("Total allocation (nominal £mn)")]})
    q = q[pd.to_datetime(q["date"], errors="coerce").notna()].copy()
    q["date"] = pd.to_datetime(q["date"]).dt.date
    q["nominal"] = _num(q["nominal"])
    return q[q["nominal"] > 0].reset_index(drop=True)


def load_qe_purchases() -> pd.DataFrame:
    """BoE APF gilt purchases (QE), 2009-2021 (data #10)."""
    return _boe_operations(paths.QE_PURCHASES)


def load_fs_operations() -> pd.DataFrame:
    """BoE 2022 financial-stability operations (data #11): purchases (Sep-Oct 2022) and the later
    sales of that portfolio. Column `kind` = 'purchase' or 'sale'."""
    files = {f.name: f for f in paths.CRISIS_OPS_DIR.iterdir()}
    parts = []
    for name, kind in [("long-dated-uk-government-bond-purchase-time-series.XLSX", "purchase"),
                       ("index-linked-gilt-purchase-results.XLSX", "purchase"),
                       ("finanical-stability-gilt-sales-time-series.XLSX", "sale")]:
        parts.append(_boe_operations(files[name]).assign(kind=kind))
    return pd.concat(parts, ignore_index=True)


def load_qt_sales() -> pd.DataFrame:
    """BoE APF gilt sales (QT): one row per operation and gilt with an allocation."""
    raw = pd.read_excel(paths.QT_SALES, header=None)
    q = raw.iloc[2:, [1, 2, 3, 4, 7]].copy()
    q.columns = ["date", "settle", "isin", "bond", "nominal"]
    q = q[pd.to_datetime(q["date"], errors="coerce").notna()].copy()
    q["date"] = pd.to_datetime(q["date"]).dt.date
    q["nominal"] = _num(q["nominal"])
    q["maturity"] = q["bond"].map(_qt_maturity)
    q = q[q["nominal"] > 0]
    q["bucket"] = [bucket((m - d).days / 365.25) for m, d in zip(q["maturity"], q["date"])]
    return q.reset_index(drop=True)


# ============================================================================ building the panel
def _match_d2_1e(a: pd.DataFrame, E: pd.DataFrame) -> pd.DataFrame:
    """ISIN and settlement date for each auction from its D2.1E row (see module docstring)."""
    priced = E[(E["section"] == "conventional") & E["price"].notna()].copy()
    priced["coupon"] = priced["name"].map(parse_coupon)
    priced["year"] = priced["name"].map(_maturity_year)
    rows = []
    for r in a.itertuples(index=False):
        c = priced[(priced["date"] > r.auction_date)
                   & (priced["date"] <= r.auction_date + dt.timedelta(days=MATCH_WINDOW_DAYS))
                   & (priced["coupon"] == parse_coupon(r.gilt_name))
                   & (priced["year"] == _maturity_year(r.gilt_name))].sort_values("date")
        same = c[(c["nominal"] - r.nominal_total).abs() < 1e-3]
        pick = same.iloc[0] if len(same) else (c.iloc[0] if len(c) else None)
        rows.append(dict(isin=None if pick is None else pick["isin"],
                         settlement_date=None if pick is None else pick["date"],
                         d2_1e_name=None if pick is None else pick["name"],
                         d2_1e_nominal=np.nan if pick is None else pick["nominal"],
                         d2_1e_cumulative=np.nan if pick is None else pick["cumulative"],
                         d2_1e_candidate_isins=c["isin"].nunique(),
                         d2_1e_nominal_matches=len(same) > 0))
    return pd.DataFrame(rows, index=a.index)


def _decimals(x: float, max_dp: int = 6) -> int:
    """Decimal places as published (float noise beyond max_dp ignored)."""
    return next((k for k in range(max_dp + 1) if abs(x - round(x, k)) < 1e-9), max_dp)


def _aap_check(err: float, aap_dp: int, aay_dp: int, dv01_per_100: float) -> str:
    """Does the DMO's AAY reprice (our terms, DMO settlement date) to the published AAP?
    'rounded': within half a unit of the AAP's last decimal (plus the price effect of the AAY's own
    rounding); 'truncated': within [0, one unit) of it, i.e. consistent with an AAP truncated
    rather than rounded (D2.1A before mid-2003); else 'FAIL'."""
    ytol = 0.5 * 10.0 ** (-aay_dp) * 100 * dv01_per_100 + 1e-6      # % -> bp -> price
    unit = 10.0 ** (-aap_dp)
    if abs(err) <= 0.5 * unit + ytol:
        return "rounded"
    if -ytol <= err < unit + ytol:
        return "truncated"
    return "FAIL"


def _window_stats(dates: np.ndarray, values: np.ndarray, lo: dt.date, hi: dt.date):
    m = (dates >= lo) & (dates <= hi)
    return int(m.sum()), float(values[m].sum()) if m.any() else 0.0


def build_panel(write: bool = True) -> pd.DataFrame:
    """The auction panel (spec §6). Writes PANEL_FILE when write=True."""
    A = load_d2_1a()
    conv = A[~A["index_linked"]]
    a = conv[(conv["auction_date"] >= config.STUDY_START) & (conv["auction_date"] <= config.STUDY_END)].copy()
    a = a.reset_index(drop=True)

    # ---- ISIN and settlement date (D2.1E)
    E = gilt_terms.load_issuance_history()
    a = pd.concat([a, _match_d2_1e(a, E)], axis=1)

    # ---- terms (gilt_terms: P3, P4)
    T = gilt_terms.load_terms().set_index("isin")
    a["coupon"] = a["isin"].map(T["coupon"])
    for c in ["maturity", "first_issue", "first_coupon", "first_coupon_source", "first_coupon_type",
              "flag_first_coupon_rule", "flag_first_coupon_manual_check", "maturity_source",
              "first_issue_source"]:
        a[c] = a["isin"].map(T[c])
    a["new_issue"] = a["settlement_date"] == a["first_issue"]
    # spec §4: an auction is 'priced with the fallback' if its first coupon date came from the rule
    # AND that date still matters, i.e. the auction settles before the first coupon is paid
    a["gilt_first_coupon_from_rule"] = a["flag_first_coupon_rule"].astype(bool)
    a["first_coupon_affects_price"] = [fc is not None and s < fc for s, fc in zip(a["settlement_date"], a["first_coupon"])]
    a["flag_first_coupon_rule"] = a["gilt_first_coupon_from_rule"] & a["first_coupon_affects_price"]
    a["settlement_is_t_plus_1"] = [s == add_business_days(d, 1) for s, d in zip(a["settlement_date"], a["auction_date"])]

    # ---- amounts and auction statistics (D2.1A)
    a["nominal_offered"] = a["nominal_auction"]
    a["nominal_allotted"] = a["nominal_auction"]
    a["paof_takeup"] = np.where(a["auction_date"] >= PAOF_START, a["paof"].fillna(0.0), np.nan)
    a["yield_at_lowest_accepted_price"] = a["aay"] + a["tail_bp"] / 100.0
    a["flag_tail_negative"] = a["tail_bp"] < 0          # impossible in a multiple-price auction: data issue
    a["d2_1e_minus_d2_1a_nominal"] = a["d2_1e_nominal"] - a["nominal_total"]   # CRND purchases (D2.1A note 2)?

    # ---- maturity, bucket, DV01, AAP check
    a["years_to_maturity"] = [(m - s).days / 365.25 for m, s in zip(a["maturity"], a["settlement_date"])]
    a["bucket"] = a["years_to_maturity"].map(bucket)
    prices = [gilt_price(s, m, c, y / 100.0, fi, fc) for s, m, c, y, fi, fc in
              zip(a["settlement_date"], a["maturity"], a["coupon"], a["aay"], a["first_issue"], a["first_coupon"])]
    a["clean_at_aay"] = [p["clean"] for p in prices]
    a["accrued_at_settlement"] = [p["accrued"] for p in prices]
    a["dv01_per_100"] = [p["dv01"] for p in prices]
    a["dv01_gbp_per_bp_auction"] = a["dv01_per_100"] * a["nominal_auction"] * 1e6 / 100.0
    a["dv01_gbp_per_bp_total"] = a["dv01_per_100"] * a["nominal_total"] * 1e6 / 100.0
    a["aap_decimals"] = [_decimals(p) for p in a["aap"]]
    a["aay_decimals"] = [_decimals(y) for y in a["aay"]]
    a["aap_check_error"] = a["clean_at_aay"] - a["aap"]
    a["aap_check"] = [_aap_check(e, dp, ydp, dv) for e, dp, ydp, dv in
                      zip(a["aap_check_error"], a["aap_decimals"], a["aay_decimals"], a["dv01_per_100"])]

    # ---- T-1 curve: last maturity and years beyond it (decision #12)
    cp = load_panel()
    t1, cdate, fb, tmax, yb = [], [], [], [], []
    for r in a.itertuples(index=False):
        d = previous_business_day(r.auction_date)
        crv, used, fallback = curve_on(cp, d)
        t1.append(d); cdate.append(used); fb.append(fallback); tmax.append(crv.t_max)
        yb.append(years_beyond_curve(r.settlement_date, r.maturity, crv, r.first_issue))
    a["t_minus_1"], a["curve_date"], a["curve_fallback"], a["curve_t_max"] = t1, cdate, fb, tmax
    a["years_beyond_curve"] = yb
    a["beyond_curve"] = a["years_beyond_curve"] > 0
    a["drop_extrapolation_robustness"] = a["years_beyond_curve"] > config.MAX_YEARS_BEYOND_CURVE

    # ---- regime, financial year
    a["regime"] = a["auction_date"].map(regime)
    a["passive_qt_2022"] = a["auction_date"].map(passive_qt_2022)
    a["tail_bp_regression"] = a["tail_bp"].where(~a["flag_tail_negative"])      # decision #15
    a["financial_year"] = a["auction_date"].map(financial_year)

    # ---- supply controls (+-5 UK business days, inclusive)
    S, Td, O, Q = load_syndications(), load_tenders(), load_other_supply(), load_qt_sales()
    qd = Q.groupby("date").agg(nominal=("nominal", "sum")).reset_index()
    QE = load_qe_purchases().groupby("date").agg(nominal=("nominal", "sum")).reset_index()
    FS = load_fs_operations()
    fsp = FS[FS["kind"] == "purchase"].groupby("date").agg(nominal=("nominal", "sum")).reset_index()
    fss = FS[FS["kind"] == "sale"].groupby("date").agg(nominal=("nominal", "sum")).reset_index()
    cols = {k: [] for k in ["synd_n", "synd_nominal", "synd_conv_n", "tender_n", "tender_nominal", "tender_conv_n",
                            "qt_sale_days", "qt_sale_nominal", "qt_sale_same_bucket_nominal",
                            "other_supply_n", "other_supply_nominal", "qe_purchase_days", "qe_purchase_nominal",
                            "fs_purchase_days", "fs_sale_days"]}
    sd, sn, sc = np.array(S["date"]), S["nominal"].to_numpy(float), np.array(~S["index_linked"])
    td, tn, tc = np.array(Td["date"]), Td["nominal"].to_numpy(float), np.array(~Td["index_linked"])
    od, on = np.array(O["date"]), O["nominal"].to_numpy(float)
    qdd, qn = np.array(qd["date"]), qd["nominal"].to_numpy(float)
    for r in a.itertuples(index=False):
        lo = add_business_days(r.auction_date, -SUPPLY_WINDOW_BDAYS)
        hi = add_business_days(r.auction_date, SUPPLY_WINDOW_BDAYS)
        n, v = _window_stats(sd, sn, lo, hi); cols["synd_n"].append(n); cols["synd_nominal"].append(v)
        cols["synd_conv_n"].append(_window_stats(sd[sc], sn[sc], lo, hi)[0])
        n, v = _window_stats(td, tn, lo, hi); cols["tender_n"].append(n); cols["tender_nominal"].append(v)
        cols["tender_conv_n"].append(_window_stats(td[tc], tn[tc], lo, hi)[0])
        n, v = _window_stats(qdd, qn, lo, hi); cols["qt_sale_days"].append(n); cols["qt_sale_nominal"].append(v)
        qb = Q[(Q["bucket"] == r.bucket)]
        cols["qt_sale_same_bucket_nominal"].append(_window_stats(np.array(qb["date"]), qb["nominal"].to_numpy(float), lo, hi)[1])
        n, v = _window_stats(od, on, lo, hi); cols["other_supply_n"].append(n); cols["other_supply_nominal"].append(v)
        n, v = _window_stats(np.array(QE["date"]), QE["nominal"].to_numpy(float), lo, hi)
        cols["qe_purchase_days"].append(n); cols["qe_purchase_nominal"].append(v)
        cols["fs_purchase_days"].append(_window_stats(np.array(fsp["date"]), fsp["nominal"].to_numpy(float), lo, hi)[0])
        cols["fs_sale_days"].append(_window_stats(np.array(fss["date"]), fss["nominal"].to_numpy(float), lo, hi)[0])
    for k, v in cols.items():
        a[f"{k}_pm5bd"] = v
    a["qe_purchase_week"] = a["qe_purchase_days_pm5bd"] > 0          # decision #15
    a["qt_sale_week"] = a["qt_sale_days_pm5bd"] > 0

    # ---- rate volatility candidates (decision open)
    a["vol_10y_20d_bp"], a["vol_own_maturity_20d_bp"] = _volatility(a, cp)

    a = a.drop(columns=["paof"])
    order = ["auction_date", "settlement_date", "settlement_is_t_plus_1", "financial_year", "regime", "passive_qt_2022",
             "gilt_name", "isin", "coupon", "maturity", "first_issue", "new_issue", "first_coupon",
             "first_coupon_source", "first_coupon_type", "first_coupon_affects_price", "flag_first_coupon_rule",
             "gilt_first_coupon_from_rule", "flag_first_coupon_manual_check",
             "nominal_offered", "nominal_allotted", "paof_takeup", "nominal_total", "cash_raised", "bid_to_cover",
             "aap", "aay", "tail_bp", "tail_bp_regression", "yield_at_lowest_accepted_price", "flag_tail_negative",
             "years_to_maturity", "bucket",
             "dv01_per_100", "dv01_gbp_per_bp_auction", "dv01_gbp_per_bp_total",
             "t_minus_1", "curve_date", "curve_fallback", "curve_t_max", "beyond_curve", "years_beyond_curve",
             "drop_extrapolation_robustness"]
    order += [c for c in a.columns if c.endswith("_pm5bd")] + ["qe_purchase_week", "qt_sale_week",
                                                               "vol_own_maturity_20d_bp", "vol_10y_20d_bp"]
    order += ["accrued_at_settlement", "clean_at_aay", "aap_decimals", "aay_decimals", "aap_check_error", "aap_check",
              "nominal_auction", "d2_1e_name", "d2_1e_nominal", "d2_1e_minus_d2_1a_nominal", "d2_1e_cumulative",
              "d2_1e_candidate_isins", "d2_1e_nominal_matches", "maturity_source", "first_issue_source"]
    a = a[order]
    if write:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        a.to_csv(PANEL_FILE, index=False)
    return a


def _volatility(a: pd.DataFrame, cp: pd.DataFrame):
    """Std of the last VOL_CHANGES daily changes (bp) of the spot rate up to T-1: at 10 years, and at
    the auctioned gilt's years to maturity (constant tenor; flat forward beyond the curve)."""
    mats = maturity_columns(cp)
    idx = cp.index
    cache = {}

    def z_at(ts, tenor):
        if ts not in cache:
            row = cp.loc[ts]
            cache[ts] = Curve(ts.date(), mats, row[mats].to_numpy(float), row["f_tmax"])
        return float(cache[ts](tenor))

    v10, vown = [], []
    for r in a.itertuples(index=False):
        end = idx.searchsorted(pd.Timestamp(r.curve_date), side="right")
        days = idx[max(0, end - VOL_CHANGES - 1):end]
        z10 = cp.loc[days, 10.0].to_numpy(float)
        zown = np.array([z_at(ts, r.years_to_maturity) for ts in days])
        v10.append(float(np.std(np.diff(z10) * 100, ddof=1)))
        vown.append(float(np.std(np.diff(zown) * 100, ddof=1)))
    return v10, vown


def load_auction_panel(build_if_missing: bool = True) -> pd.DataFrame:
    """The panel from PANEL_FILE, with dates as datetime.date."""
    if not PANEL_FILE.exists():
        if not build_if_missing:
            raise FileNotFoundError(PANEL_FILE)
        build_panel()
    P = pd.read_csv(PANEL_FILE, float_precision="round_trip")
    for c in ["auction_date", "settlement_date", "maturity", "first_issue", "first_coupon", "t_minus_1", "curve_date"]:
        P[c] = [None if pd.isna(v) else dt.date.fromisoformat(str(v)[:10]) for v in P[c]]
    return P


# ============================================================================ panel checks (spec §6)
# DMO published auction counts by financial year (see SOURCES.md #5b). 'all' = conventional and
# index-linked auctions (Gilt Market Annual Review 2023-24, Table 9). Bucket splits are outturns
# stated in the Annual Review for that year, except 2009-10 (remit plan; the DMO reports no change
# and the total, 58, equals the outturn).
GAR2024 = "https://dmo.gov.uk/media/5rqb2scf/gar2024_final.pdf"
DMO_ALL_AUCTIONS = {  # financial year: all outright auctions (conventional + index-linked)
    "1998-99": 4, "1999-00": 8, "2000-01": 7, "2001-02": 8, "2002-03": 13, "2003-04": 24, "2004-05": 26,
    "2005-06": 25, "2006-07": 36, "2007-08": 34, "2008-09": 58, "2009-10": 58, "2010-11": 49, "2011-12": 49,
    "2012-13": 44, "2013-14": 43, "2014-15": 41, "2015-16": 39, "2016-17": 48, "2017-18": 40, "2018-19": 36,
    "2019-20": 43, "2020-21": 150, "2021-22": 64, "2022-23": 59, "2023-24": 69,
}
DMO_ALL_AUCTIONS_UNCERTAIN = {"1998-99"}    # read from the table layout, not a labelled cell
DMO_BUCKET_COUNTS = {  # financial year: (short, medium, long, index-linked), source
    "2009-10": ((15, 19, 12, 12), "https://www.dmo.gov.uk/media/14488/gar0910.pdf (remit plan, p.16)"),
    "2016-17": ((13, 11, 12, 12), "https://www.dmo.gov.uk/media/vu5k3dub/gar1617.pdf (p.18)"),
    "2017-18": ((10, 9, 10, 11), "https://www.dmo.gov.uk/media/15622/gar1718.pdf (p.18)"),
    "2020-21": ((46, 39, 46, 19), "https://dmo.gov.uk/media/17809/gar2021.pdf (Table 4, p.16)"),
    "2023-24": ((20, 20, 15, 14), GAR2024 + " (Table 6, p.18)"),
}


def panel_checks(P: pd.DataFrame | None = None) -> dict:
    """The spec §6 acceptance checks plus the AAP repricing check. Returns a dict of tables/values."""
    P = load_auction_panel() if P is None else P
    A = load_d2_1a()
    A["financial_year"] = A["auction_date"].map(financial_year)
    out = {}

    # 1. counts by financial year vs the DMO (all auctions, every year; buckets, 5 years)
    ours_all = A.groupby("financial_year").size()
    t = pd.DataFrame({"dmo_all_auctions": pd.Series(DMO_ALL_AUCTIONS)}).join(ours_all.rename("d2_1a_all_auctions"))
    t["d2_1a_conventional"] = A[~A["index_linked"]].groupby("financial_year").size().reindex(t.index)
    t["d2_1a_index_linked"] = A[A["index_linked"]].groupby("financial_year").size().reindex(t.index)
    t["match"] = t["dmo_all_auctions"] == t["d2_1a_all_auctions"]
    t["dmo_figure_uncertain"] = t.index.isin(DMO_ALL_AUCTIONS_UNCERTAIN)
    out["fy_all_auctions"] = t
    rows = []
    for fy, ((s, m, l, il), src) in DMO_BUCKET_COUNTS.items():
        p = P[P["financial_year"] == fy]["bucket"].value_counts()
        n_il = int(A[(A["financial_year"] == fy) & A["index_linked"]].shape[0])
        rows.append(dict(financial_year=fy, dmo_short=s, ours_short=int(p.get("short", 0)), dmo_medium=m,
                         ours_medium=int(p.get("medium", 0)), dmo_long=l, ours_long=int(p.get("long", 0)),
                         dmo_index_linked=il, ours_index_linked=n_il, source=src))
    b = pd.DataFrame(rows).set_index("financial_year")
    b["match"] = ((b.dmo_short == b.ours_short) & (b.dmo_medium == b.ours_medium) & (b.dmo_long == b.ours_long)
                  & (b.dmo_index_linked == b.ours_index_linked))
    out["fy_buckets"] = b

    # 2. no duplicate (date, ISIN); 3. every ISIN matched to terms; 4. linkers excluded, counted
    out["duplicates"] = int(P.duplicated(["auction_date", "isin"]).sum())
    out["isin_missing"] = int(P["isin"].isna().sum())
    out["terms_missing"] = int(P["maturity"].isna().sum())
    out["ambiguous_isin"] = int((P["d2_1e_candidate_isins"] != 1).sum())
    out["d2_1e_nominal_mismatch"] = int((~P["d2_1e_nominal_matches"].astype(bool)).sum())
    win = (A["auction_date"] >= config.STUDY_START) & (A["auction_date"] <= config.STUDY_END)
    out["linkers_in_window"] = int((win & A["index_linked"]).sum())
    out["linkers_missed_by_case_sensitive_filter"] = int((win & A["index_linked"] & ~A["index_linked_case_sensitive"]).sum())
    out["conventional_in_window"] = int((win & ~A["index_linked"]).sum())
    out["panel_rows"] = len(P)
    # extra: the DMO's AAY reprices to its AAP with our terms and settlement date
    out["aap_check_counts"] = P["aap_check"].value_counts()
    out["aap_check_not_rounded"] = P.loc[P["aap_check"] != "rounded",
                                         ["auction_date", "gilt_name", "aap", "aay", "clean_at_aay", "aap_check_error",
                                          "aap_check"]]
    out["d2_1e_nominal_differences"] = P.loc[~P["d2_1e_nominal_matches"].astype(bool),
                                             ["auction_date", "gilt_name", "nominal_total", "d2_1e_nominal",
                                              "d2_1e_minus_d2_1a_nominal"]]
    out["tail_negative"] = P.loc[P["flag_tail_negative"].astype(bool), ["auction_date", "gilt_name", "aay", "tail_bp"]]
    # decision #15: a sign-convention change would make many tails negative; tabulate by period
    yrs = pd.to_datetime(P["auction_date"]).dt.year
    period = np.where(yrs < 2010, "before 2010", "2010 onwards")
    out["tail_sign_by_period"] = (P.assign(period=period).groupby("period")["tail_bp"]
                                  .agg(auctions="size", negative=lambda s: int((s < 0).sum()),
                                       zero=lambda s: int((s == 0).sum()), positive=lambda s: int((s > 0).sum()),
                                       median="median", min="min", max="max"))
    out["settlement_not_t_plus_1"] = P.loc[~P["settlement_is_t_plus_1"].astype(bool),
                                           ["auction_date", "settlement_date", "gilt_name"]]
    return out


def main():
    P = build_panel()
    C = panel_checks(P)
    pd.set_option("display.width", 220)
    print(f"Auction panel: {len(P)} conventional auctions, {P.auction_date.min()} to {P.auction_date.max()} -> {PANEL_FILE}")
    print("\n=== Counts by financial year vs DMO (all auctions) ===")
    print(C["fy_all_auctions"].to_string())
    print("\n=== Conventional auctions by bucket vs DMO ===")
    print(C["fy_buckets"].drop(columns="source").to_string())
    for k in ["duplicates", "isin_missing", "terms_missing", "ambiguous_isin", "d2_1e_nominal_mismatch",
              "linkers_in_window", "linkers_missed_by_case_sensitive_filter", "conventional_in_window", "panel_rows"]:
        print(f"{k:42s} {C[k]}")
    print("AAP check:", C["aap_check_counts"].to_dict())
    print(C["aap_check_not_rounded"].to_string())
    print(C["d2_1e_nominal_differences"].to_string())
    print(C["tail_negative"].to_string())
    print(f"settlement not T+1: {len(C['settlement_not_t_plus_1'])}")
    return P, C


if __name__ == "__main__":
    main()
