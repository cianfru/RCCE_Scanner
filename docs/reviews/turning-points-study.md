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

## Result (run 29 October 2026, after the rules above were committed at 8d57543)

`python -m research.turning_points` on the page's rows to 27 October 2026. In sample, so description; the out-of-sample run is the only clean test.

### Part A. Tops: does the median z turn down first?

| Broad uptrend | Z-turn down: day (share) | Days to the roll-over | First Cooling arrow, days after the z-turn | Typical coin 30 / 60 days after the z-turn | Share change, 30 days |
|---|---|---:|---:|---|---:|
| 6 Nov 2021 | 29 (75%) | 12 | -18 | 0% / -31% | -25 |
| 23 Dec 2021 | none | — | — | — | — |
| 17 Jan 2022 | 4 (64%) | 4 | — | -11% / -7% | -37 |
| 2 Apr 2022 | 9 (61%) | no roll-over | — | -48% / -53% | -29 |
| 20 Jul 2022 | 30 (98%) | 93 | — | -13% / -13% | -12 |
| 13 Jan 2023 | 27 (84%) | 23 | — | -16% / +1% | -50 |
| 22 Oct 2023 | 30 (95%) | 58 | — | +27% / +29% | -3 |
| 26 Feb 2024 | 19 (79%) | 10 | 7 | -30% / -24% | -55 |
| 25 Sep 2024 | 83 (96%) | 26 | -20 | -18% / -45% | -35 |
| 15 May 2025 | none | — | — | — | — |
| 11 Jul 2025 | 21 (97%) | 74 | 1 | +1% / -6% | -10 |
| 20 Mar 2026 | 58 (95%) | 44 | -1 | -15% / -23% | -8 |
| 20 Aug 2026 | 26 (77%) | 35 | 23 | +15% / censored | 0 |

- **A1, lead: bar met in sample.** In all 10 runs with both, the median z turned down before the share rolled over, a median of 30.5 days earlier (4 to 93). The same with 0.5 (10 of 10, median 48.5 days) and 1.0 (10 of 10, 20.5 days).
- **A2, prices: bar not met.** After a z-turn the typical coin's next 30 days had a median of -13%, but only 3.4 points under days in broad uptrends at the same share (lower after 6 of 11; draws 20.5%; halves -3.4 and +4.0). Not met at 0.5 or 1.0 either.
- **The share: met (reported).** It fell a median 25 points in the 30 days after a z-turn, 17.1 more than at the same share, after 9 of 11 (draws 3.2%; halves -22.3 and -2.4).
- Against the Cooling arrows there is no fixed order: of the 6 runs with both, the z turned first in 3 and the arrow in 3.
- The latest run: the median z turned down on 15 September (day 26, 77%), 35 days before the roll-over and 23 before the first Cooling arrow; the typical coin still rose 15% over the next 30 days, as the share went on to its 86% high on 30 September.

### Part B. Bottoms

| Downturn | Days | Share's low (day) | Turn-up: day | Z-turn up: day, days before the turn-up | Fear & Greed low (day) | Washed out with extreme fear: day | Typical coin 30 / 60 days from that day |
|---|---:|---|---|---|---|---|---|
| 14 May 2021 | 176 | 0% (32) | 102 | 73, 29 | 10 (10) | 16, BTC below its band | -21% / -17% |
| 17 Dec 2021 | 6 | 50% (4) | none | none | 23 (0) | — | — |
| 3 Jan 2022 | 14 | 44% (8) | none | none | 10 (5) | — | — |
| 25 Jan 2022 | 67 | 14% (2) | 13 | 12, 1 | 12 (0) | — | — |
| 21 Apr 2022 | 90 | 7% (24) | 68 | 24, 44 | 6 (58) | 22, BTC below | -26% / -30% |
| 10 Dec 2022 | 34 | 41% (11) | none | 31 | 25 (21) | — | — |
| 7 Mar 2023 | 229 | 2% (101) | 203 | 6, 197 | 30 (189) | — | — |
| 31 Jan 2024 | 26 | 29% (15) | 22 | none | 60 (0) | — | — |
| 27 Mar 2024 | 182 | 0% (54) | 149 | 26, 123 | 17 (132) | 107, BTC below | -17% / -10% |
| 22 Jan 2025 | 113 | 2% (86) | 104 | 87, 17 | 10 (36) | 34, BTC below | -8% / -10% |
| 21 May 2025 | 51 | 45% (20) | none | 42 | 42 (32) | — | — |
| 15 Oct 2025 | 156 | 5% (61) | 96 | 26, 70 | 5 (120) | 27, BTC below, traders 30%+ long | -24% / -24% |
| 15 Aug 2026 | 5 | 54% (1) | none | none | 31 (2) | — | — |
| 22 Oct 2026 | ongoing | 42% (5) | — | — | 48 (5) | — | censored |

- **B3, washed out with extreme fear: too few (5), and the wrong way.** In all 5 downturns the typical coin was lower 60 days after the first washed-out day with extreme fear (median -17%, against -9% on every downturn day). That day came early (days 16 to 107) and the share's low, Fear & Greed's low or both came later. Context, not a signal.
- **The share's low was not the price low.** From the day of the share's lowest reading (known only afterwards) the typical coin's next 30 days were mixed: lower in 7 of 13, from -38% (May 2022) to +36%.
- **B2, lead: too few (7), as declared.** The median z turned up before the share's turn-up in all 7 downturns with both, a median of 44 days earlier (1 to 197).
- **B2, prices: bar met at 0.75 only.** After the z-turn up the typical coin's next 30 days had a median of +4%, 7 points over downturn days at the same share (6 of 9; draws 91.4%; halves +7.5 and +7.0). At 0.5 the excess is -14.7 (4 of 9) and at 1.0 it is -11.5 (3 of 8): the result reverses with the size of the turn, so it does not hold up, whatever the declared row says. Context, not a signal.
- **The share's turn-up** came at a median of about day 100 of the downturn; from it the typical coin's next 30 days were lower in 5 of 8 (median about -3.5%).
- **Traders short:** the reading covers one full downturn (October 2025 to March 2026), whose traders' low was 16% long, and the current one (26% at its lowest so far). Too little to read.

### Exploratory: downturn days by age and extreme fear (owner: age as a scale)

| Downturn age (days) | Extreme fear in the last 30 days | Days (downturns) | Typical coin 30 days (up) | 60 days (up) | Share change, 30 days |
|---|---|---:|---|---|---:|
| 0-29 | no | 128 (6) | -6% (40%) | -15% (21%) | -7 |
| 0-29 | yes | 143 (8) | -21% (23%) | -21% (27%) | -6 |
| 30-59 | no | 85 (4) | -10% (40%) | -23% (25%) | 0 |
| 30-59 | yes | 150 (6) | -11% (36%) | -10% (40%) | +1 |
| 60-89 | no | 60 (2) | -18% (7%) | -16% (0%) | -4 |
| 60-89 | yes | 127 (5) | +16% (72%) | +5% (61%) | +17 |
| 90-149 | no | 111 (4) | -7% (19%) | -12% (28%) | +7 |
| 90-149 | yes | 152 (4) | -4% (36%) | -2% (43%) | +14 |
| 150+ | no | 86 (2) | -1% (45%) | +29% (69%) | +30 |
| 150+ | yes | 57 (3) | +5% (68%) | +1% (54%) | +51 |

Every downturn day: -4% over 30 days, -9% over 60.

### Reading (in sample; context, not a signal)

- **Tops:** the median z is an early warning for the share, not for prices. It turned down about a month before the share rolled over, in every run that had both, at any of the three sizes. The typical coin's next month after it was no worse than at the same share; the price warning in this record remains the late-uptrends one (greed two-plus months into a broad uptrend).
- **Bottoms mirror the tops.** Extreme fear early in a downturn, even with almost no coins in uptrend and BTC below its band, was followed by more falls (5 of 5 washed-out cases lower 60 days later; fearful days in the first month -21% over 30 days). Extreme fear two to three months into a downturn was followed by the best months in the table (+16% over 30 days, 72% of days up), across 5 downturns. "Coins bottom" (the share near 0) was not the price low.
- The median z also turned up well before the share's turn-up, but the price follow-through depends on the size of the turn, so it is not a reading to lean on.

### In the Chart view (same day)

The headline mirrors itself in a downturn: "Broad downturn, day N", how many past downturns ended sooner, its low, and four marks (Fear: Fear & Greed 25 or less in the last 30 days, its low shown; Traders short: 30% or less long; Z turned up; Turned up). Inside a broad uptrend a fourth mark joins: Z turned down. On the price, "z" marks each z-turn (above BTC for down, below for up) and a green square each turn-up, beside the red roll-over squares. Same days as this study's code on every day since 2021.
