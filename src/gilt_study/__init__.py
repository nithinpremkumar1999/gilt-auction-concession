"""gilt_study: production code for the Gilt Auction Concession Study.

Modules
  pricing    gilt cash flows, price and yield (single source of truth: cash_flows())
  curve      BoE nominal spot curve loading and pricing gilts off it
  data_io    readers for DMO files
  inventory  SHA-256 manifest of data/raw_data and its check (Stage 0)
  plotting   one chart, two outputs: seaborn PNG + Plotly HTML (decision #8)
  paths      every file location;  config  study parameters from logged decisions
"""
__version__ = "0.1.0"
