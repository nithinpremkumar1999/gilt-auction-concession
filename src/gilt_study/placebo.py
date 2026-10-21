"""Stage 5: placebo test (build spec §8): the same statistics on randomly drawn non-auction dates.

Design (proposed; listed at the Stage 5 gate)
----------------------------------------------
For each real auction (gilt g, date T, bucket b) a placebo event is the SAME gilt on a random date D
such that:
  * D is a UK business day on which no conventional gilt was auctioned;
  * g has no auction within +-10 business days of D (its own auction windows stay out);
  * g is in the same DMO bucket at D as at T (years to maturity from next-day settlement);
  * g was issued at least 121 business days before D (the beta window is real trading history), and
    the whole window D-121 .. D+10 lies inside the curve panel;
  * for M3, D+10 is on or before 21 Jul 2017 and D-10 on or after 1 Nov 1998 (reference prices).
One draw = one placebo date per real auction; the statistic (mean of each of the three numbers, by
bucket and overall) is recomputed for every draw. N_DRAWS = 1,000. Two-sided p-value: the share of
draws whose distance from the placebo average is at least the real mean's distance from it. Draws use
a fixed seed.

The M2 statistic is computed exactly as for the real auctions (measures.py): control = mean daily
change of the BoE 2-30y points more than 3 years from the gilt's maturity (available on every day of
the window), beta by OLS with intercept over k = -120..-21, AR = dy - beta*dc, three numbers from
the CAR with base T-6. M3 = the residual (market yield - model yield) changes over the same windows.

Inputs: daily model yields of every auctioned gilt over its life (interim cache, built here).
Run:  python -m gilt_study.placebo            (cache: ~15 min on 2 cores the first time)
"""
import datetime as dt
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from . import auctions as au, config, measures as ms, paths
from .curve import load_panel, maturity_columns

GILT_YIELDS_FILE = paths.INTERIM / "auctioned_gilts_daily_model_yields.csv.gz"
OUT_DIR = paths.PROCESSED / "placebo"
N_DRAWS = 1000
SEED = 20261020
OWN_AUCTION_GAP = 10              # business days
MIN_YEARS_LEFT = 1.7              # daily model yields are kept while the gilt has >= 1.7y to run


# ============================================================================ daily model yields
def build_gilt_daily_yields(write: bool = True) -> pd.DataFrame:
    """Model yield (%) of every auctioned gilt on every curve date from its first issue (or the panel
    start) until 1.7 years before maturity; next-day settlement. Reuses the auction-window cache."""
    P = au.load_auction_panel()
    cp = load_panel()
    have = ms.load_model_yields()
    have_keys = set(zip(have["isin"], have["curve_date"]))
    G = P.groupby("isin").agg(maturity=("maturity", "first"), coupon=("coupon", "first"),
                              fi=("first_issue", "first"), fc=("first_coupon", "first"))
    need = {}
    for isin, g in G.iterrows():
        fi = g.fi if isinstance(g.fi, dt.date) else None
        fc = g.fc if isinstance(g.fc, dt.date) else None
        lo = fi or cp.index[0].date()
        hi = g.maturity - dt.timedelta(days=int(MIN_YEARS_LEFT * 365.25))
        for ts in cp.index[(cp.index.date >= lo) & (cp.index.date <= hi)]:
            if (isin, ts.date()) not in have_keys:
                need.setdefault(ts, []).append((isin, g.maturity, g.coupon, fi, fc))
    items = sorted(need.items())
    n_workers = os.cpu_count() or 1
    chunks = [items[i::n_workers * 8] for i in range(n_workers * 8)]
    with ProcessPoolExecutor(max_workers=n_workers) as pool:
        res = [x for part in pool.map(ms._model_yields_for_dates, [(c,) for c in chunks]) for x in part]
    new = pd.DataFrame(res, columns=["isin", "curve_date", "settle", "model_yield"])
    Y = pd.concat([have, new], ignore_index=True).drop_duplicates(["isin", "curve_date"]).sort_values(["isin", "curve_date"])
    if write:
        Y.to_csv(GILT_YIELDS_FILE, index=False, float_format="%.12g")
    return Y.reset_index(drop=True)


def load_gilt_daily_yields() -> pd.DataFrame:
    Y = pd.read_csv(GILT_YIELDS_FILE, float_precision="round_trip")
    Y["curve_date"] = [dt.date.fromisoformat(v) for v in Y["curve_date"]]
    return Y


# ============================================================================ the event engine
class Engine:
    """Vectorised M2 (B-beta) and M3 three numbers for any set of (gilt, curve-date position) events,
    using exactly the definitions of measures.py. Validated by reproducing the real auctions."""

    def __init__(self):
        cp = load_panel()
        self.index = cp.index
        self.dates = np.array(cp.index.date)
        self.pos = {d: i for i, d in enumerate(self.dates)}
        grid = [m for m in maturity_columns(cp) if round(m, 6) in set(ms.CONTROL_GRID)]
        self.grid = np.array(grid)
        Z = cp[grid].to_numpy(float)
        self.DZ = np.vstack([np.full((1, len(grid)), np.nan), 100.0 * np.diff(Z, axis=0)])
        P = au.load_auction_panel()
        self.P = P
        self.gilts = sorted(P["isin"].unique())
        self.gid = {g: i for i, g in enumerate(self.gilts)}
        terms = P.groupby("isin").agg(maturity=("maturity", "first"), fi=("first_issue", "first"))
        self.maturity = np.array([terms.at[g, "maturity"] for g in self.gilts])
        self.first_issue = [terms.at[g, "fi"] if isinstance(terms.at[g, "fi"], dt.date) else None for g in self.gilts]
        Y = load_gilt_daily_yields()
        self.Y = np.full((len(self.gilts), len(self.dates)), np.nan)
        self.Y[[self.gid[g] for g in Y["isin"]], [self.pos[d] for d in Y["curve_date"]]] = Y["model_yield"].to_numpy()
        MY = ms.load_market_yields()
        MY = MY[MY["isin"].isin(self.gid) & MY["date"].isin(self.pos)]
        self.MK = np.full_like(self.Y, np.nan)
        self.MK[[self.gid[g] for g in MY["isin"]], [self.pos[d] for d in MY["date"]]] = MY["market_yield"].to_numpy()
        # years to maturity from next-day settlement (the next curve date)
        nxt = np.r_[self.dates[1:], self.dates[-1:]]
        self.ytm = np.array([[(m - d).days / 365.25 for d in nxt] for m in self.maturity])

    def m2(self, g: np.ndarray, p: np.ndarray) -> np.ndarray:
        """(n, 3) pre/day/post (B-beta) for events of gilts g at positions p."""
        ks = np.arange(ms.FIRST_K, ms.M2_WINDOW[1] + 1)                 # -121..10
        idx = p[:, None] + ks[None, :]
        y = self.Y[g[:, None], idx]
        dy = 100.0 * np.diff(y, axis=1)                                   # k = -120..10
        dz = self.DZ[idx[:, 1:]]                                          # (n, 131, 57)
        avail = ~np.isnan(dz).any(axis=1)                                 # on every day used
        ytm = self.ytm[g, p]
        mask = avail & (np.abs(self.grid[None, :] - ytm[:, None]) > ms.CONTROL_EXCLUSION_YEARS)
        dc = np.einsum("nkm,nm->nk", np.nan_to_num(dz), mask) / mask.sum(axis=1)[:, None]
        nb = ms.BETA_WINDOW[1] - ms.BETA_WINDOW[0] + 1                   # 100 changes, k = -120..-21
        X, Yb = dc[:, :nb], dy[:, :nb]
        xm, ym = X.mean(axis=1, keepdims=True), Yb.mean(axis=1, keepdims=True)
        beta = ((X - xm) * (Yb - ym)).sum(axis=1) / ((X - xm) ** 2).sum(axis=1)
        ar = dy - beta[:, None] * dc
        k0 = -ms.FIRST_K - 1                                              # column of k = 0 in dy
        pre = ar[:, k0 - 5:k0].sum(axis=1)
        day = ar[:, k0]
        post = ar[:, k0 + 1:k0 + 6].sum(axis=1)
        return np.column_stack([pre, day, post])

    def m3(self, g: np.ndarray, p: np.ndarray) -> np.ndarray:
        """(n, 3) pre/day/post of the bond residual (market - model, bp)."""
        r = lambda k: 100.0 * (self.MK[g, p + k] - self.Y[g, p + k])
        return np.column_stack([r(-1) - r(-6), r(0) - r(-1), r(5) - r(0)])


def candidates(E: Engine, for_m3: bool = False) -> dict:
    """Allowed placebo positions for every real auction (see the module docstring)."""
    auction_dates = set(E.P["auction_date"])
    is_auction_day = np.array([d in auction_dates for d in E.dates])
    n = len(E.dates)
    lo_pos, hi_pos = -ms.FIRST_K, n - 1 - ms.M2_WINDOW[1]
    out = {}
    own = E.P.groupby("isin")["auction_date"].apply(lambda s: np.array([E.pos[d] for d in s])).to_dict()
    for r in E.P.itertuples(index=False):
        gi = E.gid[r.isin]
        pp = np.arange(lo_pos, hi_pos + 1)
        ok = ~is_auction_day[pp]
        ok &= np.min(np.abs(pp[:, None] - own[r.isin][None, :]), axis=1) > OWN_AUCTION_GAP
        b = np.array([au.bucket(x) for x in E.ytm[gi, pp]])
        ok &= b == r.bucket
        fi = E.first_issue[gi]
        if fi is not None:
            ok &= E.dates[pp + ms.FIRST_K] >= fi
        win = pp[:, None] + np.arange(ms.FIRST_K, ms.M2_WINDOW[1] + 1)[None, :]
        ok &= ~np.isnan(E.Y[gi][win]).any(axis=1)
        if for_m3:
            ok &= (E.dates[pp - 10] >= ms.REF_DATA_WINDOW[0]) & (E.dates[pp + 10] <= ms.REF_DATA_WINDOW[1])
            for k in (-6, -1, 0, 5):
                ok &= ~np.isnan(E.MK[gi, pp + k])
        out[f"{r.auction_date}_{r.isin}"] = (gi, pp[ok])
    return out


def run(n_draws: int = N_DRAWS, seed: int = SEED, write: bool = True) -> dict:
    """Real statistics, the placebo distributions and p-values for M2 (B-beta) and M3."""
    E = Engine()
    M = ms.load_measures().set_index("auction_id")
    rng = np.random.default_rng(seed)
    results = {}
    for measure, cols, for_m3 in [("M2 (B-β)", ["m2_pre_bbeta_bp", "m2_day_bbeta_bp", "m2_post_bbeta_bp"], False),
                                  ("M3", ["m3_pre_bp", "m3_day_bp", "m3_post_bp"], True)]:
        cand = candidates(E, for_m3)
        real = M[cols].dropna()
        ids = [a for a in real.index if len(cand[a][1]) > 0]
        g = np.array([cand[a][0] for a in ids])
        buckets = M.loc[ids, "bucket"].to_numpy()
        # validation: the engine reproduces the real numbers at the real auction positions
        p_real = np.array([E.pos[M.at[a, "auction_date"]] for a in ids])
        engine_real = (E.m2 if not for_m3 else E.m3)(g, p_real)
        check = float(np.nanmax(np.abs(engine_real - real.loc[ids].to_numpy())))
        stat_real = {}
        for grp in ["all"] + BUCKETS:
            sel = np.ones(len(ids), bool) if grp == "all" else buckets == grp
            stat_real[grp] = real.loc[ids].to_numpy()[sel].mean(axis=0)
        draws = {grp: np.empty((n_draws, 3)) for grp in stat_real}
        for d in range(n_draws):
            p = np.array([rng.choice(cand[a][1]) for a in ids])
            v = (E.m2 if not for_m3 else E.m3)(g, p)
            for grp in draws:
                sel = np.ones(len(ids), bool) if grp == "all" else buckets == grp
                draws[grp][d] = np.nanmean(v[sel], axis=0)
        rows = []
        for grp in draws:
            for j, w in enumerate(WINDOWS):
                null = draws[grp][:, j]
                rows.append(dict(measure=measure, group=grp, window=w, n_events=int((buckets == grp).sum()) if grp != "all" else len(ids),
                                 real_mean_bp=stat_real[grp][j], placebo_mean_bp=null.mean(), placebo_p2_5=np.percentile(null, 2.5),
                                 placebo_p97_5=np.percentile(null, 97.5),
                                 p_value=float(np.mean(np.abs(null - null.mean()) >= abs(stat_real[grp][j] - null.mean())))))
        results[measure] = dict(table=pd.DataFrame(rows).assign(engine_check_max_abs=check,
                                                                no_placebo_date=int(len(real) - len(ids))),
                                check=check, events=len(ids),
                                no_candidate=int(len(real) - len(ids)), draws=draws)
    if write:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        pd.concat([r["table"] for r in results.values()]).to_csv(OUT_DIR / "placebo_results.csv", index=False)
        rows = []
        for measure, r in results.items():
            for grp, arr in r["draws"].items():
                for d in range(arr.shape[0]):
                    rows.append(dict(measure=measure, group=grp, draw=d, pre=arr[d, 0], day=arr[d, 1], post=arr[d, 2]))
        pd.DataFrame(rows).to_csv(OUT_DIR / "placebo_draws.csv.gz", index=False, float_format="%.6g")
    return results


WINDOWS = ["pre", "day", "post"]
BUCKETS = ["short", "medium", "long"]


if __name__ == "__main__" and "--build-yields" in sys.argv:
    Y = build_gilt_daily_yields()
    print(f"daily model yields: {len(Y):,} gilt-days for {Y['isin'].nunique()} gilts -> {GILT_YIELDS_FILE}")
elif __name__ == "__main__":
    R = run()
    pd.set_option("display.width", 200)
    for m, r in R.items():
        print(f"{m}: {r['events']} events ({r['no_candidate']} without a placebo date); engine check max |diff| {r['check']:.2e}")
        print(r["table"].round(3).to_string(index=False))
