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

## Result (run 29 October 2026, after the rules above were committed at cdf0c22)

`python -m research.late_uptrends` on the page's rows to 27 October 2026. Every in-sample number is description (the series had been seen on the page); the out-of-sample run is the only clean test.

### Part 1. How long until a broad uptrend rolls over

| Start | Days | Peak share (day) | Roll-over: day (share) | Fear & Greed high (day) | Typical coin from roll-over, 30 / 60 days | 30 days after roll-over: Uptrend / Basing / Downtrend |
|---|---:|---|---|---|---|---|
| 1 May 2021 (start unknown) | 13 | 62% (0) | none | 73 (8) | — | — |
| 6 Nov 2021 | 41 | 84% (18) | 41 (54%) | 84 (3) | +1% / -17% | 54% / 44% / 2% |
| 23 Dec 2021 | 11 | 71% (4) | 12 (50%) | 41 (1) | -34% / -38% | 17% / 29% / 54% |
| 17 Jan 2022 | 8 | 65% (1) | 8 (29%) | 24 (1) | -8% / +8% | 17% / 83% / 0% |
| 2 Apr 2022 | 19 | 66% (5) | none | 53 (3) | — | — |
| 20 Jul 2022 | 143 | 98% (20) | 123 (76%) | 47 (25) | -3% / +17% | 42% / 58% / 0% |
| 13 Jan 2023 | 53 | 86% (16) | 50 (66%) | 62 (34) | 0% / -6% | 25% / 75% / 0% |
| 22 Oct 2023 | 101 | 97% (27) | 88 (77%) | 76 (79) | +10% / +36% | 32% / 68% / 0% |
| 26 Feb 2024 | 30 | 79% (19) | 29 (59%) | 90 (8) | -30% / -24% | 7% / 43% / 51% |
| 25 Sep 2024 | 119 | 98% (55) | 109 (77%) | 94 (58) | -34% / -53% | 9% / 8% / 83% |
| 15 May 2025 | 6 | 58% (2) | none | 78 (8) | — | — |
| 11 Jul 2025 | 96 | 98% (15) | 95 (56%) | 79 (1) | -22% / -37% | 12% / 86% / 2% |
| 20 Mar 2026 | 148 | 96% (56) | 102 (72%) | 50 (46) | -5% / +12% | 62% / 38% / 1% |
| 20 Aug 2026 | 63 | 86% (41) | 61 (63%) | 78 (33) | censored | censored |

- The share peaked early: first touch at a median of day 18 (quartiles 4.5 to 34) over the 13 counted runs.
- The roll-over came late: 11 runs had one, at a median of day 61 (quartiles 29 to 102); 3 before day 30, 2 between 30 and 59, 6 at day 60 or later. 2 short runs ended without one.
- The 6 runs that reached day 60 rolled over on days 61, 88, 95, 102, 109 and 123: 1 to 63 days after day 60.
- From the roll-over day the typical coin's next 30 days were close to an ordinary day's (median -6.4% over the 10 runs with 30 days, against -6.3% on every day; 60 days: -11.5% against -12.0%). By the roll-over, much of the fall had usually happened.
- Where the coins went: 30 days after the roll-over most had moved into the Basing states (Cooling off, Building a base); into Downtrend in 3 of 10 (December 2021, March 2024, January 2025).

### Part 2. Do Cooling arrows come before coins leave their uptrend?

| Arrow | Run day | Share | Share change, 30 days | Days at the same share | Typical coin 30 / 60 days |
|---|---:|---:|---:|---:|---|
| 17 Nov 2021 | 11 | 78% | -24 | -8 | -29% / -27% |
| 23 Mar 2024 | 26 | 71% | -63 | -13 | -19% / -18% |
| 27 Nov 2024 | 63 | 94% | -4 | -7 | -15% / -27% |
| 23 Dec 2024 | 89 | 91% | -37 | -4 | -13% / -39% |
| 10 Jan 2025 | 107 | 85% | -70 | -4 | -36% / -53% |
| 2 Aug 2025 | 22 | 97% | -9 | -7 | 0% / +1% |
| 20 Aug 2025 | 40 | 97% | -7 | -7 | -1% / -33% |
| 30 Aug 2025 | 50 | 87% | -1 | -4 | -8% / -29% |
| 11 Oct 2025 | 92 | 86% | -71 | -4 | -1% / -27% |
| 16 May 2026 | 57 | 96% | -10 | -8 | -18% / -24% |
| 8 Oct 2026 | 49 | 84% | censored | -4 | censored |
| 17 Oct 2026 | 58 | 73% | censored | -12 | censored |

- **Cooling: bar not met.** 10 arrows with 30 days. The share fell a median 16.7 points in the 30 days after, and further than days at the same share after 7 of 10; median excess -9.3 points against the bar's -10. Random draws: 5.7% at or below (inside the 10% bar); halves -33.0 and -2.0 (both negative). One check short, so **context, not a signal**: "in 7 of 10".
- Every arrow came before the run's roll-over; the roll-over followed within 30 days after 5 of 10.
- The typical coin was lower 30 days after 9 of the 10 arrows and flat after one (median -14%, every day -6.3%); 60 days after, lower after 9 of 10 (median -27%, every day -12%). Reported, not deciding: the comparison was declared on the share, not on prices.
- After 5 arrows the share hardly moved in 30 days (November 2024, three in August 2025, May 2026) while over 60 days the typical coin fell 24-33% after four of them: the Uptrend label trailed prices.
- **Lifting: bar met in sample.** 29 arrows; the share rose a median 16.9 points in 30 days, 18.5 more than days at the same share; random draws 100% at or below; halves +18.9 and +14.6. The typical coin over 30 days: median -1%, 48% up. As declared, this is description until new lifting arrows from 30 October 2026 meet the same bar. The arrow comes after the share has started rising, so much of this is the share's own momentum.

### Part 3. Longs late in a broad uptrend, with greed and the crowd long

| Days in a broad uptrend | Days | Typical coin 30 days (share up) | 60 days (share up) | Lowest within 60 days | Share change, 30 days |
|---|---:|---|---|---|---|
| Early, not greedy | 369 | -7% (33%) | -18% (24%) | -22% | -6 |
| Early, greedy | 171 | 0% (50%) | -1% (47%) | -12% | -3 |
| Late, not greedy | 235 | -9% (24%) | -12% (45%) | -18% | -16 |
| Late, greedy | 73 | -20% (0%) | -42% (18%) | -44% | -38 |
| Every day | 1,976 | -6% (35%) | -12% (36%) | -20% | 0 |

Days overlap; the late, greedy days come from 3 runs. Per run:

| Run | First early, greedy day | Typical coin 30 / 60 days | First late, greedy day | Typical coin 30 / 60 days |
|---|---|---|---|---|
| 22 Oct 2023 | 25 Oct 2023, day 3, F&G 72, 77% | +22% / +50% | 21 Dec 2023, day 60, F&G 70, 92% | -7% / +9% |
| 25 Sep 2024 | 16 Oct 2024, day 21, F&G 73, 83% | +10% / +60% | 24 Nov 2024, day 60, F&G 80, 95% | -8% / -24% |
| 11 Jul 2025 | 11 Jul 2025, day 0, F&G 71, 56% | +7% / +2% | 4 Oct 2025, day 85, F&G 71, 88%, crowd long | -38% / -46% |

- **Too few to read** (3 paired runs; the bar needs 8), as stated before running. In all 3 the late, greedy day's typical coin over 60 days was below the early, greedy day's (median gap -48 points). Context, not a signal.
- The crowd long (86% or more) met a late, greedy day once: 4 October 2025.
- The latest run (from 20 August 2026) reached day 60 on 19 October with Fear & Greed at 59, under the engine's line, so it has no late, greedy day; Fear & Greed's high was 78 on day 33 and the share's peak 86% on day 41 (30 September). Cooling arrows on days 49 and 58, roll-over on day 61 (20 October), end on day 63 (22 October). Its outcomes are censored.

### Reading (in sample; context, not a signal)

- Breadth tops early and rolls over late. In the 13 broad uptrends since 2021, the share of coins in uptrend reached its high at a median of day 18; the 20-point roll-over came at a median of day 61. Runs that passed day 60 rolled over 1 to 63 days later.
- The Uptrend share is slow. Prices of the typical coin turned down before the share did: after the Cooling arrows the typical coin fell in the next 30 days after 9 of 10, while the share fell much after only half. Waiting for the share to drop 20 points came late: from that day, the typical coin did about as well as on any day.
- Greed early in a broad uptrend was not a warning in this record (typical coin flat over 30 and 60 days); greed after day 60 came before the worst outcomes in the table, in all three runs that had it. Three runs is too few to call it a rule.

## Exploratory: age as a scale, not a line (owner, 29 October 2026)

Owner: "60 days was just an example. Don't be so strict with the rule." So, after the declared run and outside it (no verdict, description only): days in a broad uptrend (share 55% or more, the first run left out) by the run's age, with greed counted at any point in the last 30 days (Fear & Greed 70 or more). Typical coin's median change, with the share of days up; runs that contribute days.

| Run age (days) | Greed in the last 30 days | Days (runs) | Typical coin 30 days (up) | 60 days (up) | Share change, 30 days |
|---|---|---:|---|---|---:|
| 0-14 | no | 98 (9) | -8% (41%) | -6% (41%) | 0 |
| 0-14 | yes | 77 (6) | -1% (47%) | -8% (38%) | -1 |
| 15-29 | no | 55 (5) | -9% (40%) | -15% (15%) | -3 |
| 15-29 | yes | 84 (6) | 0% (46%) | -13% (38%) | -8 |
| 30-44 | no | 46 (4) | -9% (9%) | -18% (4%) | -12 |
| 30-44 | yes | 70 (5) | +5% (55%) | +4% (53%) | -5 |
| 45-59 | no | 38 (3) | -13% (5%) | -24% (5%) | -11 |
| 45-59 | yes | 60 (4) | 0% (44%) | -3% (38%) | -2 |
| 60-89 | no | 81 (3) | -15% (11%) | -21% (0%) | -14 |
| 60-89 | yes | 72 (4) | -15% (9%) | -30% (36%) | -30 |
| 90+ | no | 109 (2) | -8% (27%) | +12% (74%) | -13 |
| 90+ | yes | 46 (3) | -22% (24%) | -42% (24%) | -45 |

Every day: -6.3% over 30 days, -12% over 60.

- With recent greed, the typical coin's next 30 days were about flat through a run's first two months and turned down after: in each of the 3 runs with outcomes, the median from day 60 on was below the median before (October 2023 run +16% to -2%, September 2024 run +37% to -25%, July 2025 run -4% to -31%); over 60 days in 2 of 3 (the October 2023 run's later days were followed by the February-March 2024 rally). The August 2026 run had 3 such days, without outcomes yet.
- Broad uptrends without greed were weak at most ages (mostly the 2022 bear-market rallies and the 2026 spring run, when Fear & Greed stayed low).
- The change shows between the 45-59 and 60-89 rows, but it rests on 3 runs; with this few, no day can be named as the line. Context, not a signal.
- In the Chart view (same day), the fixed day-60 mark went: the headline reads the run's day against how many past runs ended sooner, and the Greed mark lights for a reading of 70 or more in the last 30 days, showing that high.
