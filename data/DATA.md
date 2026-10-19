# Data changes log

Every change to `data/interim_data/` and `data/processed_data/` is recorded here: what changed, why, and the code that produced it. `data/raw_data/` is never written to. Its contents are pinned by `data/raw_manifest.csv` (see SOURCES.md).

## Folders

| Folder | What goes here | Written by |
|---|---|---|
| `raw_data/` | Downloads, exactly as published | Nobody (read-only). Check with `python -m gilt_study.inventory --check` |
| `raw_manifest.csv` | SHA-256 and size of every raw file | `python -m gilt_study.inventory --write`, only after a logged re-download |
| `interim_data/` | Intermediate outputs, regenerable from raw data by code | `src/gilt_study` modules |
| `processed_data/` | Analysis-ready panels and validation outputs | `src/gilt_study` modules and notebooks (named below) |

Rule: a file in `interim_data/` or `processed_data/` must be reproducible by running code. Hand-edited files are not allowed, because they cannot be re-derived when the raw data is refreshed.

## Change log

| Date | Path | Change | Why | Produced by |
|---|---|---|---|---|
| 2026-10-19 | `raw_manifest.csv` | Created: 47 files, 210.7 MB | Stage 0 gate: checksums. Hashes computed on Nithin's machine and matched in the build workspace | `python -m gilt_study.inventory --write` |
| 2026-10-19 | `interim_data/dmo_ref_price/2016.xls` | **Deleted** (8,708,096 bytes, SHA-256 `67b459d3598cfaa830e3c567cbc956e6ce4c569fbcf0a06cbe591414af441244`) | Hand-edited copy of `raw_data/dmo_ref_prices/2016-gilt-reference-prices.xls` (title rows removed so the header sits on row 0). Not reproducible by code; `gilt_study.data_io.load_reference_prices()` reads the raw file directly. Deleted with Nithin's permission | (manual) |
| 2026-10-19 | `interim_data/glc_nominal/2016_to_2024.xlsx` | **Deleted** (9,061,825 bytes, SHA-256 `c04bb7982527d474e257d87baa91ad84fd4949b199bae36877b0f2f99a4dac60`) | Hand-edited copy of `raw_data/glc_nominal/GLC Nominal daily data_2016 to 2024.xlsx` with sheets renamed (`fwds_short_end`, `fwd_curve`, `spot_short_end`, `spot_curve`). `gilt_study.curve.load_spot_workbook()` reads the raw workbook directly. Deleted with Nithin's permission | (manual) |
| 2026-10-19 | `processed_data/inventory/raw_coverage.csv` | Created: first/last observed date and row count for each of the 47 raw files | Stage 0: observed (not stated) coverage, the source for SOURCES.md tables | `notebooks/00_data_inventory.ipynb` |
| 2026-10-19 | `processed_data/exercises/exercise_a_errors.csv` | Created: 10,508 gilt-days, pricer vs DMO 2016 reference prices | Regression check after moving the code into `src/gilt_study` (0 failures, max dirty error 2.95e-5; identical to Nithin's run to 3e-14) | `python -m gilt_study.exercises.exercise_a` (also run by `pytest -m slow`) |
| 2026-10-19 | `processed_data/exercises/exercise_b_residuals.csv` | Created: 39 gilt residuals vs the BoE curve, 15 Mar 2016 | Regression check: +2.70 / −1.91 / +1.38 bp targets and 2.64 bp mean reproduced | `python -m gilt_study.exercises.exercise_b` (also run by `pytest -m slow`) |
