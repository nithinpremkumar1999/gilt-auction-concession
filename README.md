# Gilt Auction Concession Study

Should a pension fund's passive gilt team buy auctioned supply **before, at or after** the auction? This repo measures the gilt auction concession: how far the auctioned gilt cheapens against the Bank of England curve into a conventional auction, and how much reverses afterwards. It covers conventional auctions from **1 November 1998** to September 2026 (decision #7), across the QE, LDI-stress and QT regimes.

The method, conventions and every decision are in the **build spec** (`claude/build-spec.md` in the Claude project). Nothing methodological is decided in code without a logged decision. Decision numbers below refer to the spec's §10 log.

## Layout

```
├── src/gilt_study/          production code (docstrings, comments)
│   ├── pricing.py           cash_flows() (single source of truth), gilt_price(), yield_from_dirty(), UK calendar
│   ├── curve.py             BoE curve panel (1998-2026), Curve (spline, flat-forward extrapolation), curve pricer
│   ├── gilt_terms.py        first issue and first coupon dates per gilt (P3, P4), WI tranche dates (P2)
│   ├── data_io.py           DMO readers; test-scope filters (single-dated, linker spellings)
│   ├── inventory.py         SHA-256 manifest of data/raw_data and its check
│   ├── plotting.py          one chart, two outputs: seaborn PNG + Plotly HTML (decision #9)
│   ├── paths.py             every file location
│   ├── config.py            study parameters from logged decisions (sample start 1 Nov 1998, #7)
│   └── exercises/           validation scripts: exercise_a (Stage 1), exercise_b + curve_checks (Stage 2)
├── notebooks/               00 data inventory · 01 pricer test · 02 curve panel (the why, before code)
├── reports/
│   ├── figures/             static charts (seaborn), PNG
│   └── interactive/         interactive charts (Plotly), HTML
├── data/
│   ├── raw_data/            downloads, never edited (see SOURCES.md)
│   ├── raw_manifest.csv     SHA-256 of every raw file
│   ├── interim_data/        regenerable intermediate data (gilt_terms.csv)
│   ├── processed_data/      analysis-ready data and validation outputs
│   └── DATA.md              log of every change to interim/processed data
├── tests/                   pytest: Stage 0 checks, gilt terms, Stage 1 and Stage 2 regression tests
├── SOURCES.md               every raw file: URL, download date, observed coverage, SHA-256, known issues
├── requirements.txt         pinned versions (match the project .venv)
└── pyproject.toml           makes src/gilt_study installable
```

## Setup (WSL, Python 3.11)

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt        # pinned packages + `pip install -e .` for src/gilt_study
```

## Run

```bash
python -m gilt_study.inventory --check             # raw files unchanged since the manifest was written?
pytest -m "not slow"                               # fast checks (seconds; builds gilt_terms/curve panel if missing)
pytest                                             # + Stage 1 (both modes) and the curve acceptance test (~4 min)
python -m gilt_study.exercises.exercise_a          # Stage 1 pricer test as signed off (P1-P4), 1998-2017 (~2 min)
python -m gilt_study.exercises.exercise_a --as-run # the Stage 1 record as first run
python -m gilt_study.exercises.exercise_b          # Stage 2 curve acceptance test, 15 Mar 2016
python -m gilt_study.exercises.curve_checks        # Stage 2 extrapolation checks (~2 min)
```

Notebooks import the installed package (`from gilt_study import ...`), so they work from any folder.

---

## Build log

### Stage 0: repo layout, SOURCES.md, raw files in place (19 Oct 2026)

**Delivered**
- `src/gilt_study` package built from the reference code. The logic of `pricing.py`, `data_io.py` and `curve.py` is unchanged, checked by AST comparison against the 19 Oct reference zip with docstrings ignored. Changes:
  - relative imports;
  - docstrings;
  - `curve.load_spot_workbook()` reads the extracted BoE workbooks (the old `load_spot_curves()` read the ZIP, which is not in `raw_data`). Both share one splice function, identical to the old code.
- File paths are centralised in `paths.py`. Exercise outputs go to `data/processed_data/exercises/` and `reports/figures/` instead of the working directory.
- `inventory.py`: SHA-256 manifest of all 47 raw files (210.7 MB), with a `--check` command.
- SOURCES.md rewritten from the original. It adds a checksum, observed coverage and known issues for every file, and corrects file extensions, the OIS source and the coverage end dates.
- `data/DATA.md` change log. Two hand-edited interim files were deleted, with permission.
- `notebooks/00_data_inventory.ipynb`: checksums, observed coverage, curve completeness, auction counts, the D2.1A → D2.1E ISIN join, and the coverage chart.
- `plotting.py`: shared look for seaborn and Plotly. Colour-blind check run on the palette.

**Tests run**
- `pytest`: 19 passed. Covers the manifest, named paths, study-window files, 13 calendar cases, and both exercises.
- Exercise A: 0 of 10,508 gilt-days outside 1e-4 (max dirty error 2.95e-5). The output matches Nithin's 19 Oct run to 3e-14.
- Exercise B: +2.70 / −1.91 / +1.38 bp, mean |residual| 2.64 bp across 39 gilts. It now reads the raw workbook rather than the hand-edited interim copy.
- Checksums: 47 of 47 identical between Nithin's machine and the build workspace.

**Could not resolve (carried forward)**
- `notebooks/exercise.ipynb` (Nithin's Module 0–2 notebook), cells 9–10, read the two deleted interim files. Read the raw files instead: `load_spot_workbook(paths.curve_workbook("2016 to 2024"))` and `load_reference_prices(paths.ref_prices_file(2016))`.
- `.gitignore`: Nithin is adding `.venv/`. Also worth adding: `__pycache__/`, `*.egg-info/`, `.pytest_cache/`. The `.venv` was created at the old WSL path, and virtual environments don't survive being moved, so recreate it if activation fails.
- The old `src/__pycache__/` and the root `exercise_a_errors.csv` (now regenerated under `data/processed_data/exercises/`) can be deleted.
- The curve pricer rule "discount from the first issue date" (chat decision; now spec log #10) was documented in `curve.model_dirty()` for Stage 2. Implemented in Stage 2.
- Open spec items affecting later stages: Stage 1 test window and the "conventional" definition; first-issue-date rule for pre-1998 gilts; amount offered / uncovered auctions; OIS control-C start (2016 vs 2021).

### Stage 1: pricer acceptance test, spec §4 (19 Oct 2026). Signed off with P1–P4

#### 1a. As first run (the record behind the sign-off)

**Delivered**
- `exercises/exercise_a.py` is extended from 2016 to every reference-price file from 1998 to 2017. Years run in parallel.
  - `pricing.py` is unchanged: byte-identical to the Stage 0 delivery.
  - First issue dates come from D1A, and for matured gilts from the earliest D2.1E issue date per ISIN (now `first_issue_dates_as_run()`). The three inferred overrides are deleted; D2.1E gives the same three dates.
  - Every excluded row is recorded with its reason.
  - Every failing gilt-day is given a cause by `diagnose()`. It re-prices the day under one diagnostic assumption at a time, and the cause counts only if the day then passes. No convention was changed.
- Outputs, now in `data/processed_data/stage1/as_run/`: `by_year.csv`, `gilt_days.csv.gz`, `failures.csv`, `exclusions.csv`, `accrued_only.csv.gz`.
- `notebooks/01_pricer_acceptance_test.ipynb`: results, evidence for each cause, proposals with what-if pass rates. Chart: `stage1_failures_by_year` (PNG and HTML).

**Result as run: FAIL.** 138,685 of 167,608 conventional gilt-days are within 1e-4 (82.74%). The spec rule (dirty only) and the strict rule (dirty, accrued and clean) give identical counts. 2016 is 100% and 2017 is 99.85%. All 28,923 failures have a confirmed cause:

| Cause | Gilt-days |
|---|---:|
| Undated gilts (perpetuals; the file shows their 2015 call dates) | 25,012 |
| New issues with a long first coupon (pricer defaults to short; first coupon date not supplied) | 1,932 |
| When-issued lines for reopenings (DMO prices them for settlement on the tranche's issue date) | 1,489 |
| Double-dated gilts (DMO yield to the final date when below par) | 255 |
| WI lines during a long first coupon (both causes) | 202 |
| WI line labelled with the wrong redemption date or gilt (DMO data error) | 14 |
| WI line whose yield doesn't match its own clean price (DMO data error) | 6 |
| 8% Treasury Stock 2009: DMO accrued runs to the trade date (DMO data error) | 6 |
| 0¼% "Index -Linked" 2052 WI: linker missed by the filter because of its spelling | 6 |
| WI line with DMO accrued reported as 0 (DMO data error) | 1 |

**Findings**
- **No DMO yields exist for any conventional gilt before 25 Nov 2002.** The test can only run from 25 Nov 2002 to 21 Jul 2017, and 1998–2001 have no testable rows.
- Accrued-only diagnostic for 1998–2002 (not part of the pass rate):
  - It confirms actual/365 accrued before 1 Nov 1998 (9,444 of 9,512 single-dated days mismatch).
  - It shows that **"earliest D2.1E date" is wrong for 16 gilts launched before 1998.** None was auctioned in the study window, and none affects the yield test.
- Long first coupons: all 15 long-coupon new issues launched 1–45 days before the next quasi-coupon date. All 38 short-coupon issues launched 61–183 days before it.

**Tests run:** `pytest` (22 passed).
- New: D2.1E reproduces the deleted overrides; D1A and D2.1E first issue dates agree for all 71 gilts in issue.
- New (slow): the full 1998–2017 run leaves no failure unexplained.
- Still passing: 2016 gives 0 of 10,508 failures, and Exercise B hits its targets.

**Proposals, not applied (pass rates are what-ifs):**
- **P1:** test scope = single-dated gilts, and catch linker spelling variants. Gives 97.30%.
- **P2:** exclude WI lines, or price them for settlement on the tranche issue date. Gives 98.54%.
- **P3:** supply long first coupon dates from DMO data, or adopt a ≤ 45-day rule in `cash_flows()`. The second is a convention change. Gives **99.9955%**; only the 6 days of the 8% 2009 data error remain.
- **P4:** first issue date = the first D2.1E launch row, else none.
- **Window:** record the test window as 25 Nov 2002 to 21 Jul 2017.

**Could not resolve (needed decisions):** P1–P4 and the test window. Decided by Nithin on 19 Oct 2026 (spec decision #6), see 1b.

#### 1b. Final test with P1–P4 (19 Oct 2026)

**Decisions applied** (spec §4, decision #6):
- **P1:** scope is single-dated gilts. Undated, double-dated and floating-rate gilts are excluded, not failures. The "Index -Linked" and "I-L" spellings are caught.
- **P2:** WI lines are priced for settlement on the issue date of their tranche: the next priced D2.1E row of the underlying gilt within 45 days.
- **P3:** first coupon dates come from DMO data: a DMO notice (19 gilts), else the DMO's own accrued interest (61 gilts, decisive matches only). Otherwise the ≤ 45-day rule is used and flagged (36 gilts, all launched after Jul 2017, all short at 71–180 days). 46–60 days would be flagged for a manual check; no gilt needs one.
- **P4:** the first issue date comes from D1A, else the first D2.1E launch row, else none.
- **Test window:** 25 Nov 2002 – 21 Jul 2017 (`config.PRICER_TEST_WINDOW`).

`pricing.py` is still unchanged; first coupon dates enter as data through its existing `first_coupon` argument.

**Delivered**
- `gilt_terms.py` writes `data/interim_data/gilt_terms.csv` (132 gilts).
- `exercise_a.py` has two modes, `final` (default) and `--as-run`. Final outputs are in `data/processed_data/stage1/final/`.
- Notebook 01 gains §8 (the decisions) and §9 (the final test, with the first-coupon evidence chart `stage1_first_coupon_rule`).
- `config.STUDY_START` is now 1 Nov 1998 (decision #7). The window holds **912** conventional auctions, against 908 from 2000; the first is on 26 May 1999.

**Result: PASS. 135,067 of 135,094 single-dated gilt-days are within 1e-4 dirty (99.9800%).** The strict rule gives the same count. Every year is ≥ 99.90%; 2016 is still 0 of 10,508. All 27 exceptions are DMO data errors and were already listed in the as-run diagnosis:

| Exception (DMO data error) | Gilt-days |
|---|---:|
| WI line labelled with the wrong redemption date (3¼% 2011 WI; "4¾% 2010 WI", which is 4¾% 2020) | 14 |
| 8% Treasury Stock 2009: accrued to the trade date | 6 |
| WI line whose yield doesn't match its own clean price | 6 |
| WI line with accrued reported as 0 | 1 |

**Note on the logged pass rate.** Decision #6 records 99.9955%. That was the §7 what-if, which *excluded* WI lines. With P2 as decided (WI lines priced to their tranche), the 21 WI data-error days stay in the test as listed exceptions, so the pass rate is 99.9800%. Both clear 99.5%.

**Tests run:** `pytest`, 43 passed. New tests:
- `test_gilt_terms.py`: rule thresholds at 45/46/60/61 days; P4 sources; every DMO notice matched; no manual checks; the rule used only after 2017; 45-day tranche window.
- Final mode: ≥ 99.5%, 135,067 pass, every exception a DMO data error.
- As-run record: still 138,685 of 167,608 pass, nothing unexplained.

### Stage 2: curve panel and curve pricer, spec §5 (19 Oct 2026). Gate: curve acceptance test

**Delivered**
- `curve.py` rewritten (`pricing.py` untouched):
  - `build_panel()` / `load_panel()`: daily BoE spot curves, 2 Jan 1998 – 15 Oct 2026. Short end ≤ 5y spliced with the long sheet; 7,274 dates; holiday rows dropped. Each row also stores the forward at the last maturity. Written to `data/processed_data/curves/boe_nominal_spot_daily.csv.gz`; the values are identical to the raw workbooks.
  - `Curve`: a natural cubic spline in z, flat z below the first maturity and **flat forward** beyond the last (decision #5). A flat-z option is kept for diagnostics only.
  - `curve_on()`: falls back to the previous curve date for a missing date, and flags it.
  - `model_dirty()` / `model_yield()`: one `cash_flows()` throughout. A gilt that settles before its first issue date is discounted from the first issue date (decision #10).
  - `beyond_curve()`: the extrapolation flag.
  - `curve_function()` (Module 2, flat z at both ends) is kept unchanged for `notebooks/exercise.ipynb`.
- `exercises/exercise_b.py` is now the acceptance test. It uses the panel and `gilt_terms`, and draws a seaborn + Plotly chart pair.
- `exercises/curve_checks.py`: two checks of the extrapolation.
  1. Monthly DMO residuals, 2002–2017.
  2. The 2016–2026 curve cut at 25y, compared with the full curve.
- `notebooks/02_curve_panel.ipynb`. Charts: `curve_snapshots`, `exercise_b_residuals`, `curve_residuals_by_maturity`, `curve_truncation_test`.

**Acceptance test, 15 Mar 2016:**
- 39 gilts.
- 1½% 2026 **+2.70**, 4¼% 2055 **−1.91**, 4½% 2034 **+1.38** bp: all three targets reproduced exactly.
- Mean |residual| is **2.84 bp** with flat forward, against a 2.6 bp target. Flat z reproduces Module 2's 2.64 bp, and the mean within the 40y curve is 2.70 bp.
- The difference is the 3 gilts beyond 40y (2060, 2065, 2068), which move from about −2 bp to +0.7/+5.6/+7.3 bp. The BoE forward at 40y was 1.50% against a 2.17% spot rate, so the flat forward pulls the ultra-long rates down.

**Extrapolation checks.** Before 2016 the curve ends at 25y.
- **2002–2015, DMO yields:** gilts beyond 25y look rich (model yield above the DMO yield). The gap is about 0.6 bp at 25–30y, 2 bp at 30–35y, 6 bp at 35–40y and 10–11 bp beyond 40y. Mean |error| is 4.7 bp with flat forward against 6.8 bp with flat z.
- **2016–2026 curve cut at 25y:** extrapolated yields are too high by about 1 / 5 / 12 bp at 25–30 / 30–35 / 35–40y with flat forward. Flat z is worse in every bucket.

So flat forward is the better of the two, but long pre-2016 auctions carry a bias of a few bp. That bias is why the flag and the spec's robustness checks (drop flagged auctions; M1b) matter.

**Tests run:** `pytest`, 43 passed. `test_curve.py` (12 tests) covers:
- flat z below the first maturity; the spline passes through the BoE points;
- flat forward is continuous at T and holds f(T); the flat-z option;
- WI discounting from the first issue date; model yield reprices the curve price; the beyond-curve flag;
- the panel covers every UK business day, with no rows on holidays; t_max is 25y/40y and f(T) is always present;
- the Good Friday 2016 fallback is flagged; panel rows equal the raw workbook;
- the acceptance test (slow).

**Could not resolve (needs decisions at the gate)**
1. The acceptance test's mean target (2.6 bp) was set under flat z. With flat forward the mean is 2.84 bp. Options: accept on the three targets, the count and the flat-z mean; restate the target "within the curve" (2.70 bp); or revisit decision #5.
2. The extrapolation flag is binary (spec). Should the auction panel also record *years beyond the curve*, so robustness checks can use a threshold? This changes nothing by default.
3. Spec decision log: #6 quotes 99.9955%, but the as-applied figure is 99.9800% (see Stage 1b). Decisions #8–#10 (repo layout, chart pair, WI discounting in the curve pricer) were added to the log from the chat.
4. Still open from earlier stages:
   - OIS control C start: the data has the long end from Jan 2016; the spec says Dec 2021.
   - Amount offered and uncovered auctions: D2.1A has no offered amount (Stage 3).
   - The PM's benchmark (spec §1).
