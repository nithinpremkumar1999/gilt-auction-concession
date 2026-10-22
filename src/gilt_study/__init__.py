"""gilt_study: production code for the Gilt Auction Concession Study.

Modules
  pricing    gilt cash flows, price and yield (single source of truth: cash_flows())
  curve      BoE nominal curve panel (daily, 1998-2026) and the curve pricer (Stage 2)
  gilt_terms first issue and first coupon dates per gilt, WI tranche dates (Stage 1, P2-P4)
  data_io    readers for DMO files; test-scope filters (single-dated, linker spellings)
  auctions   the auction panel, one row per conventional auction (Stage 3), and its checks
  measures   M1, M1b, M2 (control B-beta), M3 (bond residual path) and the PM's three numbers (Stages 4-5)
  ois        BoE OIS curve panel (2016-2026) and M2 with control C, gilt - OIS (Stage 5)
  inference  OLS with week-clustered and calendar-time Newey-West standard errors (Stage 5)
  analysis   the Stage 5 dataset, headline means, regressions (spec §8) and robustness tables
  placebo    the placebo test: M2/M3 on random non-auction dates of the same gilt (Stage 5)
  report_charts  the report's four charts, seaborn PNG + Plotly HTML (Stage 6)
  inventory  SHA-256 manifest of data/raw_data and its check (Stage 0)
  plotting   one chart, two outputs: seaborn PNG + Plotly HTML (decision #9)
  paths      every file location;  config  study parameters from logged decisions
"""
__version__ = "0.1.0"
