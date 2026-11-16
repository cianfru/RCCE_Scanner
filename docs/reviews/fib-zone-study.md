# The 0.618 to 0.66 retracement zone of major swings (declared 16 November 2026, before running)

The owner is watching Chart Champions' longer-timeframe videos, where Fibonacci retracements and other levels are put together into "points of confluence" for swing trades. Their guides name one zone above the others: the band between the 0.618 and 0.66 retracements of a swing (their "Champion Channel"), "a strong support/resistance zone for cryptocurrencies".

Three questions, four rows:

1. **The zone.** When a pullback reaches the zone, does price turn there, and more than at other depths of a pullback?
2. **Confluence.** Does a weekly or monthly POC inside the zone add?
3. **The trade.** Does buying the zone, with a stop at the 0.786 retracement, pay?

This describes the past and runs outside the production server. Everything below is fixed before any outcome is computed. Only counts were looked at; they are quoted below. Unless a row clears its bar, it reads **context, not a signal**.

Elliott wave counts, which the same videos use, are not tested: a count is a judgement, and no rule for it could be written down.

Code: `backend/research/fib_zone.py` (tests `backend/tests/test_fib_zone.py`), run from `backend/`:

- `python -m research.fib_zone shape` (counts only: no race or trade is scored)
- `python -m research.fib_zone power --shape SHAPE.json` (the bars on made-up outcomes)
- `python -m research.fib_zone run`, then once `run --holdout`

## Data

- **Candles.** Binance USD-M perpetual 5-minute candles, December 2020 to October 2026, from Binance's public archive, fetched 16 November 2026.
- **Coins.** Every USDT perpetual with an archive file for each of those months: 71 coins (the DEFI index is left out). The twelve of the earlier studies gave too few swings: 192 to 293 touches of the zone. The list is in the code (`SYMBOLS`).
- **Hash.** SHA-256 over the 71 series (time, open, high, low, close, volume) `f85a0a4c5041ad7c2e5088eacd5c94cf24ac5277b74a7c009abfcebb171a444a`. Not kept in the repository.
- **In sample:** touches from 1 March 2021 to 31 July 2025. **Held out:** touches from 1 November 2025 to 31 July 2026, run once after the in-sample result. A trade lasts up to 90 days, so the three months between keep the two apart, and every race and trade ends inside the candles.
- **Costs:** 0.20% a trade (10 bps a side, all in). Funding is not counted (see Limits).

## Definitions

- **Daily candles**: UTC days built from the 5-minute candles (days with at least 285 of 288). **ATR**: the 14-day average true range, as of the day before.
- **A swing high** is confirmed on the first later day whose low is 3 ATRs under it; a swing low mirrors. This is the rule the coin chart's violet band is drawn from (`engines/auction_engine.swings`).
- **A leg.** An up-leg runs from a confirmed swing low to the highest price since. It starts the day after the low is confirmed and lasts until a later swing low is confirmed or price trades under its start. A down-leg mirrors. A leg counts once it is **6 ATRs tall**.
- **Depth.** How far a pullback has come back, as a share of the leg: 0 at the leg's extreme, 1 at its start. The **zone** begins at depth 0.618 and ends at 0.66.
- **A touch** of a depth: the first 5-minute candle to trade at that depth since the leg's last new extreme (a candle that sets a new extreme does not count). One per depth each time a new extreme is set.
- **Depths raced:** the named ones, 0.382, 0.5, 0.618 and 0.786, and five unnamed ones between and around them: 0.30, 0.45, 0.56, 0.70 and 0.85.
- **The race** after a touch: which comes first within 60 days, price back towards the leg's extreme by 8% of the leg (**a turn**), or on by another 8% of the leg (**deeper**)? Both are equally far, so with no memory in price it is a coin flip at every depth. One candle holding both is a tie; neither is undecided. From the zone's start at 0.618, "deeper" is depth 0.698: through the zone and out the other side.
- **A POC in the zone:** the POC of any of the 12 finished weeks or 6 finished months before the week and month of the touch (weeks from Monday 00:00 UTC, by the Value layer's code) lies between the zone's two edges, or within 0.25% of them.
- **The trade:** in at the 0.618 level when it is touched, with the leg (long in an up-leg). Stop at the 0.786 level. Out at the leg's extreme, at the stop, or after 90 days at the last price. When one 5-minute candle holds both the stop and the extreme, it counts as the stop. With no memory in price this trade makes nothing: it risks 0.168 of the leg for 0.618 of it and should win about 21% of the time.

Up-legs and down-legs are counted together; a turn is always back towards the leg's extreme.

## The four rows and their bars

Months are the unit: the coins swing together, so intervals come from resampling the months of the touches (10,000 draws, seed 20261116), and halves are the first and second half of those months by date.

- **R1. The zone turns price.** The share of decided races from 0.618 that end in a turn. Bar: at least 200 decided races over at least 30 months; the share at least 55%; the lower end of its 95% interval above 50%; above 50% in each half.
- **R2. More than at other depths.** That share minus the mean share at the five unnamed depths. Bar: at least 5 points; the lower end of the interval above 0; above 0 in each half.
- **R3. A POC in the zone adds.** The share with a POC in the zone minus the share without. Bar: at least 100 decided races over at least 20 months in each group; at least 5 points; the lower end of the interval above 0; above 0 in each half.
- **R4. The trade pays.** Mean net return. Bar: at least 200 trades over at least 30 months; above 0; the lower end of the interval above 0; above 0 in each half.

A row that meets its bar in sample is **confirmed** only if the held-out months agree: R1 above 50%, R2 and R3 above 0, R4 above 0. A row that fails in sample stays failed. A result on the other side, however large, is reported only.

## Also reported (no verdict)

- The share of turns at every depth, named and unnamed, and the counts of ties and undecided races.
- The zone by side (up-legs, down-legs), by coin and by year.
- The trade before costs, in multiples of risk, how often it stopped and how often it reached the extreme; with and without a POC in the zone; by side; BTC alone.

## Known before running

- **No race or trade of this study has been scored.** The code that reads prices after a touch has run only on made-up candles in the tests.
- The six earlier studies are known. They were on twelve of these coins, on intraday levels; none looked at swings or retracements.
- **The size of a swing (3 and 6 ATRs) and the list of coins were chosen after counting touches, before any outcome.** On the twelve coins: 192 zone touches with 4 and 8 ATRs, 293 with 3 and 6. The chart draws the same 3 and 6.
- My expectation, stated before running: turns close to half at every depth, the zone no different.
- **Counts** (`shape`):

| | In sample | Held out |
|---|---|---|
| Legs with a touch | 2,973 | 412 |
| Touches at 0.30, 0.382, 0.45 | 3,886, 2,989, 2,449 | 428, 324, 274 |
| at 0.5, 0.56 | 2,141, 1,845 | 252, 238 |
| **at 0.618 (the zone)** | **1,609** on 1,601 legs, over 53 months | **218**, over 9 months |
| at 0.70, 0.786, 0.85 | 1,289, 988, 804 | 176, 138, 116 |
| Zone touches in up-legs, down-legs | 954, 655 | 150, 68 |
| with a POC in the zone, without | 742, 867 | 108, 110 |
| per coin (BTC) | 12 to 35, median 22 (21) | 0 to 7 (3) |
| per month | 4 to 69, median 28 | |
| Leg's height at the touch, as a share of price | 31% at the 10th percentile, 52% median, 98% at the 90th | 27%, 42%, 90% |

These are large swings: half of the legs are over 50% of price tall.

## What the bars can see

`power` on made-up outcomes with these touches per month, 2,000 runs each. Two cases: the touches of one month independent, or all sharing one outcome (the coins swinging as one). The truth is between. Trade returns are assumed to spread by 15% around their mean, a guess.

| True value | Independent | One outcome a month |
|---|---|---|
| **R1**, turns 50% | 0% | 3.6% |
| 55% | 49% | 9% |
| 58% | 99% | 20% |
| 60% | 100% | 28% |
| 65% | 100% | 52% |
| **R2**, zone over the other depths by 0 | 0% | 2.6% |
| 5 points | 49% | 7% |
| 8 points | 99% | 13% |
| 15 points | 100% | 31% |
| **R3**, a POC adds 0 | 2.2% | 3.0% |
| 5 points | 48% | 8% |
| 10 points | 97% | 15% |
| **R4**, mean net 0 | 2.0% | 3.3% |
| 1% | 75% | 7% |
| 2% | 100% | 17% |
| 4% | 100% | 42% |

- If the coins' swings were independent, the bars would see an effect of 8 points or a trade worth 2%. If every coin did the same thing each month, they would see only very large effects. So a fail reads "not shown", not "shown absent", for effects of a few points.
- With nothing there, a row meets its bar 2% to 4% of the time. Four rows: about 10% that one does by luck. Hence the held-out months.

## Out of sample

Touches from 17 November 2026 on, the same code on newly fetched months.

## Limits

- **Survivors.** The 71 coins are those still trading in October 2026. Coins that were delisted are missing, and with them pullbacks that never turned. This flatters turns in up-legs.
- **Funding.** A trade can last 90 days. A long typically pays funding over that time, at times several percent; it is not counted, so R4 is flattered for longs.
- The coins swing together. Months are resampled for that; months in one market phase are not independent either. The period holds about two market cycles.
- One rule for a swing. A trader draws the retracement from the swing they judge to matter; this takes every swing the rule finds.
- Touches and races are read from 5-minute candles; the trade fills at the level, the stop and the extreme exactly.
- Binance perpetual volume for the weekly and monthly POCs.

## Results

To be added below after the run. Nothing above changes. Any later change is listed under Deviations, with its reason and whether it came before or after the first result.
