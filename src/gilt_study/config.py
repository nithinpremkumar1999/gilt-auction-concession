"""Study parameters that come from logged decisions (build spec §10). Change them only with a new
decision-log entry."""
import datetime as dt

# Decision #7 (19 Oct 2026): the auction sample starts on 1 November 1998, when gilt accrued
# interest moved to actual/actual (from actual/365) and prices to decimals (from 32nds). Earlier
# 1998 auctions may follow the old conventions, and no DMO yields exist to test them.
# (Replaces the earlier choice of 1 Jan 2000, made in chat before Stage 0.)
STUDY_START = dt.date(1998, 11, 1)

# Spec §2: auctions up to and including September 2026.
STUDY_END = dt.date(2026, 9, 30)

# Spec §4 / decision #6: the window in which the pricer acceptance test is possible. The DMO
# published no conventional gilt yields before 25 Nov 2002; the reference-price series ends 21 Jul 2017.
PRICER_TEST_WINDOW = (dt.date(2002, 11, 25), dt.date(2017, 7, 21))

# Curve panel coverage (Stage 2). Starts before the sample so that windows reaching back from the
# first auctions (M1b uses T-25) have curves; ends with the last BoE curve date in raw_data.
# A data-range setting, not a methodological one: it does not change any measure.
CURVE_PANEL_START = dt.date(1998, 1, 1)

# Decision #12 (20 Oct 2026): the auction panel records years of cash flows beyond the curve's last
# maturity; the robustness check drops auctions with more than this many years beyond.
MAX_YEARS_BEYOND_CURVE = 5.0
