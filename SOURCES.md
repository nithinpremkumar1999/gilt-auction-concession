# Data Sources:

## BoE Nominal Yield Curve, daily (archive)

- GLC Nominal:
  - Coverage: 1979 to 30 September 2026
  - Publisher: Bank of England, yield curve statistics
  - Source: [www.bankofengland.co.uk/-/media/boe/files/statistics/yield-curves/glcnominalddata.zip](https://www.bankofengland.co.uk/-/media/boe/files/statistics/yield-curves/glcnominalddata.zip)
  - Downloaded on: 2026-10-17
  - Used for: price each auctioned gilt off the T-1 spot curve to get its model yield (concession = auction yield − model yield), and track the curve at the auction maturity from T-5 to T+5 for the event study
  - Contains:
    - UK instantaneous nominal forward curve (short end)
    - UK instantaneous nominal forward curve
    - UK nominal spot curve (short end)
    - UK nominal spot curve
  - Location: **data/raw_data/glc_nominal**
- Latest Yield Curve:
  - Coverage: 01 October 2026 to 15 October 2026
  - Publisher: Bank of England, yield curve statistics
  - Source: [www.bankofengland.co.uk/-/media/boe/files/statistics/yield-curves/latest-yield-curve-data.zip](https://www.bankofengland.co.uk/-/media/boe/files/statistics/yield-curves/latest-yield-curve-data.zip)
  - Downloaded on: 2026-10-17
  - Used for: price each auctioned gilt off the T-1 spot curve to get its model yield (concession = auction yield − model yield), and track the curve at the auction maturity from T-5 to T+5 for the event study
  - Contains:
    - UK instantaneous nominal forward curve (short end)
    - UK instantaneous nominal forward curve
    - UK nominal spot curve (short end)
    - UK nominal spot curve
  - Location: **data/raw_data/latest_yield_curve**

## DMO Reference Prices, every gilt, every day

- Coverage: 1998 to 21 July 2017
- Publisher: United Kingdom, Debt Management Office
- Source: [www.dmo.gov.uk/data/gilt-market/historical-prices-and-yields](https://www.dmo.gov.uk/data/gilt-market/historical-prices-and-yields/)
- Downloaded on: 2026-10-17
- Used for: watching the *auctioned bond itself* and its neighbours cheapen and recover, instead of the smoothed curve
- Contains:
  - [year]-gilt-reference-prices.xls
- Location: **data/raw_data/dmo_ref_prices**

## Gilt Static

- Coverage: 1997 to 15 October 2026
- Publisher: United Kingdom, Debt Management Office
- Source: [www.dmo.gov.uk/data/gilt-market/gilts-in-issue](https://www.dmo.gov.uk/data/gilt-market/gilts-in-issue/)
- Downloaded on: 2026-10-17
- Gilts in issue (D1A)
  - Used for: building cash flows
- Redeemed gilts (D1C)
  - Used for: fill in the gilts auctioned in 1998–2015 that aren’t in D1A anymore
- Issuance history (D2.1E)
  - Used for: tells whether an auction was a new issue or a reopening, and how much of the gilt was already outstanding
- Location: **data/raw_data/gilt_static**

## Auction Results

- Coverage: April 1998 to October 2026
- Publisher: United Kingdom, Debt Management Office
- Source: [www.dmo.gov.uk/data/gilt-market/results-of-gilt-operations](https://www.dmo.gov.uk/data/gilt-market/results-of-gilt-operations/)
- Downloaded on: 2026-10-17
- Used for: the auction yield and the auction-level regressors (size, cover, tail)
- Location: **data/raw_data/auction_results.xls**

## SONIA, Bank Rate, OIS Curve, daily

- SONIA (IUDSOIA)
  ---------------

  - Coverage: 1997 to 14 October 2026
  - Publisher: Bank of England
  - Source: [www.bankofengland.co.uk/boeapps/database](https://www.bankofengland.co.uk/boeapps/database/)
  - Downloaded on: 2026-10-17
  - Used for: carry cost of buying later, and also the LDI funding rate
  - Location: **data/raw_data/IUDSOIA.xlsx**
- Bank Rate (IUDBEDR)
  -------------------

  - Coverage: 1997 to 14 October 2026
  - Publisher: Bank of England
  - Source: [www.bankofengland.co.uk/boeapps/database](https://www.bankofengland.co.uk/boeapps/database/)
  - Downloaded on: 2026-10-17
  - Used for: regime context and marks the days Bank Rate changed, which are confounding events in an auction window
  - Location: **data/raw_data/IUDBEDR.xlsx**
- OIS Curve
  ---------

  - Coverage: 2009 to 14 October 2026
  - Publisher: Bank of England
  - Source: [www.bankofengland.co.uk/boeapps/database](https://www.bankofengland.co.uk/boeapps/database/)
  - Downloaded on: 2026-10-17
  - Used for: striping out general rate moves and leaves the gilt-specific supply effect, which makes it a candidate event-study control. It’s also the swap hedge an LDI manager could use instead of buying the gilt
  - Location: **data/raw_data/ois**

## Syndications

- Coverage: September 2005 to September 2026
- Publisher: United Kingdom, Debt Management Office
- Source: [www.dmo.gov.uk/data/gilt-market/results-of-gilt-operations](https://www.dmo.gov.uk/data/gilt-market/results-of-gilt-operations/)
- Downloaded on: 2026-10-17
- Used for: control, or events in their own right
- Location: **data/raw_data/syndication_results.xlsx**

## Tenders

- Coverage: October 2008 to October 2026
- Publisher: United Kingdom, Debt Management Office
- Source: [www.dmo.gov.uk/data/gilt-market/results-of-gilt-operations](https://www.dmo.gov.uk/data/gilt-market/results-of-gilt-operations/)
- Downloaded on: 2026-10-17
- Used for: extra supply in the same week (a control), but not part of the auction sample
- Location: **data/raw_data/tender_results.xlsx**

## Other Gilt Opertations

- Coverage: 1998 to October 2026
- Publisher: United Kingdom, Debt Management Office
- Source: [www.dmo.gov.uk/data/gilt-market/results-of-gilt-operations](https://www.dmo.gov.uk/data/gilt-market/results-of-gilt-operations/)
- Downloaded on: 2026-10-17
- Used for:
- Location: **data/raw_data/other_gilt_operations.xlsx**

## BoE Quantitative Tightening Sales

- Coverage: November 2022 to September 2026
- Publisher: Bank of England
- Source: [www.bankofengland.co.uk/-/media/boe/files/markets/asset-purchase-facility/gilt-sales-time-series.xlsx](https://www.bankofengland.co.uk/-/media/boe/files/markets/asset-purchase-facility/gilt-sales-time-series.xlsx)
- Downloaded on: 2026-10-17
- Used for: builds the “QT sale that week” variable, and match QT sales to the same maturity sector as each auction
- Location: **data/raw_data/boe_qt_sales.xlsx**

## BoE Quantitative Easening Purchases

- Coverage: March 2009 to December 2021
- Publisher: Bank of England
- Source: [www.bankofengland.co.uk/-/media/boe/files/markets/asset-purchase-facility/gilt-purchase-operational-results.xlsx](https://www.bankofengland.co.uk/-/media/boe/files/markets/asset-purchase-facility/gilt-purchase-operational-results.xlsx)
- Downloaded on: 2026-10-17
- Used for: APF purchase
- Location: **data/raw_data/boe_qe_purchases.xlsx**

## 2022 Crisis Operations

- Coverage: September 2022 to January 2023
- Publisher: Bank of England
- Long-Dated Purchases:
  - Source: [www.bankofengland.co.uk/-/media/boe/files/markets/other-market-operations/long-dated-uk-government-bond-purchase-time-series.xlsx](https://www.bankofengland.co.uk/-/media/boe/files/markets/other-market-operations/long-dated-uk-government-bond-purchase-time-series.xlsx)
  - Used for: exact gilts the Bank bought from 28 September to 14 October 2022
- Index-Linked Purchases:
  - Source: [www.bankofengland.co.uk/-/media/boe/files/markets/other-market-operations/index-linked-gilt-purchase-results.xlsx](https://www.bankofengland.co.uk/-/media/boe/files/markets/other-market-operations/index-linked-gilt-purchase-results.xlsx)
  - Used for: exact gilts the Bank bought from 28 September to 14 October 2022
- Later Sales:
  - Sources: [www.bankofengland.co.uk/-/media/boe/files/markets/asset-purchase-facility/finanical-stability-gilt-sales-time-series.xlsx](https://www.bankofengland.co.uk/-/media/boe/files/markets/asset-purchase-facility/finanical-stability-gilt-sales-time-series.xlsx)
  - Used for: later sales of those holdings
- Location: **data/raw_data/2022_crisis_operations**

## DMO Turnover by Maturity band

- Coverage: 2001 to 2026
- Publisher: United Kingdom, Debt Management Office
- Source: [www.dmo.gov.uk/data/gilt-market/turnover-data](https://www.dmo.gov.uk/data/gilt-market/turnover-data/)
- Downloaded on: 2026-10-17
- Used for: Quarterly trading volume by sector, a liquidity proxy. Lower turnover should make inventory harder to offload and concessions bigger; it’s quarterly, so only usable as a slow-moving control
- Location: **data/raw_data/turnover_maturity_band.xlsx**
