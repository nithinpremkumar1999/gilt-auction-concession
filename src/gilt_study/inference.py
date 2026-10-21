"""Stage 5 inference helpers (build spec §8): OLS with standard errors clustered by auction week, and
a Newey-West check in calendar time.

* Clustered (main): V = c (X'X)^-1 [sum_g X_g' e_g e_g' X_g] (X'X)^-1 with the usual small-sample
  factor c = G/(G-1) * (N-1)/(N-K) (Stata CR1). Clusters = ISO week of the auction date, because
  event windows of auctions in the same week overlap. p-values from t with G-1 degrees of freedom.
* Newey-West (check): auctions are irregularly spaced, so the Bartlett kernel is applied in calendar
  time, w_ij = max(0, 1 - |d_i - d_j| / (H + 1)) with d in days and H = 30 days (the T-10..T+10
  window spans about 29 calendar days, so windows further apart than that do not overlap). Factor
  N/(N-K). With equally spaced dates d_i = i this is the textbook Newey-West estimator with H lags.
  p-values from the normal distribution.
* Fixed effects are included as dummy columns; only the other coefficients are reported.

numpy/scipy only; checked against statsmodels 0.15.0 (cluster, and HAC with equal spacing) in
tests/test_stage5.py.
"""
import numpy as np
import pandas as pd
from scipy import stats

HAC_BANDWIDTH_DAYS = 30


def auction_week(dates) -> np.ndarray:
    """ISO year-week label of each date (the clustering unit)."""
    d = pd.to_datetime(pd.Series(list(dates)))
    iso = d.dt.isocalendar()
    return (iso["year"].astype(int) * 100 + iso["week"].astype(int)).to_numpy()


def ols(y, X: pd.DataFrame, clusters=None, days=None, report=None, hac_bandwidth=HAC_BANDWIDTH_DAYS) -> dict:
    """OLS of y on X (X includes the constant / dummies you want). Returns a dict with a coefficient
    table (coef, se_cluster, t_cluster, p_cluster, se_nw, p_nw), N, K, R^2, adj. R^2, clusters."""
    y = np.asarray(y, float)
    names = list(X.columns)
    Xv = X.to_numpy(float)
    ok = np.isfinite(y) & np.isfinite(Xv).all(axis=1)
    y, Xv = y[ok], Xv[ok]
    keep = Xv.std(axis=0) > 0
    keep |= np.array([n == "const" for n in names])              # never drop the constant
    Xv = Xv[:, keep]
    names = [n for n, k in zip(names, keep) if k]
    n, k = Xv.shape
    XtX_inv = np.linalg.pinv(Xv.T @ Xv)
    b = XtX_inv @ Xv.T @ y
    e = y - Xv @ b
    r2 = 1 - (e @ e) / np.sum((y - y.mean()) ** 2)
    out = pd.DataFrame(index=names)
    out["coef"] = b
    s2 = e @ e / (n - k)
    out["se_ols"] = np.sqrt(np.diag(XtX_inv) * s2)
    res = dict(n=n, k=k, r2=r2, adj_r2=1 - (1 - r2) * (n - 1) / (n - k))
    if clusters is not None:
        g = np.asarray(clusters)[ok]
        groups = pd.Series(np.arange(n)).groupby(g).indices
        G = len(groups)
        meat = np.zeros((k, k))
        for idx in groups.values():
            s = Xv[idx].T @ e[idx]
            meat += np.outer(s, s)
        c = G / (G - 1) * (n - 1) / (n - k)
        V = c * XtX_inv @ meat @ XtX_inv
        out["se_cluster"] = np.sqrt(np.diag(V))
        out["t_cluster"] = out["coef"] / out["se_cluster"]
        out["p_cluster"] = 2 * stats.t.sf(np.abs(out["t_cluster"]), df=G - 1)
        res["clusters"] = G
    if days is not None:
        d = np.asarray(days, float)[ok]
        W = np.clip(1 - np.abs(d[:, None] - d[None, :]) / (hac_bandwidth + 1), 0, None)
        U = Xv * e[:, None]
        meat = U.T @ W @ U
        V = n / (n - k) * XtX_inv @ meat @ XtX_inv
        out["se_nw"] = np.sqrt(np.diag(V))
        out["p_nw"] = 2 * stats.norm.sf(np.abs(out["coef"] / out["se_nw"]))
    if report is not None:
        out = out.loc[[r for r in report if r in out.index]]
    res["table"] = out
    return res


def mean_test(y, clusters, days, label="mean") -> pd.Series:
    """Mean of y with clustered and Newey-West standard errors (an OLS on a constant)."""
    y = pd.Series(np.asarray(y, float))
    X = pd.DataFrame({"const": np.ones(len(y))})
    r = ols(y, X, clusters=clusters, days=days)
    t = r["table"].loc["const"]
    return pd.Series({"n": r["n"], label: t["coef"], "se_cluster": t["se_cluster"], "p_cluster": t["p_cluster"],
                      "se_nw": t["se_nw"], "p_nw": t["p_nw"], "clusters": r.get("clusters")})


def days_since(dates, origin="1998-01-01") -> np.ndarray:
    return (pd.to_datetime(pd.Series(list(dates))) - pd.Timestamp(origin)).dt.days.to_numpy()
