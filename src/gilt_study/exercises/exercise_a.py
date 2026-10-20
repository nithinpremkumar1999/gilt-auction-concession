"""
Exercise A, extended: the Stage 1 pricer acceptance test (build spec §4). Signed off 19 Oct 2026.

Every DMO reference-price file 1998-2017 is read; each gilt-day in scope is priced from the DMO's own
published yield with `gilt_study.pricing` (unchanged) and dirty price, accrued interest and clean
price are compared with the DMO's figures. Tolerance 1e-4 per £100 nominal; spec pass mark: dirty
within 1e-4 on >= 99.5% of single-dated conventional gilt-days, 25 Nov 2002 - 21 Jul 2017 (the DMO
published no conventional yields before 25 Nov 2002).

Two modes:
  final   (default) the signed-off test, with the Stage 1 decisions applied (spec §4, decision #6):
          P1 scope: single-dated conventional gilts (undated, double-dated and floating-rate gilts are
             excluded, not failures; linker spellings 'Index -Linked' and 'I-L' are caught)
          P2 when-issued (WI) lines are priced for settlement on the issue date of their tranche
          P3 first coupon dates from gilt_terms (DMO notice, DMO accrued, else the flagged rule)
          P4 first issue dates from gilt_terms (D1A, else the first genuine D2.1E launch row)
  as_run  the test as first run on 19 Oct 2026 (2016 exercise rule, earliest D2.1E first issue
          dates, no first coupon dates, WI lines settled T+1); reproduces the signed-off record.

Failing gilt-days are attributed to a cause by re-pricing under one diagnostic assumption at a time
(`diagnose` for as_run, `diagnose_final` for final); a cause counts only if the day then passes.

Run:   python -m gilt_study.exercises.exercise_a                  # final, all years
       python -m gilt_study.exercises.exercise_a --as-run         # the as-run record
       python -m gilt_study.exercises.exercise_a 2016             # chosen years (final)
Outputs in data/processed_data/stage1/<mode>/ when all years are run: by_year.csv, gilt_days.csv.gz,
failures.csv, exclusions.csv, accrued_only.csv.gz. Running 2016 also writes the original 2016
exercise output to data/processed_data/exercises/exercise_a_errors.csv.
"""
import datetime as dt
import os
import re
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from .. import config, gilt_terms, paths
from ..data_io import (conventional_only, instrument_type, is_index_linked, load_d1a,
                       load_reference_prices)
from ..pricing import (cash_flows, ex_dividend_date, gilt_price, is_business_day,
                       next_business_day, parse_coupon)

# ---------------------------------------------------------------- CONFIG (paths live in paths.py)
YEARS = range(1998, 2018)                   # every reference-price file (the series ends 21 Jul 2017)
REF_FILE = paths.ref_prices_file(2016)      # kept for exercise_b
D1A_FILE = paths.D1A
OUT_DIR = paths.PROCESSED / "exercises"     # original 2016 exercise output
STAGE1_DIR = paths.PROCESSED / "stage1"
DIRTY_TOL = CLEAN_TOL = 1e-4                # the DMO yield is computed from its rounded clean price,
                                            # so clean prices from the DMO yield match to ~1e-5
SPEC_PASS_RATE = 0.995                      # spec §4
CONVENTION_CHANGE = dt.date(1998, 11, 1)    # actual/365 -> actual/actual accrued (DMO, 1998)
TEST_WINDOW = config.PRICER_TEST_WINDOW    # 25 Nov 2002 - 21 Jul 2017 (spec §4, decision #6)
MODES = ("final", "as_run")


# ---------------------------------------------------------------- first issue dates
def first_issue_dates_as_run() -> pd.DataFrame:
    """As-run rule (superseded by P4, gilt_terms): D1A for gilts in issue, else the earliest D2.1E
    issue date.

    Returns columns isin, first_issue (date), source ('D1A' or 'D2.1E earliest'). D2.1E starts on
    21 Jan 1998, so for gilts launched before then its earliest row is a later event (a tap,
    cancellation or conversion), not the launch; diagnose() checks for that.
    """
    d1a = load_d1a(D1A_FILE)[["isin", "first_issue"]].assign(source="D1A")
    raw = pd.read_excel(paths.D2_1E, header=None)
    e = raw.iloc[5:, [1, 2]].copy()
    e.columns = ["isin", "date"]
    e = e[e["isin"].fillna("").astype(str).str.startswith("GB")]
    earliest = (pd.to_datetime(e["date"]).dt.date.groupby(e["isin"]).min()
                .rename("first_issue").reset_index().assign(source="D2.1E earliest"))
    earliest = earliest[~earliest["isin"].isin(d1a["isin"])]
    return pd.concat([d1a, earliest], ignore_index=True)


# ---------------------------------------------------------------- which rows are tested
def when_issued_lines(G: pd.DataFrame) -> pd.Series:
    """True for rows of a when-issued (WI) line: a temporary line the DMO quotes for a gilt's
    forthcoming tranche. Recognised by 'WI' at the end of the name, or by an ISIN that is not the
    main ISIN for its coupon and redemption date (e.g. a second '3¾% Treasury Gilt 2019' ISIN
    quoted for 7 days in Feb 2010)."""
    main = (G.groupby(["coupon", "redemption", "isin"]).size().reset_index(name="n").sort_values("n")
            .drop_duplicates(["coupon", "redemption"], keep="last")["isin"])
    return G["name"].str.contains(r"WI$") | ~G["isin"].isin(set(main))


def exclusion_reason(name, yld, mode: str = "final") -> str | None:
    """Why a reference-price row is not tested (same order of tests as data_io.conventional_only)."""
    if (re.search("index-linked", name, re.I) if mode == "as_run" else is_index_linked(name)):
        return "index-linked"
    if re.search("strip", name, re.I):
        return "STRIP"
    if mode != "as_run" and instrument_type(name) != "single-dated":
        return f"{instrument_type(name)} gilt (out of test scope, P1)"
    if parse_coupon(name) is None:
        return "coupon not readable from name (no '%')"
    if pd.isna(yld):
        return "no DMO yield published"
    return None


def split_year(year: int, mode: str = "final"):
    """(tested rows, excluded rows) for one reference-price file; asserts the tested set equals
    data_io.conventional_only() (same scope) minus rows settling on or after redemption."""
    ref = load_reference_prices(paths.ref_prices_file(year))
    ref["reason"] = [exclusion_reason(n, y, mode) for n, y in zip(ref["name"], ref["yield"])]
    ref["settle"] = ref["date"].map(next_business_day)
    after = ref["reason"].isna() & (ref["settle"] >= ref["redemption"])
    ref.loc[after, "reason"] = "settles on or after redemption date"
    tested = ref[ref["reason"].isna()].copy()
    tested["coupon"] = tested["name"].map(parse_coupon)
    scope = "as_run" if mode == "as_run" else "single-dated"
    conv, _ = conventional_only(ref.drop(columns=["reason", "settle"]), scope=scope)
    assert len(conv) - int(after.sum()) == len(tested), f"{year}: tested set differs from conventional_only"
    return tested, ref[ref["reason"].notna()].copy()


# ---------------------------------------------------------------- pricing one gilt-day
def errors(settle, redemption, coupon, yld, dirty, accrued, clean, first_issue, first_coupon=None):
    """Pricer minus DMO for dirty price, accrued interest and clean price (per £100 nominal)."""
    p = gilt_price(settle, redemption, coupon, yld / 100.0, first_issue, first_coupon)
    return p["dirty"] - dirty, p["accrued"] - accrued, p["clean"] - clean


def within(d, a, c) -> bool:
    """Strict rule (as in the 2016 exercise): dirty, accrued and clean all within tolerance."""
    return abs(d) <= DIRTY_TOL and abs(a) <= DIRTY_TOL and abs(c) <= CLEAN_TOL


# ---------------------------------------------------------------- failure diagnostics
# Each cause below is confirmed, not assumed: the failing gilt-day is re-priced under ONE diagnostic
# assumption and must then pass the strict rule. The diagnostics explain failures; the test itself
# (the pricer and its conventions) is never changed.
CAUSE_UNDATED = "undated gilt: outside the pricer's scope"
CAUSE_DOUBLE = "double-dated gilt: outside the pricer's scope"
CAUSE_WI = "when-issued line for a reopening: DMO prices it for settlement on the tranche's issue date"
CAUSE_FIRST_ISSUE = "first issue date is not the launch date"
CAUSE_LONG_FIRST = "new issue with a long first coupon: first coupon date not supplied (pricer defaults to short)"
CAUSE_TRADE_DATE = "DMO accrued interest runs to the trade date, not settlement (DMO data error; clean price matches)"
CAUSE_WI_LONG = ("when-issued line for a reopening during a long first coupon: both causes above "
                 "(tranche settlement and first coupon date)")
CAUSE_WI_REDEMPTION = ("when-issued line labelled with the wrong redemption date (DMO data error); passes "
                       "as the gilt actually issued")
CAUSE_WI_YIELD = ("when-issued line: DMO yield inconsistent with its own clean price that day (DMO data "
                  "error; accrued matches the tranche settlement)")
CAUSE_WI_ACCRUED_ZERO = "when-issued line: DMO accrued interest reported as 0 (DMO data error; yield matches the clean price)"
CAUSE_IL_SPELLING = "index-linked gilt not caught by the filter: name spelled 'Index -Linked'"
CAUSE_UNEXPLAINED = "UNEXPLAINED"


def second_quasi_date(redemption, first_issue):
    """The second quasi-coupon date after the first issue date: the first coupon date of a gilt
    with a long first coupon. None if the gilt has fewer than two quasi dates after issue."""
    k, quasi = 0, []
    while True:
        q = (pd.Timestamp(redemption) - pd.DateOffset(months=6 * k)).date()
        if q <= first_issue:
            break
        quasi.append(q)
        k += 1
    quasi = sorted(quasi)
    return quasi[1] if len(quasi) >= 2 else None


def issue_events() -> pd.DataFrame:
    """D2.1E issue events that carry a price (auctions, syndications, tenders): isin, date. Rows with
    no price are direct issues to the DMO (cash management), which are not market issues."""
    raw = pd.read_excel(paths.D2_1E, header=None)
    e = raw.iloc[5:, [1, 2, 4]].copy()
    e.columns = ["isin", "date", "price"]
    e = e[e["isin"].fillna("").astype(str).str.startswith("GB")]
    e = e[pd.to_numeric(e["price"], errors="coerce").notna()]
    return pd.DataFrame({"isin": e["isin"].values, "date": pd.to_datetime(e["date"]).dt.date.values})


def _passes(settle, redemption, coupon, yld, r, first_issue=None, first_coupon=None) -> bool:
    p = gilt_price(settle, redemption, coupon, yld / 100.0, first_issue, first_coupon)
    return within(p["dirty"] - r.dmo_dirty, p["accrued"] - r.dmo_accrued, p["clean"] - r.dmo_clean)


def diagnose(F: pd.DataFrame, G: pd.DataFrame, first_issue: dict, events: pd.DataFrame) -> pd.Series:
    """Cause of each failing gilt-day in F (failing rows of G). G supplies the underlying gilt of a
    when-issued line; events supplies tranche issue dates (D2.1E)."""
    # underlying gilt for a (coupon, redemption): the ISIN with first-issue data and the most rows
    known = G[G["isin"].isin(first_issue.keys())]
    underlying = (known.groupby(["coupon", "redemption", "isin"]).size().reset_index(name="n")
                  .sort_values("n").drop_duplicates(["coupon", "redemption"], keep="last")
                  .set_index(["coupon", "redemption"])["isin"].to_dict())
    ev = events.groupby("isin")["date"].apply(sorted).to_dict()
    base_redemption = known.groupby("isin")["redemption"].first().to_dict()
    same_coupon = {}
    for (cpn, isin), red in known.groupby(["coupon", "isin"])["redemption"].first().items():
        same_coupon.setdefault(cpn, []).append((isin, red))
    # fallback for a WI line whose redemption date is wrong: match on the name without ' WI'
    by_stem = (known.groupby(["name", "isin"]).size().reset_index(name="n").sort_values("n")
               .drop_duplicates("name", keep="last").set_index("name")["isin"].to_dict())

    causes = []
    for r in F.itertuples(index=False):
        kind = instrument_type(r.name)
        fi = None if pd.isna(r.first_issue) else r.first_issue
        cause = CAUSE_UNEXPLAINED
        if re.search(r"index\s*-\s*linked", r.name, re.I):
            cause = CAUSE_IL_SPELLING
        elif kind == "undated":
            cause = CAUSE_UNDATED
        elif kind == "double-dated":
            cause = CAUSE_DOUBLE
        else:
            # (1) when-issued line: unknown/temporary ISIN or 'WI' in the name. Settle on the
            #     underlying gilt's next priced issue date (within 45 days of the trade date), trying
            #     in turn: as is; with a long first coupon; with the underlying's redemption date
            is_wi = bool(re.search(r"WI$", r.name)) or r.isin not in first_issue
            stem = re.sub(r"\s*WI$", "", r.name)
            base = underlying.get((r.coupon, r.redemption)) or by_stem.get(stem)
            if is_wi and base and base != r.isin:
                nxt = [d for d in ev.get(base, []) if r.date < d <= r.date + dt.timedelta(days=45)]
                base_fi, base_red = first_issue.get(base), base_redemption.get(base, r.redemption)
                trials = [(CAUSE_WI, r.redemption, None)]
                if base_fi:
                    trials.append((CAUSE_WI_LONG, r.redemption, second_quasi_date(r.redemption, base_fi)))
                if base_red != r.redemption:
                    trials.append((CAUSE_WI_REDEMPTION, base_red, None))
                    if base_fi:
                        trials.append((CAUSE_WI_REDEMPTION, base_red, second_quasi_date(base_red, base_fi)))
                if nxt:
                    for label, red, fc in trials:
                        if _passes(nxt[0], red, r.coupon, r.dmo_yield, r, base_fi, fc):
                            cause = label
                            break
                # data errors on a WI day: the tranche-settlement accrued matches the DMO's, but the
                # DMO yield does not reproduce the DMO clean price; or the DMO accrued is 0
                if cause == CAUSE_UNEXPLAINED and nxt:
                    for _, red, fc in trials:
                        p = gilt_price(nxt[0], red, r.coupon, r.dmo_yield / 100.0, base_fi, fc)
                        if abs(p["accrued"] - r.dmo_accrued) <= DIRTY_TOL:
                            cause = CAUSE_WI_YIELD
                            break
                        if r.dmo_accrued == 0 and abs(p["clean"] - r.dmo_clean) <= CLEAN_TOL:
                            cause = CAUSE_WI_ACCRUED_ZERO
                            break
            # (1b) a WI line labelled with another gilt's maturity: try every gilt with the same coupon
            #      that had a priced issue within 45 days (e.g. '4¾% 2010 WI' in Jan 2006 = 4¾% 2020)
            if cause == CAUSE_UNEXPLAINED and is_wi:
                for other, red in same_coupon.get(r.coupon, []):
                    o_nxt = [d for d in ev.get(other, []) if r.date < d <= r.date + dt.timedelta(days=45)]
                    o_fi = first_issue.get(other)
                    if o_nxt and o_fi and red != r.redemption and any(
                            _passes(o_nxt[0], red, r.coupon, r.dmo_yield, r, o_fi, fc)
                            for fc in (None, second_quasi_date(red, o_fi))):
                        cause = CAUSE_WI_REDEMPTION
                        break
            # (2) first issue date: passes when no first issue date is used
            if cause == CAUSE_UNEXPLAINED and fi is not None and _passes(
                    r.settle, r.redemption, r.coupon, r.dmo_yield, r, None):
                cause = f"{CAUSE_FIRST_ISSUE} ({r.first_issue_source})"
            # (3) long first coupon: passes with first coupon = second quasi-coupon date after issue
            if cause == CAUSE_UNEXPLAINED and fi is not None:
                fc = second_quasi_date(r.redemption, fi)
                if fc and _passes(r.settle, r.redemption, r.coupon, r.dmo_yield, r, fi, fc):
                    cause = CAUSE_LONG_FIRST
            # (4) DMO accrued to the trade date: accrued for settlement on the trade date matches and
            #     the clean price is within tolerance
            if cause == CAUSE_UNEXPLAINED and abs(r.clean_err) <= CLEAN_TOL:
                ai_trade = cash_flows(r.date, r.redemption, r.coupon, fi)["accrued"]
                if abs(ai_trade - r.dmo_accrued) <= DIRTY_TOL:
                    cause = CAUSE_TRADE_DATE
        causes.append(cause)
    return pd.Series(causes, index=F.index, dtype=object)


# ---------------------------------------------------------------- final mode: terms and WI lines
CAUSE_WI_NO_TRANCHE = "when-issued line: no priced tranche of the gilt within 45 days (UNEXPLAINED)"


def build_context(mode: str) -> dict:
    """Static inputs for one mode: first issue/coupon dates and their sources, WI-line lookups."""
    if mode == "as_run":
        fi = first_issue_dates_as_run()
        return dict(mode=mode, first_issue=dict(zip(fi["isin"], fi["first_issue"])),
                    first_issue_source=dict(zip(fi["isin"], fi["source"])))
    T = gilt_terms.load_terms()
    return dict(
        mode=mode,
        first_issue=dict(zip(T["isin"], T["first_issue"])),
        first_issue_source=dict(zip(T["isin"], T["first_issue_source"])),
        first_coupon=dict(zip(T["isin"], T["first_coupon"])),
        first_coupon_source=dict(zip(T["isin"], T["first_coupon_source"])),
        flag_rule=dict(zip(T["isin"], T["flag_first_coupon_rule"])),
        maturity=dict(zip(T["isin"], T["maturity"])),
        by_coupon_maturity={(c, m): i for i, c, m in zip(T["isin"], T["coupon"], T["maturity"])},
        by_coupon_year={(c, str(m.year)): i for i, c, m in zip(T["isin"], T["coupon"], T["maturity"])},
        tranches=gilt_terms.tranche_issue_dates(),
    )


def wi_underlying(name: str, isin: str, coupon: float, redemption, ctx: dict):
    """(is_wi_line, underlying ISIN) for a reference-price row in final mode. A WI line has 'WI' at the
    end of its name, or an ISIN unknown to D1A/D2.1E while a known gilt has the same coupon and
    maturity. The underlying is that known gilt: matched on coupon + maturity; for lines named 'WI'
    also on coupon + the maturity year in the name (WI lines quoted with a wrong redemption date)."""
    by_cm = ctx["by_coupon_maturity"].get((coupon, redemption))
    named_wi = bool(re.search(r"WI$", name))
    by_cy = None
    if named_wi:
        stem_year = re.findall(r"(\d{4})", re.sub(r"\s*WI$", "", name))
        by_cy = ctx["by_coupon_year"].get((coupon, stem_year[-1])) if stem_year else None
    unknown = isin not in ctx["first_issue"]
    base = by_cm or by_cy
    is_wi = (named_wi or unknown) and base is not None and base != isin
    return is_wi, (base if is_wi else None)


# ---------------------------------------------------------------- one year
GILT_DAY_COLUMNS = ["year", "name", "isin", "date", "settle", "redemption", "coupon", "dmo_yield",
                    "dmo_dirty", "dmo_accrued", "dmo_clean", "dirty_err", "ai_err", "clean_err",
                    "first_issue", "first_issue_source", "first_coupon", "first_coupon_source",
                    "flag_first_coupon_rule", "wi_line", "underlying_isin", "settle_used", "tranche_found"]


def evaluate_year(year: int, ctx: dict):
    """Price every tested gilt-day of one year. Returns (gilt_days, exclusions, accrued_only)."""
    mode = ctx["mode"]
    tested, excluded = split_year(year, mode)
    rows = []
    for r in tested.itertuples(index=False):
        own = r.isin
        wi, base, settle, found = False, None, r.settle, None
        if mode == "final":
            wi, base = wi_underlying(r.name, r.isin, r.coupon, r.redemption, ctx)
            if wi:                                  # P2: settle on the tranche's issue date
                own = base
                tranche = gilt_terms.next_tranche_date(ctx["tranches"], base, r.date)
                found = tranche is not None
                settle = tranche if found else r.settle
        fi = ctx["first_issue"].get(own)
        fc = ctx.get("first_coupon", {}).get(own)
        d, a, c = errors(settle, r.redemption, r.coupon, r._7, r.dirty, r.accrued, r.clean, fi, fc)
        rows.append(dict(year=year, name=r.name, isin=r.isin, date=r.date, settle=r.settle,
                         redemption=r.redemption, coupon=r.coupon, dmo_yield=r._7, dmo_dirty=r.dirty,
                         dmo_accrued=r.accrued, dmo_clean=r.clean, dirty_err=d, ai_err=a, clean_err=c,
                         first_issue=fi, first_issue_source=ctx["first_issue_source"].get(own, "none"),
                         first_coupon=fc, first_coupon_source=ctx.get("first_coupon_source", {}).get(own),
                         flag_first_coupon_rule=bool(ctx.get("flag_rule", {}).get(own, False)),
                         wi_line=wi, underlying_isin=base, settle_used=settle, tranche_found=found))
    G = pd.DataFrame(rows, columns=GILT_DAY_COLUMNS)    # explicit columns: a year can have no tested rows
    G["pass_dirty"] = G["dirty_err"].abs() <= DIRTY_TOL
    G["pass_strict"] = pd.Series([within(d, a, c) for d, a, c in zip(G.dirty_err, G.ai_err, G.clean_err)],
                                 index=G.index, dtype=bool)
    G["in_window"] = (G["date"] >= TEST_WINDOW[0]) & (G["date"] <= TEST_WINDOW[1])

    X = (excluded.groupby(["reason", "name"]).agg(isin=("isin", "first"), gilt_days=("date", "size"),
                                                  first=("date", "min"), last=("date", "max"))
         .reset_index().assign(year=year))
    X["type"] = X["name"].map(instrument_type)
    X.loc[X["name"].str.contains(r"\bI-L\b"), "type"] = "index-linked ('I-L' in name)"

    # diagnostic only: accrued interest on rows that have no DMO yield (so cannot be tested)
    ny = excluded[excluded["reason"] == "no DMO yield published"]
    acc = []
    for r in ny.itertuples(index=False):
        if r.settle >= r.redemption:
            continue
        cpn = parse_coupon(r.name)
        ai = cash_flows(r.settle, r.redemption, cpn, ctx["first_issue"].get(r.isin),
                        ctx.get("first_coupon", {}).get(r.isin))["accrued"]
        acc.append(dict(year=year, name=r.name, isin=r.isin, date=r.date, settle=r.settle,
                        type=instrument_type(r.name), dmo_accrued=r.accrued, ai_err=ai - r.accrued,
                        pre_nov_1998=r.settle < CONVENTION_CHANGE))
    return G, X, pd.DataFrame(acc)


def _evaluate(args):
    return evaluate_year(*args)


def diagnose_final(F: pd.DataFrame, ctx: dict) -> pd.Series:
    """Cause of each failing gilt-day in final mode (after P1-P4). Every cause is confirmed by a
    re-price under one diagnostic assumption; what remains are DMO data errors."""
    causes = []
    for r in F.itertuples(index=False):
        cause = CAUSE_UNEXPLAINED
        if r.wi_line:
            base = r.underlying_isin
            fi, fc = ctx["first_issue"].get(base), ctx["first_coupon"].get(base)
            if r.tranche_found:
                p = gilt_price(r.settle_used, r.redemption, r.coupon, r.dmo_yield / 100.0, fi, fc)
                base_red = ctx["maturity"].get(base)
                if base_red != r.redemption and _passes(r.settle_used, base_red, r.coupon, r.dmo_yield,
                                                        r, fi, fc):
                    cause = CAUSE_WI_REDEMPTION
                elif abs(p["accrued"] - r.dmo_accrued) <= DIRTY_TOL:
                    cause = CAUSE_WI_YIELD
                elif r.dmo_accrued == 0 and abs(p["clean"] - r.dmo_clean) <= CLEAN_TOL:
                    cause = CAUSE_WI_ACCRUED_ZERO
            else:
                # a WI line labelled with another gilt's maturity: any gilt with the same coupon and a
                # priced tranche within 45 days that reproduces the DMO figures
                for other, mat in ((i, m) for (c, m), i in ctx["by_coupon_maturity"].items() if c == r.coupon):
                    tr = gilt_terms.next_tranche_date(ctx["tranches"], other, r.date)
                    if tr and other != base and _passes(tr, mat, r.coupon, r.dmo_yield, r,
                                                        ctx["first_issue"].get(other),
                                                        ctx["first_coupon"].get(other)):
                        cause = CAUSE_WI_REDEMPTION
                        break
                else:
                    cause = CAUSE_WI_NO_TRANCHE
        elif abs(r.clean_err) <= CLEAN_TOL:
            ai_trade = cash_flows(r.date, r.redemption, r.coupon, r.first_issue, r.first_coupon)["accrued"]
            if abs(ai_trade - r.dmo_accrued) <= DIRTY_TOL:
                cause = CAUSE_TRADE_DATE
        causes.append(cause)
    return pd.Series(causes, index=F.index, dtype=object)


# ---------------------------------------------------------------- the original 2016 report
def classify(row, first_issue):
    """Which known convention issue explains a Module-0 mismatch?"""
    cf = cash_flows(row.settle, row.redemption, row.coupon, first_issue)
    nxt = cf["dates"][0]          # next coupon date (no long first coupons in this data)
    labels = []
    if row.settle == ex_dividend_date(nxt):
        labels.append("A: settles ON ex-div date")
    if cf["is_ex"] and nxt == row.redemption:
        labels.append("B: final period, ex-div")
    if first_issue is not None and row.settle <= nxt and (nxt - first_issue).days < 200:
        labels.append("C: new issue (irregular 1st coupon / when-issued)")
    return "; ".join(labels) or "UNEXPLAINED"


def report_2016(G16: pd.DataFrame):
    """The original Exercise A output for 2016: Module 0 comparison and ex-dividend counting rules."""
    E = G16.copy()
    naive = [gilt_price(r.settle, r.redemption, r.coupon, r.dmo_yield / 100.0, None, None,
                        cum_on_ex_date=False) for r in E.itertuples()]
    E["naive_dirty_err"] = [p["dirty"] for p in naive] - E["dmo_dirty"]
    E["naive_ai_err"] = [p["accrued"] for p in naive] - E["dmo_accrued"]
    E["naive_bad"] = (E.naive_dirty_err.abs() > DIRTY_TOL) | (E.naive_ai_err.abs() > DIRTY_TOL)
    E["bad"] = ~E["pass_strict"]

    print("\n=== 2016: Module 0 conventions (settle >= ex-div date is ex; no first-issue handling) ===")
    nb = E[E.naive_bad].copy()
    nb["why"] = [classify(r, r.first_issue) for r in nb.itertuples()]
    print(f"mismatching gilt-days: {len(nb)} of {len(E)}")
    print(nb.groupby("why").agg(days=("name", "size"), gilts=("name", "nunique")).to_string())

    fin = [r for r in E.itertuples()
           if cash_flows(r.settle, r.redemption, r.coupon)["is_ex"]
           and len(cash_flows(r.settle, r.redemption, r.coupon)["dates"]) == 1]
    print(f"B: final-period ex-div gilt-days (DMO accrued = 0, handled): {len(fin)} "
          f"across {len({r.name for r in fin})} gilts")

    print("\n=== Ex-dividend date: which business-day counting rule matches the DMO? ===")

    def roll_back_first(coupon_date, n=7):
        """numpy busday_offset(roll='backward') style: roll a non-business coupon date back to the
        previous business day, which then counts as day 0."""
        d = coupon_date
        while not is_business_day(d):
            d -= dt.timedelta(days=1)
        k = 0
        while k < n:
            d -= dt.timedelta(days=1)
            if is_business_day(d):
                k += 1
        return d

    def weekdays_only(coupon_date, n=7):
        """pandas BDay without UK holidays."""
        d, k = coupon_date, 0
        while k < n:
            d -= dt.timedelta(days=1)
            if d.weekday() < 5:
                k += 1
        return d

    rules = {"ours (UK holidays, coupon date not counted)": ex_dividend_date,
             "roll back first (numpy style)": roll_back_first,
             "weekdays only (pandas BDay, no holidays)": weekdays_only}
    d1a = load_d1a(D1A_FILE)
    checks = []
    for g in d1a.itertuples():
        cf = cash_flows(g.dmo_ex_div, g.redemption, g.coupon, g.first_issue)
        nxt = cf["dates"][0]
        checks.append(dict(coupon_date=nxt, weekend=not is_business_day(nxt), dmo=g.dmo_ex_div))
    C = pd.DataFrame(checks)
    print(f"(1) D1A published ex-div dates: {len(C)} gilts, {C.weekend.sum()} with a non-business-day coupon")
    for label, f in rules.items():
        print(f"    {label:45s}: {(C.coupon_date.map(f) == C.dmo).sum()}/{len(C)} match")
    print("(2) 2016 reference prices: days where the rule's ex/cum flag disagrees with the DMO's")
    sub = E[[len(cash_flows(r.settle, r.redemption, r.coupon, r.first_issue)["dates"]) > 1
             for r in E.itertuples()]]
    dmo_ex = sub.dmo_accrued < 0
    for label, f in rules.items():
        flags = [r.settle > f(cash_flows(r.settle, r.redemption, r.coupon, r.first_issue)["dates"][0])
                 for r in sub.itertuples()]
        print(f"    {label:45s}: {(pd.Series(flags, index=sub.index) != dmo_ex).sum()} disagreements")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    E.to_csv(OUT_DIR / "exercise_a_errors.csv", index=False)


# ---------------------------------------------------------------- summary tables
def by_year(G: pd.DataFrame, X: pd.DataFrame) -> pd.DataFrame:
    """Pass rate per year under the spec rule (dirty) and the strict rule (dirty, accrued, clean)."""
    t = G.groupby("year").agg(tested=("name", "size"), gilts=("isin", "nunique"),
                              pass_dirty=("pass_dirty", "sum"), pass_strict=("pass_strict", "sum"),
                              max_abs_dirty_err=("dirty_err", lambda s: s.abs().max()))
    t["pass_rate_dirty"] = t["pass_dirty"] / t["tested"]
    t["pass_rate_strict"] = t["pass_strict"] / t["tested"]
    fails = (G[~G["pass_strict"]].pivot_table(index="year", columns="cause", values="name",
                                              aggfunc="size", fill_value=0).add_prefix("fail: "))
    excl = (X.pivot_table(index="year", columns="reason", values="gilt_days", aggfunc="sum",
                          fill_value=0).add_prefix("excluded: "))
    out = t.join(fails, how="outer").join(excl, how="outer")
    count_cols = [c for c in out.columns if c.startswith(("fail: ", "excluded: "))] + \
                 ["tested", "gilts", "pass_dirty", "pass_strict"]
    out[count_cols] = out[count_cols].fillna(0).astype(int)
    out.index.name = "year"
    return out.reset_index()


def main(years=YEARS, mode: str = "final"):
    """Run the test for `years` in `mode` ('final' or 'as_run'); returns (by_year, gilt_days,
    exclusions, accrued_only). Writes data/processed_data/stage1/<mode>/ when all years are run."""
    years = list(years)
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    ctx = build_context(mode)
    print(f"Mode: {mode}. First issue dates: " + ", ".join(
        f"{v} {k}" for k, v in pd.Series(ctx["first_issue_source"]).value_counts().items()))

    with ProcessPoolExecutor(max_workers=min(len(years), os.cpu_count() or 1)) as pool:
        results = list(pool.map(_evaluate, [(y, ctx) for y in years]))
    G = pd.concat([r[0] for r in results], ignore_index=True)
    X = pd.concat([r[1] for r in results], ignore_index=True)
    A = pd.concat([r[2] for r in results], ignore_index=True)
    G["type"] = G["name"].map(instrument_type)
    if mode == "as_run":
        G["wi_line"] = when_issued_lines(G)
    G["cause"] = pd.Series(None, index=G.index, dtype=object)
    fail = ~G["pass_strict"]
    if mode == "as_run":
        fi = first_issue_dates_as_run()
        G.loc[fail, "cause"] = diagnose(G[fail], G, dict(zip(fi["isin"], fi["first_issue"])), issue_events())
    else:
        G.loc[fail, "cause"] = diagnose_final(G[fail], ctx)
    T = by_year(G, X)

    pd.set_option("display.width", 200)
    print(f"\n=== Pass rate per year (tolerance 1e-4 per £100; mode {mode}) ===")
    cols = ["year", "tested", "gilts", "pass_rate_dirty", "pass_rate_strict", "max_abs_dirty_err"]
    print(T[cols].to_string(index=False, float_format=lambda v: f"{v:.6f}"))
    W = G[G["in_window"]]
    tot = W["pass_dirty"].mean() if len(W) else float("nan")
    print(f"\nTest window {TEST_WINDOW[0]} to {TEST_WINDOW[1]}: {len(W):,} gilt-days; dirty within 1e-4: "
          f"{W['pass_dirty'].sum():,} ({tot:.4%}); strict: {W['pass_strict'].mean():.4%}. "
          f"Spec pass mark {SPEC_PASS_RATE:.1%} -> {'PASS' if tot >= SPEC_PASS_RATE else 'FAIL'}")

    F = G[~G["pass_strict"]]
    print("\n=== Failing gilt-days by cause (strict rule) ===")
    if len(F):
        print(F.groupby("cause").agg(gilt_days=("name", "size"), lines=("isin", "nunique"),
                                     first=("date", "min"), last=("date", "max"),
                                     max_dirty_err=("dirty_err", lambda s: s.abs().max()))
              .to_string())
    else:
        print("none")

    print("\n=== Excluded gilt-days per year, by reason ===")
    print(X.pivot_table(index="year", columns="reason", values="gilt_days", aggfunc="sum",
                        fill_value=0).to_string())

    if 2016 in years:
        report_2016(G[G["year"] == 2016])

    if years == list(YEARS):
        out = STAGE1_DIR / mode
        out.mkdir(parents=True, exist_ok=True)
        T.to_csv(out / "by_year.csv", index=False)
        G.to_csv(out / "gilt_days.csv.gz", index=False)          # ~41 MB uncompressed
        F.to_csv(out / "failures.csv", index=False)
        X.to_csv(out / "exclusions.csv", index=False)
        A.to_csv(out / "accrued_only.csv.gz", index=False)
        print(f"\nSaved by_year, gilt_days, failures, exclusions, accrued_only to {out}")
    return T, G, X, A


if __name__ == "__main__":
    args = sys.argv[1:]
    run_mode = "as_run" if "--as-run" in args else "final"
    yrs = [int(a) for a in args if a.isdigit()]
    main(yrs or YEARS, run_mode)
