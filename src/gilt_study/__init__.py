"""gilt_study: production code for the Gilt Auction Concession Study.

Modules
  pricing    gilt cash flows, price and yield (single source of truth: cash_flows())
  curve      BoE nominal curve panel (daily, 1998-2026) and the curve pricer (Stage 2)
  gilt_terms first issue and first coupon dates per gilt, WI tranche dates (Stage 1, P2-P4)
  data_io    readers for DMO files; test-scope filters (single-dated, linker spellings)
  auctions   the auction panel, one row per conventional auction (Stage 3), and its checks
  inventory  SHA-256 manifest of data/raw_data and its check (Stage 0)
  plotting   one chart, two outputs: seaborn PNG + Plotly HTML (decision #9)
  paths      every file location;  config  study parameters from logged decisions
"""
__version__ = "0.1.0"
