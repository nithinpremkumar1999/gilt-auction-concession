"""Study parameters that come from logged decisions (build spec §10). Change them only with a new
decision-log entry."""
import datetime as dt

# Decision #7: the study starts with auctions dated 1 January 2000. Gilt conventions changed on
# 1 Nov 1998 (actual/365 -> actual/actual accrued, 1/32nds -> decimal prices) and D2.1A yields
# before Nov 1998 are only to 2 d.p. Raw data from 1998 is kept but not analysed.
STUDY_START = dt.date(2000, 1, 1)

# Spec §2: auctions up to and including September 2026.
STUDY_END = dt.date(2026, 9, 30)
