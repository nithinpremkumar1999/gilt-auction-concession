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
│   ├── measures.py          M1, M1b, M2 (control B-β; B), M3 (bond residual path), the PM's three numbers
│   ├── ois.py               BoE OIS curve panel (2016-2026) and M2 with control C, gilt − OIS (Stage 5)
│   ├── inference.py         OLS with week-clustered and calendar-time Newey-West SEs (Stage 5)
│   ├── analysis.py          Stage 5 dataset, headline means, regressions (spec §8), robustness tables
│   ├── placebo.py           placebo test: M2/M3 on random non-auction dates of the same gilt (Stage 5)
│   ├── report_charts.py     the report's four charts, PNG + HTML (Stage 6)
│   ├── data_io.py           DMO readers; test-scope filters (single-dated, linker spellings)
│   ├── inventory.py         SHA-256 manifest of data/raw_data and its check
│   ├── plotting.py          one chart, two outputs: seaborn PNG + Plotly HTML (decision #9)
│   ├── paths.py             every file location
│   ├── config.py            study parameters from logged decisions (sample start 1 Nov 1998, #7)
│   └── exercises/           validation scripts: exercise_a (Stage 1), exercise_b + curve_checks (Stage 2),
│                            handcheck_stage4 (Stage 4 hand-check workbook)
├── notebooks/               00 inventory · 01 pricer · 02 curve · 03 auction panel · 04 measures · 05 inference
│                            · 06 report charts
│                            (the why, before code)
├── reports/
│   ├── figures/             static charts (seaborn), PNG
│   ├── interactive/         interactive charts (Plotly), HTML
│   └── tables/              report tables: the exact p-value appendix (CSV + HTML)
├── data/
│   ├── raw_data/            downloads, never edited (see SOURCES.md)
│   ├── raw_manifest.csv     SHA-256 of every raw file
│   ├── interim_data/        regenerable intermediate data (gilt terms, model/market yield caches)
│   ├── processed_data/      analysis-ready data and validation outputs
│   └── DATA.md              log of every change to interim/processed data
├── tests/                   pytest: Stage 0 checks, gilt terms, Stages 1-5
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
python -m gilt_study.measures                      # M1, M1b, M2, M3 (builds the yield caches the first time; ~1 min after)
python -m gilt_study.exercises.handcheck_stage4    # Stage 4 hand-check workbook (recalculate in Excel/LibreOffice)
python -m gilt_study.ois                           # Stage 5 OIS panel + control C
python -m gilt_study.analysis                      # Stage 5 headline means, regressions, robustness
python -m gilt_study.placebo --build-yields        # Stage 5 daily model yields for the placebo (~12 min, once)
python -m gilt_study.placebo                       # Stage 5 placebo, 1,000 draws, both designs (~5 min); run before analysis
python -m gilt_study.report_charts                 # Stage 6 report charts (needs the analysis and placebo outputs)
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

### Stage 4: M1, M1b, M2, spec §7 (20 Oct 2026). Signed off 20 Oct 2026

**Sign-off** (spec v0.5, decisions #16–17). Nithin reproduced M1 for the short, medium and long hand-check auctions independently.
- Keep the strict M1b rule.
- The three numbers as defined: pre T-6→T-1, day T-1→T, post T→T+5.
- M1 to the auction settlement date.
- The 2022 financial-stability purchases stay separate.
- Post-2017 M1 levels are not concession estimates; M1 after 2017 is used only with gilt fixed effects.
- M3 is promoted to the MVP, with yields from the DMO clean price before Nov 2002, and M1b is extended to those years (see Stage 5).

The record below is as delivered at the gate.

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

### Stage 5: M3, control C, inference, regressions, placebo, robustness, spec §7–§8 (20 Oct 2026). Signed off 21 Oct 2026

The record below is as delivered at the gate. The sign-off and the re-run follow it ("Stage 5 re-run").

**Delivered**
- **Market yields back to Nov 1998** (decision #17), `measures.build_market_yields()`.
  - DMO yields where they are published.
  - Before 25 Nov 2002, the yield from the DMO clean price plus our accrued interest, priced for next-day settlement with `pricing.py` unchanged.
  - Where both exist, the two agree to 0.0001bp (3,000 random gilt-days).
- **M1b** uses these market yields: **319 auctions** (from 309), back to 26 May 1999.
- **M3** (`measures.m3`): the residual (market yield − model yield) from T-10 to T+10, with the same three numbers as residual changes.
  - Coverage: pre 395, day 417, post 416 auctions, 1999–Jul 2017.
  - New issues have no pre number. *(Corrected 21 Oct: 28 of the 50 new issues to Jul 2017 do have one, because the DMO reference prices carry the when-issued line by T-6.)*
  - Output: `data/processed_data/measures/m3_paths.csv.gz`.
- **Control C** (`ois.py`): Δ model yield − Δ OIS spot at the gilt's remaining maturity, for auctions from 1 Dec 2021 (241).
  - Beyond the OIS curve's 25y the curve is extended flat-forward (38 auctions).
  - The 1 May 2024 OIS curve is missing, so the previous curve is used (5 auctions affected).
- **Inference** (`inference.py`):
  - Main: OLS with SEs clustered by ISO week of the auction (CR1; t with G−1 df).
  - Check: Newey-West in calendar time (Bartlett, 30 days).
  - Both reproduce statsmodels 0.15.0 to 1e-10.
- **Regressions** (`analysis.py`, spec §8, decision #17):
  - M1b (1999–2017);
  - M1 with **gilt fixed effects** (2018–2026);
  - M2 B-β pre/day/post (all years);
  - M3 pre/day/post;
  - M1 pooled on the M1b sample;
  - H4: long × post-2022 in the M1-FE and M2 regressions.

  Regressors: DV01 (£m/bp, allotment excl. PAOF), bucket, cover surprise, tail (4 Mar 2009 missing), new issue, QT-sale week, QE-purchase week, syndication/tender within ±5 business days, volatility at the gilt's maturity, and regime dummies. The 2 post-QT-decision auctions are descriptive only.
- **Placebo** (`placebo.py`): 1,000 draws (seed 20261020).
  - Each real auction is replaced by the same gilt on a random non-auction date, in the same bucket, at least 10 business days from its own auctions.
  - M2 and M3 are recomputed exactly. The engine reproduces the real auctions to 5e-14 (M2) and 7e-10 (M3).
- **Robustness:**
  - M2: drop the LDI window; drop Feb–Oct 2022; drop > 5y beyond the curve; control B (β = 1); B-β vs C on the C sample.
  - M3: drop > 5y beyond the curve.
  - M1b: looser exclusion rules.
  - Regressions: DV01 incl. PAOF; volatility at 10y; conventional-only supply; the three sample drops.
- `notebooks/05_inference.ipynb`. Charts: `stage5_three_numbers`, `stage5_m3_paths`, `stage5_regimes`, `stage5_placebo`. Tables: `data/processed_data/stage5/`, `data/processed_data/placebo/`.

**Results** (bp; positive = the gilt cheapened; p clustered unless stated)

| | pre T-6→T-1 | day T-1→T | post T→T+5 |
|---|---|---|---|
| M2 B-β, all years (912) | +0.43 (p 0.012; placebo 0.008) | +0.04 (0.63; 0.35) | −0.43 (0.006; placebo 0.074) |
| M3, 1999–2017 (≈400) | +0.37 (< 0.001; < 0.001) | −0.32 (< 0.001; < 0.001) | −0.18 (0.010; 0.007) |

- **Levels to 2017:** M1b +1.39bp (319 auctions) vs M1 +1.92bp on the same auctions. By bucket, M1b is short 2.08, medium 0.93, long 1.19. M1 for long gilts is −0.12, because long gilts sit rich to the curve; M1b removes that.
- **By regime (M2):**
  - pre-crisis: pre +1.13, post −0.88;
  - QE: pre +0.59, post −0.62;
  - active QT: pre −0.16 (n.s.), day +0.32 (p 0.047).
  - LDI window: 3 auctions, 2 clusters, so no reliable SE.
- **Regressions:**
  - Cover surprise is negative in M1b (−1.54***), M2 day (−1.12***) and M3 day (−0.57***).
  - Volatility is positive in M1b (+0.43***).
  - QE is negative in M1b (−1.69***).
  - In the M1 FE regression (base QE): DV01 +1.27**, QT-sale week −2.26***, LDI +9.15***, active QT +6.29***.
  - H4: long × post-2022 is −7.96*** in M1 FE and not significant in M2.
- **Control C vs B-β** (Dec 2021+, 241 auctions): neither is significant. They disagree on the pre number: B-β −0.16, C +0.48 (p 0.14).
- **Robustness:** the M2 and M3 means survive every sample drop and control B. In the regressions, active QT in M1 FE falls to +4.14 (n.s.) when Feb–Oct 2022 is dropped. Looser M1b rules give 1.31 and 1.29bp.

**Tests run:** `pytest`, 92 passed. New: `tests/test_stage5.py` (9 tests) covers:
- inference vs statsmodels and the week clusters;
- market-yield sources and M1b back to 1999;
- M3 = residual changes;
- the control-C sample and missing rule;
- cover surprise from earlier auctions only;
- the regime base;
- the placebo engine check and its 1,000 draws.

`test_measures.py` was updated for M1b = 319.

**Could not resolve (needs decisions at the gate)**
1. **Cover surprise** = bid-to-cover − the mean of the previous 5 auctions in the same bucket. Is 5 the right lookback?
2. **Supply controls** are dummies (any syndication or tender within ±5 business days, linkers included). Use dummies or counts?
3. **H4 "post-2022"** = auctions from 1 Nov 2022 (active QT).
4. **Newey-West bandwidth** = 30 calendar days.
5. **Placebo design** as above, with a two-sided p-value around the placebo mean. 15 auctions (M2) and 3 (M3) have no eligible date.
6. **Control C** is extrapolated flat-forward beyond 25y (38 auctions).
7. **Cover and tail are auction outcomes**, unknown during the pre window. Keep them in all specifications, or split out an "auction outcome" specification?
8. **The LDI dummy** rests on 3 auctions in 2 weeks. Report it but do not interpret it?
9. **M3 attenuation.** The BoE nominal curve is fitted to conventional gilts "with a significant amount in issue and having more than three months to maturity", so the auctioned gilt is one of its own fitting points. M3 (and M1) residual changes are therefore biased towards zero; M2 is not, because its control excludes ±3y around the gilt. Note this as a limitation, or test it with our own refit excluding the gilt (a new curve build)?
10. **The placebo and clustered SEs disagree on M2 post** (0.074 vs 0.006): the placebo centre is −0.11bp, not 0. Which leads in the write-up?
11. Still open: the PM's benchmark (§1).

#### Stage 5 sign-off and re-run (21 Oct 2026; spec decisions #18–#20)

**Sign-off**
- **#18:** the proposed defaults are approved.
  - Cover surprise vs the previous 5 auctions in the bucket (10 as robustness).
  - H4 from 1 Nov 2022.
  - Newey-West bandwidth 30 calendar days.
  - The placebo design.
  - OIS flat forward beyond 25y.
  - Supply controls as dummies, with counts as robustness.
- **#19:** two specifications. **Ex-ante** (variables known before bidding) for the PM's prediction; **auction-outcome** (adds cover surprise and tail) for explanation. Cover and tail never enter pre-window regressions.
- **#20:**
  - The LDI dummy is reported, not interpreted.
  - M3 attenuation is recorded as a limitation, with no refit.
  - Inference leads with the placebo-centred p-value, with clustered SEs alongside.

**What changed in the code and outputs**
- **`analysis.py`**
  - `EX_ANTE` and `AUCTION_OUTCOME` regressor sets; `specs_for()` keeps M2 pre and M3 pre out of the auction-outcome specification.
  - `regressions.csv` carries a `specification` column. The wide tables `regressions_ex_ante.csv` and `regressions_outcome.csv` replace `regressions_wide.csv`, which is deleted. H4 is run under both specifications.
  - Robustness gains "supply counts (not dummies)" and "cover surprise vs previous 10". Every variant runs under both specifications.
  - `headline.csv` gains `p_placebo`, `placebo_mean_bp`, `n_placebo`, `p_placebo_same_regime`, `lead_p`, `lead_p_source` and `note` (the LDI rows), plus M1b/M1 levels by regime.
- **`placebo.py`**
  - Regime groups are added, by the real auction's regime.
  - **Each M3 window is now drawn on its own sample**, the same as its headline mean: 391/412/412 events, where Stage 5 used 391 for all three.
    - All auctions: only the post p moves, 0.007 → 0.004.
    - By bucket: medium post crosses 5% (0.069 → 0.021); long post 0.180 → 0.234; long pre 0.008 → 0.005.
  - Mean placebo paths are kept for chart 1 (`placebo_paths.csv.gz`).
  - A second design, "same regime", is added for a Stage 6 gate question.
  - M2 results are identical to the Stage 5 run (same seed, same draw order).
- **Notebook 05** is rebuilt.
  - The charts `stage5_three_numbers` and `stage5_regimes` are removed; report charts 2 and 3 replace them.
  - `stage5_m3_paths` and `stage5_placebo` are kept.

**Re-run results** (bp; positive = cheapened; lead p = placebo-centred)

| | pre T-6→T-1 | day T-1→T | post T→T+5 |
|---|---|---|---|
| M2 B-β, all years (912) | +0.43 (p 0.008) | +0.04 (0.345) | −0.43 (0.074) |
| M3, 1999–2017 (395/417/416) | +0.37 (< 0.001) | −0.32 (< 0.001) | −0.18 (0.004) |

- **Ex-ante regressions** (clustered SEs):
  - M1b: volatility +0.46***, QE −1.80***, medium −1.65**, long −2.02**, DV01 +0.61*.
  - M1 with gilt FE: DV01 +1.02**, long −3.53**, QT-sale week −2.19***, active QT +6.02**.
  - M3: volatility +0.42*** pre and −0.17*** day.
  - M2: nothing significant at 5% except the LDI dummy, which is not interpreted.
- **Auction-outcome regressions** are the Stage 5 main table without the pre windows (same regressors).

### Stage 6: report charts, spec §9 (21 Oct 2026). Chart gate held 21 Oct 2026; changes applied, stopped after re-render

The record below is as delivered at the gate. The decisions and changes follow it ("Chart gate").

**Delivered**
- `report_charts.py` (`python -m gilt_study.report_charts`) and `notebooks/06_report_charts.ipynb` (data and reasoning per chart).
- Four chart pairs, each a PNG in `reports/figures/` and an HTML in `reports/interactive/`:
  1. `report_1_paths`: the average path T-10…T+10 for M2 (all 912 auctions) and M3 (the 367 with a complete path). Each line has a blue band for the 95% CI of the mean (clustered by week) and a grey band for the placebo 95% range (2.5–97.5 percentiles of 1,000 placebo mean paths). Dotted lines mark the three windows.
  2. `report_2_by_bucket`: the three numbers by bucket for M2 and M3, plus the M1b level, with all auctions alongside.
  3. `report_3_by_regime`: the same by regime (pre-crisis, QE, active QT). The LDI window is in the tables only.
  4. `report_4_ex_ante_drivers`: ex-ante coefficients with 95% CIs, one panel per dependent variable. M2 and M3 are by window; M1b and M1 (gilt FE) are levels.
- **Common encoding:**
  - bars are 95% CIs from clustered SEs;
  - **filled marker = lead p < 0.05** (placebo-centred for M2/M3 means, clustered for M1b and coefficients);
  - one y-axis per chart;
  - buckets use categorical slots 1–3; regimes use slots 7, 4, 5 (validator: worst CVD ΔE 16.3, normal 19.6).
- **Checked by eye:** both versions of every chart. The PNGs were checked directly, and the Plotly HTML through screenshots rendered in Chromium.

**Tests run:** `pytest`, 96 passed. `tests/test_stage5.py` gains:
- the two specifications (no cover or tail in ex-ante or pre-window regressions, including robustness);
- the headline leading with the placebo p;
- the placebo per-window M3 samples, two designs and 1,000 draws;
- the placebo paths (engine check, zero at T-6);
- the data behind the charts.

**Could not resolve (needs decisions at the gate)**
1. **Chart 1 bands:** clustered CI plus the placebo range (as drawn), or one band only?
2. **Chart 1 M3 sample:** the 367 auctions with a complete path (as drawn), or all available auctions at each k (a changing sample)?
3. **Marker fill for the lead p** (as drawn), or p-values as text labels?
4. **Placebo design for the regime rows:** decision #18 (as drawn), or dates restricted to the auction's own regime?
   - No marker in chart 3 changes fill. The largest moves are M2 pre-crisis post 0.262 → 0.135, M3 pre-crisis post 0.320 → 0.084, and M2 active-QT day 0.030 → 0.013.
   - Used throughout, the same-regime design would move the headline M2 post p from 0.074 to 0.014, with a placebo centre of −0.04 instead of −0.11bp. It also drops 10 more auctions, including the 3 LDI ones.
5. **Chart 4:**
   - raw units (as drawn) or standardised;
   - regime dummies off the chart;
   - M1 with gilt FE in the level row.
6. **Ex-ante DV01** is priced at the AAY (an outcome) with the D2.1A amount. Repricing at the T-1 model yield moves it by 0.55% on average (max 6.9%; correlation 0.9998). Switch so it is strictly ex-ante?
7. **Titles are descriptive,** because interpretation is Nithin's (decision #2). Headline-style titles can follow the write-up.
8. Still open: the PM's benchmark (§1).

#### Chart gate (21 Oct 2026): decisions and changes

**Decisions**
1. **Chart 1:** keep both bands, with captions explaining each.
2. **Chart 1 M3 sample:** fixed at 367 auctions ✓.
3. **Marker fill for the lead p** ✓, plus an appendix table of exact p-values.
4. **Placebo:** decision #18 stays the main placebo. The own-regime placebo is a labelled robustness check, noted as added after seeing the results.
5. **Chart 4 layout** ✓.
6. **DV01** is switched to the T-1 model yield.
7. **New windows:** T-10 → T-1 as a robustness pre-auction window for M2 and M3, and the M3 total move T-10 → T+1. Both were added after seeing chart 1, where M3 rises from T-8.
8. **Titles:** headline titles follow Nithin's write-up.

**Changes**
- **Captions** (`report_charts.py`): every chart has one in both versions.
  - Chart 1 explains the blue and grey bands and the dotted window lines.
  - Charts 2–3 explain the fill, the bars and why a hollow marker can have a bar that clears zero.
  - Chart 3's caption is computed from the data: with own-regime placebo dates, no marker changes fill.
  - Chart 4's note says that DV01 is priced at the T-1 model yield.
- **Appendix:** `reports/tables/appendix_p_values.csv` and `.html` (156 rows, `write_appendix()`).
  - Columns: every charted point's estimate, 95% CI, lead p and lead test, the decision #18 placebo p, the own-regime robustness p (labelled), and the clustered and Newey-West p.
  - Rows the charts leave out are included and marked "table only": the LDI window, M1 on the M1b sample, regime dummies, and the new windows.
  - Placebo p-values are in steps of 0.001 ("< 0.001" when no draw is as extreme).
- **DV01** (`analysis.dv01_per_100_t1`): priced at the T-1 model yield for the auction settlement date. The AAY version is kept as `dv01_aay`.
  - The level changes little: 0.55% on average, 6.9% at most, correlation 0.9998.
  - The coefficients move more, because the AAY version was mechanically tied to M1 (a higher AAY means a lower DV01):
    - ex-ante M1b DV01: +0.61 (p 0.069) → +0.74 (0.028);
    - M1 with gilt FE: +1.02 (0.040) → +1.46 (0.004).
  - Other coefficients that cross 5%: the medium and long buckets in M1b (auction-outcome) and in M1 on the M1b sample.
  - The amount is still the D2.1A amount.
- **New windows** (`measures.M2_EXTRA_WINDOWS`, `M3_EXTRA_WINDOWS`): new columns `m2_pre10_bbeta_bp`, `m3_pre10_bp` and `m3_total_bp`. Existing measure values are unchanged except for < 1e-9 bp in M1b/M3, which are now read from the market-yield cache.
  - Placebo: M2 pre10 reuses the main draws' dates; the M3 windows use their own random stream. Every earlier placebo number is reproduced exactly.
  - Results (lead p = placebo):

    | Window | Mean | p |
    |---|---|---|
    | M2 T-10 → T-1 | +0.28bp | 0.215 |
    | M3 T-10 → T-1 | +0.60bp | < 0.001 |
    | M3 total T-10 → T+1 | +0.16bp | 0.012 |

  - By bucket, M3 T-10 → T-1 is short +1.03, medium +0.51 and long +0.32, all < 0.001. M2 T-10 → T-1 is significant only for long: +0.63, p 0.006.
- **Own-regime placebo:** `design_note` in the placebo results; `p_placebo_same_regime` and `p_placebo_same_regime_note` on every headline row (it was on regime rows only before).
- **Notebooks 05 and 06** are rebuilt, with the chart-gate record in notebook 06 §6.

**Tests run:** `pytest`, 100 passed. New tests cover:
- DV01 at the T-1 model yield;
- the new windows as path differences;
- the robustness labels;
- the appendix covering every charted point.

**Still open:** the PM's benchmark (§1). The spec's decision log needs the chart-gate decisions.
