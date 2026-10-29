# Turning points: the median z early warning, and the signs of a bottom (declared 29 October 2026, before running)

Two questions from the owner (29 October 2026), after the late-uptrends study (docs/reviews/late-uptrends-study.md) found that prices turned before the share of coins in uptrend did:

1. **Tops.** Does the median z-score turn down before coins leave their uptrends?
2. **Bottoms, the opposite:** "when are the signs that the market is bottoming ... when fear and greed bottoms, coins bottom, BTC bottoms, and traders are also still shorting, but the market is about to reverse again."

This describes the past and runs outside the production server. Everything below is fixed before any outcome is computed; only counts were looked at. Unless a result clears its bar, it reads **context, not a signal**.

Code: `backend/research/turning_points.py` (tests `backend/tests/test_turning_points.py`), on the page's daily rows from `research/export_page_rows.mjs` (now with the median z and BTC's weekly band) and a copy of the server's `market_history_live.json`: `python -m research.turning_points --rows ROWS --live LIVE`.

## Data and known before running

- As in the late-uptrends study (same rows, same typical coin, same broad uptrends, roll-overs and Market heat turns), plus the **median z**: the median of the coins' engine z-scores on the day (how far the typical coin stands from its own trend), on all 2,006 days, and **BTC's weekly band** (lower edge) as the page draws it.
- Known: everything in the late-uptrends study and its results (prices of the typical coin fell after 9 of 10 Cooling arrows while the share often held; lifting arrows met their bar in sample). The Median z pane has been on the Chart view, so its shape against BTC has been seen. All in-sample numbers are description; the out-of-sample run (from 30 October 2026) is the only clean test.
- Shape (counts only): median z ranges from -2.44 to 2.83, quartiles -0.76 and 0.82; its highest point in each broad uptrend came between day 0 and day 70. 13 counted broad uptrends; the z-turn below happened in 11 (11 at 0.5, 10 at 1.0), 10 of them with a roll-over. 14 downturns (one ongoing, from 22 October 2026): 8 had a turn-up, 9 a z turn-up (9 at 0.5, 8 at 1.0), 7 both; 6 reached the washed-out level, 5 of them with extreme fear in the 30 days before.

## Definitions

- **Z-turn down:** the first day of a broad uptrend with the median z 0.75 or more under the run's highest median z so far. 0.75 is about half the middle range of the median z (quartiles -0.76 to 0.82). 0.5 and 1.0 are reported, never deciding.
- **Downturn:** the days from a broad uptrend's end (the first of its 5 days under 55%) to the next one's start; known on the 5th day under 55%. Age from its first day.
- **Turn-up:** the first day of a downturn with the share of coins in uptrend 20 points or more over the downturn's low so far (the mirror of the roll-over). A shallow downturn can end, with a new broad uptrend, without one.
- **Z-turn up:** the first day of a downturn with the median z 0.75 or more over its lowest so far (0.5 and 1.0 reported).
- **Washed out:** 15% or fewer coins in uptrend (the risk-on cycles study's level). **Extreme fear:** Fear & Greed at 25 or less at some point in the last 30 days (alternative.me's band; the engine's fear gate, 40, reported). **Traders short:** the profitable traders' share long at 30% or less (the positioning study's line), from October 2025. **BTC below its band:** BTC's close under the weekly band's lower edge.
- **Outcomes** as in the late-uptrends study: the typical coin over 30 and 60 days and its lowest point within 60 days, the share's change over 30 days, BTC (reported); windows past 27 October 2026 censored.

## Part A. Tops: does the median z turn down first?

- Per run: the z-turn's day and age, the share then, its lead in days over the roll-over, the first Cooling arrow and the run's end, and the outcomes from the z-turn and from the roll-over.
- **A1, lead:** in the runs with both a z-turn and a roll-over, the days from the z-turn to the roll-over.
- **A2, prices:** the typical coin's 30-day change after each z-turn against days in broad uptrends at a share within 10 points, not within 30 days after a z-turn (each turn's excess over its own comparison median). Reported the same way: the share's 30-day change.

## Part B. Bottoms

- **B1, the downturns** (description): start, end, length; the share's low and its age; the turn-up and its age; the median z's low and the z-turn up; the first lifting arrow; Fear & Greed's low and its age; the traders' low (from October 2025); the first washed-out day with extreme fear, with BTC's side of its band and the traders then; outcomes from the low (known only afterwards), the turn-up, the z-turn up and the washed-out day.
- **B2, lead and prices:** the days from the z-turn up to the turn-up (runs with both), and the typical coin's 30-day change after each z-turn up against downturn days at a share within 10 points, not within 30 days after one (the share's change reported).
- **B3, washed out with extreme fear:** per downturn, its first washed-out day with extreme fear; the typical coin over 60 days against every downturn day.
- **Exploratory** (reported, never deciding, as the owner asked for age as a scale): downturn days by age (0-29, 30-59, 60-89, 90-149, 150+) and extreme fear in the last 30 days.

## Decision rules

- **Leads (A1, B2):** "the median z turned first" needs at least 8 runs with both, the z first in at least 75% of them, and a median lead of 10 days or more.
- **Prices (A2, B2):** at least 8 events; the median excess at least 5 points lower (A2) or higher (B2); the events' median at or below the 10th percentile (A2) or at or above the 90th (B2) of 10,000 random draws of one comparison day per event; the same sign in the first and second half by date.
- **B3:** at least 8 downturns; the median 60-day change at least 10 points over every downturn day's median; beyond the 90th percentile of the draws; positive in both halves.
- Stated before running: B2's lead has 7 downturns with both and B3 has 5, so both are **too few to read** in sample, case lists only. Otherwise "in k of n", context, not a signal.

## Out of sample

From 30 October 2026 the same code on the page's new days; new turns and downturns count toward each bar.

## Limits

- 13 broad uptrends and 14 downturns over two cycles plus 2026; runs in one cycle are not independent.
- Today's coin list: coins that died are missing, which flatters bounces from a bottom most of all.
- The median z and the share come from the same engine on the same coins, so they are not independent readings; the question is only which one moves first.
- One Fear & Greed series; the traders' reading covers one year (one full downturn, from October 2025, and the current one).
