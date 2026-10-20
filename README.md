# Gilt Auction Concession Study

Should a pension fund's passive gilt team buy auctioned supply **before, at or after** the auction? This repo measures the gilt auction concession: how far the auctioned gilt cheapens against the Bank of England curve into a conventional auction, and how much reverses afterwards. It covers conventional auctions from **1 November 1998** to September 2026 (decision #7), across the QE, LDI-stress and QT regimes.

The method, conventions and every decision are in the **build spec** (`claude/build-spec.md` in the Claude project). Nothing methodological is decided in code without a logged decision. Decision numbers below refer to the spec's §10 log.

## Layout

```
├── src/gilt_study/          production code (docstrings, comments)
│   ├── pricing.py           cash_flows() (single source of truth), gilt_price(), yield_from_dirty(), UK calendar
│   ├── curve.py             BoE curve panel (1998-2026), Curve (spline, flat-forward extrapolation), curve pricer
│   ├── gilt_terms.py        first issue and first coupon dates per gilt (P3, P4), WI tranche dates (P2)
│   ├── auctions.py          the auction panel (Stage 3): D2.1A + D2.1E + terms + curve, panel checks
│   ├── measures.py          M1, M1b, M2 (control B-β; B) and the PM's three numbers (Stage 4)
│   ├── data_io.py           DMO readers; test-scope filters (single-dated, linker spellings)
│   ├── inventory.py         SHA-256 manifest of data/raw_data and its check
│   ├── plotting.py          one chart, two outputs: seaborn PNG + Plotly HTML (decision #9)
│   ├── paths.py             every file location
│   ├── config.py            study parameters from logged decisions (sample start 1 Nov 1998, #7)
│   └── exercises/           validation scripts: exercise_a (Stage 1), exercise_b + curve_checks (Stage 2),
│                            handcheck_stage4 (Stage 4 hand-check workbook)
├── notebooks/               00 inventory · 01 pricer · 02 curve · 03 auction panel · 04 measures (the why, before code)
├── reports/
│   ├── figures/             static charts (seaborn), PNG
│   └── interactive/         interactive charts (Plotly), HTML
├── data/
│   ├── raw_data/            downloads, never edited (see SOURCES.md)
│   ├── raw_manifest.csv     SHA-256 of every raw file
│   ├── interim_data/        regenerable intermediate data (gilt_terms.csv)
│   ├── processed_data/      analysis-ready data and validation outputs
│   └── DATA.md              log of every change to interim/processed data
├── tests/                   pytest: Stage 0 checks, gilt terms, Stages 1-4
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
python -m gilt_study.auctions                      # Stage 3 auction panel + panel checks (~20 s)
python -m gilt_study.measures                      # Stage 4 M1, M1b, M2 (~4 min first time; ~1 min from the cache)
python -m gilt_study.exercises.handcheck_stage4    # Stage 4 hand-check workbook (recalculate in Excel/LibreOffice)
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

### Stage 2: curve panel and curve pricer, spec §5 (19 Oct 2026). Signed off 20 Oct 2026

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

**Sign-off (20 Oct 2026; decisions #11–12).** The mean target was restated as **2.70 bp for the 36 gilts within the 40y curve**; the three named targets stand and flat forward stays. **Result: pass** (`exercise_b.TARGET_MEAN_ABS_BP_WITHIN_CURVE`). The auction panel records **years beyond the curve** (`curve.years_beyond_curve()`); robustness drops auctions more than **5 years** beyond (`config.MAX_YEARS_BEYOND_CURVE`).

**Could not resolve at the gate** (items 1–3 resolved on 20 Oct: decisions #11–12 and the corrected #6; item 4 carried to Stage 3)
1. The acceptance test's mean target (2.6 bp) was set under flat z. With flat forward the mean is 2.84 bp. Options: accept on the three targets, the count and the flat-z mean; restate the target "within the curve" (2.70 bp); or revisit decision #5.
2. The extrapolation flag is binary (spec). Should the auction panel also record *years beyond the curve*, so robustness checks can use a threshold? This changes nothing by default.
3. Spec decision log: #6 quotes 99.9955%, but the as-applied figure is 99.9800% (see Stage 1b). Decisions #8–#10 (repo layout, chart pair, WI discounting in the curve pricer) were added to the log from the chat.
4. Still open from earlier stages:
   - OIS control C start: the data has the long end from Jan 2016; the spec says Dec 2021.
   - Amount offered and uncovered auctions: D2.1A has no offered amount (Stage 3).
   - The PM's benchmark (spec §1).

### Stage 3: auction panel, spec §6 (20 Oct 2026). Signed off 20 Oct 2026

**Delivered**
- `auctions.py` builds `build_panel()`, which writes `data/processed_data/auctions/auction_panel.csv`: **912 conventional auctions**, 26 May 1999 – 29 Sep 2026, 69 columns. Its inputs:
  - **D2.1A**: amounts, cover, AAP, AAY, tail. Linkers are excluded case-insensitively.
  - **D2.1E**: ISIN and **settlement date = the DMO issue date** (spec §4). The match is the first priced row within 5 days with the same coupon, maturity year and total nominal.
  - **gilt_terms**: maturity, first issue, first coupon and its source.
  - **The Stage 2 curve**: T-1 curve, years beyond the curve, robustness drop flag.
- It also computes the remaining spec §6 fields:
  - new issue / reopening;
  - nominal offered = allotted;
  - PAOF take-up;
  - yield at the lowest accepted price (AAY + tail);
  - years to maturity and bucket (short < 7, medium 7–15, long > 15);
  - DV01 per £100 and £ per bp, for the allotment and for the total incl. PAOF;
  - regime;
  - supply controls (syndications, tenders, QT sale days, all ±5 business days);
  - two rate-volatility candidates.
- `panel_checks()` runs the spec §6 checks plus an AAP repricing check. The DMO reference counts and result-notice figures are in SOURCES.md #5b.
- `notebooks/03_auction_panel.ipynb`. Charts: `auction_counts_by_fy`, `auction_years_beyond_curve`, `auction_dv01_over_time`.
- Stage 2 sign-off applied: restated acceptance target (decision #11) and `years_beyond_curve` (#12). Notebook 02 §6 records the decisions.

**Panel checks: all pass**

| Check (spec §6) | Result |
|---|---|
| Counts by financial year reconcile to the DMO | **26 of 26** financial years (1998-99 to 2023-24) match the DMO's total auction count; **5 of 5** spot-check years match by bucket (2009-10, 2016-17, 2017-18, 2020-21, 2023-24) |
| No duplicate (date, ISIN) | 0 duplicates |
| Every ISIN matched to terms | 912 of 912 (each auction has exactly one candidate ISIN) |
| Linkers excluded and counted | 328 linker auctions in the window excluded; 5 spelled "Index-Linked" would slip past a case-sensitive filter |
| *Extra:* the DMO's AAY reprices to its AAP (our terms, DMO settlement) | **912 of 912**. From 29 Jul 2003 within 2e-5. Before then the published AAP was truncated (all 32 errors in [0, 0.01)). The 89 auctions priced with a rule-based first coupon all reprice within 1e-5, which confirms the rule's dates |
| *Extra:* DMO result notices | 25 Mar 2009 (uncovered; full amount allotted) and 10 Aug 2010 match field by field |

**Other facts from the panel**
- Every DMO settlement date is T+1.
- 80 new issues and 832 reopenings.
- 101 auctions are priced partly beyond the curve (88 before 2016); 75 are more than 5 years beyond.
- Regimes, after the sign-off: pre-crisis 129, QE 570 (including the 24 Feb–Oct 2022 auctions, flagged `passive_qt_2022`), LDI stress 3, active QT 208, post-QT-decision 2.

**Tests run:** `pytest`, 69 passed. New: `test_auctions.py` (26 tests): calendar helpers, bucket and regime boundaries, the four spec checks, settlement, AAP repricing, two result notices, years beyond the curve, new-issue and first-coupon flags, the supply window, the negative-tail flag.

**Sign-off (20 Oct 2026; decisions #13–15), applied in Stage 4:**
- Volatility at the gilt's own maturity (10y as robustness).
- DV01 from the allotment excluding PAOF (including PAOF as robustness).
- Feb–Oct 2022 in QE (`passive_qt_2022` flags it for the robustness drop). This includes 18–26 Oct 2022, after the LDI window.
- Syndications and tenders include linker operations (conventional-only as robustness).
- `qe_purchase_week` dummy: an APF QE purchase within ±5 business days (321 auctions); `qt_sale_week` alongside it (157).
- `tail_bp_regression` sets the 4 Mar 2009 tail to missing. No other tail is negative: 173 positive and 4 zero before 2010, so there is no sign-convention change.

**Could not resolve at the gate** (all decided as above)
1. **Rate volatility** is not defined in spec §6. The panel has two candidates: the 20-day realised volatility of the BoE spot rate to T-1, at 10y and at the gilt's own maturity (correlation 0.90).
2. **Auction DV01 nominal:** the allotment (known before the auction), or the total including the PAOF (partly an outcome)? Both are recorded.
3. **Feb–Oct 2022** (24 auctions outside the LDI window): regime treatment is open (spec §8). They are labelled `Feb-Oct 2022 (open)`.
4. **4 Mar 2009, 4¼% 2039: D2.1A tail −5.5 bp** (impossible; data issue). Kept and flagged. Keep it, set it to missing, or drop the auction from tail regressions?
5. **Supply controls:** should syndications and tenders include linker operations? Both versions are recorded. Should QE purchases be added (data #10, not in spec §6)?
6. Still open: the M2 control (Module 4, today), the PM's benchmark (§1), and the OIS control C start date.

### Stage 4: M1, M1b, M2, spec §7 (20 Oct 2026). Gate: hand check of 5 auctions; distribution plots

**Delivered**
- `measures.py` (`python -m gilt_study.measures`):
  - **M1** = AAY − model yield off the T-1 curve, priced for the auction's settlement date.
  - **M1b** = M1 − the gilt's mean DMO residual over T-25…T-6.
  - **M2**: the T-10…T+10 path with control **B-β** (decision #13): mean change of BoE spot points 2–30y lying more than 3y from the gilt; β by OLS over T-120…T-21; AR = Δy − β·Δc; CAR = 0 at T-6. Robustness **B** (β = 1) and the raw path are kept.
  - The PM's three numbers.
  - Event days are UK business days, which are exactly the BoE curve dates.
- Outputs: `data/processed_data/measures/{auction_measures.csv, m2_paths.csv.gz, m1b_residuals.csv.gz}` and the model-yield cache `data/interim_data/auction_gilt_model_yields.csv.gz`.
- **Hand check:** `data/processed_data/measures/handcheck_5_auctions.xlsx` covers five auctions:
  - short: 6 Aug 2013, 1¼% 2018;
  - medium: 21 Oct 2010, 3¾% 2020;
  - long: 9 Oct 2012, 4¼% 2032;
  - new issue: 15 Mar 2018, 1⅝% 2028, with a long first coupon;
  - Sept–Oct 2022: 4 Oct 2022, 0½% 2061 (LDI window).

  Each has every intermediate value as live formulas: cash flows, z, DF, PV, dirty price, the re-pricing at the model yield, the M1b residuals, the 132 days of model yields and control changes, β by SLOPE, AR, CAR and the three numbers. LibreOffice recalculates all 32,145 formulas with 0 errors and reproduces the Python results to ~1e-8. Notebook 04 §5 shows the same tables.
- `notebooks/04_measures.ipynb`. Charts: `m1_m1b_by_bucket`, `m1_over_time`, `m2_car_paths`, `m2_pm_numbers`, `m2_beta_distribution`.
- Stage 3 sign-off applied to the panel (see Stage 3).

**Results (descriptive; inference is Stage 5)**
- **Coverage:** M1 and M2 for all 912 auctions. M1b for 309 (2003–2017). It is missing for 472 auctions outside the DMO yields, 80 new issues, and 51 with < 10 valid days.
- **M1** mean / median: short 7.0 / 5.4bp, medium 2.4 / 2.4bp, long −0.2 / −0.1bp. **M1b**: 2.1 / 1.4, 0.9 / 0.9, 1.1 / 1.0bp.
- **β:** 0.40–1.42 (median ≈ 1, median R² 0.93). No outliers (β < 0 or > 3).
- **M2 (B-β):** mean pre-auction +0.4 to +0.5bp, auction day −0.1 to +0.2bp, post-auction −0.3 to −0.7bp by bucket. B (β = 1) correlates 0.94–0.96 with B-β. The LDI-window auctions are extreme: pre −18bp, then cheapening.
- **M1's settlement choice is immaterial:** pricing for the curve's own settlement date instead moves M1 by ≤ 0.17bp.

**Tests run:** `pytest`, 83 passed. New: `test_measures.py` (11 tests) covers:
- the CAR, OLS and control-set arithmetic on synthetic data;
- M1 for every auction and the settlement check;
- M1b coverage and rules;
- the M2 path consistency (CAR 0 at T-6, steps = AR, three numbers = CAR differences, no α);
- the coverage counts and the five hand-check auctions.

`test_auctions.py` gains the decision #14–15 checks.

**Could not resolve (needs decisions at the gate)**
1. **M1b exclusion rule** (spec: "excludes … any earlier auction of the same gilt inside [the window]"). Built as: drop days within ±5 business days of an earlier auction, with ≥ 10 valid days required. Looser rules give 352–359 auctions instead of 309, with mean M1b 1.27–1.30bp instead of 1.37bp.
2. **The PM's three numbers.** Built as pre = CAR(T-1) − CAR(T-6), day = CAR(T) − CAR(T-1), post = CAR(T+5) − CAR(T). Confirm this reading of "T-5 → T-1" and "T → T+5".
3. **M1 after 2017 is mostly gilt-level cheapness.** The gilt's own mean explains 69% of M1's variance for 2018–2026 (48% before). Examples: 4⅛% 2027 sits at 17–43bp over 9 auctions, 3½% 2025 at 7–35bp. M1b cannot be computed after Jul 2017. Options:
   - gilt fixed effects in the Stage 5 regressions;
   - a within-gilt M1;
   - leaning on M2 for 2018–2026.
4. **2022 financial-stability purchases** were also made through the APF. They are not in `qe_purchase_week`; they are recorded separately (5 auctions). Should they count?
5. Control C (gilt − OIS, from Dec 2021) and all inference are Stage 5.
