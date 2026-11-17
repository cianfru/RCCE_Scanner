# The POC rule on swing profiles: does trading from the POC pay? (declared 17 November 2026, before running)

Owner (17 November 2026), after the chart's profiles were moved from days and weeks to swings: "and then put a rule such as -- if price goes below VAL, trade from POC. vice versa".

The rule is on the chart as the method's rule (the POC tag reads "POC · short" or "POC · long"). This asks whether it paid. Everything below is fixed before any trade is scored. Without a row that meets its bar and is confirmed on the held-out months, the rule stays **context, not a signal**.

Code: `backend/research/poc_rule.py` (tests `backend/tests/test_poc_rule.py`). Run from `backend/`: `python -m research.poc_rule shape | power | run [--holdout]`. It reads the candles already on disk from the earlier studies and costs nothing.

## The rule, as tested

- **The profile** is the one the chart draws: the last finished move's (a rise from a swing low to the next swing high, or a fall from a high to the next low), with its POC, VAH and VAL. Swings are daily, confirmed once price has come back 3 daily ATRs; a pullback of less than half a move does not end it when the move then goes on (`engines/auction_engine`).
- **As it stood each day.** At every day's close the structure is rebuilt from what was known then: the swings confirmed by that close, the pullbacks merged by then, and the profile of the move that was then the last finished one. A later swing or merge never reaches back.
- **Price goes below VAL:** a day closes under the move's VAL. **Trade from POC:** a sell order rests at the move's POC from the next day; it fills in the first 5-minute candle whose range holds the POC.
- **Vice versa:** a day closes over the move's VAH; a buy order rests at its POC.
- **One order per move and side**, the first time its condition is met. The order lapses after 30 days, or when another move becomes the last finished one.
- **The POC must have room:** at least 0.5% from each edge of the value area.
- **Stop:** the far edge of the value area (VAH for a sell, VAL for a buy). **Exit:** the edge price broke (VAL for a sell, VAH for a buy). After 30 days the trade is closed at the last price. When one 5-minute candle holds both the stop and the exit, it counts as the stop.
- **Costs:** 0.20% a trade (10 bps a side). Funding is not counted.

The stop and the exit are my reading: the owner's sentence names the entry only. They are the two nearest levels of the same profile, so the trade stays inside the value area it is taken from.

## Data

- The 71 Binance USDT perpetuals of the retracement study, 5-minute candles, the same files (hash below). Profiles are built from hourly candles made of them, as the chart builds its own from Hyperliquid's hourly candles.
- **In sample:** orders placed 1 March 2021 to 31 July 2025. **Held out:** 1 November 2025 to 31 July 2026, run only after the in-sample result is written down. The same split as the retracement study; no outcome of this rule has been computed on either.

## Rows and bars

Months are the unit: the trades of one month are resampled together (95% interval, 10,000 draws).

| Row | Claim | Bar, in sample |
|---|---|---|
| **R1** | The rule pays, both sides together | 200 or more trades over 30 or more months; mean net return above 0; its interval above 0; above 0 in each half |
| **R2** | Selling at the POC after a close under VAL pays | 100 or more trades over 20 or more months; the same |
| **R3** | Buying at the POC after a close over VAH pays | the same |

- **Confirmed** when a row that met its bar has a mean net return above 0 on the held-out months.
- A row that does not meet its bar gets no verdict, whatever the held-out months show.

## Reported, never deciding

- The trade before costs and in multiples of the risk taken; how often the stop came first, how often the exit, how often neither in 30 days.
- Of the trades that ended at the stop or the exit, the share that reached the exit, against the share a price with no memory would give (the distance to the stop over the two distances together).
- By side, after a rise and after a fall, with the move and against it, by year, and BTC alone.

## Known before running

- From the earlier studies on these candles: every mechanical rule on calendar-session profiles made about nothing before costs and lost after them; the retracement zone turned price no more than chance.
- Never computed: any outcome on swing profiles.
- My expectation, stated before running: about zero before costs for both sides, so a loss of about the costs after them.

## Limits

- **Binance, not Hyperliquid.** The chart reads Hyperliquid; the test needs five years of history, which only Binance has. Levels differ a little between the two.
- **Hourly profiles** differ from tick-built ones by a few tenths of a percent (spec, "How close candle-built profiles are").
- **The swings are the engine's**, not a trader's eye. A trader may anchor the profile elsewhere, and may judge which breaks to take.
- **Survivors.** The 71 coins are those still trading in October 2026.
- **One order per move and side.** A trader could take the same level again; the test takes it once.

## Shape (counts only, 17 November 2026; no trade scored)

`python -m research.poc_rule shape`. Candles sha256 `f85a0a4c5041ad7c…` (the retracement study's files).

| | In sample | Held out |
|---|---:|---:|
| Orders placed | 5,140 | 684 |
| Orders filled | 2,045 over 54 months | 240 over 10 months |
| Sells, buys | 1,052, 993 | 132, 108 |
| Fills a month (least, median, most) | 5, 36, 87 | 5, 21, 46 |
| POC to stop (10th, 50th, 90th percentile) | 2.6%, 7.4%, 20.4% | 2.6%, 6.5%, 18.3% |
| POC to exit | 2.3%, 6.1%, 16.3% | 1.9%, 5.5%, 12.3% |
| Days from the close to the fill | 1, 4, 14 | 1, 4, 12 |

- All 71 coins have fills; BTC has 24 in sample.
- A price with no memory would reach the exit before the stop in 54% of trades: the exit is a little nearer than the stop.

## Power (made-up outcomes, 2,000 runs each)

`python -m research.poc_rule power`. Made-up trades with these fills per month; a trade's return spreads by 6.7% around its mean (the size of a typical win or loss here). Two cases: the trades of a month independent, or all sharing one outcome (the coins moving as one). The truth is between.

| True mean net return a trade | R1, independent | R1, one outcome a month | R2 or R3, independent | R2 or R3, one outcome a month |
|---|---:|---:|---:|---:|
| 0 | 3% | 3% | 3% | 3% |
| +0.5% | 91% | 8% | 66 to 68% | 7 to 9% |
| +1% | 100% | 18% | 100% | 16 to 17% |
| +2% | 100% | 52% | 100% | 46 to 51% |

A rule with no edge meets a bar about 3 times in 100. A rule worth 1% a trade is found almost surely if coins move apart, and about 1 time in 5 if they move as one.

## Result (run 17 November 2026, after the rules above were committed at 1f82e48)

`python -m research.poc_rule run`, then `run --holdout` after the in-sample rows below were committed.

**No row met its bar. The rule made a little on average, before and after costs, and that average cannot be told from zero. Context, not a signal.**

### In sample (orders placed March 2021 to July 2025)

| Row | Mean net return a trade (95% interval) | By half | Bar |
|---|---|---|---|
| **R1** both sides | **+0.32%** (-0.39 to +1.00), 2,045 trades over 54 months | +0.10%, +0.54% | not met (interval reaches under 0) |
| **R2** sell at the POC after a close under VAL | **-0.06%** (-1.30 to +1.08), 1,052 trades | -0.33%, +0.22% | not met |
| **R3** buy at the POC after a close over VAH | **+0.73%** (-0.40 to +1.73), 993 trades | +0.57%, +0.87% | not met (interval reaches under 0) |

Reported:

- **Before costs** +0.52% a trade (-0.19 to +1.20), or 0.06 of the risk taken. The exit came first in 55.6%, the stop in 42.4%, neither within 30 days in 2.0%.
- **Against a price with no memory:** of the trades that ended at the stop or the exit, 56.7% (53.4 to 59.9) reached the exit; a price with no memory would give 54.3% (53.2 to 55.3). 2.5 points more, with intervals that overlap.
- **By side, before costs:** sells +0.14%, buys +0.93%.
- **After a rise** +0.36% net, **after a fall** +0.29%. **With the move** (buying after a rise, selling after a fall) -0.04%; **against it** +0.53%.
- **By year, net:** 2021 +1.00%, 2022 -0.02%, 2023 -0.45%, 2024 +0.83%, 2025 +0.10%. Every year's interval holds 0.
- **BTC:** 24 trades, +0.93% (-1.23 to +3.34).

### Held out (orders placed November 2025 to July 2026; reported, no verdict)

| Row | Mean net return a trade (95% interval) | By half |
|---|---|---|
| R1 both sides | +0.41% (-0.36 to +1.23), 240 trades over 10 months | +0.57%, +0.21% |
| R2 sells | +1.36% (-0.05 to +2.52), 132 trades | +2.20%, +0.10% |
| R3 buys | -0.75% (-1.83 to +0.87), 108 trades | -1.95%, +0.32% |

- Before costs +0.61% (-0.16 to +1.43). The exit came first in 56.3%, the stop in 42.9%.
- Of the decided trades 56.7% (50.4 to 62.5) reached the exit, against 54.3% for a price with no memory: the same 2.4 points as in sample.
- The sides changed places: in sample the buys carried the average, held out the sells did.

### Independent recount

BTC, ETH and SOL in sample, recounted with separately written code (plain loops; its own daily and hourly candles, ATR, swings, merging of pullbacks, profile, orders, fills and trades): 24, 27 and 23 trades with mean net +0.9307%, -0.7275% and +0.6283%, the same as the study to the last digit shown.

### Reading

- Both periods lean the same way: about +0.3% to +0.4% a trade after costs, and the exit reached about 2.5 points more often than a price with no memory would. That is what a small real edge would look like. It is also inside what chance gives: every interval holds zero, in sample and held out.
- Neither side is steady. Buys led in sample and lost held out; sells did the reverse. A rule whose good side changes from one period to the next has not shown which side to trust.
- It is the first rule from this method that did not lose after costs on these candles. The calendar-session rules lost 0.14% to 0.33% a trade.
- To tell +0.3% a trade from zero with trades this wide (a typical win or loss is 6% to 7%) would take several times the history there is.
- **Context, not a signal.** The chart keeps showing the rule as the method's rule, with this result in its tip.

