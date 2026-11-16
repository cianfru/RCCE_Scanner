# Five more studies of the auction levels (declared 16 November 2026, before running)

The owner asked for the remaining studies of the method taught by Daniel of Chart Champions (docs/reviews/auction-levels-spec.md) after the first one, the 80% rule on UTC days, met no bar (docs/reviews/value-area-rule-study.md).

| # | Question |
|---|---|
| S2 | Naked POCs: is price drawn back to a POC, more than to a price as far away on the other side? |
| S3 | A value-area edge: when price is accepted outside, does it go on? |
| S4 | Sweeps of the previous day's high and low: does fading them pay, and do open interest and delta sort the good ones from the bad? |
| S5 | Confluence: is a sweep worth more when other levels sit at the same price? |
| S6 | The 80% rule again, on New York trading hours instead of UTC days. |

Each describes the past and runs outside the production server. Everything below is fixed before any outcome is computed. Only counts were looked at; they are quoted below. Unless a row clears its bar, it reads **context, not a signal**.

Code: `backend/research/auction_studies.py` (tests `backend/tests/test_auction_studies.py`), run from `backend/`:

- `python -m research.auction_studies fetch-oi` (open interest, below)
- `python -m research.auction_studies shape` (counts only: no trade or race is scored)
- `python -m research.auction_studies power --shape SHAPE.json` (the bars on made-up outcomes)
- `python -m research.auction_studies run`, then once `run --holdout`

## Data

- **Candles.** The 80% rule study's: Binance USD-M perpetual 5-minute candles of twelve coins (BTC, ETH, BNB, XRP, ADA, DOGE, SOL, LTC, LINK, DOT, AVAX, BCH), December 2020 to October 2026, SHA-256 `728e169c2460f16360dac85286af153b0580887d30be95068e9b697999d87f67`. Each candle carries its taker buy volume.
- **Open interest.** Binance's public 5-minute readings (`data.binance.vision/data/futures/um/daily/metrics/`), fetched 16 November 2026: BTC from 1 December 2020, the other eleven from 1 December 2021 (the archive has nothing earlier for them). SHA-256 over the twelve series `f53afe7a311e76797fd2a840cddbd9d79a11d1f8e29512c249f29c6b7f682fbd`. Neither is kept in the repository.
- **In sample:** 1 January 2021 to 30 April 2026. **Held out:** 1 May to 31 October 2026, run once after the in-sample result. The same split as the 80% rule study.
- **Days used:** a UTC day counts when it has at least 285 of its 288 candles; an event day needs the day before to count too.
- **Value areas** come from the code the coin chart's Value layer draws (`engines/auction_engine.session_levels`), as in the 80% rule study.
- **Costs:** 0.20% a trade (10 bps a side, all in). Funding is not counted.

## What every row shares

- **Half-hour bars** from 00:00 UTC (S6: from 09:30 New York). A bar's close is its last price.
- **Days are the unit.** The coins move together, so intervals come from resampling event days (S2: weeks, because its races run for days). 10,000 draws, seed 20261116. Halves are the first and second half of those days (or weeks) by date.
- **A trade "pays"** (the trade bar) only if all of: at least 200 trades on at least 100 days; mean net return above 0; the lower end of its 95% interval above 0; above 0 in each half; above 0 on BTC alone.
- **One group "beats" another** (the gap bar) only if all of: at least 200 trades on at least 100 days in each group; the difference in mean net return is at least 0.10%; the lower end of its 95% interval is above 0; the difference is above 0 in each half.
- A row that meets its bar in sample is **confirmed** only if the held-out months agree in direction (stated per study). A row that fails in sample stays failed. A result on the other side, however large, is reported only.

## S2. Naked POCs

The claim: a POC that price has not traded back to "acts as a magnet".

**The race.** Take a finished day's POC and the **mirror** price: as far from the current price as the POC, on the other side. Which is traded first? With no pull either way it is a coin flip: the two are equally far. A price is traded when a 5-minute candle's range holds it.

- **Fresh** (row S2-R1). At a day's end, with the day's close as the current price. Only when the POC is at least 0.25% from the close, and the mirror lies inside that day's own range (so both prices traded that day). The race runs for the next 3 days.
- **Old** (row S2-R2). A POC that was not traded on the whole following day: the dashed line the chart keeps. At that following day's end, with its close as the current price, POC at least 0.25% away. The race runs for the next 10 days.

A race counts only if its whole window is inside the period and has its candles. It is **decided** when one price is traded before the other; both in one candle is a tie, neither is "none".

**The bar**, for each row: at least 500 decided races over at least 100 weeks; the POC first in at least 55% of them; the lower end of the 95% interval above 50%; above 50% in each half. Confirmed if the held-out months are above 50%.

**Reported:** ties and undecided races; the share by distance (0.25 to 0.5%, 0.5 to 1%, 1 to 2%, over 2%); BTC alone; and, with no comparison, how soon every day's POC was traded again (within 1, 3, 7 and 30 days), by its distance from the close.

## S3. Accepted outside the value area

The claim: when price leaves the value area and is accepted outside, value is moving and price goes on.

- **Days:** those that opened inside the previous day's value area.
- **Accepted outside:** the first half-hour bar of the day to close outside an edge, and the next bar closes outside the same edge. The moment is that second close. (If the next bar closes back inside, it is "rejected": that branch is the control of the 80% rule study.) One per coin and day: the first excursion only.
- **The trade:** in at that second close, with the break (long above VAH, short below VAL). Out at the first later half-hour close back inside the value area, or at the day's last price.

**Row S3-R1:** the trade bar. Confirmed if the held-out mean net return is above 0.

**Reported:** the trade before costs; how often it ended by a close back inside; how often the day closed outside on that side; the same trade with a price stop one row back inside the edge; the trade taken one bar earlier, at the first close outside; by side, time of day and year.

## S4. Sweeps of the previous day's high and low

The claim: a wick through a key level that closes back inside (a swing failure pattern) is a reversal; open interest falling and aggressive volume being absorbed make it stronger.

- **A sweep:** the half-hour bar in which price first trades beyond the previous day's high that day, when that same bar closes back below the high. Mirror for the low. If that bar closes beyond the level, it is a break and there is no sweep on that side that day. At most one per side, coin and day.
- **The fade:** in at that bar's close, away from the level (short after a sweep of the high). Stop one price row beyond the bar's extreme. Out at the previous day's POC (when the entry is beyond it), at the stop, or at the day's last price. When one 5-minute candle holds both the stop and the POC, it counts as the stop.
- **Flush:** open interest at the bar's end is lower than at its start (positions were closed through the sweep). Readings are the last at or before each time, at most 10 minutes old; a sweep without both is left out of this row.
- **Absorbed:** the bar's taker volume is one-sided in the sweep's direction by at least 10% of its volume (on a sweep of the high: taker buys minus taker sells, over volume, at least 0.10), and yet the bar closed back inside.

**Rows:**

- **S4-R1:** the fade pays (the trade bar).
- **S4-R2:** sweeps with a flush beat those without (the gap bar).
- **S4-R3:** absorbed sweeps beat the rest (the gap bar).

Confirmed if the held-out months agree: R1 mean net above 0; R2 and R3 a difference above 0.

**Reported:** the fade before costs and in multiples of risk; how often the stop came first and how often the POC was reached; by side, time of day, year and coin; sweeps with both a flush and absorption against those with neither.

## S5. Confluence

The claim: a level is worth more when other levels sit at the same price ("two or more technical factors aligning").

- **Events and trade:** S4's sweeps and their fade.
- **Other levels**, all known before the sweep:
  - profile levels: the previous day's VAH, VAL and POC; the previous week's VAH, VAL and POC (weeks from Monday 00:00 UTC with at least 1,915 of their 2,016 candles); the POCs of the 30 days before the previous day that were still naked when the day began;
  - opens and extremes: the day's open, this week's and this month's open, the previous week's high and low.
- **Near:** within 0.25% of the swept level. **k** is the number of other levels near.

**Row S5-R1:** sweeps with at least one other level near (k of 1 or more) beat sweeps alone (k of 0): the gap bar. Confirmed if the held-out difference is above 0.

**Reported:** the fade by k (0, 1, 2, 3 or more); with a profile level near; with only an open or extreme near.

## S6. The 80% rule on New York hours

The first study used UTC days, whose "open" is only a clock time. Chart Champions' site describes CME-style hours for Bitcoin, and the rule was made for sessions like that.

- **Session:** 09:30 to 16:15 New York time (daylight saving followed), Monday to Friday. 81 five-minute candles; a session counts with at least 79. Holidays are not removed.
- **The previous session** is the previous weekday's (Friday for Monday). Its value area comes from its own candles only.
- **Everything else** is the 80% rule study's, with "session" for "day": opened outside (the 09:30 price against the previous session's value area), the two readings of "accepted" (two half-hour closes inside; one), the rule and control events, reaching the other edge by 16:15, and the trade. Half-hour bars count from 09:30; the last one is 15 minutes long.

**Rows,** for each reading, with the 80% rule study's bars unchanged: **R1** the claim (at least 75% reached the other edge, interval from 70%, halves 70%), **R2** the open (rule minus control at least 10 points), **R3** the trade (the trade bar). Six rows. Confirmed as there: R1 at least 70%, R2 above 0, R3 above 0 in the held-out months.

**Reported:** as in the 80% rule study.

## Known before running

- **The 80% rule study's results are known** and were on the same days: about 40% of its events reached the other edge; its control (opened inside, closed outside, came back) reached it in 43% and its trade lost 0.09%. S3 is the other branch of that control; S6 is the same rule on other hours.
- **No outcome of S2 to S6 has been computed.** The code that scores a race or a trade has run only on made-up candles in the tests.
- The absorption threshold (10%) was set after looking at how one-sided sweep bars are on BTC, ETH and DOGE (median 6% in the sweep's direction, a third of bars at 10% or more). No outcome was read for that.
- My expectations, stated before running: S2 somewhat above 50%; S3 and S4 near zero before costs, so negative after; S6 below 80%.
- **Counts** (`shape`, in sample):

| | In sample | Held out |
|---|---|---|
| **S2** fresh races, over weeks | 8,985 over 279 | 813 |
| old races, over weeks | 7,327 over 278 | 612 |
| **S3** coin-days that opened inside | 13,575 | 1,439 |
| accepted outside (above, below), on days | 8,798 (4,413, 4,385) on 1,770 | 906 |
| rejected; never closed outside; no next bar | 3,865; 890; 22 | 425; 105; 3 |
| accepted, BTC | 721 | 72 |
| **S4** sweeps (highs, lows), on days | 10,771 (5,226, 5,545) on 1,883 | 1,062 |
| with a POC to exit at | 10,554 | 1,043 |
| flush: yes, no, no reading | 4,664, 4,528, 1,579 | 572, 490, 0 |
| absorbed: yes, no | 3,422, 7,349 | 550, 512 |
| sweeps, BTC | 880 | 83 |
| **S5** other levels near: none, one, two, three or more | 7,538, 2,523, 577, 133 | 635, 312, 82, 33 |
| a profile level near; an open or extreme near | 2,120; 1,507 | 310; 177 |
| **S6** coin-sessions | 16,668 | 1,572 |
| opened above, inside, below | 6,604, 4,124, 5,940 | 546, 388, 638 |
| two closes: rule events on sessions (BTC) | 2,289 on 874 (216) | 218 on 84 (10) |
| never accepted; crossed first | 9,499; 756 | 888; 78 |
| control events on sessions | 1,375 on 659 | 154 on 72 |
| one close: rule events on sessions (BTC) | 3,525 on 1,065 (317) | 328 on 100 (21) |
| control events on sessions | 1,897 on 779 | 202 on 80 |
| median width of the value area | 1.78% of price | 1.28% |

Three sessions in four opened outside the previous session's value area (42% of UTC days did): hours apart, price has usually moved on.

## What the bars can see

`power` on made-up outcomes with these events per day (or week), 2,000 runs each. Events on one day (or week) share one outcome there, the harder case. Trade returns are assumed to spread by 1.5% around their mean, a guess: the real spread is an outcome.

| True value | Met the bar |
|---|---|
| **S2**, POC first 50% | 2.5% to 2.8% |
| 52% | 8% to 10% |
| 55% | 36% |
| 57% | 61% to 63% |
| 60% | 89% to 90% |
| **Trade bar** (S3, S4-R1), mean net 0 | 2.4% to 2.5% |
| 0.05% | 23% to 26% |
| 0.10% | 68% to 74% |
| 0.20% | 100% |
| **Trade bar, S6**, mean net 0 | 2.8% |
| 0.10% | 35% |
| 0.20% | 91% |
| **Gap bar** (S4-R2, S4-R3, S5), true gap 0 | 2.0% to 2.4% |
| 0.10% | 33% to 36% |
| 0.20% | 87% to 89% |
| 0.30% | 100% |

- With nothing there, a row meets its bar about 1 time in 40. There are 13 rows (2 + 1 + 3 + 1 + 6). If they were independent, the chance that at least one met its bar by luck would be about 28%; they are not independent, so it is less, but it is not small. That is why a row counts only once the held-out months agree.
- The gap bars see a difference of about 0.2% a trade; a smaller one is not excluded by a fail.
- S6-R1 and R2 use the 80% rule study's bars, whose reach was shown there.

## Out of sample

Days from 17 November 2026 on, the same code on newly fetched months.

## Limits

- Those of the 80% rule study: twelve coins that exist today; coins moving together; Binance perpetual volume and 5-minute candles; fills at the bar's close, at the stop and at the exit price exactly; funding left out.
- **S2.** Races that start a day apart overlap and share most of their path. Weeks are resampled for that, but neighbouring weeks are not independent either. The mirror is a fair coin only for a market with no drift and no memory; a tendency to reverse after any move would show as "POC first" too. The row cannot tell a pull to the POC from a pull back in general.
- **S3 and S4.** One mechanical reading each of setups the method leaves to judgement.
- **S4.** Open interest before December 2021 exists for BTC only. The reading is every 5 minutes, at most 10 minutes old. "Absorbed" is measured over the whole half-hour bar, not at the level.
- **S5.** The zone (0.25%) and the list of levels are one choice among many.
- **S6.** Weekdays only; holidays kept; a 6.75-hour session of a market that trades all day.

## Results

To be added below after the run. Nothing above changes. Any later change is listed under Deviations, with its reason and whether it came before or after the first result.
