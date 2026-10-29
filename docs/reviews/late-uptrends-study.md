# Late broad uptrends: how long, the Cooling arrows, and longs late in the run (declared 29 October 2026, before running)

Question from the owner (29 October 2026), after the Chart view's Market heat: the market itself matters as much as BTC. "Once we have so many coins in an uptrend, how long that uptrend lasts before things start to roll over." The test of a Cooling arrow should be "does the arrow that shows a cooling off precede a reduction of coins that are on an uptrend?" And "the relationship between the greed and traders that are long and the danger of opening a long position on any coin after, let's say, 60 days ... When everything is in an uptrend and has been going on for a while, plus the greed is high, plus everybody's long, I don't think there is much juice left before things start to roll over."

This describes the past and runs outside the production server. Everything below is fixed before any outcome is computed. Only counts were looked at (quoted under "Known before running"). Unless a result clears its bar in "Decision rules", it reads **context, not a signal**.

Code: `backend/research/late_uptrends.py` (tests `backend/tests/test_late_uptrends.py`), run from `backend/` as `python -m research.late_uptrends --rows ROWS --live LIVE`. ROWS comes from `node research/export_page_rows.mjs` (the page's own code turning saved `/api/market-history` and `/api/market-history/wallets` responses into daily rows); LIVE is a copy of the server's `market_history_live.json`.

## Data

- **The page's daily rows**, 1 May 2021 to 27 October 2026, 2,006 days: the Uptrend share (Uptrend plus Overheated; Overheated is 0 on every day), the Downtrend and Basing shares (Building a base, Cooling off, Washed out), Fear & Greed (alternative.me) and the profitable traders' share long (from 1 October 2025). Built from `seeds/market_history_seed.json`, the server's daily record to 27 October 2026 and the wallet seeds, exactly as the page reads them.
- **The typical coin** ("any coin"): the median simple return of the coins other than BTC (at least 20), as on the page and in the earlier breadth studies (`market_history.make_alt_ret`): the seed's typical-coin paths (5-day steps to 60 days) for days to 28 January 2026, then the record's per-coin closes. So the typical coin's change is known at 5, 10, ... 60 days, not over any span.

## Known before running

- The risk-on cycles study (docs/reviews/risk-on-cycles-study.md): the runs to 25 September 2026 with their lengths and peaks, survival (of the 5 runs that reached 60 days, all lasted 30 more and 2 lasted 60 more), and the typical coin from start to end and from peak to end. The page's charts of the Uptrend share, Fear & Greed and Market heat with its arrows have been seen against BTC, including October 2026 (82% in uptrend on 27 September, 42% on 27 October). So every in-sample number below is description; the out-of-sample run is the only clean test.
- Counts (`--shape`, no outcome): 14 runs, the first under way on 1 May 2021 (start unknown, so not counted); the 13 counted runs start and end exactly as in the risk-on cycles study, plus 2026-03-20 to 2026-08-15 (148 days) and 2026-08-20 to 2026-10-22 (63 days). 6 runs reached day 60; 3 had a day at day 60 or later with Fear & Greed at 70 or more, and 8 had such a day before day 60. 11 runs had a roll-over (below). Market heat recomputed here gives the page's 12 cooling and 29 lifting turns; 10 cooling and 29 lifting turns have 30 days after them. The traders' reading covers 392 days.

## Definitions

- **Broad uptrend** (a run): the page's point-in-time rule. It starts on the first day with 55% or more of coins in uptrend and ends when the share has been under 55% for 5 days in a row; dips of 1 to 4 days stay inside. Its end is the first day of those 5 (as in the risk-on cycles study). **Age** on a day: days since the start (the start is day 0).
- **Roll-over**: the first day of a run with the share 20 points or more under the run's highest reading so far (20 points is the market-breadth study's fade). Known on the day. A run can end without one.
- **Greed**: Fear & Greed at 70 or more, the engine's own line (its Not greedy check fails there). 80 is reported, not used.
- **Crowd long**: the profitable traders' share long at 86% or more (the positioning study's extreme-long line). From October 2025 only.
- **Market heat and its turns**: as in docs/reviews/market-heat.md (frontend/src/utils/marketHeat.js at c159b51).
- **Outcomes** from a day's close: the change in the Uptrend share over 14 and 30 days (points); the typical coin over 30 and 60 days; the typical coin's lowest point within 60 days (the lowest of its 5-day-step values, the low of the typical path, not the median of each coin's low); BTC over 30 and 60 days (reported). A window past 27 October 2026 is censored and not counted.

## Part 1. How long until a broad uptrend rolls over (description)

Per run: start, end, length; the peak share and the age it was first reached; the roll-over day and its age (or none before the end); Fear & Greed on the peak day, its highest in the run and the age of the first greedy day; from the roll-over day, the outcomes above; from the peak day (known only afterwards), the typical coin over 30 and 60 days; and where the coins went: the Uptrend, Downtrend and Basing shares on the peak day and 30 days after the roll-over. Summary: the age at the peak and at the roll-over (median, quartiles), roll-overs before day 30, between 30 and 59, at 60 or later. No verdict.

## Part 2. Do Cooling arrows come before coins leave their uptrend?

- **Events**: cooling turns with 30 days after them. Deciding outcome: the Uptrend share's change over the next 30 days.
- **Comparison**: for each turn, the days whose share was within 10 points of the turn day's, with 30 days after them, and not a cooling turn or within 30 days after one. Each turn's excess = its change minus the median change of its comparison days.
- Reported, never deciding: the 14-day change, the typical coin over 30 days, whether the run had already rolled over at the arrow, and whether it rolled over within 30 days.
- **Lifting turns**: the mirror (a rise in the share), same rules.

## Part 3. Longs late in a broad uptrend, with greed and the crowd long

- **Cells**: days inside a run with the share at 55% or more, by age (early: under 60; late: 60 or more) and greed (Fear & Greed 70 or more, or not): early, early and greedy, late, late and greedy.
- Per cell over all days: the outcomes (days overlap: description) and the days with the crowd long.
- **Per run** (the unit of evidence): the first day of each cell, with its outcomes; and the first late, greedy day with the crowd long, where the traders' reading exists. Paired: in each run with both, the typical coin over 60 days from the first late, greedy day against the first early, greedy day.

## Decision rules

- **Part 2** (cooling): a verdict ("Cooling arrows were followed by more coins leaving their uptrend than days at the same share") needs all of: at least 8 turns with 30 days; the median excess at least 10 points of share lower; the turns' median change at or below the 10th percentile of 10,000 random draws (each draw takes one comparison day per turn); a negative median excess in both the first and the second half of the turns by date. Lifting: the mirror (10 points higher, at or above the 90th percentile, positive in both halves). Otherwise "in k of n", context, not a signal.
- **Part 3**: a verdict ("longs late in a greedy broad uptrend did worse than early ones") needs at least 8 paired runs, the late, greedy day's typical coin over 60 days lower than the early, greedy day's in at least 75% of them, and the median gap at least 10 points. The record has 3 runs with a late, greedy day, so in sample Part 3 is a case list, **too few to read**, stated before running.
- **Part 1** gives no verdict.

## Out of sample

From 30 October 2026, the same code on the page's new days: new turns count toward Part 2's out-of-sample verdict (rerun when each has 30 days), new runs add Part 1 and Part 3 cases.

## Limits

- About 13 runs over two market cycles plus 2026; runs in one cycle are not independent.
- Today's coin list (coins that died are missing, so the typical coin reads better than it was), Binance spot closes, fewer coins early on (40 in May 2021, 145 now).
- Market heat contains the Uptrend share, so a cooling turn often comes after the share has already fallen; Part 2 asks whether more fall followed.
- One Fear & Greed series for the whole market; the traders' reading covers one year (two runs).
- The 2026-08-20 run's start rests on one coin (risk-on cycles study): without that coin it would continue the 2026-03-20 run.
