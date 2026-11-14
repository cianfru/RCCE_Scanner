# A coin's ratio to BTC crossing above its weekly band: did it keep beating BTC? (declared 14 November 2026, before running)

The owner's request (14 November 2026), after the ranking study: coins beating the market matter, but a 14-day number does not show it ("INJ is outperforming but there is no way for me to see it clearly"). Drawn as INJ / BTC with the weekly band on the ratio, INJ crossed above the band on 8 May and has stayed above or inside it since. The ranking study asked whether a 14-day lead picks better trades over the next 10 days, a horizon too short for a trend like this one.

Question: when a coin's ratio to BTC closes above its weekly band after at least two weeks without doing so, did the coin keep beating BTC over the next one to three months, more than it usually did at that time?

This describes the past and runs outside the production server. Everything below is fixed before any outcome is computed. Unless the bar is met, the result reads **context, not a signal**. Nothing in the engine or the executor changes either way.

Code: `backend/relative_band.py` (the ratio, its band, the crosses), `backend/backtest/relative_band_study.py`; tests in `backend/tests/test_relative_band.py`.

## Known before running

- One example, drawn for the owner: INJ / BTC crossed above its band on 8 May 2026 and was 168 on 13 November (100 a year before), above its band.
- The ranking study (same day): over 10 days, strength against the median coin did not pick better trades among many long signals.
- Nothing else about crosses of the ratio's band has been computed.

## Data

- Coins: the Market page's list (`seeds/market_history_seed.json`, 151 Binance spot pairs), without BTC and PAXG (gold). Binance spot daily closes from 2017 through 13 November 2026 (`backtest/binance_history.py`, the archive when the live ticker was re-used), the days a coin and BTC both have.
- A coin enters once its ratio has the band (20 completed weeks).

## Definitions

- **Ratio:** the coin's daily close divided by BTC's.
- **Band:** the 20-week SMA and the 21-week EMA of the ratio (`band_stretch.band_edges`: weeks start Thursday, the week under way counted at the day's close). Above: the ratio closes above the higher edge; under: below the lower edge.
- **Cross up:** a day the ratio closes above its band, after at least 14 days with the band defined and no close above it. **Cross down:** the mirror.
- **Outcome:** the log change of the ratio over the next 30, 60 and 90 days, minus the coin's usual change over the same horizon: the mean of that horizon's log change over all the coin's days within 365 days either side of the cross (the era). Shown as a percentage of the ratio. Only crosses with a complete 90 days are counted.

## The bar (fixed now)

The cross up is a mark worth showing as more than context only if all hold:
1. At least 60 crosses from at least 20 coins (else "too few").
2. Median 60-day excess at least **+5 points**, and at least **55%** of crosses with a positive 60-day excess.
3. Condition 2 holds in both halves of the coins (alphabetical, alternately).
4. The median 60-day excess is above 0 in both time halves (crosses before 2023, from 2023).
5. The median 90-day excess is above 0.

Cross downs are reported the same way, without a verdict.

## What follows

- **Met:** the cross up becomes a mark on the scanner's list and the coin page ("beating BTC since"), described as a pattern that held in the past. Any use in the engine or the executor needs its own declared test and the owner's approval.
- **Not met:** the against-BTC view (state, last cross, the ratio with its band) is shown as context only.

## Limits

- The list is today's Market page coins; coins that died before today are missing, and most survivors were listed later than 2017.
- Crosses of one coin can follow each other within the horizon; the coin halves and time halves are the guard, not a p-value.
- Binance spot, not Hyperliquid: the ratio of two spot closes, no funding.

## Results (run 14 November 2026, after the declaration was committed)

Data check (counts only, before the run): 149 pairs with data, 215,017 coin-days.

**Verdict: not met. Context, not a signal.** After a cross up, coins did worse against BTC than they usually did at that time, not better.

Excess change of the ratio coin / BTC after a cross, over the coin's era mean (median; share of crosses positive):

| Crosses | n | 30 days | 60 days | 90 days |
|---|---|---|---|---|
| **Up, all** | 966 (130 coins) | −5.2 (39%) | **−6.9 (40%)** | −8.2 (40%) |
| Up, coins A | 497 | −6.1 (37%) | −6.3 (41%) | −8.5 (38%) |
| Up, coins B | 469 | −4.7 (42%) | −7.0 (38%) | −7.4 (41%) |
| Up, before 2023 | 322 | −3.9 (43%) | −3.8 (44%) | −0.1 (49%) |
| Up, from 2023 | 644 | −5.8 (38%) | −8.5 (37%) | −11.2 (35%) |
| Down, all | 780 (127 coins) | −3.5 (42%) | −6.4 (41%) | −8.0 (37%) |

Conditions: 1 met (966 crosses, 130 coins); 2, 3, 4 and 5 not met.

### Context, not part of the bar

The declared measure compares a median with an era mean, and these ratio changes are skewed (a few large pumps), so even an ordinary day's median excess is below zero. The same measure on every 10th day the band is defined, by the ratio's state that day (60 days):

| Days | n | Median | Mean | Positive |
|---|---|---|---|---|
| All | 18,140 | −1.6 | +0.4 | 47% |
| Above the band | 3,742 | **−10.8** | −7.8 | 34% |
| Inside | 1,253 | −3.9 | −2.0 | 43% |
| Under the band | 13,145 | +0.7 | +3.1 | 51% |
| Cross up | 966 | −6.9 | −2.6 | 40% |
| Cross down | 780 | −6.4 | −4.5 | 41% |

Read against ordinary days (−1.6), the cross up is still worse, and being above the band is worse still: coins above their band against BTC gave back about 11 points more than usual over the next 60 days (median), and only a third did better than usual. The effect is stronger from 2023.

## Reading

- On these 149 coins since 2017, beating BTC did not persist as a trend: once a coin's ratio to BTC was above its weekly band, it more often gave the lead back over the following one to three months. This agrees with the ranking study, where 14-day leaders gave back on the smaller coins.
- INJ today is above its band against BTC. The pattern above describes what happened to coins in that state before; it is not a statement about INJ.
- As declared, the against-BTC view is shown as context: today's state, the last cross and the ratio with its band, with this finding in its (i).
