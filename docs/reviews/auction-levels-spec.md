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
| C | Two of Chart Champions' member cheat sheets, supplied by the owner on 18 November 2026: "Entry Triggers" (9 pages) and "Liquidity" (15 pages). | **Read in full.** Summarised below in our own words; the files are not kept in the repository. |

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

The "CCV 2.0" manual, the other cheat sheets and the daily level sheets are for members only and were not read.

## What the two cheat sheets add (source C)

They cover what to wait for once price reaches a level, and where the stop goes. Nothing in them says to trade the touch of a level.

| Topic | What the sheets say | Effect here |
|---|---|---|
| Where stops rest ("liquidity") | Longs put their stops under a support level, shorts over a resistance level. Most stops sit at the edges of a range or consolidation, at swing highs and lows. | **Drawn**: each swing high and low of the chart's structure is carried on as a level until price trades through it. |
| Swing failure (SFP) | Price swings beyond a significant high or low and the candle closes back inside the previous range. Also called a stop hunt or liquidity grab. Preferred on 5 to 30 minute candles. No close back, no setup. The setup is wrong once price returns to the SFP candle's extreme. | **Drawn** as a sweep, on hourly closes (the chart's candles). The plain fade was tested on the previous day's high and low (S4). |
| Failed auction | The same, but price stays beyond the level for hours or days before it comes back. Preferred on 30 minutes and 4 hours; "the higher the timeframe the more follow-through". Preferred when open interest rose on the breakout. Daniel likes it when price is in a sideways range. | **Drawn** as a sweep that took more than an hour. |
| The order of an entry | Wait for the level to be hit. Then, on the 1 or 5 minute chart: check volume, delta and open interest; wait for a change of market structure; on the retest, check for a CVD divergence. | Study S9 (declared separately). |
| Market structure change | After resistance is hit: a lower high, then a break of the low between. That break is the entry; the stop goes above the high. Mirror at support. | Study S9. |
| Retest with a CVD divergence | After the level is hit, look for trapped traders in the order flow; on the retest, a CVD divergence is the entry. Called the more aggressive entry. | Study S9, with candle-level delta. Trapped traders need a footprint chart, which is not feasible here. |
| When not to enter | Open interest falls on the pullback from the level, then rises again on the retest with new positions in the direction of the break: no fade. | Study S9. |
| Mini range | The same triggers inside a small range on a low timeframe, often when price stops short of a key level. | Not defined well enough to test. |
| 3rd touch | First pivot: a key high or low. Second: a swing failure or failed auction of it. Third: the retest of the first pivot's price, which is the entry; the stop goes beyond the sweep's candle. | Study S9. |
| Exits | Depend on context: first at the POC of the range (or of a fixed range), second at the far side of the range; a structure change in the trade's favour lets the rest run. After the first exit the stop may go to the entry. | The studies exit at the range's POC. |
| Their numbers | Two only, "collected during a bear market", with no sample size: 26% and 52% for a reversal at the last low or high before a swing failure. On both pages the words and the picture disagree about which side is meant. | Not used. |

Every chart in the sheets is an example that worked. No setup comes with a rate of success.

## The rules

"Drawn" means the Value layer shows it today. "Proposed" definitions are mine: they turn a rule that needs judgement into one a study can test, and they are fixed only when that study is declared.

| # | Rule (as the outline states it) | Outline's tag | Sources | Exact definition | State |
|---|---|---|---|---|---|
| 1.1 | Sort the market into trending or balanced before trading a value-area edge. Trending: distributions migrate; trade pullbacks. Balanced: price rotates between the edges; fade them. | Mechanical / Discretionary | O, A | Proposed. Balanced: today's value area overlaps at least half of yesterday's. Migrating: the daily POC steps the same way three days running and the overlap is under half. | Not drawn. Thresholds to be fixed in a study. |
| 1.2 | The value area holds about 70% of a session's volume. VAH and VAL are its edges; the POC is the price with the most volume. | Mechanical | O, P, A | See "Exact definitions" below. | **Drawn.** |
| 1.2 | The POC "acts as a price magnet". | (claim) | O, P | A claim about what follows, not a definition. | Study S2. |
| 2.1 | Mark the previous day's high and low (PDH, PDL). | Mechanical | O, P | High and low of the previous UTC day, from daily candles. | **Drawn.** |
| 2.1 | Mark the overnight high and low (ONH, ONL). | Mechanical | O only | Not defined for crypto: a market open 24 hours has no overnight session. The public scripts use the Initial Balance instead (high and low of the first hour after 00:00 UTC), which the 1H chart draws. | Not drawn. Needs the video to say which session he means. |
| 2.1 | Mark naked POCs: POCs price has not revisited. | Mechanical | O, P | A finished session's POC until a later candle's low-to-high range includes it. | Drawn in version 1. Not drawn since profiles follow moves (version 2). |
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

## Exact definitions (the Value layer, engine version `auction-3`)

Code: `backend/engines/auction_engine.py`, served by `backend/auction.py` at `/api/auction/{symbol}`, drawn by `frontend/src/components/ValueAreas.js`.

**What is profiled: swings, not calendar sessions** (owner, 17 November 2026, with a chart of a profile drawn from a low to a high: "can you do it for low to high points instead?"). Version 1 drew a profile per UTC day (1H, 4H) or week (1D). Version 2 draws one per move: a rise from a swing low to the next swing high, a fall from a high to the next low, and the move still running.

- **Swings** are the daily ones the retracement zone uses: a high is a swing once price has come back 3 daily ATRs from it (lows mirror).
- **A pullback of less than half a move does not end it, when the move then goes on.** A rise, a dip that gives back under 50% of it, then a higher high: one rise to the higher high. Falls mirror. Checked on BTC: the rise of August and September 2026 (62,237 to 87,471) is one move although it dipped from 82,268 to 74,903 on the way (37% of the rise so far), as on the owner's chart; its POC is 77,263 against about 77,200 there.
- **A move's candles** run from the hourly candle with the lowest low of the swing low's day (the highest high of a swing high's day) to the hourly candle of the next swing. The running move ends at the last candle. A move the candles start inside is left out.
- **Candles read:** Hyperliquid's 1-hour candles, 180 days. One answer serves a coin's 1H, 4H and 1D charts.
- The running move changes as it goes: its profile grows with each candle, and a move that looked finished is joined to the next one when price goes beyond its end after a pullback of under half.

**Swing levels and sweeps** (version 3, 18 November 2026; owner, on the cheat sheets: "are we going to be able to draw the levels they are referring to, to the charts?"). `engines/auction_engine.swing_levels`.

- **A level** is the high or low of a swing point of the structure above, as that structure stood at a day's close: only swings confirmed by then, with the pullbacks merged by then. It is a level from the next day, for 180 days, until price trades beyond it. A pullback low or high stops being a level when the move runs on from it and the structure drops it.
- **Taken:** the first hourly candle that trades beyond the level.
- **Swept:** an hourly candle closes back inside the level within 72 hours of the taking candle's open (that candle included). Within the hour is what the sheets call a swing failure; later, a failed auction. No close back within 72 hours is a break.
- Each day's extremes are read from the chart's own hourly candles where they cover the day, so a level is taken on the candles the chart shows even when the daily candles come from another exchange.
- Hourly closes, not the 5 to 30 minute candles the sheets prefer: the layer reads hourly candles only.

**Sessions** (what version 1 drew, and what the studies below measured) are UTC. A day starts at 00:00, a week on Monday 00:00, a month on its first day. Their code stays in the engine for the studies.

**Profile of a move or a session.**

1. Price rows of a fixed height: the largest of 1, 2, 2.5 or 5 times a power of ten that is at most a set fraction of the last price (0.05% for moves and weeks, 0.02% for days, 0.1% for months). For BTC near 65,000 a move's row is 25.
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

**One Layers control** (owner, 18 November 2026: "the chart itself, the main point of interest", the rest in "a drop-down menu" with "multiple choices"). Everything that can be drawn over the candles sits behind it, on every screen size. It opens a list of switches in three groups, and any number can be on:

| Group | Switches |
|---|---|
| Price | Swing profiles, Levels, Pullback zone, Opens, prior highs and lows |
| Trend | Averages (the 200-day average and the BMSB), Trend line, Ribbon, Patterns |
| Traders | Trader entries, Wallet levels |

- The button shows how many are on. **Clear all** leaves the candles alone.
- Averages is on until turned off; the rest are off until turned on. The four Price switches, Averages and Trader entries are remembered.
- The four Price switches are the parts of what was one Value switch, and one answer serves them: one request with any of them on, none with all off. Someone who had Value on keeps the profiles, the pullback zone and the opens.
- One (i) beside the control explains every switch.
- On a desktop the coin page's chart takes most of the window's height (620 to 900 px, in steps of 40).

**Swing profiles.** With it on:

- a box over each move, from its first candle to its last and from its low to its high (the running move fainter);
- along the box's left edge, the move's volume by price (the POC row in gold, the value-area rows brighter); when that edge is scrolled out of view, the bars sit at the pane's left edge;
- across the box, a gold line at the move's POC and grey lines at its VAH and VAL;
- the last finished move's three lines run on, dashed, to the right edge, with the tags VAH, POC and VAL;
- **the POC rule** (owner, 17 November 2026: "if price goes below VAL, trade from POC. vice versa"): while the last price is under that move's VAL the POC tag reads "POC · short", and over its VAH "POC · long"; the tip gives the rule in words. Shown as the method's rule, not as a signal: its test (`docs/reviews/poc-rule-study.md`) met no bar.

**Opens, prior highs and lows.** Right of the last candle, labelled ticks: the opens, the previous day's high and low (the previous week's on 1D), and on 1H the first hour's high and low (IB high, IB low).

**Pullback zone.** In violet, the latest major swing as a dotted line and a band over its 0.618 to 0.66 retracement (Chart Champions' "Champion Channel"), fainter once price has traded into it. Its label adds "POC" when a point of control sits in the band. Swings come from the stored daily candles, so this costs no extra request: a swing high is confirmed once a later day's low is 3 daily ATRs under it (lows mirror), and a leg is shown once it is 6 ATRs tall and until price trades beyond its start (`engines/auction_engine.fib_zones`).

**Levels** (owner, 18 November 2026: these should "only appear when you press the levels button", because the charts were getting busy). With it on:

- **swing levels** (the cheat sheets' "liquidity"): each swing high and low carried on as a dotted line from its candle, to the right edge while price has not traded through it, otherwise to the candle that did, fainter;
- **a ring** on that candle marks a sweep: price traded through and an hourly candle closed back within three days. A line that ends without a ring was broken;
- the tip says where price turned, how far it went beyond and how long it took to close back.

Tapping or hovering a box, a line, a ring or a tag says what it is in plain words, with its own prices, and how the method's traders use it. **The tips carry no study results** (owner, 18 November 2026: "Just give an explanation of what it is ... do not include the testing results"). What each study found stays in the table below and in its own document.

The layers say what happened and where. A ring is a sweep that has happened; it does not mark an entry or an exit.

## On TradingView

`tradingview/reflex_levels.pine` (owner, 18 November 2026: "is there a way where we can create a TV indicator?") draws the Levels, the last finished swing's VAH, POC and VAL with the POC rule's tag, and the pullback zone, by the rules above. Paste it into TradingView's Pine Editor and add it to a chart.

- **The same rules, from hourly candles.** Before it was written, its logic was modelled line by line in Python and run on the saved BTC, ETH and SOL candles: the same levels, takes, sweeps and extremes as `swing_levels`, the same last swing's POC, VAH and VAL, and the same pullback zones as the app.
- **The exchange decides the numbers.** The app reads Hyperliquid's candles. On another exchange's chart the swings and levels are found the same way, on that exchange's prices.
- **Under 1 hour** the chart's candles are joined into hours, so a take or a sweep shows once its hour has closed. Where TradingView has no hourly candles for an old bar, the bar itself stands in for them.
- **Differences from the app:** a swing confirmed by the running day shows from the next day; only the last finished swing's profile is drawn (TradingView's own Fixed Range Volume Profile draws any other); the opens and prior highs and lows are left to TradingView's own tools.
- Hovering a ring or a tag shows what it is and how the method uses it, with no study results.

## Cost

- No candles are stored and nothing runs in the background. A build happens when someone turns the layer on.
- Each answer (3 to 5 KB with the swing levels, which need no extra request) is kept for 15 minutes, the newest 48 at most: under 250 KB.
- A build costs 92 of Hyperliquid's request weight and serves the coin's three charts (version 1 needed 68 for 1H and 4H and another 92 for 1D). The 1H chart's candles cost 30. Together they have their own share of 240 a minute; beyond that the toggle reads "Value: busy" (or the 1H chart says so) and the page tries again after 30 seconds. The scan's share is untouched.
- The endpoint is in the "exchange" rate-limit class, like `/api/chart`.

## Studies (S1 to S7 run on 16 November 2026, S8 on 17 November, S9 on 18 November)

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
| S8 | The POC rule on swing profiles (17 November 2026; `docs/reviews/poc-rule-study.md`): after a daily close under the last finished swing's VAL, sell at its POC; after a close over its VAH, buy at its POC. Stop at the far edge of the value area, exit at the edge price broke. | +0.32% a trade after costs on 2,045 trades (-0.39 to +1.00), +0.41% on 240 held-out trades (-0.36 to +1.23). The first rule here that did not lose after costs, and not told from zero. **No bar met.** |

| S9 | The cheat sheets' entry triggers on the chart's swing levels (18 November 2026; `docs/reviews/entry-trigger-study.md`): entering after a 5-minute structure change, the 3rd touch, and whether open interest or a CVD divergence on the retest sorts the trades. | Structure change -0.36% a trade after costs on 3,219 trades (-1.41 to +0.74), 3rd touch -0.29% on 2,274 (-0.99 to +0.44), the plain fade on the same levels -0.33%; held out -0.78%, -0.79% and -1.19%. Open interest on the retest: +0.31% the sheets' way in sample, -1.09% held out. A CVD divergence: nothing. Nine in ten levels taken were swept. **No bar met.** |

S1: docs/reviews/value-area-rule-study.md. S2 to S6: docs/reviews/auction-level-studies.md. S7: docs/reviews/fib-zone-study.md (71 coins, March 2021 to July 2025, with November 2025 to July 2026 held out).

Data: Binance futures 5-minute candles (with taker buy volume) and 5-minute open interest for twelve coins, January 2021 to April 2026, with May to October 2026 held out. Hyperliquid serves only the latest 5,000 candles per series, too few for a study.

What the studies do not test: the method as traded, with judgement over which levels and reactions to take. They test whether the named levels and triggers, taken every time, carry an edge.

## Open

- The videos: their transcripts, to check the O rules against what Daniel says. docs/reviews/auction-video-brief.md says which videos, what to look for and the form of the answer.
- The members' "CCV 2.0" manual: it would say how Chart Champions state the 80% rule today (which session, what counts as a range day).
