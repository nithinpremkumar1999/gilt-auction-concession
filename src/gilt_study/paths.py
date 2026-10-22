"""Every file location in the project, in one place.

The project root is found from this file's location (src/gilt_study/paths.py -> two levels up),
which works for an editable install (`pip install -e .`). Set the environment variable
GILT_STUDY_ROOT to override it.

Folder rules (decision #8):
  data/raw_data        untouched downloads; never written by code
  data/interim_data    intermediate outputs, regenerable from raw_data
  data/processed_data  analysis-ready panels and validation outputs
  reports/figures      static charts (seaborn)
  reports/interactive  interactive charts (Plotly HTML)
Every change to interim/processed data is documented in data/DATA.md.
"""
import os
from pathlib import Path

ROOT = Path(os.environ.get("GILT_STUDY_ROOT", Path(__file__).resolve().parents[2]))

DATA = ROOT / "data"
RAW = DATA / "raw_data"
INTERIM = DATA / "interim_data"
PROCESSED = DATA / "processed_data"
RAW_MANIFEST = DATA / "raw_manifest.csv"          # SHA-256 of every raw file (Stage 0)

REPORTS = ROOT / "reports"
FIGURES = REPORTS / "figures"                     # seaborn PNGs
INTERACTIVE = REPORTS / "interactive"             # Plotly HTML
TABLES = REPORTS / "tables"                       # report tables (CSV + HTML), e.g. the p-value appendix

# ------------------------------------------------------------------ raw files (see SOURCES.md)
CURVE_DIR = RAW / "glc_nominal"                   # #1 BoE nominal curve archive (extracted)
CURVE_LATEST_DIR = RAW / "latest_yield_curve"     # #1 current-month BoE nominal curve
OIS_DIR = RAW / "ois"                             # #7 BoE OIS curve archive (extracted)
REF_PRICES_DIR = RAW / "dmo_ref_prices"           # #2 DMO reference prices, one file per year
GILT_STATIC_DIR = RAW / "gilt_static"
D1A = GILT_STATIC_DIR / "gilts_issue.xls"         # #4 gilts in issue
D1C = GILT_STATIC_DIR / "redeemed.xls"            # #4 redeemed gilts
D2_1E = GILT_STATIC_DIR / "issuance_history.xls"  # #4 issuance history
D2_1A = RAW / "auction_results.xls"               # #5 outright auction results
SYNDICATIONS = RAW / "syndication_results.xlsx"   # #8 D10A
TENDERS = RAW / "tender_results.xls"              # #8 D2.1PROF9
OTHER_OPERATIONS = RAW / "other_gilt_operations.xls"  # #8 D2.1PROF7 (switches, conversions, ...)
QT_SALES = RAW / "boe_qt_sales.xlsx"              # #9
QE_PURCHASES = RAW / "boe_qe_purchases.XLSX"      # #10 (upper-case extension as downloaded)
CRISIS_OPS_DIR = RAW / "2022_crisis_operations"   # #11
SONIA = RAW / "IUDSOIA.xlsx"                      # #7a
BANK_RATE = RAW / "IUDBEDR.xlsx"                  # #7b
TURNOVER = RAW / "turnover_maturity_band.xlsx"    # #12


def ref_prices_file(year: int) -> Path:
    """DMO reference-price workbook for one calendar year (1998-2017)."""
    return REF_PRICES_DIR / f"{year}-gilt-reference-prices.xls"


def curve_workbook(label: str) -> Path:
    """BoE nominal curve workbook by its year label, e.g. '2016 to 2024' or '2025 to present'."""
    return CURVE_DIR / f"GLC Nominal daily data_{label}.xlsx"


CURVE_CURRENT_MONTH = CURVE_LATEST_DIR / "GLC Nominal daily data current month.xlsx"
