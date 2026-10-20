"""Gilt reference terms: one row per conventional gilt (ISIN), built from DMO static data.

These are the inputs `pricing.cash_flows()` needs beyond coupon and maturity. The rules come from the
build spec §4 (Stage 1 sign-off, P2-P4); `pricing.py` itself is unchanged.

* Maturity (redemption date): D1A for gilts in issue; D1C for redeemed gilts, matched on coupon and
  maturity year (all 61 matches unique, 19 Oct 2026).
* First issue date (P4): D1A for gilts in issue; for redeemed gilts, the first D2.1E row that is a
  genuine launch (cumulative amount in issue equals that row's own nominal, i.e. nothing was
  outstanding before it). A gilt with no launch row was launched before D2.1E starts (21 Jan 1998)
  and gets no first issue date, which is correct: its first coupon is long past.
* First coupon date (P3): from DMO data where available, otherwise the fallback rule, flagged.
    1. "DMO notice": the first coupon date stated in a DMO issuance/pre-auction notice or
       prospectus (DMO_NOTICES below, with URL and quoted text; read 19 Oct 2026).
    2. "DMO reference prices (accrued interest)": the DMO's own accrued interest (1998-2017 files)
       is matched against a short and a long first coupon; it is used when exactly one fits every
       day from launch to the second quasi-coupon date (days from 1 Nov 1998, actual/actual).
    3. Fallback rule on the gap from first issue to the next quasi-coupon date: <= 45 days -> long
       first coupon (second quasi date); >= 61 days -> short (first quasi date); 46-60 days -> no
       evidence either way: priced short and flagged for a manual check against the DMO notice.
       Every gilt priced with the rule is flagged (flag_first_coupon_rule).
* Tranche issue date (P2): when-issued (WI) trades settle on the issue date of the tranche, i.e. the
  next D2.1E issue event with a price for the underlying gilt (rows without a price are direct
  issues to the DMO, not market tranches).

Output: data/interim_data/gilt_terms.csv (rebuilt by `build_terms()`; read by `load_terms()`).
"""
import datetime as dt
import re

import numpy as np
import pandas as pd

from . import paths
from .data_io import load_d1a, load_reference_prices
from .pricing import cash_flows, next_business_day, parse_coupon

# First coupon dates stated in DMO notices (issuance/pre-auction notices and prospectuses), read on
# 19 Oct 2026 for every post-2017 new gilt that the fallback rule priced long or flagged 46-60 days,
# plus one 72-day check. Matched on (coupon, maturity). URL and quoted text for each; see SOURCES.md.
SRC_DMO_NOTICE = "DMO notice (issuance/pre-auction notice or prospectus)"
DMO_NOTICES = [
    # coupon, maturity, first coupon, notice URL, quoted text
    (0.25, "2025-01-31", "2022-01-31", "https://www.dmo.gov.uk/media/jarfujjl/pr240621.pdf",
     "Next Interest Payment Date 31 January 2022 - £0.145028 per £100 nominal (Long First Coupon)"),
    (1.625, "2028-10-22", "2018-10-22", "https://www.dmo.gov.uk/media/njgorwql/prosp150318.pdf",
     "will rank for the payment of the non-standard first coupon on 22 October 2018"),
    (4.0, "2029-05-22", "2026-05-22", "https://dmo.gov.uk/media/vfbee0y0/prosp081025b.pdf",
     "rank for the payment of the non-standard first coupon on 22 May 2026"),
    (4.625, "2032-03-07", "2027-03-07", "https://dmo.gov.uk/media/drzceara/prosp040826.pdf",
     "will rank for the payment of the non-standard first coupon on 7 March 2027"),
    (3.25, "2033-01-31", "2023-07-31", "https://dmo.gov.uk:443/media/m2bbq4nr/prosp030123.pdf",
     "the first interest payment will be due on 31 July 2023 at the rate of £1.801630 per £100 nominal"),
    (4.5, "2035-03-07", "2025-09-07", "https://www.dmo.gov.uk/media/0jeppipl/pr040225.pdf",
     "will pay a long first coupon on 7 September 2025"),
    (1.125, "2039-01-31", "2022-01-31", "https://www.dmo.gov.uk/media/2zucvjlv/pr060721.pdf",
     "It will pay a long first coupon on 31 January 2022"),
    (0.875, "2046-01-31", "2021-07-31", "https://www.dmo.gov.uk/media/w1ocebci/pr310321a.pdf",
     "Next Interest Payment Date 31 July 2021- £0.463655 per £100 nominal (Long First Coupon)"),
    (4.375, "2054-07-31", "2024-07-31", "https://www.dmo.gov.uk/media/5oeb504d/pr160124.pdf",
     "will pay a long first coupon on 31 July 2024"),
    (0.125, "2026-01-30", "2021-01-30", "https://www.dmo.gov.uk/media/mnyn5x2f/prosp260520.pdf",
     "the first interest payment will be due on 30 January 2021 at the rate of £0.082074 per £100 nominal"),
    (0.375, "2026-10-22", "2021-10-22", "https://www.dmo.gov.uk/media/cfxlrkdh/prosp230221a.pdf",
     "the first interest payment will be due on 22 October 2021 at the rate of £0.239011 per £100 nominal"),
    (3.75, "2027-03-07", "2024-09-07", "https://www.dmo.gov.uk/media/oq1jaj5a/pr030124.pdf",
     "Next Interest Payment Date 7 September 2024 - £2.451923 per £100 nominal (Long First Coupon)"),
    (0.125, "2028-01-31", "2021-01-31", "https://www.dmo.gov.uk/media/n1ylxsoe/pr040620b.pdf",
     "31 January 2021 - £0.079327 per £100 nominal (Long First Coupon)"),
    (4.375, "2030-03-07", "2025-09-07", "https://www.dmo.gov.uk/media/u41gljwp/prosp280125.pdf",
     "which will be due on 7 September 2025 at the rate of £2.876381 per £100 nominal"),
    (4.0, "2031-10-22", "2024-10-22", "https://www.dmo.gov.uk/media/52dlkrjw/prosp210224.pdf",
     "the first interest payment will be due on 22 October 2024 at the rate of £2.579235 per £100 nominal"),
    (1.0, "2032-01-31", "2022-01-31", "https://www.dmo.gov.uk/media/1jnasbzb/prosp241121.pdf",
     "the first interest payment will be due on 31 January 2022 at the rate of £0.163043 per £100 nominal"),
    (4.25, "2034-07-31", "2025-01-31", "https://www.dmo.gov.uk/media/flomkmh1/pr040624_1.pdf",
     "will pay a long first coupon on 31 January 2025"),
    (4.75, "2035-10-22", "2026-04-22", "https://dmo.gov.uk/media/mblmcjem/prosp030226a.pdf",
     "will rank for the payment of the non-standard first coupon on 22 April 2026"),
    (4.625, "2030-05-22", "2026-11-22", "https://www.dmo.gov.uk/media/mh2pkmjz/prosp030926.pdf",
     "the first interest payment will be due on 22 November 2026 at the rate of £0.904891 per £100 nominal"),
]

TERMS_FILE = paths.INTERIM / "gilt_terms.csv"
ACTUAL_ACTUAL_FROM = dt.date(1998, 11, 1)   # DMO accrued is actual/365 before this date
LONG_MAX_DAYS, SHORT_MIN_DAYS = 45, 61      # fallback rule thresholds (spec §4)
TRANCHE_WINDOW_DAYS = 45                    # a WI line's tranche must issue within this window
SRC_DMO_ACCRUED = "DMO reference prices (accrued interest)"
SRC_RULE_LONG = "rule: issued <= 45 days before next quasi date -> long"
SRC_RULE_SHORT = "rule: issued >= 61 days before next quasi date -> short"
SRC_MANUAL = "manual check: issued 46-60 days before next quasi date (priced short)"
SRC_NOT_NEEDED = "not needed: launched before D2.1E (first coupon long past)"


# ----------------------------------------------------------------------------- DMO static data
def load_issuance_history() -> pd.DataFrame:
    """Tidy D2.1E: one row per issue event with name, isin, date, kind, price, yield, nominal,
    cumulative amount in issue and section ('conventional' or 'index-linked')."""
    raw = pd.read_excel(paths.D2_1E, header=None).iloc[5:, :9]
    raw.columns = ["name", "isin", "date", "kind", "price", "yield", "nominal", "_", "cumulative"]
    section, sections = None, []
    for name, isin in zip(raw["name"], raw["isin"]):
        if isinstance(name, str) and pd.isna(isin) and not name.startswith("Note"):
            section = "index-linked" if "index" in name.lower() else "conventional"
        sections.append(section)
    raw["section"] = sections
    e = raw[raw["isin"].fillna("").astype(str).str.startswith("GB")].drop(columns="_").copy()
    e["date"] = pd.to_datetime(e["date"]).dt.date
    for c in ["price", "yield", "nominal", "cumulative"]:
        e[c] = pd.to_numeric(e[c], errors="coerce")
    e["name"] = e["name"].str.strip()
    return e.sort_values(["isin", "date"]).reset_index(drop=True)


def load_redemptions() -> pd.DataFrame:
    """Tidy D1C (conventional only): name, redemption date, coupon, maturity year."""
    raw = pd.read_excel(paths.D1C, header=None).iloc[4:, :3]
    raw.columns = ["redemption", "name", "amount"]
    raw = raw[pd.to_datetime(raw["redemption"], errors="coerce").notna()].copy()
    raw = raw[~raw["name"].str.contains(r"index\s*-\s*linked", case=False, regex=True)]
    raw["redemption"] = pd.to_datetime(raw["redemption"]).dt.date
    raw["coupon"] = raw["name"].map(parse_coupon)
    raw["year"] = raw["name"].map(_maturity_year)
    return raw.reset_index(drop=True)


def _maturity_year(name: str):
    years = re.findall(r"(\d{4})", str(name))
    return years[-1] if years else None


# ----------------------------------------------------------------------------- quasi-coupon dates
def quasi_dates_after(maturity: dt.date, start: dt.date, n: int = 2) -> list:
    """The first n quasi-coupon dates strictly after `start` (6-month steps back from maturity)."""
    k, out = 0, []
    while True:
        q = (pd.Timestamp(maturity) - pd.DateOffset(months=6 * k)).date()
        if q <= start:
            break
        out.append(q)
        k += 1
    return sorted(out)[:n]


def first_coupon_rule(first_issue: dt.date, maturity: dt.date):
    """Fallback rule (spec §4). Returns (first coupon date, source label, days issue -> quasi)."""
    q = quasi_dates_after(maturity, first_issue, 2)
    gap = (q[0] - first_issue).days
    if gap <= LONG_MAX_DAYS and len(q) > 1:
        return q[1], SRC_RULE_LONG, gap
    if gap >= SHORT_MIN_DAYS or len(q) == 1:
        return q[0], SRC_RULE_SHORT, gap
    return q[0], SRC_MANUAL, gap


# ----------------------------------------------------------------------------- DMO-observed first coupons
def observed_first_coupons(terms: pd.DataFrame, years=range(1998, 2018)) -> pd.DataFrame:
    """First coupon date shown by the DMO's own accrued interest in the reference prices.

    For each gilt launched in or before the data, compare the DMO accrued on every day from launch
    to the second quasi-coupon date with the pricer's accrued under a short and under a long first
    coupon. Returns isin, short_fits, long_fits, days, decisive_days (days on which the two differ).
    """
    t = terms[terms["first_issue"].notna()].set_index("isin")
    rows = []
    for year in years:
        ref = load_reference_prices(paths.ref_prices_file(year))
        ref = ref[ref["isin"].isin(t.index)]
        for r in ref.itertuples(index=False):
            g = t.loc[r.isin]
            q = quasi_dates_after(g.maturity, g.first_issue, 2)
            settle = next_business_day(r.date)
            if len(q) < 2 or settle >= q[1] or settle < ACTUAL_ACTUAL_FROM or settle >= g.maturity:
                continue
            short = cash_flows(settle, g.maturity, g.coupon, g.first_issue, q[0])["accrued"]
            long_ = cash_flows(settle, g.maturity, g.coupon, g.first_issue, q[1])["accrued"]
            rows.append(dict(isin=r.isin, short_ok=abs(short - r.accrued) <= 1e-4,
                             long_ok=abs(long_ - r.accrued) <= 1e-4, decisive=abs(short - long_) > 1e-4))
    d = pd.DataFrame(rows, columns=["isin", "short_ok", "long_ok", "decisive"])
    return (d.groupby("isin").agg(days=("short_ok", "size"), decisive_days=("decisive", "sum"),
                                  short_fits=("short_ok", "all"), long_fits=("long_ok", "all"))
            .reset_index())


# ----------------------------------------------------------------------------- the terms table
def build_terms(write: bool = True, observe: bool = True) -> pd.DataFrame:
    """One row per conventional gilt in D2.1E or D1A with maturity, first issue and first coupon
    dates and their sources. Writes data/interim_data/gilt_terms.csv when write=True."""
    e = load_issuance_history()
    conv = e[e["section"] == "conventional"]
    d1a = load_d1a(paths.D1A).set_index("isin")
    d1c = load_redemptions()

    names = conv.groupby("isin")["name"].last()
    names = pd.concat([names, d1a["name"][~d1a.index.isin(names.index)]])
    T = pd.DataFrame({"isin": names.index, "name": names.values})
    T["coupon"] = T["name"].map(parse_coupon)
    T["year"] = T["name"].map(_maturity_year)

    # maturity: D1A, else D1C on (coupon, maturity year)
    T["maturity"] = T["isin"].map(d1a["redemption"])
    T["maturity_source"] = np.where(T["maturity"].notna(), "D1A", None)
    d1c_map = d1c.set_index(["coupon", "year"])["redemption"].to_dict()
    miss = T["maturity"].isna()
    T.loc[miss, "maturity"] = [d1c_map.get((c, y)) for c, y in zip(T.loc[miss, "coupon"], T.loc[miss, "year"])]
    T.loc[miss & T["maturity"].notna(), "maturity_source"] = "D1C (coupon + year)"

    # first issue date (P4): D1A, else the first genuine launch row in D2.1E, else none
    launch = conv[((conv["cumulative"] - conv["nominal"]).abs() < 1e-3) & (conv["nominal"] > 0)]
    launch = launch.groupby("isin")["date"].first()
    T["first_issue"] = T["isin"].map(d1a["first_issue"])
    T["first_issue_source"] = np.where(T["first_issue"].notna(), "D1A", None)
    miss = T["first_issue"].isna()
    T.loc[miss, "first_issue"] = T.loc[miss, "isin"].map(launch)
    T.loc[miss & T["first_issue"].notna(), "first_issue_source"] = "D2.1E launch row"
    T["first_issue_source"] = T["first_issue_source"].fillna("none: launched before D2.1E starts")
    T["first_issue"] = pd.Series([v if isinstance(v, dt.date) else None for v in T["first_issue"]],
                                 index=T.index, dtype=object)

    # first coupon (P3): DMO-observed, else rule (flagged)
    fc, src, gaps = [], [], []
    for r in T.itertuples(index=False):
        if r.first_issue is None:
            fc.append(None); src.append(SRC_NOT_NEEDED); gaps.append(np.nan)
            continue
        date, label, gap = first_coupon_rule(r.first_issue, r.maturity)
        fc.append(date); src.append(label); gaps.append(gap)
    T["first_coupon"], T["first_coupon_source"], T["days_issue_to_quasi"] = fc, src, gaps
    T["rule_first_coupon"] = T["first_coupon"]
    if observe:
        obs = observed_first_coupons(T).set_index("isin")
        for i, r in T.iterrows():
            if r["isin"] not in obs.index or r["first_issue"] is None:
                continue
            o = obs.loc[r["isin"]]
            if o["decisive_days"] > 0 and o["short_fits"] != o["long_fits"]:
                q = quasi_dates_after(r["maturity"], r["first_issue"], 2)
                T.at[i, "first_coupon"] = q[1] if o["long_fits"] else q[0]
                T.at[i, "first_coupon_source"] = SRC_DMO_ACCRUED
        T = T.join(obs.add_prefix("dmo_obs_"), on="isin")
    # DMO notices take precedence over everything else (they state the date directly)
    T["dmo_notice_url"] = None
    for cpn, mat, fc_date, url, _quote in DMO_NOTICES:
        hit = T.index[(T["coupon"] == cpn) & (T["maturity"] == dt.date.fromisoformat(mat))]
        if len(hit) != 1:
            raise ValueError(f"DMO notice {cpn}% {mat} matches {len(hit)} gilts")
        T.at[hit[0], "first_coupon"] = dt.date.fromisoformat(fc_date)
        T.at[hit[0], "first_coupon_source"] = SRC_DMO_NOTICE
        T.at[hit[0], "dmo_notice_url"] = url
    T["first_coupon_type"] = [
        None if f is None else ("long" if quasi_dates_after(m, fi, 1)[0] < f else "short")
        for f, m, fi in zip(T["first_coupon"], T["maturity"], T["first_issue"])]
    T["flag_first_coupon_rule"] = T["first_coupon_source"].isin([SRC_RULE_LONG, SRC_RULE_SHORT, SRC_MANUAL])
    T["flag_first_coupon_manual_check"] = T["first_coupon_source"].eq(SRC_MANUAL)
    T = T.drop(columns="year").sort_values(["maturity", "coupon"]).reset_index(drop=True)
    if write:
        paths.INTERIM.mkdir(parents=True, exist_ok=True)
        T.to_csv(TERMS_FILE, index=False)
    return T


def load_terms() -> pd.DataFrame:
    """The terms table from data/interim_data/gilt_terms.csv (built if missing), with dates as
    datetime.date and missing dates as None."""
    if not TERMS_FILE.exists():
        build_terms()
    T = pd.read_csv(TERMS_FILE)
    for c in ["maturity", "first_issue", "first_coupon", "rule_first_coupon"]:
        T[c] = [None if pd.isna(v) else dt.date.fromisoformat(str(v)[:10]) for v in T[c]]
    return T


# ----------------------------------------------------------------------------- tranches (P2)
def tranche_issue_dates() -> dict:
    """ISIN -> sorted list of the dates of its D2.1E issue events that carry a price (market
    tranches: auctions, syndications, tenders); direct issues to the DMO have no price."""
    e = load_issuance_history()
    e = e[e["price"].notna()]
    return e.groupby("isin")["date"].apply(sorted).to_dict()


def next_tranche_date(tranches: dict, isin: str, trade_date: dt.date, window_days: int = TRANCHE_WINDOW_DAYS):
    """Issue date of the next priced tranche of `isin` after `trade_date` (within window_days), or None."""
    for d in tranches.get(isin, []):
        if trade_date < d <= trade_date + dt.timedelta(days=window_days):
            return d
    return None
