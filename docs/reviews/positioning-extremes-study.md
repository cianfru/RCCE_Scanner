# Profitable traders at extremes: what followed? (declared 29 October 2026, before running)

Question from the owner (29 October 2026), with HyperLens's profitable traders at 19% long and 81% short of 1,161 positions: "how many times in the past we had profitable traders like today ... historically positions that were quite extreme, like today, where everybody's short, do they continue? Does the price continue? ... I don't know if this means that the price is getting closer to a bottom." And the other side: on 8 May 2026 they were 90% long, on 16 May 55%, and then the market fell.

This describes the past and runs outside the production server. Everything below is fixed before any analysis code runs on the data. Only the data's shape and counts were looked at (quoted under "Known before running"). Unless a result clears the bar in "Decision rule", it is read as **context, not a signal**.

Code: `backend/research/positioning_extremes.py`, run from `backend/` as `python -m research.positioning_extremes --live PATH` (PATH: a copy of the server's `market_history_live.json`). Tests: `backend/tests/test_positioning_extremes.py`.

## Data

- **Positioning.** `seeds/crowd_share_seed.json` (`backtest.crowd_history_rebuild`, built 29 October 2026): the profitable traders' share of positions long at each 00:00 UTC close, HyperLens's daily pick (the best 600 by 30-day return) applied to the wallet rebuild's sample. 1 October 2025 to 28 October 2026, 393 days, none missing, one method throughout. The rebuilt values are used as they are: the page moves them to the recorded level by a constant, which changes no rank or percentile. Method and limits: docs/reviews/wallet-history.md.
- **Price.** BTC's daily close as the market history page draws it (Binance): `seeds/market_history_seed.json` from 19 July 2019, then the server's daily record (`market_history_live.json`), to the newest close in the copy.

## Known before running

- The owner has seen the panel against the price on the page.
- While checking the rebuild (29 October 2026) two correlations were computed over the rebuilt year: the share long against BTC's change over the previous 30 days (0.77) and over the next 30 days (-0.05). The series' broad relation to price has been seen, so the in-sample numbers below are description; the out-of-sample run is the only clean test.
- Counts (shape only). Percentiles of the daily share long: 5th 25.5%, 10th 30.0%, median 59.2%, 90th 86.0%, 95th 88.1%. With the rules below: extreme short on 40 days in 3 episodes (from 6 November 2025, 3 February 2026 and 25 October 2026, the last still running); extreme long on 40 days in 6 episodes (from 1 October 2025, the series' first day, then 4 January, 28 April, 5 July, 19 August and 12 September 2026). As short as the newest rebuilt reading (28.5% on 28 October 2026): 4 episodes.

## Definitions

- **Reading:** the share of positions long at a close.
- **Extreme short:** a reading at or below 30.0% (the rebuilt year's 10th percentile). **Extreme long:** at or above 86.0% (the 90th). Fixed numbers from here on.
- **Episode:** days beyond the line, a return inside it for up to 14 days still counting as the same episode. Outcomes are measured from the episode's first day. An episode that starts on the series' first day is reported but not counted (its real start is unknown).
- Reported, never deciding: the episode's most extreme day (known only afterwards), the day the reading came back inside the line, the 5th and 95th percentile lines, and "as short as 28 October" (28.5%).

## Outcomes (BTC, close to close)

- The change over the next 7, 30 and 60 days from the episode's first close.
- Within the next 60 days: the largest fall and the largest rise from that close, and the day each came.
- A window reaching past the newest close is censored: shown as far as it goes, never counted.

## Comparisons

1. **Every day** of the window (1 October 2025 to the newest close with a complete outcome): the median, quartiles and share of rises of the same change.
2. **Same past month:** the window's days whose BTC change over the previous 30 days falls in the same fifth of the window's days as the episode start, with a reading inside both lines: their median change. The reading follows the month that produced it; this asks whether it adds anything to that month.
3. **Seven years, price only:** from 19 July 2019, every run of days whose previous-30-day BTC change was at or below the episode start's (extreme short; at or above for extreme long), each run one case from its first day (the same 14-day rule), with its 7, 30 and 60-day changes: what followed a month like this one.

## Decision rule

A verdict ("extreme-short readings were followed by BTC rises beyond what the past month explains", and the mirror: extreme-long readings followed by falls) needs all of:

1. at least 8 counted episodes with a complete 30-day outcome, in sample and out of sample together;
2. their median 30-day change above comparison 2's median by at least 5 points (below it, for extreme long);
3. that median above the 90th percentile (below the 10th) of 10,000 random draws of as many starts among the window's days in the same past-month fifths;
4. the same direction in the first and the second half of the episodes by date.

Otherwise each result reads "in k of n", with "too few to read" under 8 episodes: context, not a signal.

## Out of sample

From 30 October 2026: the page's own series (recorded days, the `crowd` rows of `/api/market-history/wallets`), with both lines moved by the feed's `crowd.overlap.offset_pts` (the rebuilt-to-recorded shift), the same code run with `--feed PATH`. It is rerun whenever an episode's 60 days complete. The episode from 25 October 2026 began before this declaration, but its outcome lies after it; it is reported with the out-of-sample run.

## Limits

- One year of positioning, from a sample of wallets that were in smart money or whales at some point (smaller accounts are missing).
- The reading counts every coin's positions; the outcome is BTC alone.
- Episodes overlap in time with the market's own phases, so they are not independent of each other or of the past month's move.

## Result (run 29 October 2026, after the rules above were committed)

Run: `python -m research.positioning_extremes --live market_history_live.json` (the server's record to 27 October 2026; BTC closes through 27 October, so windows past it are censored). Output kept with the run, not in the repository.

**Verdict: the bar is not met on either side. Too few episodes to read (3 extreme-short and 5 extreme-long episodes with a complete 30-day outcome, against 8 needed). Context, not a signal.**

**Count corrected when running.** The pre-run count used the unrounded 10th percentile (30.03%); the declared line is 30.0%. As declared, 10 February 2026 (30.03%) is inside the line, so early and late February 2026 are two episodes: 39 days in 4 extreme-short episodes, not 40 in 3. The extreme-long side is unchanged (41 days at the declared 86.0%, the same 6 episodes). Either count is far under 8, so the verdict is the same.

### Extreme short (30.0% long or less)

| Episode start | Reading | BTC | BTC past 30 days | Next 7 days | Next 30 days | Next 60 days | Within 60 days: largest fall, largest rise | Same past month, 30 days | Seven years after a month like it: 30-day median (cases) |
|---|---|---|---|---|---|---|---|---|---|
| 6 Nov 2025 | 27.5% | $101,346 | -16.5% | -1.6% | -11.9% | -7.4% | -16.4% (day 16), +4.6% (day 4) | +2.7% | +0.2% (13) |
| 3 Feb 2026 | 25.9% | $75,770 | -17.2% | -9.1% | -6.4% | -11.2% | -17.0% (day 2), never above the start | +2.7% | +1.1% (14) |
| 18 Feb 2026 | 29.9% | $66,461 | -28.3% | +2.3% | +6.1% | +11.0% | -3.6% (day 6), +16.0% (day 58) | +2.7% | +0.4% (7) |
| 25 Oct 2026 (running) | 29.6% | $80,154 | -4.7% | censored | censored | censored | +0.9% to 27 Oct | -11.4% | -4.5% (28) |

- After the three finished episodes BTC fell further twice (November 2025 and early February 2026, with new lows 16-17% under the start) and was near its low once (late February 2026). Median 30-day change -6.4%, against +2.7% for days after the same kind of month with ordinary readings, and +0.2% for every day of the window. Random draws from the same past-month fifths: 5.5% at or below that median. First and second half: -11.9% and -0.2%.
- **Today's episode** (from 25 October in the rebuilt series; the page's recorded reading on 29 October is 19% long) differs from the earlier three: BTC had fallen only 4.7% over the 30 days before it, while the share of coins in Uptrend fell from 81% to 52% over the same 30 days (42% by 27 October). The extreme comes from the whole market's month more than BTC's. Over seven years, after a 30-day BTC change of -4.7% or worse (28 cases), BTC's next 30 days had a median of -4.5% and rose in 46% of cases; the next 60 days, -3.4% and 39%. Within this window, days after the same kind of BTC month with ordinary readings had a 30-day median of -11.4% (55 days, a falling year).
- As short as the newest rebuilt reading (28.5% on 28 October, reported only): 4 episodes, from 6 November 2025, 3 February, 26 February and 26 October 2026; the finished three were followed by -11.9%, -6.4% and -1.6% over 30 days and -7.4%, -11.2% and +14.6% over 60.
- At the 5th percentile (25.5%, reported only): 2 episodes, from 22 November 2025 (+4.6% over 30 days, +5.6% over 60) and 27 February 2026 (+0.2%, +15.9%).

### Extreme long (86.0% long or more)

| Episode start | Reading | BTC | BTC past 30 days | Next 7 days | Next 30 days | Next 60 days | Within 60 days: largest fall, largest rise | From the day back under the line: 30 days |
|---|---|---|---|---|---|---|---|---|
| 1 Oct 2025 (not counted: the series' first day) | 86.3% | $118,595 | +8.6% | +4.0% | -7.6% | -23.8% | -28.5% (day 52), +5.1% (day 5) | -16.7% |
| 4 Jan 2026 | 93.1% | $91,530 | +2.5% | -0.6% | -17.2% | -22.5% | -31.3% (day 32), +5.9% (day 10) | -27.0% |
| 28 Apr 2026 | 88.5% | $76,343 | +15.7% | +6.0% | -3.6% | -21.4% | -21.7% (day 58), +7.7% (day 12) | -16.9% |
| 5 Jul 2026 | 86.9% | $63,650 | +4.2% | +0.2% | +0.7% | +27.7% | -2.1% (day 3), +27.7% (day 60) | +0.2% |
| 19 Aug 2026 | 90.4% | $69,335 | +6.3% | +14.0% | +16.7% | +18.4% | +5.3% (day 1, never below), +24.9% (day 33) | +8.5% |
| 12 Sep 2026 | 86.2% | $77,279 | +21.7% | +5.1% | +5.9% | censored | -2.1% (day 3), +12.1% (day 9) | censored |

- Of the five counted episodes, two were followed by large falls (January 2026, and late April into May 2026, the owner's May case) and three by rises. Median 30-day change +0.7%, against +4.3% after the same kind of month with ordinary readings: 3.6 points under, short of the 5 the rule asks. Random draws: 38.7% at or below. Halves: -10.4% and +5.9%.
- From the day the reading came back under 86% (reported, never deciding): October 2025 -16.7%, January 2026 -27.0%, May 2026 -16.9%, July +0.2%, August +8.5% over the next 30 days. Three of five turns down from an extreme long were followed by falls of 16% or more, in a year whose every-day 60-day median was -6.8%.

### Every day of the window (the base rate)

BTC from 1 October 2025: over 7 days a median of -0.5% (up 45% of days), over 30 days +0.2% (51%), over 60 days -6.8% (44%). A year that rose to $125K (6 October 2025), fell to $59K (30 June 2026) and came back to $81K.

### What it means

- No verdict: one year of positioning holds 3 finished extreme-short episodes and 5 extreme-long ones. Each reading is "in k of n" and too few to read.
- In this year an extreme short was more often followed by further falls than by a bottom (2 of 3). The rebuilt list is last month's winners, so it reaches an extreme short after a falling month; what followed a falling month over seven years was close to even.
- The out-of-sample run takes the page's recorded series from 30 October 2026. The running episode's 60 days complete on 24 December 2026; it is reported then, with any new episode.
