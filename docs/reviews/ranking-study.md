# Ranking the long signals when many fire at once (declared 14 November 2026, before running)

The owner's request (14 November 2026): the scanner is useful when the market falls, because the few coins still rising stand out (MERL today). When the market rises, most coins carry a long signal and the priority score does not say which are the best trades. "How can we make it better and improve the detection system ... what are the best positions?"

Question: on days when many coins carry a long signal at once, does ranking them by how much they beat the market pick coins that do better over the next 10 and 20 days than the ones it ranks last, and better than today's priority score does?

This describes the past on replays and runs outside the production server. Everything below is fixed before any spread is computed. Unless a score clears the bar, the result reads **context, not a signal**. Nothing in the engine or the executor changes either way.

Code: `backend/backtest/ranking_study.py`, tests in `backend/tests/test_ranking_study.py`.

## Known before running

- Counts only (no outcome): in the 4H replays of the live rules, about three quarters of long readings fall on bars where a quarter or more of the set's coins carry a long signal; in the hottest stretches 14 to 19 of 30 coins do.
- Today's live scan: 15 of 206 coins with a long signal; the top 12 priority scores sit between 56 and 65.
- The sector-momentum study (26 September 2026): sectors that beat BTC kept beating it over 10 days (leaders over laggards by 3.8%), but blocking entries by sector strength failed. That was a filter on all entries; this study ranks within the long signals on crowded days, which was not tested.

## Data

The recorded rows of the 4H replays of today's live rules (`rule_capture`), windows 1-9 (21 October 2021 to 29 March 2026):
- **primary**: 10 coins (ADA, AVAX, BNB, BTC, DOGE, DOT, ETH, LINK, SOL, XRP);
- **secondary**: 30 coins (the secondary set);
- **third**: the 30 coins first used in the executor-gap study's Check 1 (ranks 31-60).

Window 10 is reported for each set as well, but it does not count: it has been read in earlier studies for all three sets.

## Definitions

- **Long signal:** STRONG_LONG, LIGHT_LONG, REVIVAL_SEED or REVIVAL_SEED_CONFIRMED.
- **Crowded day:** a 00:00 UTC bar where at least 25% of the set's coins with a row, and at least 3 coins, carry a long signal. One reading per day.
- **Market:** the set's median coin. Each 4H bar, the median log return of the coins with a price at both closes, summed.
- **Scores** (closes up to the decision bar only):
  - **P**: the scanner's priority score from the fields the replay records (signal tier, conditions met, distance from the weekly band, heat headroom). Floor, momentum, CVD and volume are not recorded and are left out. This is the baseline.
  - **RS14, RS30**: the coin's log return over 14 or 30 days minus the market's.
  - **RR14, RR30**: the coin's log return over 14 or 30 days minus beta times the market's. Beta is the coin's 4H log returns against the market's over the prior 90 days (at least 45 days of data).
- **Spread:** on each crowded day, among the long-signal coins with a score and a forward price, the top third's mean return minus the bottom third's (a third is at least one coin; ties in alphabetical order). Forward returns are simple, close to close, at 10 and 20 days.

## The bar (fixed now)

A score other than P passes only if, on **each** of the three coin sets (windows 1-9):
1. the median 10-day spread is at least **+2.0 points**;
2. the median 10-day spread is above 0 in both halves (windows 1-5 and 6-9);
3. its median 10-day spread is above P's;
4. its median 20-day spread is above 0.

If more than one passes, the one with the highest mean of the three sets' median 10-day spreads is used.

## What follows from the result

- **A score passes:** it orders a new "Best longs now" list on the scanner and Radar, shown with its reasons (beating the market by how much, traders in and arriving, room before stretched). The priority score is not changed for the executor; any executor use needs its own declared test and the owner's approval.
- **None passes:** the list is still built, ordered as today, with the same reasons shown as context.
- Trader positioning cannot be tested here (its record starts in September 2026). It is shown in the list as context only.

## Limits

- The coin sets are lists fixed in advance; coins delisted later drop out where their data ends, and coins without a price 10 or 20 days on drop out of that day.
- Crowded days follow each other, so the days are not independent; the halves and the three sets are the guard, not a p-value.
- Five scores are compared; the bar asks for every condition on every set to limit picking the luckiest.

## Results (run 14 November 2026, after the declaration was committed)

**Verdict: no score passes. Context, not a signal.** On crowded days, neither strength against the market nor the priority score picked coins that did better over the next 10 or 20 days than the ones they ranked last.

Median spread, top third minus bottom third of the long-signal coins, percentage points (windows 1-9):

| Set (crowded days) | Score | 10 days | Halves (W1-5, W6-9) | Days positive | 20 days |
|---|---|---|---|---|---|
| primary (405) | P | −0.01 | −0.24, +0.25 | 50% | −1.87 |
| | RS14 | −0.36 | −1.17, +0.48 | 48% | −2.82 |
| | RR14 | +0.69 | −0.33, +1.99 | 54% | −1.12 |
| | RS30 | −0.50 | −0.21, −0.68 | 48% | −1.04 |
| | RR30 | −0.38 | −0.48, +0.42 | 49% | −2.11 |
| secondary (296) | P | −0.49 | −0.59, −0.38 | 47% | +0.35 |
| | RS14 | −0.38 | −1.05, +1.12 | 49% | −2.34 |
| | RR14 | −0.95 | −1.77, +0.47 | 45% | −2.20 |
| | RS30 | +0.49 | −0.04, +1.00 | 51% | −1.20 |
| | RR30 | −0.74 | −0.71, −1.14 | 45% | −2.17 |
| third (281) | P | −1.28 | −1.15, −2.23 | 42% | −1.33 |
| | RS14 | −2.13 | −2.08, −2.34 | 37% | −1.15 |
| | RR14 | −2.03 | −2.58, −0.96 | 36% | −1.15 |
| | RS30 | −2.35 | −2.76, −1.71 | 36% | −1.09 |
| | RR30 | −2.14 | −2.33, −1.71 | 37% | −0.06 |

- Every strength score fails condition 1 on every set (the best median is +0.69, against +2.0 needed).
- On the third set (30 smaller coins) the order is reversed: the coins that had beaten the market most did about 2 points worse over the next 10 days than those that had beaten it least, in both halves. On the other two sets the spreads are within half a point of zero.
- Crowded days come in a few episodes (most in windows 3, 5 and 7); window 2 has none.
- **Check:** RS14 recomputed with separate code (pandas pivot tables) gives the same day counts and the same medians on all three sets (−0.36, −0.38, −2.13).
- **Window 10** (does not count): only the third set has its window-10 rows saved. It holds 13 crowded days in one episode, all spreads −11 to −13 points.

### Context, not part of the bar

Long-signal coins against the set's other coins over 10 days (median of the daily difference of means):

| Set | Crowded days | Quiet days (some longs, under 25% of coins) |
|---|---|---|
| primary | +1.00 (56% of days positive) | −0.36 (48%) |
| secondary | −0.04 (50%) | +0.35 (53%) |
| third | −0.41 (47%) | −2.01 (40%) |

Over a fixed 10 days, coins with a long signal did not beat the coins without one by much on any set, on crowded days or on quiet ones.

## Reading

- In broad rallies, which coin beat the market most over the last two to four weeks did not tell which would do best over the next two to four; on smaller coins the leaders tended to give some back. Ranking by strength would not have helped choose among many long signals, and the priority score did not either.
- The quiet-day row bears on the owner's MERL case: a coin rising while the market falls is real information about what happened, but on these sets it did not, on average, keep beating the other coins over the next 10 days.
- The engine's replay gains come from when it is in and out (the regime, the exits, the BTC band block), not from picking which coin beats another over a fixed 10 days. That fits the earlier entry-quality and sector-tilt studies.
- As declared, the "Best longs now" list can still be built, ordered as today, with its reasons shown as context.

## Deviation from the declaration

- `--window10` could not read window 10 for the primary and secondary sets: their captures predate the saving of window-10 rows. The script now skips a set without them. Window 10 does not count, so the verdict is unaffected.
