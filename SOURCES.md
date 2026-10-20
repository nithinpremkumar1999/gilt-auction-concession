# Data Sources

Every raw file used by the study, where it came from, what it actually contains, and its SHA-256 checksum.

- **Raw files live in `data/raw_data/` and are never edited.** Cleaned or derived data goes to `data/interim_data/` or `data/processed_data/`, and every change is logged in `data/DATA.md`.
- **Checksums** were computed on Nithin's machine on 19 Oct 2026 (`sha256sum`, 47 files, 210.7 MB) and are stored in `data/raw_manifest.csv`. Check them at any time with `python -m gilt_study.inventory --check`. A file that is re-downloaded gets a new hash. Log the new download date here, then rewrite the manifest with `--write`.
- **Observed coverage** is the first and last date that actually has data, read from the file (`notebooks/00_data_inventory.ipynb`, saved as `data/processed_data/inventory/raw_coverage.csv`). Where it differs from the publisher's description, the difference is listed under *Known issues*.
- IDs (#1, #2, …) follow the data-download checklist and build spec §3.

---

## #1 BoE nominal yield curve, daily

- Publisher: Bank of England, yield curve statistics
- Source (archive): [glcnominalddata.zip](https://www.bankofengland.co.uk/-/media/boe/files/statistics/yield-curves/glcnominalddata.zip), extracted to **data/raw_data/glc_nominal**
- Source (current month): [latest-yield-curve-data.zip](https://www.bankofengland.co.uk/-/media/boe/files/statistics/yield-curves/latest-yield-curve-data.zip). Only the nominal workbook was kept, in **data/raw_data/latest_yield_curve**
- Downloaded on: 2026-10-17
- Used for: pricing each auctioned gilt off the T-1 spot curve to get its model yield (concession = auction yield − model yield), and tracking the curve from T-10 to T+10 for the event study
- Contains (every workbook, same layout): sheet 0 info; 1 forwards, short end; 2 forward curve; **3 spot, short end** (1 month to 5 years, monthly); **4 spot curve** (0.5 years upwards, half-yearly). Maturities on row 3, data from row 5, dates in column 0. Rates are % per year, continuously compounded.

| File | MB | Observed coverage | Rows | SHA-256 |
|---|---:|---|---:|---|
| `glc_nominal/GLC Nominal daily data_1979 to 1984.xlsx` | 4.94 | 1979-01-02 → 1984-12-31 | 1,517 curve days | `125e27da95ce109e090704d8e8cc6368c7941c8416a2296658a5efc9ae0109d0` |
| `glc_nominal/GLC Nominal daily data_1985 to 1989.xlsx` | 3.70 | 1985-01-02 → 1989-12-29 | 1,264 curve days | `508f8a8f0be92acb546b7bc8f78a57ebcd58373f65b859bdfba19dc6761f707b` |
| `glc_nominal/GLC Nominal daily data_1990 to 1994.xlsx` | 4.68 | 1990-01-02 → 1994-12-30 | 1,265 curve days | `9717b48bc97882a53954ebe49a215c84c5921e9860853d430f4f6d042236cfec` |
| `glc_nominal/GLC Nominal daily data_1995 to 1999.xlsx` | 4.82 | 1995-01-03 → 1999-12-30 | 1,264 curve days | `b4429f40b1c1c3ca898ff4cc87fdb2dd5a6db90e0bc48d5c7b84f9328a1cbfcd` |
| `glc_nominal/GLC Nominal daily data_2000 to 2004.xlsx` | 4.89 | 2000-01-04 → 2004-12-31 | 1,264 curve days | `f3ddf65657594ffb7b27eefd0722bfd35cc43c75455031b1422abfa021a584d3` |
| `glc_nominal/GLC Nominal daily data_2005 to 2015.xlsx` | 8.73 | 2005-01-04 → 2015-12-31 | 2,779 curve days | `7f79396d8c2c70f6ed3d7040fbbc62cea32feefee70ad1ac11964374135342f6` |
| `glc_nominal/GLC Nominal daily data_2016 to 2024.xlsx` | 9.11 | 2016-01-04 → 2024-12-31 | 2,273 curve days | `a85505c7dbf619cea6b3cf39d4e70e8b5eab3fc906d47914006849a1ed3d4a5c` |
| `glc_nominal/GLC Nominal daily data_2025 to present.xlsx` | 1.70 | 2025-01-02 → 2026-09-30 | 442 curve days | `44a1facf02d745cd5a83cc79bee6bde4600768e62cd8bb43a0772abaaf630245` |
| `latest_yield_curve/GLC Nominal daily data current month.xlsx` | 0.21 | 2026-10-01 → 2026-10-15 | 11 curve days | `b28807d9b38b9178df84d7d4f3d0088e096bcf0931196a04bfeab3c7bf8b30a9` |

Known issues:
- **Maximum maturity is 25 years from 29 Jan 1998 to end-2015 (23 years before that), and 40 years from 2016.** Under decision #5, the curve is extended beyond its last maturity T with a **flat forward**: the BoE instantaneous forward at T, from sheet 2 on the same day, is held constant, and every affected price is flagged. On every day the forward sheet and the spot sheet end at the same maturity. This affects long gilts auctioned from Nov 1998 to 2015, and ultra-longs (> 40y) from 2016. Notebook 02 measures the error.
- Shortest available maturity is 1 month until 2012, then 0.25–1 year. z is flat below it (spec §5).
- Empty rows on UK holidays are dropped by the loader. From 2 Jan 1998 to 15 Oct 2026, no UK business day is missing and no data falls on a weekend or holiday (`tests/test_curve.py`).
- The archive workbooks and the current-month file do not overlap (the archive ends 30 Sep 2026; the current-month file covers 1–15 Oct 2026).
- The BoE revises fitted curves. Results are tied to the checksums above.

## #2 DMO reference prices, every gilt, every day

- Publisher: UK Debt Management Office
- Source: [DMO historical prices and yields](https://www.dmo.gov.uk/data/gilt-market/historical-prices-and-yields/), one .xls per year
- Downloaded on: 2026-10-17
- Used for: pricer validation (Stage 1); watching the auctioned bond itself and its neighbours cheapen and recover, rather than the smoothed curve (M1b, M3)
- Contains: header on row 4 in every year. Columns: Gilt Name, ISIN Code, Redemption Date, Close of Business Date, Clean Price, Dirty Price, Accrued Interest, Yield, Modified Duration. Includes conventionals, index-linked gilts and STRIPS.
- Location: **data/raw_data/dmo_ref_prices**

| File | MB | Observed coverage | Rows | SHA-256 |
|---|---:|---|---:|---|
| `dmo_ref_prices/1998-gilt-reference-prices.xls` | 4.56 | 1998-01-02 → 1998-12-31 | 36,214 gilt-days | `a382e8d5f3b93a7ec41780d578dd059d0c2b4b1b766d6d3e58ce908ddd864ab6` |
| `dmo_ref_prices/1999-gilt-reference-prices.xls` | 4.37 | 1999-01-04 → 1999-12-30 | 35,965 gilt-days | `2f8462530c6e967046f5f31ed4e0a3e212e00a1547209a0f01bda467f9c849bf` |
| `dmo_ref_prices/2000-gilt-reference-prices.xls` | 4.19 | 2000-01-04 → 2000-12-29 | 34,838 gilt-days | `e230bca5b910a763a356fa9aac50a45005a1d661f97bf11e76d4db4c45911b7a` |
| `dmo_ref_prices/2001-gilt-reference-prices.xls` | 4.18 | 2001-01-02 → 2001-12-31 | 34,643 gilt-days | `1c240b54974d65b922b41b85be751f4b5b156eb8ccaa3e7781a7b210a9a54e3a` |
| `dmo_ref_prices/2002-gilt-reference-prices.xls` | 5.25 | 2002-01-02 → 2002-12-31 | 42,148 gilt-days | `6a042695f5b64b27245e174a206dc2537f2ed9ab69faafe549fa583a0e571bf9` |
| `dmo_ref_prices/2003-gilt-reference-prices.xls` | 7.31 | 2003-01-02 → 2003-12-31 | 47,355 gilt-days | `660639751dcf719999fbd33a349b49e139b13865664bc77664648867c6a14440` |
| `dmo_ref_prices/2004-gilt-reference-prices.xls` | 7.76 | 2004-01-02 → 2004-12-31 | 50,216 gilt-days | `20887e435056e541d163eb6997738819cc09743d852554b8127cf8d47793ffb6` |
| `dmo_ref_prices/2005-gilt-reference-prices.xls` | 7.84 | 2005-01-04 → 2005-12-30 | 50,700 gilt-days | `2c0c220fa5c88992fae9c820665078a6e9df28d138a28ac669dffe8866459e7a` |
| `dmo_ref_prices/2006-gilt-reference-prices.xls` | 9.15 | 2006-01-03 → 2006-12-29 | 59,134 gilt-days | `f70158dac5fa3fb9f078521abe4ea551694401669a6a52391616633b3c3dcc32` |
| `dmo_ref_prices/2007-gilt-reference-prices.xls` | 9.12 | 2007-01-02 → 2007-12-31 | 58,902 gilt-days | `a9c8f4f4a3229b1c999c2e446cad1a88fb9a86874ccdcd95d5c37eff6a90afee` |
| `dmo_ref_prices/2008-gilt-reference-prices.xls` | 9.15 | 2008-01-02 → 2008-12-31 | 59,138 gilt-days | `4fd0d1c44c7f072b9c4193cc29f662ddfb30134687a5434e33688db567f1ba72` |
| `dmo_ref_prices/2009-gilt-reference-prices.xls` | 9.47 | 2009-01-02 → 2009-12-31 | 61,218 gilt-days | `5701ed92ee120af8e025ff7d18f47c14f62e57fa68dcc110a1f689fd5f7af80a` |
| `dmo_ref_prices/2010-gilt-reference-prices.xls` | 9.62 | 2010-01-04 → 2010-12-31 | 62,260 gilt-days | `403a5201c357efcf4e954711ec61df8f93b582f226f865a20d1929919e4f4e83` |
| `dmo_ref_prices/2011-gilt-reference-prices.xls` | 9.46 | 2011-01-04 → 2011-12-30 | 61,235 gilt-days | `5ffef703423829869e50b1d0c2088d783e407b07d6c54482e4b5cf0211f35869` |
| `dmo_ref_prices/2012-gilt-reference-prices.xls` | 9.35 | 2012-01-03 → 2012-12-31 | 60,499 gilt-days | `da013e2e1e8a4d574ba328b33ea0fc4edf002f089a4de51b10405791bf7fdb2a` |
| `dmo_ref_prices/2013-gilt-reference-prices.xls` | 9.34 | 2013-01-02 → 2013-12-31 | 60,535 gilt-days | `39d74ea51de60e1279fe47c30470b2e39dd9152d5e2cc1d4e7aa192e72f0eb58` |
| `dmo_ref_prices/2014-gilt-reference-prices.xls` | 9.25 | 2014-01-02 → 2014-12-31 | 59,926 gilt-days | `a9e081b5c33decb22347f3d5c5f080bfe0fe85e793c9a967f94dcb7897994685` |
| `dmo_ref_prices/2015-gilt-reference-prices.xls` | 8.94 | 2015-01-02 → 2015-12-31 | 57,848 gilt-days | `1653e2566577bbfe5ad3ad1ec58536729f75be7daefc350d74f8a3c0671c2069` |
| `dmo_ref_prices/2016-gilt-reference-prices.xls` | 8.71 | 2016-01-04 → 2016-12-30 | 56,365 gilt-days | `6e00b4dd3be2b45440b82e42db286c3402ea7526dbd5a16d0bcdae51ef5a6127` |
| `dmo_ref_prices/2017-gilt-reference-prices.xls` | 4.82 | 2017-01-03 → 2017-07-21 | 31,110 gilt-days | `6153f72afa794ef6b2787653bc120a05e0bcc09b445584847c810d7a57a7ec5c` |

Known issues:
- The series **ends on 21 Jul 2017**; the DMO stopped publishing reference prices then.
- Before **1 Nov 1998**, accrued interest was actual/365 and prices were in 1/32nds (DMO convention changes paper). The auction sample starts on 1 Nov 1998 (decision #7).
- **No DMO yield is published for any conventional gilt before 25 Nov 2002**, so the pricer test window is 25 Nov 2002 – 21 Jul 2017 (spec §4). The 1998–2002 files give accrued interest only.
- Besides single-dated conventionals, the files include **double-dated** (e.g. 12% Exchequer 2013-17), **undated** (3½% War Loan, Consols, Annuities) and **floating-rate** gilts. The Stage 1 test covers single-dated gilts only (P1, decision #6).
- Index-linked gilts are mostly named "Index-linked", but the files also use **"Index -Linked"** (0¼% 2052 WI) and **"I-L"**. `data_io.is_index_linked()` catches all three.
- **When-issued (WI) lines**: before a reopening, the DMO quotes a temporary line with its own ISIN (name ending "WI", or a short name). The DMO prices it for settlement on the tranche's issue date. Data errors on 21 WI gilt-days are listed in notebook 01 (wrong redemption date on two lines, yield inconsistent with the clean price, accrued reported as 0).
- **8% Treasury Stock 2009**, 21 Aug – 15 Sep 2009: the DMO's accrued interest runs to the trade date, not to settlement (6 days).

## #4 Gilt static data

- Publisher: UK Debt Management Office
- Source: [DMO gilts in issue](https://www.dmo.gov.uk/data/gilt-market/gilts-in-issue/) (D1A, D1C, D2.1E)
- Downloaded on: 2026-10-17
- Location: **data/raw_data/gilt_static**
- Gilts in issue (D1A, `gilts_issue.xls`): a snapshot of gilts in issue on 16 Oct 2026, with ISIN, redemption date, first issue date, dividend dates, the current/next ex-dividend date and the amount in issue. Used for building cash flows.
- Redeemed gilts (D1C, `redeemed.xls`): redemption date, name and amount outstanding at redemption. Used for gilts auctioned in 1998–2026 that have since matured and are no longer in D1A (maturity matched on coupon and maturity year).
- Issuance history (D2.1E, `issuance_history.xls`): one row per issue event, with ISIN, issue date, type, price, yield, nominal and cumulative amount. Used for the auction → ISIN match, new issue vs reopening, and amount outstanding before each auction.

| File | MB | Observed coverage | Rows | SHA-256 |
|---|---:|---|---:|---|
| `gilt_static/gilts_issue.xls` | 0.04 | 2026-10-16 | 105 gilts | `b7fca1c126f299516439415cf03a187e80c1ae22b53bab7afbfaf8877ead0bf9` |
| `gilt_static/redeemed.xls` | 0.04 | 1981-01-15 → 2026-07-22 | 237 redemptions | `f5daa3a808a888b381ea93c6f7c8322b34d5c02fe37121245e3ef0e616c22e94` |
| `gilt_static/issuance_history.xls` | 0.44 | 1998-01-21 → 2026-10-15 | 2,371 issue events | `ad12a46674cc6ccf794b75179547ff228701888ca9915c5b4d1ebb9576767b69` |

Known issues:
- **D1C has no ISIN and no first issue date.** Matured gilts get their ISIN and dates from D2.1E.
- **D2.1E starts on 21 Jan 1998.** For gilts first issued before then, the earliest row is a cancellation, conversion or later issue, so "min issue date per ISIN" is wrong for 16 such gilts (Stage 1). Rule adopted (P4, decision #6): first issue = D1A, else the first D2.1E row that is a genuine launch (cumulative amount = its own nominal), else none. Built into `data/interim_data/gilt_terms.csv`.
- D2.1E's *Issue Date* is the **settlement date** (auction date + 1 UK business day, for all 915 conventional auctions). The auction panel takes each auction's settlement date from it, not from an assumed T+1 (spec §4).
- WI lines are priced to the issue date of their tranche: the next D2.1E row with a price for the underlying ISIN, within 45 days of the trade date (P2).
- D2.1E's "Outright" type also includes **direct issues to the DMO** for cash management (791 rows with no price). On six auction days one is dated the auction day itself. The auction row is the one with a price.
- D2.1E **truncates** the auction price to 2 d.p. and the yield to 3 d.p. (914 of 915), so auction prices and yields come from D2.1A.
- D2.1E excludes "rump" gilts (not relevant to auctions).

## #4b DMO notices: first coupon dates of new gilts

- Publisher: UK Debt Management Office (press releases, pre-auction and issuance notices, prospectuses)
- Read on: 2026-10-19 (web pages, not downloaded; the URL and the sentence quoted are stored in `gilt_study.gilt_terms.DMO_NOTICES`)
- Used for: the first coupon date of new gilts with a non-standard first coupon (P3, decision #6). Where no notice is listed, the date comes from the DMO's accrued interest in the reference prices (61 gilts), else from the flagged ≤ 45-day rule (36 gilts, all launched after Jul 2017, all short)

| Gilt (coupon, maturity) | First coupon | Notice | Quoted |
|---|---|---|---|
| 0.25% 2025-01-31 | 2022-01-31 | [pr240621.pdf](https://www.dmo.gov.uk/media/jarfujjl/pr240621.pdf) | "Next Interest Payment Date 31 January 2022 - £0.145028 per £100 nominal (Long First Coupon)" |
| 0.125% 2026-01-30 | 2021-01-30 | [prosp260520.pdf](https://www.dmo.gov.uk/media/mnyn5x2f/prosp260520.pdf) | "the first interest payment will be due on 30 January 2021 at the rate of £0.082074 per £100 nominal" |
| 0.375% 2026-10-22 | 2021-10-22 | [prosp230221a.pdf](https://www.dmo.gov.uk/media/cfxlrkdh/prosp230221a.pdf) | "the first interest payment will be due on 22 October 2021 at the rate of £0.239011 per £100 nominal" |
| 3.75% 2027-03-07 | 2024-09-07 | [pr030124.pdf](https://www.dmo.gov.uk/media/oq1jaj5a/pr030124.pdf) | "Next Interest Payment Date 7 September 2024 - £2.451923 per £100 nominal (Long First Coupon)" |
| 0.125% 2028-01-31 | 2021-01-31 | [pr040620b.pdf](https://www.dmo.gov.uk/media/n1ylxsoe/pr040620b.pdf) | "31 January 2021 - £0.079327 per £100 nominal (Long First Coupon)" |
| 1.625% 2028-10-22 | 2018-10-22 | [prosp150318.pdf](https://www.dmo.gov.uk/media/njgorwql/prosp150318.pdf) | "will rank for the payment of the non-standard first coupon on 22 October 2018" |
| 4% 2029-05-22 | 2026-05-22 | [prosp081025b.pdf](https://dmo.gov.uk/media/vfbee0y0/prosp081025b.pdf) | "rank for the payment of the non-standard first coupon on 22 May 2026" |
| 4.375% 2030-03-07 | 2025-09-07 | [prosp280125.pdf](https://www.dmo.gov.uk/media/u41gljwp/prosp280125.pdf) | "which will be due on 7 September 2025 at the rate of £2.876381 per £100 nominal" |
| 4.625% 2030-05-22 | 2026-11-22 | [prosp030926.pdf](https://www.dmo.gov.uk/media/mh2pkmjz/prosp030926.pdf) | "the first interest payment will be due on 22 November 2026 at the rate of £0.904891 per £100 nominal" |
| 4% 2031-10-22 | 2024-10-22 | [prosp210224.pdf](https://www.dmo.gov.uk/media/52dlkrjw/prosp210224.pdf) | "the first interest payment will be due on 22 October 2024 at the rate of £2.579235 per £100 nominal" |
| 1% 2032-01-31 | 2022-01-31 | [prosp241121.pdf](https://www.dmo.gov.uk/media/1jnasbzb/prosp241121.pdf) | "the first interest payment will be due on 31 January 2022 at the rate of £0.163043 per £100 nominal" |
| 4.625% 2032-03-07 | 2027-03-07 | [prosp040826.pdf](https://dmo.gov.uk/media/drzceara/prosp040826.pdf) | "will rank for the payment of the non-standard first coupon on 7 March 2027" |
| 3.25% 2033-01-31 | 2023-07-31 | [prosp030123.pdf](https://dmo.gov.uk:443/media/m2bbq4nr/prosp030123.pdf) | "the first interest payment will be due on 31 July 2023 at the rate of £1.801630 per £100 nominal" |
| 4.25% 2034-07-31 | 2025-01-31 | [pr040624_1.pdf](https://www.dmo.gov.uk/media/flomkmh1/pr040624_1.pdf) | "will pay a long first coupon on 31 January 2025" |
| 4.5% 2035-03-07 | 2025-09-07 | [pr040225.pdf](https://www.dmo.gov.uk/media/0jeppipl/pr040225.pdf) | "will pay a long first coupon on 7 September 2025" |
| 4.75% 2035-10-22 | 2026-04-22 | [prosp030226a.pdf](https://dmo.gov.uk/media/mblmcjem/prosp030226a.pdf) | "will rank for the payment of the non-standard first coupon on 22 April 2026" |
| 1.125% 2039-01-31 | 2022-01-31 | [pr060721.pdf](https://www.dmo.gov.uk/media/2zucvjlv/pr060721.pdf) | "It will pay a long first coupon on 31 January 2022" |
| 0.875% 2046-01-31 | 2021-07-31 | [pr310321a.pdf](https://www.dmo.gov.uk/media/w1ocebci/pr310321a.pdf) | "Next Interest Payment Date 31 July 2021- £0.463655 per £100 nominal (Long First Coupon)" |
| 4.375% 2054-07-31 | 2024-07-31 | [pr160124.pdf](https://www.dmo.gov.uk/media/5oeb504d/pr160124.pdf) | "will pay a long first coupon on 31 July 2024" |

Known issues: notices are matched to gilts on (coupon, maturity); `gilt_terms.build_terms()` fails if any notice matches no gilt or more than one.

## #5 Auction results (D2.1A)

- Publisher: UK Debt Management Office
- Source: [DMO results of gilt operations](https://www.dmo.gov.uk/data/gilt-market/results-of-gilt-operations/), D2.1A "Results of outright gilt auctions"
- Downloaded on: 2026-10-17
- Used for: the auction yield and the auction-level regressors (size, cover, tail)
- Contains: Auction Date, Gilt Name, nominal issued via auction, via PAOF and in total, cash raised, bid-to-cover, average accepted price, yield at the average accepted price, and yield tail (bp). Conventional and index-linked auctions are listed together.
- Location: **data/raw_data/auction_results.xls**

| File | MB | Observed coverage | Rows | SHA-256 |
|---|---:|---|---:|---|
| `auction_results.xls` | 0.28 | 1998-05-20 → 2026-10-14 | 1,244 auctions | `c2fb427586910d7c0f9cb42a5b5667390b77c31ee114c3bec6d2fa24d811ff42` |

Known issues:
- **No ISIN, no amount offered, no lowest accepted price.** ISIN from D2.1E. Highest accepted yield = yield at the average accepted price + tail.
- **915 conventional auctions** (case-insensitive "index-linked" filter). Five auctions of the 0 1/8% 2056 linker (2018–2021) are spelled "Index-**L**inked", so a case-sensitive filter wrongly gives 920.
- **912 conventional auctions** fall in the study window (1 Nov 1998 to 30 Sep 2026). Two are before Nov 1998 (May and Jul 1998) and one is in October 2026. The first auction in the window is 26 May 1999.
- D2.1A note 4: yields before Nov 1998 are given to 2 d.p. only, and tails are whole numbers.
- PAOF (post-auction option) exists only from 1 June 2009.

## #7 SONIA, Bank Rate, OIS curve, daily

- SONIA (IUDSOIA) and Bank Rate (IUDBEDR)
  - Publisher: Bank of England database, [boeapps/database](https://www.bankofengland.co.uk/boeapps/database/)
  - Downloaded on: 2026-10-17
  - Used for: SONIA as the carry cost of buying later and the LDI funding rate. Bank Rate for regime context and for flagging Bank Rate change days, which are confounding events inside an auction window
  - Contains: two title rows, then date ("14 Oct 26" format) and value, newest first
  - Location: **data/raw_data/IUDSOIA.xlsx**, **data/raw_data/IUDBEDR.xlsx**

| File | MB | Observed coverage | Rows | SHA-256 |
|---|---:|---|---:|---|
| `IUDSOIA.xlsx` | 0.11 | 1997-01-02 → 2026-10-14 | 7,526 days | `f79c0f527308b27a7a84a2d97d1292c35f57b0f4dc565d09a350fa8968a377c4` |
| `IUDBEDR.xlsx` | 0.08 | 1997-01-02 → 2026-10-15 | 7,527 days | `06c0fc340ad9645d30556e2099e2d156c9666a6b3ec8387293e3684af1f988ac` |

- OIS curve
  - Publisher: Bank of England, yield curve statistics
  - Source: the BoE OIS curve archive, [oisddata.zip](https://www.bankofengland.co.uk/-/media/boe/files/statistics/yield-curves/oisddata.zip). *Corrected: the earlier entry pointed to the BoE database. The file names are the archive's. Please confirm.*
  - Downloaded on: 2026-10-17
  - Used for: stripping out general rate moves to leave the gilt-specific supply effect (event-study control C), and the swap hedge an LDI manager could use instead of buying the gilt
  - Location: **data/raw_data/ois**

| File | MB | Observed coverage | Rows | SHA-256 |
|---|---:|---|---:|---|
| `ois/OIS daily data_2009 to 2015.xlsx` | 3.34 | 2009-01-02 → 2015-12-31 | 1,768 curve days | `0f52f311e9b875e2c07577ead030ec24359600f8794cf2d4a13b5bb3ac3060d5` |
| `ois/OIS daily data_2016 to 2024.xlsx` | 7.49 | 2016-01-04 → 2024-12-31 | 2,272 curve days | `1a7333e29aa5774d086981eead5493926f711b02fc2664ae9e13cf3a6240d458` |
| `ois/OIS daily data_2025 to present.xlsx` | 1.36 | 2025-01-02 → 2026-09-30 | 442 curve days | `db300785a35b0b54cbf8ebac48999a45e58a46413ee28bf1238cb7ee5c11929f` |

Known issues:
- The OIS archive **ends on 30 Sep 2026**. No current-month OIS file was kept, so control C has no data for the October T+n days of late-September 2026 auctions.
- The long end (to 25y) is present **from Jan 2016**. The 2009–2015 file stops at 5y. The build spec (§2, §7) dates control C from Dec 2021; the data would allow Jan 2016 (open, for Nithin).
- The OIS curve stops at 25y, so longer gilts need extrapolation for control C.
- SONIA was reformed on 23 Apr 2018.

## #8 Syndications, tenders and other gilt operations

- Publisher: UK Debt Management Office, [results of gilt operations](https://www.dmo.gov.uk/data/gilt-market/results-of-gilt-operations/)
- Downloaded on: 2026-10-17
- Syndications (D10A, `syndication_results.xlsx`): used as a control (other supply in the same week); not part of the auction sample
- Tenders (D2.1PROF9, `tender_results.xls`): used as a control; not part of the auction sample. Includes an *Issue Date* column
- Other gilt operations (D2.1PROF7, `other_gilt_operations.xls`): five sections: switch auctions, conversion offers, reverse auctions, **taps** and mini-tenders. Taps and mini-tenders add supply, so they belong with the supply controls (Stage 3)
- Location: **data/raw_data/** (top level)

| File | MB | Observed coverage | Rows | SHA-256 |
|---|---:|---|---:|---|
| `syndication_results.xlsx` | 0.01 | 2005-09-22 → 2026-09-08 | 110 syndications | `3d662feff0f8a847ed0671f7f90f3538765998f44b02e21ae84ccabece18a544` |

| File | MB | Observed coverage | Rows | SHA-256 |
|---|---:|---|---:|---|
| `tender_results.xls` | 0.03 | 2008-10-20 → 2026-10-13 | 94 tenders | `345062f9176b9db3660369750139dd0e7eb8e6b632fcfa4b5c4ade4ff96d627e` |

| File | MB | Observed coverage | Rows | SHA-256 |
|---|---:|---|---:|---|
| `other_gilt_operations.xls` | 0.06 | 1998-04-03 → 2025-04-14 | 46 operations | `165c1a21aca88e1266ce0fa31ea396170d3068ce4fa10609a314315a09d39c62` |

Known issues:
- The earlier entries gave `.xlsx` for tenders and other operations; both files are `.xls`.
- Syndications and tenders include index-linked operations (filter case-insensitively, as for D2.1A).
- Other operations ends on 14 Apr 2025 and is sparse (46 operations over 27 years).

## #9 BoE quantitative tightening (QT) sales

- Publisher: Bank of England, Asset Purchase Facility
- Source: [gilt-sales-time-series.xlsx](https://www.bankofengland.co.uk/-/media/boe/files/markets/asset-purchase-facility/gilt-sales-time-series.xlsx)
- Downloaded on: 2026-10-17
- Used for: the "QT sale that week" variable, matched to the same maturity sector as each auction
- Contains: header on row 1; one row per bond per operation (operation date, settlement date, ISIN, bond, offers, allocation in proceeds and nominal, accepted yield and prices, tail)
- Location: **data/raw_data/boe_qt_sales.xlsx**

| File | MB | Observed coverage | Rows | SHA-256 |
|---|---:|---|---:|---|
| `boe_qt_sales.xlsx` | 0.78 | 2022-11-01 → 2026-09-14 | 1,499 bond lines | `6e93c615a3d57a667dbb3489e379cdba8529844f06cd38b3d990053447a027c0` |

Known issues: dates are on a **trade (operation) date** basis. Rows with zero allocation are bonds that were offered but not sold.

## #10 BoE quantitative easing (QE) purchases

- Publisher: Bank of England, Asset Purchase Facility
- Source: [gilt-purchase-operational-results.xlsx](https://www.bankofengland.co.uk/-/media/boe/files/markets/asset-purchase-facility/gilt-purchase-operational-results.xlsx)
- Downloaded on: 2026-10-17
- Used for: APF purchases in the same week as an auction (demand working against the auction's supply)
- Contains: header on row 1; one row per bond per operation, with proceeds and nominal in separate columns
- Location: **data/raw_data/boe_qe_purchases.XLSX** (upper-case extension, as downloaded)

| File | MB | Observed coverage | Rows | SHA-256 |
|---|---:|---|---:|---|
| `boe_qe_purchases.XLSX` | 1.24 | 2009-03-11 → 2021-12-15 | 7,680 bond lines | `b6b595a21e41b7be765275583f5612b9aab165a1d15865997559189fb2d4ea0d` |

## #11 BoE 2022 financial stability operations

- Publisher: Bank of England
- Long-dated purchases: [long-dated-uk-government-bond-purchase-time-series.xlsx](https://www.bankofengland.co.uk/-/media/boe/files/markets/other-market-operations/long-dated-uk-government-bond-purchase-time-series.xlsx). The exact gilts the Bank bought from 28 Sep to 14 Oct 2022
- Index-linked purchases: [index-linked-gilt-purchase-results.xlsx](https://www.bankofengland.co.uk/-/media/boe/files/markets/other-market-operations/index-linked-gilt-purchase-results.xlsx). The exact linkers bought from 11 to 14 Oct 2022
- Later sales: [finanical-stability-gilt-sales-time-series.xlsx](https://www.bankofengland.co.uk/-/media/boe/files/markets/asset-purchase-facility/finanical-stability-gilt-sales-time-series.xlsx) (the BoE's spelling). Sales of those holdings, 29 Nov 2022 to 12 Jan 2023
- Downloaded on: 2026-10-17
- Used for: marking the LDI-crisis window precisely
- Location: **data/raw_data/2022_crisis_operations**

| File | MB | Observed coverage | Rows | SHA-256 |
|---|---:|---|---:|---|
| `2022_crisis_operations/finanical-stability-gilt-sales-time-series.XLSX` | 0.50 | 2022-11-29 → 2023-01-12 | 360 bond lines | `df4403edfca0cb0b29df145689b8a02fc59294231bf3f4330e93ae67cb5f2bcc` |
| `2022_crisis_operations/index-linked-gilt-purchase-results.XLSX` | 0.02 | 2022-10-11 → 2022-10-14 | 92 bond lines | `5d406edfefae00a22430dfd07990671b6a83d6110ba7bdd8e4d2ff06e40bbb9f` |
| `2022_crisis_operations/long-dated-uk-government-bond-purchase-time-series.XLSX` | 0.03 | 2022-09-28 → 2022-10-14 | 241 bond lines | `42d50bee228d164434cf52b427554fb6edd1dc9026393b27acb17be7917fb574` |

## #12 DMO turnover by maturity band

- Publisher: UK Debt Management Office
- Source: [DMO turnover data](https://www.dmo.gov.uk/data/gilt-market/turnover-data/)
- Downloaded on: 2026-10-17
- Used for: quarterly trading volume by sector, as a liquidity proxy. Lower turnover should make inventory harder to offload and concessions bigger. Quarterly, so only usable as a slow-moving control
- Contains: one sheet per year (2001–2026) plus Notes. One block per quarter with customer, professional and combined turnover by band (0–12m, 1–3y, 3–5y, 5–7y, 7–10y, 10–15y, 15+y, index-linked, and strips in early years)
- Location: **data/raw_data/turnover_maturity_band.xlsx**

| File | MB | Observed coverage | Rows | SHA-256 |
|---|---:|---|---:|---|
| `turnover_maturity_band.xlsx` | 0.20 | 2001-01-01 → 2026-06-30 | 102 quarters | `5d1ee506cbf424a2d9d8ea756a86f97c2e383fa15209c331d1ed39f110791179` |

Known issues: turnover is based on market values reported by GEMMs. The bands add up exactly to the DMO auction buckets: short < 7y = 0–7y bands; medium = 7–10y + 10–15y; long = 15+y.

## Derived from software, not downloaded

- **UK business-day calendar (checklist #17):** Python `holidays` 0.106, England. It includes one-off closures (31 Dec 1999, 3 Jun 2002, 29 Apr 2011, 5 Jun 2012, 3 Jun 2022, 19 Sep 2022 State Funeral, 8 May 2023 Coronation) and moved bank holidays (`tests/test_stage0.py`). Version pinned in `requirements.txt`.

## Not yet downloaded (checklist tiers 2–3)

#3 per-gilt prices after July 2017 (Tradeweb or Bath library terminals); #13 MPC announcement dates; #14 UK data-release dates; #15 fiscal events; #16 US Treasury yields (FRED DGS10, DGS30); #18 gilt holdings by sector.
