# The 80% rule on crypto days (declared 16 November 2026, before running)

The owner asked for the method taught by Daniel of Chart Champions to be tested on real data (docs/reviews/auction-levels-spec.md, study S1). This is its best known claim:

> When a day opens outside the previous day's value area, and price comes back inside and is accepted there, it goes on to the other edge of that value area about 80% of the time.

Three questions, each with its own bar:

1. **The claim.** Did such days reach the other edge about as often as claimed?
2. **The open.** Did opening outside add anything, against days that opened inside, left the value area and came back the same way?
3. **The trade.** Did trading it mechanically pay after costs?

This describes the past and runs outside the production server. Everything below is fixed before any outcome is computed. Only counts were looked at; they are quoted below. Unless a row clears its bar, it reads **context, not a signal**.

Code: `backend/research/value_area_rule.py` (tests `backend/tests/test_value_area_rule.py`), run from `backend/`:

- `python -m research.value_area_rule fetch` (public candles, below)
- `python -m research.value_area_rule shape` (counts only: nothing after an event's time is read)
- `python -m research.value_area_rule power --shape SHAPE.json` (the bars on made-up outcomes)
- `python -m research.value_area_rule run` (the study), then once `run --holdout`

## Where the rule comes from

- **Auction Market Theory** (Dalton, *Mind Over Markets*), on futures with fixed trading hours: if a session opens outside the previous session's value area, and price then trades inside it for two half-hour periods in a row, it has about an 80% chance of crossing the whole value area.
- **Chart Champions.** Two community TradingView scripts written from the videos call it "CCV": "based on the 80% rule of the dOpen opening outside of the pdVAH/pdVAL", with days starting at 00:00 UTC. Chart Champions' own manual for it is for members only and was not read.
- **Acceptance, in Chart Champions' words.** Their public guide to failed auctions says: "A good signal for acceptance is a 30-minute candle close back inside the range." That is one half-hour close, where the textbook asks for two. (Read as a search engine's excerpt of chartchampions.com; the site refuses automated readers, so the wording could not be checked on the page itself.)
- **The videos themselves** could not be read. On 16 November 2026 YouTube refused transcript requests from the research machine (it asks for a sign-in), and the transcript panel of the public pages loaded once and then stayed empty. No way around that was tried. So no definition below rests on a video; if a video later states the rule differently, that form is a new declared row, run on new data.

Crypto trades all day with no session open, so the 00:00 UTC "open" is only a clock time. Whether the rule carries over is the question.

## Data

- **Candles.** Binance USD-M perpetual 5-minute candles from Binance's public archive (`data.binance.vision/data/futures/um/monthly/klines/{PAIR}/5m/`), December 2020 to October 2026, fetched 16 November 2026. No month was missing.
- **Coins.** Twelve perpetuals listed before 2021: BTC, ETH, BNB, XRP, ADA, DOGE, SOL, LTC, LINK, DOT, AVAX, BCH (against USDT). Fixed before any outcome.
- **In sample:** event days 1 January 2021 to 30 April 2026. **Held out:** 1 May to 31 October 2026, run once after the in-sample result.
- **Hash.** SHA-256 over the twelve series (time, open, high, low, close, volume) `728e169c2460f16360dac85286af153b0580887d30be95068e9b697999d87f67`. The candles are not kept in the repository; the hash identifies them.
- **Days used.** A day counts only if it and the day before each have at least 285 of their 288 candles. XRP, SOL and LTC miss five calendar days in the archive, so each has 1,939 usable days; the others have all 1,946. In all: 23,331 coin-days in sample, 2,208 held out.
- The app draws its levels from Hyperliquid volume, which only goes back 5,000 candles. Binance is the larger market and the one most charts of this method read.

## Definitions

All times UTC. A **day** runs 00:00 to 24:00.

- **The previous day's value area**: VAH, VAL and POC from the previous day's 5-minute candles, by the code the coin chart's Value layer uses (`engines/auction_engine.session_levels`): rows of a round size near 0.02% of the previous close, each candle's volume split evenly over the rows its range touches, the value area grown from the POC two rows at a time towards the side with more volume until it holds 70%.
- **Opened outside**: the day's first price is above VAH (**above**) or below VAL (**below**). Otherwise it **opened inside** (an edge itself is inside).
- **Half-hour bars**: 00:00, 00:30, ... A bar **closes inside** when its last price is between VAL and VAH, edges included.
- **Accepted**, in two readings, each studied on its own:
  - **two closes** (the textbook): two half-hour bars in a row close inside; the moment is the close of the second;
  - **one close** (Chart Champions' guide): one half-hour bar closes inside; the moment is its close.

**A rule event** (one per coin and day at most, in each reading): the day opened outside, was accepted back inside, and had not touched the other edge between 00:00 and that moment. For a day that opened above, the other edge is VAL.

- If it touched the other edge before being accepted, it is counted as "crossed first" and is not an event: there is nothing left to wait for.
- If it was never accepted that day, it is "no acceptance".

**A control event** (one per coin and day at most, in each reading): the day opened inside; a half-hour bar closed outside one edge; later it was accepted back inside by the same reading; and price had not touched the other edge since the start of the bar that first closed outside.

**Outcomes**, from the moment of acceptance to the end of that UTC day:

- **Reached the other edge**: some 5-minute candle traded at or beyond it.
- **The trade**: in at the acceptance close, towards the other edge (short after an open above, long after an open below).
  - Stop: one price row beyond the furthest price of the excursion so far (since 00:00; for a control event, since the bar that first closed outside).
  - Out at the other edge, at the stop, or at the day's last price, whichever comes first. When one 5-minute candle holds both the stop and the edge, it counts as the stop.
  - **Net return** = the price change in the trade's direction, less 0.20% (10 bps a side, all in, the repo's convention). Funding is not counted.

## The three rows and their bars

Each row is computed twice, once per reading of "accepted": six rows in all, each judged on its own.

Days are the unit throughout: the twelve coins move together, so intervals come from resampling event days (10,000 draws, seed 20261116), and halves are the first and second half of the event days by date.

**R1. The claim.** The share of rule events that reached the other edge. It meets the bar only if all of:

1. at least 200 events on at least 100 days;
2. the share is at least 75%;
3. the lower end of its 95% interval is at least 70%;
4. it is at least 70% in each half.

Met: "the rule held: k of n reached the other edge". Not met: the 80% figure is not shown on crypto days, and the measured share is reported.

**R2. The open.** The share for rule events minus the share for control events. It meets the bar only if all of:

1. at least 200 events on at least 100 days in each group;
2. the difference is at least 10 points;
3. the lower end of its 95% interval is above 0;
4. the difference is above 0 in each half.

**R3. The trade.** The mean net return of the rule events' trades. It meets the bar only if all of:

1. at least 200 events on at least 100 days;
2. the mean is above 0;
3. the lower end of its 95% interval is above 0;
4. it is above 0 in each half;
5. it is above 0 on BTC alone.

A row that meets its bar in sample is **confirmed** only if the held-out months agree: R1 at least 70%, R2 a difference above 0, R3 a mean net return above 0. A row that fails in sample stays failed whatever the held-out months show. A result on the other side, however large, is reported only.

The two readings share most of their events, so their rows move together: two looks at one question, not two independent tries.

## Also reported (no verdict)

- The trade before costs, in multiples of the risk taken, how often the stop came first, and the control events' trades.
- How often price reached the POC first, where the entry was beyond it.
- The other edge within 24 hours of acceptance instead of by the day's end.
- By side (above, below), by time of acceptance (00-06, 06-12, 12-18, 18-24), by the value area's width (thirds), by coin, by year.
- A third reading of "accepted": one hourly close inside (the form in the outline the owner supplied, rule 3.1).
- All days, whatever they did: how often a day touched both edges of the previous day's value area, by where it opened.

## Known before running

- **No outcome of these events has been computed.** The code that reads prices after an event (`score`) has run only on made-up candles in the tests.
- My expectation, stated before running: below 80%. The median value area is 2.7% of price wide (counts below), which is a long way for the rest of a day.
- **Counts** (`shape`, in sample; no outcome):
  - 23,331 coin-days. Opened above 5,016, inside 13,575, below 4,740: 42% opened outside.
  - Width of the value area as a share of price: 1.1% at the 10th percentile, 1.7% at the 25th, 2.7% median, 4.4% at the 75th, 6.8% at the 90th.

  | | Two closes | One close |
  |---|---|---|
  | **Rule**: coin-days that opened outside | 9,756 | 9,756 |
  | events | 6,069 (3,048 above, 3,021 below) | 6,874 (3,480 above, 3,394 below) |
  | on days | 1,631 | 1,694 |
  | never accepted | 3,372 | 2,748 |
  | crossed first | 315 | 134 |
  | events per coin (BTC) | 480 to 544 (507) | 529 to 611 (571) |
  | accepted 00-06, 06-12, 12-18, 18-24 | 3,739, 1,100, 831, 399 | 4,675, 985, 811, 403 |
  | days with one coin, two to five, six or more | 408, 854, 369 | 344, 902, 448 |
  | **Control**: coin-days that opened inside | 13,575 | 13,575 |
  | events | 8,987 | 10,158 |
  | on days | 1,760 | 1,802 |
  | never came back | 3,242 | 2,355 |
  | never closed outside | 890 | 890 |
  | crossed first | 456 | 172 |

- **Held out** (counts only): 2,208 coin-days. Two closes: 450 rule events on 146 days, 932 control events on 172 days. One close: 514 on 151 days, 1,043 on 173 days.

## What the bars can see

`power` on made-up outcomes, with this study's events per day (two closes; one close has slightly more), 2,000 runs each. Two cases: the coins' events on a day independent, or all sharing one outcome (the truth is between). The interval there is the normal approximation of the resampling interval.

| True value | Independent | One outcome a day |
|---|---|---|
| **R1**, true share 70% | 0% | 0.1% |
| 75% | 52% | 50% |
| 78% | 100% | 99% |
| 80% | 100% | 100% |
| **R2**, true difference 0 | 0% | 0% |
| 5 points | 0% | 0.7% |
| 10 points | 50% | 50% |
| 15 points | 100% | 99% |
| **R3**, true mean net 0 | 2.7% | 2.2% |
| 0.05% | 74% | 19% |
| 0.10% | 100% | 59% |
| 0.20% | 100% | 99% |

(R3 assumes trade returns spread by 1.5% around their mean, a guess: the real spread is an outcome.)

So R1 separates a true 80% from a true 70% almost surely; R2 sees a gap of 15 points; R3 sees a mean of 0.2% a trade and passes by luck about 1 time in 40 when there is nothing (a little more often across the two readings, which move together).

## Out of sample

Days from 17 November 2026 on, the same code on newly fetched months: `run --from 2026-11-17`. Reported next to the declared rows; at about 95 rule events a month the first clean year adds about 1,100.

## Limits

- Twelve coins that exist today and were liquid throughout. Coins that died are missing; for a question about one day's path this matters less than for returns over months.
- The coins move together. Days are resampled for that, but days in one market phase are not independent either.
- UTC midnight is a clock time, not a market open. A rule made for sessions with an open may behave differently at other cut times; none other is tested here.
- Binance perpetual volume, 5-minute candles. A profile from every trade, or from another exchange, moves the edges a little (docs/reviews/auction-levels-spec.md: 15-minute candles were within 0.25% of 1-minute ones on four coin-days).
- The trade fills at the close of the bar that completes acceptance, at the edge and at the stop exactly. Real fills slip; the 10 bps a side is meant to cover that. Funding is left out (a position held under a day crosses at most three funding times).
- The stop and exits are one mechanical reading of the method. The method as taught leaves entries and stops to judgement.

## Results

Added after the run. Nothing above changed. Any later change is listed under Deviations, with its reason and whether it came before or after the first result.

Computed once on 16 November 2026 by `run` at commit c1e59ae, the commit that holds the final declaration, then `run --holdout` once at the same commit. Inputs: the candles with the hash above.

**No row met its bar. The 80% figure is not shown on crypto days: about 40% of the events reached the other edge, not 80%. Context, not a signal.**

### In sample (1 January 2021 to 30 April 2026)

Brackets are 95% intervals from resampling days.

| | Two closes | One close |
|---|---|---|
| Rule events, on days | 6,069 on 1,631 | 6,874 on 1,694 |
| **R1** reached the other edge | **40.4%** (38.4 to 42.4) | **39.2%** (37.2 to 41.1) |
| first half, second half | 40.0%, 40.7% | 38.8%, 39.6% |
| bar (75%, interval from 70%, halves 70%) | not met | not met |
| Control events, on days | 8,987 on 1,760 | 10,158 on 1,802 |
| control reached the other edge | 43.3% (41.7 to 44.9) | 42.0% (40.5 to 43.6) |
| **R2** rule minus control | **-2.9 points** (-5.3 to -0.5) | **-2.8 points** (-5.1 to -0.6) |
| first half, second half | -4.2, -1.7 | -4.4, -1.3 |
| bar (10 points, interval above 0) | not met | not met |
| **R3** mean net return a trade | **-0.25%** (-0.35 to -0.13) | **-0.26%** (-0.37 to -0.15) |
| first half, second half | -0.20%, -0.30% | -0.23%, -0.29% |
| BTC alone | -0.13% (-0.27 to +0.01), 507 trades | -0.13% (-0.26 to 0.00), 571 trades |
| bar (above 0, interval above 0, BTC above 0) | not met | not met |

- **R1, the claim.** About four events in ten reached the other edge by the day's end. The same in both halves, in every year (37% to 43%) and for every coin (36% to 44%).
- **R2, the open.** Opening outside did not add. Days that opened inside, left and came back reached the other edge a little more often. That is a result on the other side: reported only.
- **R3, the trade.** It lost 0.25% a trade after costs. Before costs it made nothing: -0.05% (-0.15 to +0.07), or -0.03 of the risk taken (-0.07 to +0.01). The stop came before the other edge in 40% of trades (46% with one close).

### Held out (1 May to 31 October 2026), run once

| | Two closes | One close |
|---|---|---|
| Rule events, on days | 450 on 146 | 514 on 151 |
| reached the other edge | 39.8% (32.3 to 47.3) | 38.3% (31.2 to 45.7) |
| control | 42.3% of 932 | 41.2% of 1,043 |
| rule minus control | -2.5 points (-10.4 to +5.3) | -2.9 points (-10.7 to +4.7) |
| mean net return a trade | -0.32% (-0.53 to -0.12) | -0.34% (-0.52 to -0.15) |

The same picture. No row met its bar in sample, so there was nothing to confirm.

### Reported, no verdict (in sample, two closes unless said)

- **The POC first.** Of the 5,488 trades that entered beyond the POC, price traded at the POC by the day's end in 62.8% (61.0 to 64.6). No comparison was declared for this, so it is a description, not a finding.
- **Within 24 hours of acceptance** instead of by the day's end: 47.5% reached the other edge.
- **By time of acceptance.** 00-06: 47.6% of 3,739. 06-12: 35.9% of 1,100. 12-18: 27.0% of 831. 18-24: 12.8% of 399. Less of the day left, less often reached. Net return by the same hours: -0.20%, -0.28%, -0.36%, -0.31%.
- **By the value area's width.** Narrow third: 56.9%. Middle: 41.5%. Wide: 22.7%. Net return: -0.22%, -0.26%, -0.26%. A narrow value area is crossed more often and pays less each time.
- **By side.** Above (shorts): 41.9%, net -0.18%. Below (longs): 38.8%, net -0.31%.
- **By year.** 2021: 38.2%. 2022: 41.1%. 2023: 41.3%. 2024: 42.6%. 2025: 39.3%. 2026 to April: 37.3%.
- **By coin.** BTC 44.0%, ETH 38.9%, BNB 41.7%, XRP 37.9%, ADA 36.4%, DOGE 35.9%, SOL 43.5%, LTC 40.5%, LINK 43.9%, DOT 41.6%, AVAX 40.0%, BCH 39.5%. Net return from -0.11% (BNB) to -0.37% (LTC): negative for all twelve.
- **When the other edge was reached**, it took a median of 370 minutes from acceptance.
- **Control events' trades**: -0.09% net (-0.15 to -0.02).
- **One hourly close** as acceptance: 39.5% of 6,512 (37.5 to 41.5), net -0.25%. Held out: 38.6% of 487, net -0.33%.
- **All days, whatever they did.** 36.1% of the 23,331 coin-days touched both edges of the previous day's value area. Days that opened outside: 29.1% of 9,756. Days that opened inside: 41.1% of 13,575. Held out: 35.5%, 27.7%, 39.7%.

### Checks

- BTC was recounted with separately written code (plain loops over days and half hours, its own value-area routine): 1,946 days, 798 opened outside, 507 events, 223 reached the other edge, 44.0%. The same as the study's code.
- The run scores exactly the events `shape` counted (tested), and `shape` reads nothing after an event's time.

### What this does and does not say

- It says the 80% figure does not carry over to UTC days on these twelve perpetuals, in any of three readings of "accepted", and that the open being outside the value area did not help.
- It does not test the method as traded: with judgement, confluence, a chosen session, or only after "range days". The community script's wording has that last condition ("if the previous day is a range day"); no definition of a range day was found, so none was applied. The nearest reported figure is the narrow third of value areas: 56.9%, still not 80%.
- It does not test sessions with a real open. Chart Champions' site describes CME-style hours for Bitcoin (regular hours 13:30 to 20:15 UTC). The rule on those sessions would be a new declared study.
- The 62.8% for the POC is the one figure pointing to a smaller move that happens more often than not. It was not compared with anything. A study of it has to be declared first and judged on days after 16 November 2026, because these days have now been seen.

### Deviations

None after the first result. Before any result, and after the declaration was first committed (8236c9d), one line changed: the note on the videos was completed (c1e59ae). No definition, row or bar changed.
