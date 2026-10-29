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
