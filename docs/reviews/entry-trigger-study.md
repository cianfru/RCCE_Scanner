# The cheat sheets' entry triggers on swing levels: do they pay? (S9, declared 18 November 2026, before running)

Owner (18 November 2026), on Chart Champions' "Entry Triggers" and "Liquidity" cheat sheets ("these are the files used to see setups"), after being shown which of their rules had not been tested here: "go for it boss".

Everything below is fixed before any trade is scored. The counts (`shape`) and the test of the bars on made-up outcomes (`power`) are added before the run, the results after it. Without a row that meets its bar and is confirmed on the held-out months, the triggers stay **context, not a signal**. Nothing here changes a signal or a trade of the app.

Code: `backend/research/entry_triggers.py` (tests `backend/tests/test_entry_triggers.py`). Run from `backend/`: `python -m research.entry_triggers shape | power | run [--holdout]`. It reads the candles and open interest on disk and costs nothing.

## What the sheets teach, and what was already tested

- **Level first, trigger second.** The sheets never trade the touch of a level. Once price reaches one they wait: for a swing failure or failed auction, for a change of structure on the 1 or 5 minute chart, for the retest. `docs/reviews/auction-levels-spec.md` has the summary.
- **Already tested (S4):** the plain fade of a sweep, in at the close of the candle that closed back, on the previous day's high and low. It made nothing before costs and lost 0.18% a trade after them. Open interest falling through the sweep and one-sided delta made no difference.
- **Not tested until now:**
  1. waiting for the structure to change before entering;
  2. the 3rd touch (a level, a sweep of it, then the retest);
  3. the "when not to enter" rule on open interest;
  4. a CVD divergence on the retest.

## The levels: the ones the chart draws

`engines/auction_engine.swing_levels`, the same code that draws the chart's dotted lines and rings.

- **A level** is the high or low of a swing point of the chart's structure as it stood at a day's close: daily swings (a turn of 3 daily ATRs), with pullbacks of under half a move merged. It is a level from the next day, for 180 days, until price trades beyond it.
- **Taken:** the first hourly candle that trades beyond it. Here the 5-minute candle inside that hour that does so first is "the take".
- **Swept:** an hourly candle closes back inside the level within 72 hours of the taking candle's open (that candle included). Quick: within the hour (the sheets' swing failure). Slow: later (their failed auction). No close back in 72 hours: a break.
- **The level's range:** the hourly candles from the swing's candle to the hour before the take. Its POC is found by the chart's rule (rows of 0.05% of the price).

## The triggers, as tested

Written for a swing high (trades are short). At a swing low everything is mirrored (trades are long).

- **The unit:** the average high-to-low range of the 288 five-minute candles (one day) before the take. A 5-minute swing is a turn of **3 units**, as the chart's daily swings are a turn of 3 daily ATRs.

**R1. The structure changes.** From the take, for 72 hours:

- **the high**: the highest price since the take. A higher one starts everything after it again;
- **the pullback low**: the lowest low after the high, once a later candle has bounced 3 units from it;
- **the lower high**: the highest high after the pullback low, once a later candle has come back 3 units from it;
- **the entry**: the first 5-minute candle that closes under the pullback low and under the level. Short at that close. One trade a level.

**R2. The 3rd touch.** After a sweep (first pivot: the swing; second: the sweep), from the close back, for 72 hours:

- price moves 3 units away from the level;
- then a later 5-minute candle comes back to the level: short at the level's price, as a resting order;
- no trade when price trades beyond the sweep's extreme before it has moved away.

**B. The plain fade** (reported, never deciding): short at the close of the hour that closed back inside.

**For every trade:**

- **Stop:** one price row beyond the furthest price reached beyond the level: up to the entry for R1, the sweep's extreme for R2 and B.
- **Exit:** the POC of the level's range. A trade whose POC is less than 0.5% beyond the entry is not taken.
- Otherwise out at the last price after 14 days. The stop wins when one candle holds both. An R2 order filled by a candle that also reaches the stop is stopped.
- **Costs:** 0.20% a round trip.

**The two readings, on R1's trades:**

- **R3, "when not to enter".** Open interest at the close of the lower high's candle is above open interest at the close of the pullback low's candle: it **rose on the retest**. The sheets skip those. Claim: the trades where it did not rise beat the ones where it rose.
- **R4, CVD divergence.** CVD is the running sum of taker buys minus taker sells, a 5-minute candle at a time. A divergence: CVD at the lower high is above CVD at the high (more net buying, a lower price). Claim: the trades with it beat the ones without.

## Data

- **Candles:** Binance futures 5-minute candles with taker buy volume, the 71 perpetuals of the retracement study, December 2020 to October 2026. Hourly and daily candles are built from them.
- **Open interest:** Binance's 5-minute readings from its daily metrics archives, from December 2021 (Bitcoin from December 2020). Read for the other 59 coins on 18 November 2026; some coins' archives end early. A reading is the last one at or before a candle's close, at most 10 minutes old; a trade without both readings is left out of R3.
- **In sample:** levels taken from 1 March 2021 to 31 July 2025. **Held out:** 1 November 2025 to 31 July 2026 (the periods of S7 and S8). Run only after the in-sample result is written down.
- **Months are the unit** of every interval (resampled 10,000 times): coins move together.

## Rows and bars

| Row | Claim | Bar, in sample |
|---|---|---|
| **R1** | Entering on the structure change pays | 200 or more trades over 30 or more months; mean net return above 0; its 95% interval above 0; above 0 in each half |
| **R2** | The 3rd touch pays | the same |
| **R3** | Open interest not rising on the retest marks the better trades | each group 100 or more trades over 20 or more months; the gap 0.10% a trade or more; its 95% interval above 0; above 0 in each half |
| **R4** | A CVD divergence on the retest marks the better trades | the same |

- **Confirmed** when a row that met its bar also holds on the held-out months: mean net return above 0 (R1, R2); the gap above 0 (R3, R4).
- A row that does not meet its bar gets no verdict, whatever the held-out months show.
- If a row is confirmed, it is a proposal to the owner. Nothing is shown as a signal without the owner's approval.

## Reported, never deciding

- The plain fade (B) on these levels.
- Each trade row before costs, in multiples of the risk taken, how often the stop came first and how often the POC was reached, and the POC-first share against what a price with no memory gives (risk over risk plus reward).
- Shorts at highs against longs at lows; after quick sweeps, slow sweeps and takes that were not swept; Bitcoin alone; by year.
- The sheets' full open-interest condition (fell on the pullback, then rose on the retest).
- R3's and R4's readings on R2 and B.

## Known before running

- **S4:** fading sweeps of the previous day's high and low lost 0.18% a trade after costs; the stop came first in 64.5%.
- **S8:** the POC rule on swing profiles made +0.3% a trade, not told from zero. Exits at a range's POC have not lost here.
- **Counts seen while writing the code** (BTC, SOL and ZRX in sample, counts only): about 60 levels taken a coin, 5 in 6 of them swept, about 50 R1 trades a coin.
- **Charts seen:** while building the chart's swing levels I looked at the last 180 days of BTC, ETH and SOL on Hyperliquid with their sweeps marked (June to November 2026). June and July 2026 are inside the held-out months. No trade of this study was computed on them.
- **My expectation, stated before running:** R1 and R2 lose 0.1% to 0.3% a trade after costs. Their stops are tight, so costs of 0.20% are a large part of the risk. R3 and R4 show gaps inside what chance gives.

## Limits

- **Hourly closes decide a sweep**, where the sheets prefer 5 to 30 minute candles. It keeps the study on the levels and rings the chart draws.
- **5-minute candles, no footprint.** The sheets read the 1-minute chart and a footprint (trapped traders, imbalances). That needs every trade.
- **One exchange's delta and open interest**, from candles.
- **One exit.** The sheets take part off at the POC, part at the far side of the range, move the stop by judgement and let a part run. Here: all out at the POC.
- **The chart's daily swings only.** Smaller ranges ("mini range") and the levels a trader picks by eye are not tested.
- **Judgement is left out.** This tests the named triggers taken every time, not the method as a person trades it.
- **The held-out months were used before**, by S7 and S8, for other rules on the same candles.
- **Survivors:** the 71 coins are those listed since 2020 and still trading.

## Shape and power (counted 18 November 2026, before any trade was scored)

**Counts**

| | In sample (1 Mar 2021 to 31 Jul 2025) | Held out (1 Nov 2025 to 31 Jul 2026) |
|---|---|---|
| Levels taken | 3,751 | 473 |
| Swept: an hourly close back within 72 hours | 3,411 (91%) | 431 (91%) |
| ... within the hour | 2,075 (55%) | 263 (56%) |
| Broken: no close back in 72 hours | 340 (9%) | 42 (9%) |
| R1 trades (shorts, longs) | 3,219 (1,415, 1,804) over 53 months | 390 (109, 281) over 10 months |
| R2 trades (shorts, longs) | 2,274 (1,032, 1,242) over 53 months | 293 (74, 219) over 10 months |
| B trades (shorts, longs) | 3,370 (1,490, 1,880) over 53 months | 430 (114, 316) over 10 months |
| Not taken, the POC under 0.5% away: R1, R2, B | 55, 0, 41 | 2, 0, 1 |
| R1: from the entry to the stop, median (10% to 90%) | 6.1% (2.5 to 17.9) | 4.2% (1.9 to 13.0) |
| R1: from the entry to the POC | 16.6% (6.1 to 42.7) | 12.1% (4.8 to 34.0) |
| R2: from the entry to the stop | 2.3% (0.3 to 13.1) | 1.4% (0.2 to 8.1) |
| R2: from the entry to the POC | 18.6% (7.8 to 46.6) | 14.4% (6.8 to 36.4) |
| The POC first, for a price with no memory: R1, R2, B | 31%, 17%, 24% | 29%, 14%, 20% |
| Hours from the take to the entry, median: R1, R2 | 4.5, 7.6 | 5.7, 7.4 |
| R3: R1 trades where open interest did not rise, and rose | 1,356 and 1,316, over 48 and 47 months | 180 and 210, over 9 and 10 months |
| R4: R1 trades with a divergence, and without | 1,087 and 2,132, over 53 and 53 months | 158 and 232, over 9 and 10 months |

- All 71 coins have trades in sample, and every row has the trades and months its bar asks for.
- **Open interest** is on record for all 71 coins from December 2021 (Bitcoin from December 2020). For nine coins the record ends early, between July 2024 and January 2026. R1 trades without both readings (about 1 in 6 in sample, mostly from 2021) are left out of R3.
- **Nine in ten levels that are taken are swept by this definition.** An hourly close back inside within three days is what usually happens, and over half the time it happens within the hour. The sheets' swing failure and failed auction are the common case, not a rare one.
- **The stops are not tight.** I expected them to be. By the time the structure has changed, price is well under the high it made: R1's stop is a median 6% away, R2's 2%. Costs of 0.20% are a small part of that, so the reason I gave for expecting a loss does not hold. The expectation stays as written.
- **The POC is far**: a median 17% from the entry, about three times the distance to the stop. Many trades will end at the 14-day limit, not at the stop or the POC.

**The bars on made-up trades** (`power`: this study's trades a month; a trade's return spread by 10% around its mean for R1 and 6.6% for R2; 2,000 runs each; no real outcome involved)

How often each bar is met, by the true mean net return a trade (for R3 and R4: the true gap between the groups).

If every trade is independent:

| Truth | R1 | R2 | R3 | R4 |
|---|---|---|---|---|
| none | 2 in 100 | 3 in 100 | 3 in 100 | 3 in 100 |
| 0.2% | 20 in 100 | 33 in 100 | 10 in 100 | 8 in 100 |
| 0.5% | 79 in 100 | 94 in 100 | 28 in 100 | 28 in 100 |
| 1% | 100 in 100 | 100 in 100 | 72 in 100 | 78 in 100 |
| 2% | 100 in 100 | 100 in 100 | 100 in 100 | 100 in 100 |

If all the trades of a month share one outcome (the coins moving as one):

| Truth | R1 | R2 | R3 | R4 |
|---|---|---|---|---|
| none | 3 in 100 | 3 in 100 | 3 in 100 | 3 in 100 |
| 0.5% | 5 in 100 | 8 in 100 | 4 in 100 | 4 in 100 |
| 1% | 11 in 100 | 19 in 100 | 8 in 100 | 8 in 100 |
| 2% | 27 in 100 | 52 in 100 | 14 in 100 | 14 in 100 |
| 5% | 90 in 100 | 100 in 100 | 55 in 100 | 56 in 100 |

- **What the study can see:** with trades close to independent, +0.5% a trade (R1 and R2) and a gap of 1% (R3 and R4). If a month's trades win and lose together, only several percent a trade would show. The truth is between the two.
- A bar is met by chance about 3 times in 100. With four rows, about 1 study in 10 like this has a row meet its in-sample bar by chance; the held-out months are the guard.

## Result

To be added after the run.
