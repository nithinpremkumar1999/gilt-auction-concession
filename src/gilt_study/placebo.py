"""Stage 5: placebo test (build spec §8; decisions #18, #20): the same statistics on randomly drawn
non-auction dates. Inference on the PM's three numbers leads with the placebo-centred p-value.

Design (decision #18)
---------------------
For each real auction (gilt g, date T, bucket b) a placebo event is the SAME gilt on a random date D
such that:
  * D is a UK business day on which no conventional gilt was auctioned;
  * g has no auction within +-10 business days of D (its own auction windows stay out);
  * g is in the same DMO bucket at D as at T (years to maturity from next-day settlement);
  * g was issued at least 121 business days before D (the beta window is real trading history), and
    the whole window D-121 .. D+10 lies inside the curve panel;
  * for M3, the residuals the statistic needs exist at D (both ends of the window for a three-number
    statistic; every day T-10..T+10 for the path). Each M3 window is therefore drawn on its own, with
    the same sample of real auctions as that window's headline mean.
Auctions with no eligible date are dropped from the test and counted (`no_placebo_date`).
One draw = one placebo date per real auction; the statistic (mean of each of the three numbers, overall,
by bucket and by the real auction's regime) is recomputed for every draw. N_DRAWS = 1,000.
Placebo-centred two-sided p-value: the share of draws whose distance from the placebo average is at
least the real mean's distance from it. With 1,000 draws the smallest attainable p is 0.001 ("< 0.001"
when no draw is as extreme). Draws use a fixed seed.

A second design, "same regime", adds one condition: D lies in the same regime as T. Under decision
#18 a QE-era auction's placebo date can fall in another regime, so the placebo centre mixes regimes.
Chart gate (21 Oct 2026): decision #18 stays the main placebo; "same regime" is a labelled robustness
check, added after seeing results (`design_note`).

Extra windows (chart gate, 21 Oct 2026; added after seeing chart 1, `window_note`): M2 and M3 pre10
(T-10 -> T-1, robustness) and the M3 total move (T-10 -> T+1). The M2 one reuses the main draws' dates;
the M3 ones use their own random stream, so every earlier result is reproduced exactly.

The M2 statistic is computed exactly as for the real auctions (measures.py): control = mean daily
change of the BoE 2-30y points more than 3 years from the gilt's maturity (available on every day of
the window), beta by OLS with intercept over k = -120..-21, AR = dy - beta*dc, three numbers from
the CAR with base T-6. M3 = the residual (market yield - model yield) changes over the same windows.
For the report's path chart, the mean placebo paths (CAR, and the M3 residual relative to T-6, for
k = -10..+10) are kept for every draw of the main design.

Inputs: daily model yields of every auctioned gilt over its life (interim cache, built here).
Run:  python -m gilt_study.placebo --build-yields   (cache: ~12 min on 2 cores, once)
      python -m gilt_study.placebo                  (both designs, ~5 min)
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

        self.regime = np.array([au.regime(d) for d in self.dates])

    # ---------------------------------------------------------------- M2 (B-beta)
    def m2_ar(self, g: np.ndarray, p: np.ndarray) -> np.ndarray:
        """(n, 131) abnormal changes AR_k = dy_k - beta*dc_k for k = -120..+10."""
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
        return dy - beta[:, None] * dc

    @staticmethod
    def _col(k: int) -> int:
        """Column of AR_k in the m2_ar output (k = -120 is column 0)."""
        return k - ms.FIRST_K - 1

    def m2(self, g: np.ndarray, p: np.ndarray) -> np.ndarray:
        """(n, 3) pre/day/post (B-beta) for events of gilts g at curve-date positions p."""
        return self.m2_numbers(self.m2_ar(g, p))

    def m2_numbers(self, ar: np.ndarray) -> np.ndarray:
        c = self._col
        pre = ar[:, c(-5):c(-1) + 1].sum(axis=1)                          # CAR(-1) - CAR(-6)
        day = ar[:, c(0)]
        post = ar[:, c(1):c(5) + 1].sum(axis=1)                           # CAR(5) - CAR(0)
        return np.column_stack([pre, day, post])

    def m2_window(self, ar: np.ndarray, a: int, b: int) -> np.ndarray:
        """CAR(b) - CAR(a) for a < b: the AR of days a+1..b."""
        c = self._col
        return ar[:, c(a + 1):c(b) + 1].sum(axis=1)

    def m2_path(self, ar: np.ndarray) -> np.ndarray:
        """(n, 21) CAR for k = -10..+10, 0 at the base T-6 (measures.cumulate)."""
        c = self._col
        out = np.zeros((ar.shape[0], len(PATH_K)))
        for j, k in enumerate(PATH_K):
            if k > ms.M2_BASE:
                out[:, j] = ar[:, c(ms.M2_BASE + 1):c(k) + 1].sum(axis=1)
            elif k < ms.M2_BASE:
                out[:, j] = -ar[:, c(k + 1):c(ms.M2_BASE) + 1].sum(axis=1)
        return out

    # ---------------------------------------------------------------- M3 (bond residual)
    def residual(self, g: np.ndarray, p: np.ndarray, k: int) -> np.ndarray:
        return 100.0 * (self.MK[g, p + k] - self.Y[g, p + k])

    def m3_window(self, g: np.ndarray, p: np.ndarray, a: int, b: int) -> np.ndarray:
        """Residual change from k = a to k = b (bp)."""
        return self.residual(g, p, b) - self.residual(g, p, a)

    def m3(self, g: np.ndarray, p: np.ndarray) -> np.ndarray:
        """(n, 3) pre/day/post of the bond residual (market - model, bp)."""
        return np.column_stack([self.m3_window(g, p, a, b) for a, b in ms.PM_NUMBERS.values()])

    def m3_path(self, g: np.ndarray, p: np.ndarray) -> np.ndarray:
        """(n, 21) residual at k = -10..+10 relative to T-6."""
        base = self.residual(g, p, ms.M2_BASE)
        return np.column_stack([self.residual(g, p, k) - base for k in PATH_K])


PATH_K = np.arange(ms.M2_WINDOW[0], ms.M2_WINDOW[1] + 1)               # -10..+10
WINDOWS = list(ms.PM_NUMBERS)                                           # pre, day, post
BUCKETS = ["short", "medium", "long"]
REGIMES = ["pre-crisis", "QE", "LDI stress", "active QT"]               # post-QT-decision (2) is too small
DESIGNS = {"main": False, "same regime": True}                         # name: same-regime condition
DESIGN_NOTES = {"main": "decision #18",
                "same regime": "robustness: placebo dates in the auction's own regime (added after seeing results, 21 Oct 2026)"}
EXTRA_NOTE = "added after seeing chart 1 (21 Oct 2026)"


def candidates(E: Engine, need_k=None, same_regime: bool = False) -> dict:
    """Allowed placebo positions for every real auction (module docstring). need_k: offsets at which
    the M3 residual must exist (None for M2)."""
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
        if same_regime:
            ok &= E.regime[pp] == r.regime
        fi = E.first_issue[gi]
        if fi is not None:
            ok &= E.dates[pp + ms.FIRST_K] >= fi
        win = pp[:, None] + np.arange(ms.FIRST_K, ms.M2_WINDOW[1] + 1)[None, :]
        ok &= ~np.isnan(E.Y[gi][win]).any(axis=1)
        for k in (need_k or ()):
            ok &= ~np.isnan(E.MK[gi, pp + k]) & ~np.isnan(E.Y[gi, pp + k])
        out[f"{r.auction_date}_{r.isin}"] = (gi, pp[ok])
    return out


def _groups(M: pd.DataFrame, ids) -> dict:
    """Event selections: all, each bucket and each regime (of the real auction)."""
    b = M.loc[ids, "bucket"].to_numpy()
    rg = M.loc[ids, "regime"].to_numpy()
    out = {"all": np.ones(len(ids), bool)}
    out.update({x: b == x for x in BUCKETS})
    out.update({x: rg == x for x in REGIMES if (rg == x).any()})
    return out


def _p_value(null: np.ndarray, real: float) -> float:
    centre = null.mean()
    return float(np.mean(np.abs(null - centre) >= abs(real - centre)))


def _test(E, M, rng, cand, real: pd.Series, stat, n_draws):
    """One statistic (a single window): draw placebo positions for every real event with a candidate;
    return per-group real means, null draws, the engine check and the count without a date."""
    ids = [a for a in real.index if len(cand[a][1]) > 0]
    g = np.array([cand[a][0] for a in ids], dtype=int)
    p_real = np.array([E.pos[M.at[a, "auction_date"]] for a in ids])
    check = float(np.nanmax(np.abs(stat(g, p_real) - real.loc[ids].to_numpy())))
    groups = _groups(M, ids)
    rv = real.loc[ids].to_numpy()
    null = {k: np.empty(n_draws) for k in groups}
    for d in range(n_draws):
        p = np.array([rng.choice(cand[a][1]) for a in ids])
        v = stat(g, p)
        for k, sel in groups.items():
            null[k][d] = v[sel].mean()
    return dict(real={k: float(rv[sel].mean()) for k, sel in groups.items()}, null=null,
                n={k: int(sel.sum()) for k, sel in groups.items()}, check=check, no_date=len(real) - len(ids))


def run(n_draws: int = N_DRAWS, seed: int = SEED, write: bool = True) -> dict:
    """Placebo distributions and placebo-centred p-values for M2 (B-beta) and M3, both designs, plus
    the mean placebo paths (main design, all auctions)."""
    E = Engine()
    M = ms.load_measures().set_index("auction_id")
    M["regime"] = M.index.map(E.P.assign(auction_id=[f"{d}_{i}" for d, i in zip(E.P["auction_date"], E.P["isin"])])
                              .set_index("auction_id")["regime"])
    rng = np.random.default_rng(seed)
    rng_extra = np.random.default_rng([seed, 1])     # own stream: the main results stay as before
    rows, draw_rows, path_rows = [], [], []

    def record(design, measure, window, t):
        for k in t["real"]:
            null = t["null"][k]
            rows.append(dict(design=design, design_note=DESIGN_NOTES[design], measure=measure, group=k,
                             group_type="all" if k == "all" else "bucket" if k in BUCKETS else "regime",
                             window=window, n_events=t["n"][k], real_mean_bp=t["real"][k],
                             placebo_mean_bp=null.mean(), placebo_p2_5=np.percentile(null, 2.5),
                             placebo_p97_5=np.percentile(null, 97.5), p_value=_p_value(null, t["real"][k]),
                             engine_check_max_abs=t["check"], no_placebo_date=t["no_date"],
                             window_note="" if window in WINDOWS else EXTRA_NOTE))
            draw_rows.append(pd.DataFrame(dict(design=design, measure=measure, group=k, window=window,
                                               draw=np.arange(n_draws), mean_bp=null)))

    for design, same in DESIGNS.items():
        # M2: one set of dates per draw serves all three windows and the path
        cand = candidates(E, None, same)
        cols = [f"m2_{w}_bbeta_bp" for w in WINDOWS]
        real = M[cols].dropna()
        ids = [a for a in real.index if len(cand[a][1]) > 0]
        g = np.array([cand[a][0] for a in ids], dtype=int)
        p_real = np.array([E.pos[M.at[a, "auction_date"]] for a in ids])
        ar_real = E.m2_ar(g, p_real)
        check = float(np.nanmax(np.abs(E.m2_numbers(ar_real) - real.loc[ids].to_numpy())))
        P2 = pd.read_csv(ms.OUT_DIR / "m2_paths.csv.gz", usecols=["auction_id", "k", "car_bbeta"])
        want = P2.pivot(index="auction_id", columns="k", values="car_bbeta").loc[ids, list(PATH_K)].to_numpy()
        check = max(check, float(np.nanmax(np.abs(E.m2_path(ar_real) - want))))
        groups = _groups(M, ids)
        rv = real.loc[ids].to_numpy()
        null = {k: np.empty((n_draws, 3)) for k in groups}
        paths = np.empty((n_draws, len(PATH_K)))
        extra = ms.M2_EXTRA_WINDOWS                                       # same dates, no extra randomness
        null_x = {w: {k: np.empty(n_draws) for k in groups} for w in extra}
        rx = {w: M.loc[ids, f"m2_{w}_bbeta_bp"].to_numpy() for w in extra}
        for w, (a, b) in extra.items():
            check = max(check, float(np.nanmax(np.abs(E.m2_window(ar_real, a, b) - rx[w]))))
        for d in range(n_draws):
            p = np.array([rng.choice(cand[a][1]) for a in ids])
            ar = E.m2_ar(g, p)
            v = E.m2_numbers(ar)
            for k, sel in groups.items():
                null[k][d] = v[sel].mean(axis=0)
            paths[d] = E.m2_path(ar).mean(axis=0)
            for w, (a, b) in extra.items():
                vx = E.m2_window(ar, a, b)
                for k, sel in groups.items():
                    null_x[w][k][d] = vx[sel].mean()
        for j, w in enumerate(WINDOWS):
            record(design, "M2 (B-β)", w, dict(real={k: float(rv[sel, j].mean()) for k, sel in groups.items()},
                                               null={k: v[:, j] for k, v in null.items()},
                                               n={k: int(sel.sum()) for k, sel in groups.items()},
                                               check=check, no_date=len(real) - len(ids)))
        for w in extra:
            record(design, "M2 (B-β)", w, dict(real={k: float(rx[w][sel].mean()) for k, sel in groups.items()},
                                               null=null_x[w], n={k: int(sel.sum()) for k, sel in groups.items()},
                                               check=check, no_date=len(real) - len(ids)))
        if design == "main":
            path_rows.append(pd.DataFrame(paths, columns=PATH_K).assign(measure="M2 (B-β)", draw=np.arange(n_draws),
                                                                        engine_check=check, n_events=len(ids)))

        # M3: each window on its own sample and candidate set
        for (w, (a, b)) in ms.PM_NUMBERS.items():
            cand = candidates(E, (a, b), same)
            real = M[f"m3_{w}_bp"].dropna()
            t = _test(E, M, rng, cand, real, lambda g, p, a=a, b=b: E.m3_window(g, p, a, b), n_draws)
            record(design, "M3", w, t)
        for (w, (a, b)) in ms.M3_EXTRA_WINDOWS.items():                 # own random stream
            cand_x = candidates(E, (a, b), same)
            real = M[f"m3_{w}_bp"].dropna()
            t = _test(E, M, rng_extra, cand_x, real, lambda g, p, a=a, b=b: E.m3_window(g, p, a, b), n_draws)
            record(design, "M3", w, t)
        if design == "main":
            cand = candidates(E, tuple(PATH_K), same)
            R3 = pd.read_csv(ms.M3_PATHS_FILE).pivot(index="auction_id", columns="k", values="residual_rel_t6_bp")
            full = R3.dropna().index
            ids = [a for a in full if len(cand[a][1]) > 0]
            g = np.array([cand[a][0] for a in ids], dtype=int)
            p_real = np.array([E.pos[M.at[a, "auction_date"]] for a in ids])
            chk = float(np.nanmax(np.abs(E.m3_path(g, p_real) - R3.loc[ids, list(PATH_K)].to_numpy())))
            paths = np.empty((n_draws, len(PATH_K)))
            for d in range(n_draws):
                p = np.array([rng.choice(cand[a][1]) for a in ids])
                paths[d] = E.m3_path(g, p).mean(axis=0)
            path_rows.append(pd.DataFrame(paths, columns=PATH_K).assign(measure="M3", draw=np.arange(n_draws),
                                                                        engine_check=chk, n_events=len(ids)))
    R = pd.DataFrame(rows)
    D = pd.concat(draw_rows, ignore_index=True)
    PTH = pd.concat(path_rows, ignore_index=True).melt(id_vars=[c for c in ["measure", "draw", "engine_check", "n_events"]],
                                                        var_name="k", value_name="mean_bp")
    if write:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        R.to_csv(OUT_DIR / "placebo_results.csv", index=False)
        D.to_csv(OUT_DIR / "placebo_draws.csv.gz", index=False, float_format="%.6g")
        PTH.to_csv(OUT_DIR / "placebo_paths.csv.gz", index=False, float_format="%.6g")
    return dict(results=R, draws=D, paths=PTH)


def load_results(design: str = "main") -> pd.DataFrame:
    R = pd.read_csv(OUT_DIR / "placebo_results.csv")
    return R[R["design"] == design].reset_index(drop=True)


if __name__ == "__main__" and "--build-yields" in sys.argv:
    Y = build_gilt_daily_yields()
    print(f"daily model yields: {len(Y):,} gilt-days for {Y['isin'].nunique()} gilts -> {GILT_YIELDS_FILE}")
elif __name__ == "__main__":
    out = run()
    pd.set_option("display.width", 220)
    R = out["results"]
    print(R.groupby(["design", "measure", "window"])[["engine_check_max_abs", "no_placebo_date"]].first())
    print(R[R.group_type != "regime"].round(3).to_string(index=False))
