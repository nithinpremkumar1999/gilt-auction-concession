"""Readers for DMO files (reference prices, D1A).

Reference-price layout (checked for every year 1998-2017): header on row 4, columns
Gilt Name, ISIN Code, Redemption Date, Close of Business Date, Clean Price, Dirty Price,
Accrued Interest, Yield, Modified Duration. The last date in the series is 21 Jul 2017.
"""
import datetime as dt
import re

import pandas as pd

from .pricing import parse_coupon

# Index-linked names seen in the DMO files: 'Index-linked', 'Index-Linked', 'Index -Linked', 'I-L'
LINKER_PATTERN = re.compile(r"index\s*-\s*linked|\bI-L\b", re.IGNORECASE)

REF_COLUMNS = ["name", "isin", "redemption", "date", "clean", "dirty", "accrued", "yield", "mod_dur"]


def load_reference_prices(path):
    """DMO historical reference prices (.xls, one year). Returns all instruments, junk rows dropped."""
    raw = pd.read_excel(path, header=4)
    raw.columns = REF_COLUMNS
    raw = raw.dropna(subset=["isin", "date"]).copy()
    for c in ["redemption", "date"]:
        raw[c] = pd.to_datetime(raw[c]).dt.date
    return raw


def instrument_type(name: str) -> str:
    """'single-dated', or one of the special conventional types in the 1998-2017 files:
    'floating-rate', 'double-dated' (e.g. '12% Exchequer Stock 2013-2017') or 'undated' (no year)."""
    if re.search(r"floating", name, re.I):
        return "floating-rate"
    if re.search(r"\d{4}\s*-\s*\d{2,4}", name):
        return "double-dated"
    if not re.search(r"\d{4}", name):
        return "undated"
    return "single-dated"


def is_index_linked(name: str) -> bool:
    """True for any spelling of an index-linked gilt name (see LINKER_PATTERN)."""
    return bool(LINKER_PATTERN.search(str(name)))


def conventional_only(ref, scope="single-dated"):
    """Rows of a reference-price file in the pricer's test scope. Returns (rows, names whose
    coupon cannot be read from the name).

    scope='single-dated' (spec §4, Stage 1 sign-off P1): not index-linked (any spelling), not a
        STRIP, single-dated (undated, double-dated and floating-rate gilts out), coupon readable
        from the name, DMO yield published.
    scope='as_run': the original 2016 rule (only 'Index-linked' and 'Strip' names removed), kept to
        reproduce the Stage 1 as-run record.
    """
    if scope == "as_run":
        is_il = ref["name"].str.contains("Index-linked", case=False)
    else:
        is_il = ref["name"].map(is_index_linked)
    is_strip = ref["name"].str.contains("Strip", case=False)
    out = ref[~is_il & ~is_strip].copy()
    if scope != "as_run":
        out = out[out["name"].map(instrument_type) == "single-dated"]
    out["coupon"] = out["name"].map(parse_coupon)
    excluded = sorted(set(out.loc[out["coupon"].isna(), "name"]))
    out = out[out["coupon"].notna() & out["yield"].notna()]
    return out, excluded


def load_d1a(path):
    """DMO D1A 'Gilts in issue' (.xls). Returns conventional gilts with terms and DMO ex-div date."""
    raw = pd.read_excel(path, header=None)
    rows, section = [], None
    for _, r in raw.iterrows():
        name = r[0]
        if isinstance(name, str) and name.startswith("Index-linked"):
            section = "index-linked"
        elif isinstance(name, str) and name.strip() == "Conventional Gilts":
            section = "conventional"
        if section == "conventional" and isinstance(r[1], str) and r[1].startswith("GB"):
            rows.append(dict(name=name.strip(), isin=r[1],
                             redemption=pd.to_datetime(r[2]).date(),
                             first_issue=pd.to_datetime(r[3]).date(),
                             dividend_dates=r[4],
                             dmo_ex_div=pd.to_datetime(r[5]).date(),
                             amount_m=r[6]))
    d1a = pd.DataFrame(rows)
    d1a["coupon"] = d1a["name"].map(parse_coupon)
    return d1a
