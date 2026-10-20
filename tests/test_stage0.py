"""Stage 0 checks: package layout, raw-data integrity and the business-day calendar.

Run:  pytest -m "not slow"     (seconds)
"""
import datetime as dt

import pytest

from gilt_study import config, inventory, paths
from gilt_study.pricing import is_business_day


def test_package_imports():
    """All production modules import from the installed package (no flat `from pricing import`)."""
    import gilt_study.curve  # noqa: F401
    import gilt_study.data_io  # noqa: F401
    import gilt_study.exercises.exercise_a  # noqa: F401
    import gilt_study.exercises.exercise_b  # noqa: F401
    import gilt_study.plotting  # noqa: F401


def test_raw_data_matches_manifest():
    """Every raw file is present and byte-identical to data/raw_manifest.csv (SHA-256)."""
    assert paths.RAW_MANIFEST.exists(), "run: python -m gilt_study.inventory --write"
    assert inventory.verify_manifest() == []


def test_named_raw_paths_exist():
    """Every raw file referenced in paths.py exists."""
    named = [paths.D1A, paths.D1C, paths.D2_1E, paths.D2_1A, paths.SYNDICATIONS, paths.TENDERS,
             paths.OTHER_OPERATIONS, paths.QT_SALES, paths.QE_PURCHASES, paths.SONIA,
             paths.BANK_RATE, paths.TURNOVER, paths.CURVE_CURRENT_MONTH,
             paths.curve_workbook("2016 to 2024"), paths.ref_prices_file(2016)]
    missing = [str(p) for p in named if not p.exists()]
    assert not missing, missing


def test_raw_files_cover_study_window():
    """Reference prices exist for every year from the study start to 2017; curve workbooks too."""
    for year in range(config.STUDY_START.year, 2018):
        assert paths.ref_prices_file(year).exists(), year
    for label in ["1995 to 1999", "2000 to 2004", "2005 to 2015", "2016 to 2024", "2025 to present"]:
        assert paths.curve_workbook(label).exists(), label


@pytest.mark.parametrize("day", [dt.date(1999, 12, 31), dt.date(2002, 6, 3), dt.date(2002, 6, 4),
                                 dt.date(2011, 4, 29), dt.date(2012, 6, 4), dt.date(2012, 6, 5),
                                 dt.date(2020, 5, 8), dt.date(2022, 6, 2), dt.date(2022, 6, 3),
                                 dt.date(2022, 9, 19), dt.date(2023, 5, 8)])
def test_one_off_closures_are_holidays(day):
    """One-off UK closures (jubilees, royal wedding, State Funeral, Coronation) are not business days."""
    assert not is_business_day(day)


@pytest.mark.parametrize("day", [dt.date(2012, 5, 28), dt.date(2020, 5, 4)])
def test_moved_bank_holidays_are_business_days(day):
    """Bank holidays moved for one-off events are ordinary business days on their usual date."""
    assert is_business_day(day)
