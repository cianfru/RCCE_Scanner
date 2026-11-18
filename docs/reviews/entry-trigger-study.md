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

## Shape and power

To be added before the run.

## Result

To be added after the run.
