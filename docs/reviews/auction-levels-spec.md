# Auction levels: the method and what the chart draws (spec, 16 November 2026)

The owner asked for the trading method taught by Daniel of Chart Champions (value areas, points of control, market structure, order flow) to be written down as exact rules and shown on the coin chart.

This document does three things:

1. lists each rule of the method with where it comes from and how far that source has been checked;
2. gives the exact definition the app uses for the rules it draws (the coin chart's **Value** layer);
3. lists what is not drawn yet and the studies to declare before any rule becomes more than a drawing.

Nothing here is a signal. The Value layer is display only: no scanner signal, alert or executor code reads it. Seven studies have been run (below). No trade paid; one comparison row was confirmed.

## Sources, and how far each is checked

| Tag | Source | State |
|---|---|---|
| O | The outline the owner supplied on 16 November 2026: a summary of the videos written by Gemini, with rules tagged Mechanical, Approximated or Discretionary. | **Not checked against the videos.** Its "source" fields name course modules ("Volume Profile Masterclass", "Daily Routine & Session Preparation Videos") with no video title or timestamp, so no rule in it can be traced to a statement yet. |
| P | Two community TradingView scripts written from the videos: [Chart Champions Part 2: CCV, IBs, POCs](https://www.tradingview.com/script/dkGe7rmo-Chart-Champions-Part-2-CCV-IBs-POCs) and [Chart Champions Value, Points of Interest](https://in.tradingview.com/script/AHNKTwcK-Trading-Ideas-Chart-Champions-Value-Points-of-Interest). | Read on 16 November 2026. They give levels and session times, not entries, stops or exits. |
| A | Standard Auction Market Theory (Steidlmayer; Dalton, *Mind Over Markets*), which the method is built on. | General knowledge, not specific to Daniel. |
| S | Chart Champions' own public guides on chartchampions.com (written by "Chart Champions Team", not signed by Daniel). | Read on 16 November 2026 **as a search engine's excerpts only**: the site refuses automated readers, so no wording could be checked on the page itself. |

**The videos could not be read.** On 16 November 2026 YouTube refused transcript requests from the research machine (it asks for a sign-in) and the public pages' transcript panel loaded once and then stayed empty; no way around that was tried. To move a rule from O to checked, it still needs the video and the timestamp where it is said: the owner can paste transcripts, or name the videos.

## What Chart Champions' own guides add (source S)

| Topic | What the excerpts say | Effect here |
|---|---|---|
| Acceptance | "A good signal for acceptance is a 30-minute candle close back inside the range." More time inside means more acceptance. | One 30-minute close is the second declared reading in the 80% rule study. |
| Failed auction against SFP | An SFP is quick: a wick beyond a level and a close back inside on the same candle. A failed auction "tends to linger": price can spend hours beyond the level before closing back inside. | Rule 3.1's signal candle is a 30-minute close in their words, not the outline's 1-hour close. |
| Exits | "We usually aim to take profit at the POC": first exit at the POC of the range's profile, second at its VAH (or VAL), part of the position each time. | The study reports how often the POC was reached. |
| SFP stop | "The invalidation of the SFP setup is just above the new high or below the new low recently made." | Matches the study's stop. |
| Entry | Wait for the reaction: a rejection or a retest after price reclaims the level. "Without that trigger ... a line on the chart, not a trade." | Entries stay a matter of judgement; nothing is marked on the chart. |
| Sessions for Bitcoin | CME-style hours: regular hours 13:30 to 20:15 UTC, the overnight session before them, with the overnight high and low marked as places a liquidity grab can happen. | Explains the outline's ONH and ONL (rule 2.1). Not drawn; a study on these sessions would be new. |
| Initial Balance | The range of the first hour of trading. A narrow one tends to be extended; a wide one tends to hold the day. | Drawn on 1H from 00:00 UTC. |
| Open against value | "The relationship between the daily open and the previous day's value areas is a crucial edge." | The claim tested in the 80% rule study. |
| Fibonacci | The band between 0.618 and 0.66 ("Champion Channel"). | Not drawn. |
| Confluence | Two or more factors aligning; a volume-profile level on a horizontal level, confirmed by price action, is what they call an A+ trade. | Study S5. |
| Open interest and delta | Not entry triggers on their own: "an extra layer of confluence once price reaches your level". | Study S4. |
| Risk | At most 1% of the account a trade; stop for the day after three losing trades; reward at least twice the risk. | Not used by the app. |

The "CCV 2.0" manual, the cheat sheets and the daily level sheets are for members only and were not read.

## The rules

"Drawn" means the Value layer shows it today. "Proposed" definitions are mine: they turn a rule that needs judgement into one a study can test, and they are fixed only when that study is declared.

| # | Rule (as the outline states it) | Outline's tag | Sources | Exact definition | State |
|---|---|---|---|---|---|
| 1.1 | Sort the market into trending or balanced before trading a value-area edge. Trending: distributions migrate; trade pullbacks. Balanced: price rotates between the edges; fade them. | Mechanical / Discretionary | O, A | Proposed. Balanced: today's value area overlaps at least half of yesterday's. Migrating: the daily POC steps the same way three days running and the overlap is under half. | Not drawn. Thresholds to be fixed in a study. |
| 1.2 | The value area holds about 70% of a session's volume. VAH and VAL are its edges; the POC is the price with the most volume. | Mechanical | O, P, A | See "Exact definitions" below. | **Drawn.** |
| 1.2 | The POC "acts as a price magnet". | (claim) | O, P | A claim about what follows, not a definition. | Study S2. |
| 2.1 | Mark the previous day's high and low (PDH, PDL). | Mechanical | O, P | High and low of the previous UTC day, from daily candles. | **Drawn.** |
| 2.1 | Mark the overnight high and low (ONH, ONL). | Mechanical | O only | Not defined for crypto: a market open 24 hours has no overnight session. The public scripts use the Initial Balance instead (high and low of the first hour after 00:00 UTC), which the 1H chart draws. | Not drawn. Needs the video to say which session he means. |
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
| Initial Balance (first hour after 00:00 UTC) | **Drawn on the 1H chart** (IB high, IB low). On 4H a day is six candles and the first hour cannot be seen. |
| Daily, weekly and monthly VWAP | Not drawn. |
| "CCV": the 80% rule for a day opening outside the previous day's value area | Study S1. |

## Exact definitions (the Value layer, engine version `auction-1`)

Code: `backend/engines/auction_engine.py`, served by `backend/auction.py` at `/api/auction/{symbol}`, drawn by `frontend/src/components/ValueAreas.js`.

**Sessions** are UTC. A day starts at 00:00, a week on Monday 00:00, a month on its first day.

**Candles.** Hyperliquid candles one step below the chart's:

| Chart | Sessions drawn | Outer sessions (ticks only) | Candles read |
|---|---|---|---|
| 1H | days | weeks | 15-minute, 30 days (one answer shared with 4H) |
| 4H | days | weeks | 15-minute, 30 days |
| 1D | weeks | months | 1-hour, 180 days |

The 1H chart is a view of the chart only (a 1H switch in the chart's toolbar; its 600 candles are read from Hyperliquid on demand and kept for 2 minutes). The scan, its signals, the trend line and the ribbon stay on 4H and 1D.

**Profile of a session.**

1. Price rows of a fixed height: the largest of 1, 2, 2.5 or 5 times a power of ten that is at most a set fraction of the last price (0.02% for days, 0.05% for weeks, 0.1% for months). For BTC near 65,000 a daily row is 10.
2. Each candle's volume is split evenly between the rows its low-to-high range touches.
3. **POC**: the row with the most volume, reported at the row's centre. Ties go to the row nearest the middle of the session's range.
4. **Value area**: start at the POC row. Compare the two rows above with the two rows below, add the pair with more volume (ties go up), and repeat until the area holds 70% of the session's volume. **VAH** is the top of its highest row, **VAL** the bottom of its lowest.

A session the candles start inside is left out.

**Naked POC.** A finished session's POC is naked until a later candle's range includes it. The running session's POC moves and is never naked.

**Opens and prior extremes** come from the stored daily candles: today's open, the previous day's high and low, this week's and this month's open on 1H and 4H; this week's and month's open and the previous week's high and low on 1D. On 1H, the **Initial Balance** is added: the high and low of the running day's first hour, from the 15-minute candles.

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
- right of the last candle, labelled ticks: the opens, the previous day's (or week's) high and low, the previous outer session's VAH, POC and VAL (PW on 1H and 4H, PM on 1D), older outer POCs still naked (W nPOC, M nPOC), and on 1H the first hour's high and low (IB high, IB low).

- in violet, the latest major swing as a dotted line and a band over its 0.618 to 0.66 retracement (Chart Champions' "Champion Channel"), fainter once price has traded into it. Its label adds "POC" when a point of control sits in the band. Swings come from the stored daily candles, so this costs no extra request: a swing high is confirmed once a later day's low is 3 daily ATRs under it (lows mirror), and a leg is shown once it is 6 ATRs tall and until price trades beyond its start (`engines/auction_engine.fib_zones`).

The layer says what happened and where. It does not mark setups, entries or exits.

## Cost

- No candles are stored and nothing runs in the background. A build happens when someone turns the layer on.
- Each answer (about 10 KB) is kept for 15 minutes, the newest 48 at most: under 1 MB.
- A build costs 68 (1H and 4H, shared) or 92 (1D) of Hyperliquid's request weight, and the 1H chart's candles 30. Together they have their own share of 240 a minute, about three new charts a minute; beyond that the toggle reads "Value: busy" (or the 1H chart says so) and the page tries again after 30 seconds. The scan's share is untouched.
- The endpoint is in the "exchange" rate-limit class, like `/api/chart`.

## Studies (all run on 16 November 2026)

Each was declared, with its rules and bars, before any outcome was computed. Without a result that clears its bar, a finding reads "context, not a signal".

| # | Question | Result |
|---|---|---|
| S1 | The 80% rule on UTC days: a day opens outside the previous day's value area and comes back inside. | About 40% reached the other edge, not 80%. Opening outside did not help. The trade lost 0.25%. **No bar met.** |
| S2 | Naked POCs: is price drawn to them, more than to a price as far away on the other side? | The POC was reached first in 51.5% of fresh races and 48.7% of old ones. **No bar met.** Most POCs are traded again soon (69% within a day), because most are near price. |
| S3 | Accepted outside the value area: does price go on? | The trade lost 0.14%; before costs +0.06%. **No bar met.** |
| S4 | Sweeps of the previous day's high and low: does fading them pay, and do open interest and delta help? | The fade lost 0.18%. A flush or absorption made no difference. **No bar met.** |
| S5 | Confluence: is a sweep worth more with other levels at the same price? | No difference (-0.17% against -0.18%). **No bar met.** |
| S6 | The 80% rule on New York hours (09:30 to 16:15). | 34% to 39% reached the other edge. The trade lost 0.18%. **One row met its bar and was confirmed**: opening outside did add there (39% against 29% for sessions that opened inside). It is not a trade. |

| S7 | The 0.618 to 0.66 retracement zone of major swings (the band the chart draws): does price turn there, more than at other depths, and more with a weekly or monthly POC in it? | Price turned in 46.6% of 1,602 touches, the same as at other depths (45% to 51%). A POC in the zone made no difference. The trade made nothing. **No bar met.** |

S1: docs/reviews/value-area-rule-study.md. S2 to S6: docs/reviews/auction-level-studies.md. S7: docs/reviews/fib-zone-study.md (71 coins, March 2021 to July 2025, with November 2025 to July 2026 held out).

Data: Binance futures 5-minute candles (with taker buy volume) and 5-minute open interest for twelve coins, January 2021 to April 2026, with May to October 2026 held out. Hyperliquid serves only the latest 5,000 candles per series, too few for a study.

What the studies do not test: the method as traded, with judgement over which levels and reactions to take. They test whether the named levels and triggers, taken every time, carry an edge.

## Open

- The videos: their transcripts, to check the O rules against what Daniel says. docs/reviews/auction-video-brief.md says which videos, what to look for and the form of the answer.
- The members' "CCV 2.0" manual: it would say how Chart Champions state the 80% rule today (which session, what counts as a range day).
