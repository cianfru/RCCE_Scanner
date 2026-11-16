# Auction levels: the method and what the chart draws (spec, 16 November 2026)

The owner asked for the trading method taught by Daniel of Chart Champions (value areas, points of control, market structure, order flow) to be written down as exact rules and shown on the coin chart.

This document does three things:

1. lists each rule of the method with where it comes from and how far that source has been checked;
2. gives the exact definition the app uses for the rules it draws (the coin chart's **Value** layer);
3. lists what is not drawn yet and the studies to declare before any rule becomes more than a drawing.

Nothing here is a signal. The Value layer is display only: no scanner signal, alert or executor code reads it. No study has been run; no outcome has been computed.

## Sources, and how far each is checked

| Tag | Source | State |
|---|---|---|
| O | The outline the owner supplied on 16 November 2026: a summary of the videos written by Gemini, with rules tagged Mechanical, Approximated or Discretionary. | **Not checked against the videos.** Its "source" fields name course modules ("Volume Profile Masterclass", "Daily Routine & Session Preparation Videos") with no video title or timestamp, so no rule in it can be traced to a statement yet. |
| P | Two community TradingView scripts written from the videos: [Chart Champions Part 2: CCV, IBs, POCs](https://www.tradingview.com/script/dkGe7rmo-Chart-Champions-Part-2-CCV-IBs-POCs) and [Chart Champions Value, Points of Interest](https://in.tradingview.com/script/AHNKTwcK-Trading-Ideas-Chart-Champions-Value-Points-of-Interest). | Read on 16 November 2026. They give levels and session times, not entries, stops or exits. |
| A | Standard Auction Market Theory (Steidlmayer; Dalton, *Mind Over Markets*), which the method is built on. | General knowledge, not specific to Daniel. |

To move a rule from O to checked, it needs the video and the timestamp where it is said. That needs either the list of videos or their transcripts.

## The rules

"Drawn" means the Value layer shows it today. "Proposed" definitions are mine: they turn a rule that needs judgement into one a study can test, and they are fixed only when that study is declared.

| # | Rule (as the outline states it) | Outline's tag | Sources | Exact definition | State |
|---|---|---|---|---|---|
| 1.1 | Sort the market into trending or balanced before trading a value-area edge. Trending: distributions migrate; trade pullbacks. Balanced: price rotates between the edges; fade them. | Mechanical / Discretionary | O, A | Proposed. Balanced: today's value area overlaps at least half of yesterday's. Migrating: the daily POC steps the same way three days running and the overlap is under half. | Not drawn. Thresholds to be fixed in a study. |
| 1.2 | The value area holds about 70% of a session's volume. VAH and VAL are its edges; the POC is the price with the most volume. | Mechanical | O, P, A | See "Exact definitions" below. | **Drawn.** |
| 1.2 | The POC "acts as a price magnet". | (claim) | O, P | A claim about what follows, not a definition. | Study S2. |
| 2.1 | Mark the previous day's high and low (PDH, PDL). | Mechanical | O, P | High and low of the previous UTC day, from daily candles. | **Drawn.** |
| 2.1 | Mark the overnight high and low (ONH, ONL). | Mechanical | O only | Not defined for crypto: a market open 24 hours has no overnight session. The public scripts use the Initial Balance instead (high and low of the first hour after 00:00 UTC). | Not drawn. Needs the video to say which session he means. |
| 2.1 | Mark naked POCs: POCs price has not revisited. | Mechanical | O, P | A finished session's POC until a later candle's low-to-high range includes it. | **Drawn.** |
| 2.2 | Profile shape gives bias: P (volume near the top), b (near the bottom), bell (balanced). | Approximated | O, A | Proposed. P: the POC is in the top third of the session's range; b: the bottom third; bell: otherwise. | Not drawn. |
| 3.1 | Setup A, failed auction. Price pushes beyond VAH or VAL (often sweeping PDH or PDL), a 1-hour candle closes back inside the value area with a rejection wick and high volume. Enter on that close, stop beyond the wick, exit at the POC or the opposite edge. | Mechanical | O, A; P for the "80% rule" form (a day that opens outside the previous day's value area) | Proposed. A 1-hour candle whose high is above the previous day's VAH and whose close is below it (mirror at VAL). "Rejection wick": the wick beyond the level is at least half the candle's range. "High volume": at least 1.5 times the median of the previous 20 candles. | Not drawn. Studies S1 and S3 first. |
| 3.2 | Setup B, acceptance. Price leaves the value area and builds volume outside; a retest of the broken edge holds. Enter on the retest. | Discretionary | O, A | Proposed. Two 1-hour closes in a row outside the previous day's value area, and the running day's POC is outside it too. | Not drawn. Study S3. |
| 4.1 | Confirm entries at the edges with order flow: CVD divergence, stacked imbalances and unfinished auctions on a footprint chart. | Approximated | O only | CVD can be computed from taker buy and sell volume (Binance candles carry it; the app already reads CoinGlass's). Footprint charts need every trade and are not feasible within the hosting budget. | Not built. Study S4 for CVD and open interest. |
| 5.1 | Stops go behind the structure that proves the trade wrong; reward is measured edge to edge. | Mechanical | O, A | Used as the outcome definition of the studies: stop beyond the rejection wick, exits at the POC and the opposite edge. | Not drawn. |

In the public scripts but not in the outline:

| Level | State |
|---|---|
| Daily, weekly and monthly opens | **Drawn** (D open, W open, M open). |
| Previous day's and previous week's midpoint (EQ) | Not drawn. |
| Initial Balance (first hour after 00:00 UTC) | Not drawn: the chart's shortest candle is 4 hours. |
| Daily, weekly and monthly VWAP | Not drawn. |
| "CCV": the 80% rule for a day opening outside the previous day's value area | Study S1. |

## Exact definitions (the Value layer, engine version `auction-1`)

Code: `backend/engines/auction_engine.py`, served by `backend/auction.py` at `/api/auction/{symbol}`, drawn by `frontend/src/components/ValueAreas.js`.

**Sessions** are UTC. A day starts at 00:00, a week on Monday 00:00, a month on its first day.

**Candles.** Hyperliquid candles one step below the chart's:

| Chart | Sessions drawn | Outer sessions (ticks only) | Candles read |
|---|---|---|---|
| 4H | days | weeks | 15-minute, 30 days |
| 1D | weeks | months | 1-hour, 180 days |

**Profile of a session.**

1. Price rows of a fixed height: the largest of 1, 2, 2.5 or 5 times a power of ten that is at most a set fraction of the last price (0.02% for days, 0.05% for weeks, 0.1% for months). For BTC near 65,000 a daily row is 10.
2. Each candle's volume is split evenly between the rows its low-to-high range touches.
3. **POC**: the row with the most volume, reported at the row's centre. Ties go to the row nearest the middle of the session's range.
4. **Value area**: start at the POC row. Compare the two rows above with the two rows below, add the pair with more volume (ties go up), and repeat until the area holds 70% of the session's volume. **VAH** is the top of its highest row, **VAL** the bottom of its lowest.

A session the candles start inside is left out.

**Naked POC.** A finished session's POC is naked until a later candle's range includes it. The running session's POC moves and is never naked.

**Opens and prior extremes** come from the stored daily candles: today's open, the previous day's high and low, this week's and this month's open on 4H; this week's and month's open and the previous week's high and low on 1D.

**How close candle-built profiles are.** A profile built from candles is an approximation of one built from every trade. One check, on two finished days (14 and 15 November 2026) of BTC and ETH on Hyperliquid, against the same days built from 1-minute candles:

| Candles | Largest difference in VAH, VAL or POC |
|---|---|
| 15-minute | 0.25% |
| 1-hour | 0.42% |

Four coin-days is a small sample. Levels also differ from charts that read another exchange's volume (Binance, Bybit).

## What the chart draws

The coin chart has a **Value** toggle next to Wallet levels, off until turned on; the choice is remembered. With it on:

- a band over each session's value area and a gold line at its POC;
- a dashed gold line running on from each naked POC;
- dashed grey lines carrying the last finished session's VAH and VAL forward;
- on the left, volume by price of the sessions in view (the POC row in gold, the value-area rows brighter);
- right of the last candle, labelled ticks: the opens, the previous day's (or week's) high and low, the previous outer session's VAH, POC and VAL (PW on 4H, PM on 1D), and older outer POCs still naked (W nPOC, M nPOC).

The layer says what happened and where. It does not mark setups, entries or exits.

## Cost

- No candles are stored and nothing runs in the background. A build happens when someone turns the layer on.
- Each answer (about 10 KB) is kept for 15 minutes, the newest 48 at most: under 1 MB.
- A build costs 68 (4H) or 92 (1D) of Hyperliquid's request weight. The layer has its own share of 240 a minute, about three new charts a minute; beyond that the toggle reads "Value: busy" and the page tries again after 30 seconds. The scan's share is untouched.
- The endpoint is in the "exchange" rate-limit class, like `/api/chart`.

## Studies to declare (none run)

Each gets its own declaration, with its rules and bar, committed before any outcome is computed. Without a result that clears its bar, a finding reads "context, not a signal".

| # | Question |
|---|---|
| S1 | The 80% rule: a day opens outside the previous day's value area and comes back inside. How often does it reach the other edge, against days that open inside? |
| S2 | Naked POCs: are they traded back to more often than other prices at the same distance? |
| S3 | Value-area edges: what followed acceptance outside (rule 3.2) against rejection back inside (rule 3.1)? |
| S4 | Sweeps of PDH, PDL, VAH and VAL: does the outcome differ by open interest falling or rising, and by CVD divergence? |
| S5 | Confluence: is the reaction larger where several levels sit at one price? |

Data that can carry them: Binance futures 1-minute candles (they include taker buy volume, so CVD) and 5-minute open interest, both public at data.binance.vision and going back years. Hyperliquid serves only the latest 5,000 candles per series, too few for a study.

## Open

- The videos: a list of them, or their transcripts, to check the O rules and fill in rule 2.1's overnight levels.
- A 1-hour chart: the daily levels are intraday tools. On the 4-hour chart a day is six candles, and the Initial Balance and the 1-hour signal candle of rule 3.1 cannot be seen.
