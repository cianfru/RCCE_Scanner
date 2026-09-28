# Do profitable traders turn when coins top out? (declared 28 September 2026, before running)

Question: when a coin, or the market, is stretched to the upside, do the profitable traders start going short or cut their longs? Or do they keep their longs? And when they do turn, did price tend to fall afterwards?

This is a one-off reconstruction from Hyperliquid's public records, like docs/reviews/traders-vs-spikes-study.md. It runs outside the production server and describes the past.

Everything below is fixed before any analysis code runs on the data. Only file formats and counts were looked at; the counts quoted below come from that check. Unless the result clears the bar in "Decision rule", it is read as context about who is doing what, not as a signal.

Code: `backend/research/traders_turn.py`, run as `python research/traders_turn.py <data dir>`.

## Data

**Wallets.** Today's tracked roster, the same pull as the spikes study:
- 278 profitable traders (top 300 by monthly return that were also in profit before this month);
- 299 large accounts (top 300 by account value, profit not checked). These are the control group.
- 4 wallets are in both groups. They count in both.

**Fills.** Per wallet, the latest 2,000 regular fills (same-time fills merged) and the latest 2,000 timed-order (TWAP) slices, pulled on 26 September 2026. Each fill carries the position size before it.
- The two lists are separate records. Only 6 of 251,746 TWAP slices share a coin and time with a regular fill.

**Coins.**
- Only perpetual markets with Hyperliquid hourly candles count (182 coins; 171 still trading at the end).
- Builder-dex markets (names with ':'), spot ('@' or '/') and outcome markets ('#') are excluded.

**Prices.**
- Hourly closes from 10 March 2026 to 26 September 2026. No gaps were found.
- The newest hourly candle was still open when pulled, so it is dropped.
- The data end is 26 September 2026 20:00 UTC.

## Building positions

- Position after each fill = position before it, plus the size for a buy or minus it for a sell.
- **Position at time t** on a coin: the position after the wallet's last fill on that coin before t. If there is none, the position recorded before its next fill on that coin. If the wallet never traded the coin, flat.
- **Sampling.** At every 4-hour close: 00, 04, 08, 12, 16 and 20 UTC. Fills strictly before the close count.

**Coverage.**
- When a wallet's regular list hit the 2,000 cap, fills older than its oldest one may be missing. The same holds for the TWAP list.
- A wallet's coverage starts at the later of the two cut-offs, or at the start of time if neither list is capped.
- This is stricter than the spikes study, which looked only at the regular list. It matters because TWAP slices are not in the regular list.
- Profitable traders covered: 182 of 278 from 180 days before the end, 228 from 30 days before.

**Same wallets at both ends.** A comparison from t minus L to t uses only wallets whose coverage starts at or before t minus L. The same wallets are counted at both ends.

**Blind spot.** A position opened before a wallet's coverage, and not traded again before the data end, cannot be seen.

## Stretch (the engine's z-score)

- **4-hour close** at time T: the close of the hourly candle that opens at T minus 1 hour. If it were missing, the latest hourly close inside the 4 hours; if none, the bar is missing.
- **z at T:** the engine's own function, `_calc_zscore_hybrid` (200-bar average, 300-bar regression line, no smoothing, scale 1), on the coin's 4-hour closes up to and including T.
- It is multiplied by the engine's warm-up factor, min(1, (n − 200) / 200), where n is the number of 4-hour bars up to T. Below 200 bars the factor is 0.
- Every window in the formula looks back only, so reading bar T from one pass over the series is the same as computing with data up to T.
- A coin gets full weight after 400 bars (about 67 days). Early in the window z is scaled down, as the engine does.
- Where z is not available, the coin-bar is skipped for anything that needs z.
- **STRETCHED:** z at T of 2.0 or more.

## Measures

Per coin, per 4-hour close, per group, over the wallets counted for that comparison:

| Measure | Meaning |
|---|---|
| Wallets long | wallets with a long position on the coin |
| Wallets short | wallets with a short position on the coin |
| Long share by wallets | wallets long ÷ (wallets long + wallets short). Not defined if nobody holds the coin. |
| Long share by notional | long position value ÷ all position value. Value = size × the coin's 4-hour close at that time. |

**Eligible.** A coin counts for a 24-hour comparison ending at T only if at least 5 of the counted wallets hold it, on either side, at T minus 24 hours.

## Events

### TURN (one coin)

Over the previous 24 hours (6 bars), same wallets, coin eligible, either:
- long share by wallets falls by 20 points or more (for example from 80% to 60%); or
- wallets short rise by 2 or more.

If nobody holds the coin at T, the first test is not met.

**Timing.** The event is the first bar of a run: the test holds at T and did not hold, or could not be run, at the bar before. A new event on the same coin needs at least 72 hours since its last one.

With exactly 5 holders, one wallet switching from long to short moves the share by 20 points. So each event also records how many wallets changed side, and single-wallet events are counted in the report.

### The events compared

- **Primary: turning at a top.** A TURN event with z of 2.0 or more at the event bar.
- **Secondary: TURN at any z.** All TURN events.
- **Control: stretched without a turn.** Another coin at the same time that is:
  - eligible;
  - at z of 2.0 or more;
  - showing no TURN test at that bar or at any of the 6 bars before it.

Only the past is used to pick control coins, so a coin is not dropped because its traders turned later.

**Matching the control.**
- Each primary event is matched to control coins at the same 4-hour bar. If there are none, it uses control coins on the same UTC day, each at its first qualifying bar that day.
- An event's control value is the median outcome of its matched coins.
- Events with no match are left out of the comparison with the control only.

### MARKET TURN

- At each 4-hour close T, each group has a market-wide long share by notional. It adds up long and total position value across the coins eligible at T minus 24 hours, over the same wallets and the same coins at both ends.
- **Event:** this share falls by 10 points or more over 24 hours. First bar of a run, then at least 72 hours before the next.
- As a description only, the report says how many market turns came while BTC's 4-hour z was 2.0 or more.

## Outcomes

- **Coin return** 1, 3 and 7 days after the event, from the event bar's 4-hour close to the 4-hour close 1, 3 or 7 days later.
- **Excess return:** the coin's return minus the basket's return over the same interval. The basket is the equal-weight average return of all coins with closes at both ends.
- A coin delisted before the horizon has no return at that horizon.
- **Per set, report:**
  - the number of events;
  - the mean and median, raw and excess;
  - the share negative (below zero);
  - a 90% interval for the median.
- **The interval** comes from a bootstrap: whole UTC days of events are drawn with replacement 2,000 times (seed 20260926). The 5th and 95th percentiles of the resampled medians give the interval. Drawing whole days keeps coins that turned on the same day together, so one market-wide day cannot look like many independent events.
- **Market turns:** BTC and basket returns, raw, at 1, 3 and 7 days. The comparison is all 4-hour bars in the same period where the market share is defined.

## Selection bias, handled before looking

The profitable traders are chosen for being profitable this month, so their recent calls look good by construction.
- **Headline:** events at or before 27 August 2026 20:00 UTC, 30 days before the data end.
- **All events:** reported alongside and labelled biased.
- **Large accounts:** everything is repeated for them. Their selection does not look at profit.

## What they do around stretch and tops (description only)

No verdict hangs on these tables. They answer "who is doing what". Profitable traders and large accounts are shown side by side, on the headline period and on all events.

- **D1, by stretch.** All eligible coin-bars split by z: below 0, 0 to 1, 1 to 2, and 2 or more. For each band:
  - the average wallets long, wallets short, and long share by wallets and by notional;
  - their average change over the previous 24 hours.
- **D2, as a stretch starts.** The first bar where an eligible coin's z reaches 2.0 after being below it, with 72 hours between events per coin. Measured over the wallets covered from 24 hours before:
  - the change in wallets long, wallets short and both long shares from 24 hours before to the bar;
  - the same change from the bar to 24 hours after, and to 72 hours after.
- **D3, at tops seen in hindsight.** A 4-hour close on an eligible coin that is its highest from 3 days before to 3 days after, with z of 2.0 or more, with 72 hours between events per coin. Measured the same way as D2. This uses later prices to find the top, so it can never be a signal. It only shows whether they sold into tops.

## Decision rule (fixed now)

**Primary event.** It is informative only if all of these hold on the headline set (profitable traders, events older than 30 days):
1. At least 30 events.
2. The median excess return is −1.5% or lower at 3 days and at 7 days.
3. At least 60% of events have a negative excess return, at 3 days and at 7 days.
4. The 90% interval of the 7-day median excess return lies entirely below 0.
5. On the events with a matched control, the 7-day median excess return is at least 1.5 points below the control's median. If fewer than 30 events have a match, this is not met.

**Market turn.** The same five tests on BTC's raw forward return:
- at least 30 market turns;
- median −1.5% or lower at 3 and 7 days;
- at least 60% negative at 3 and 7 days;
- the 90% interval of the 7-day median entirely below 0;
- a 7-day median at least 1.5 points below the median over all headline 4-hour bars.

**Otherwise** the result is descriptive context only.

**Reading.**
- If the profitable traders pass and the large accounts show the same thing, it means big wallets turning in general, not these traders' skill.
- All-events numbers never count towards the verdict.
- No threshold is tuned after seeing results. Any extra cut is labelled exploratory.

## Results

To be added below after the run. Nothing above changes.

### Run 28 September 2026 (data pulled 26 September)

**Short answer.**
- Profitable traders mostly keep their longs when a coin is stretched. They add longs once a stretch starts and into local tops. In the 72 hours after a top they trim a little: about one wallet per coin, and rarely to short.
- "Turning" at a top is rare: 3 events in the headline period. That is far too few to test whether price fell afterwards. Both declared verdicts (coin level and market level) are **not informative**, so everything below is context about who is doing what, not a signal.
- The large-account control is too thin to compare against: about 30 wallets on 4 coins.

Numbers come from `python research/traders_turn.py <data dir>` (result saved as `turn/result.json` in the session scratchpad). Returns are medians in %. "Excess" means minus the equal-weight basket.

### Fixes and deviations

**Fix made after independent checks (changes the numbers, not the verdict).**
- Rounding leftovers were counted as open positions. The API's sizes carry float noise (for example `727061.7999999999`), so a full close could leave a position of ±1e-10. That wallet then counted as a long or short holder.
- Positions smaller than 1e-6 are now flat. In this data every leftover is below 1e-8, and the smallest real position is 1e-5 (BTC's size step), so any cut between the two gives the same result.
- Effect on the headline for profitable traders:
  - eligible coin-bars 8,606 → 8,274;
  - TURN events at any z 46 → 47;
  - D2 events 48 → 46 and D3 events 39 → 35;
  - control 3-day median −2.51% → −3.17%.
  - The 3 primary events and their returns are unchanged, and so is every verdict.
- Two reviewers' independent rebuilds (one reads the next fill's recorded start position, the other accumulates fills) match the corrected code cell for cell.

**Deviations from the declared rules.**
1. *Position at the coverage start.* The declared rule takes the position after the last fill before t. At t on or after a wallet's coverage start, when that last fill is older than the coverage start, fills in between may be missing. If a later fill exists, its recorded start position is used instead.
   - Applying the rule literally changes 3,621 covered wallet-coin-bars.
   - It gives the same 3 primary events and the same verdicts (`sensitivity_literal_position_rule`).
2. *z below 200 bars.* The protocol says the warm-up factor is 0 there. The engine returns no z below 200 bars, so those coin-bars are skipped rather than counted as z = 0.
   - This keeps 738 headline eligible coin-bars for profitable traders (82 for large accounts) out of D1. They would otherwise sit in the "0 to 1" band.
   - No event set changes.

**Added for reading only (no verdict uses them):**
- wallet concentration per event set and per table;
- for market turns, the drop with the largest wallet left out;
- D1 by month;
- event sets cut so that outcome windows end by the headline cut-off;
- a second sensitivity run that treats stale pre-coverage positions as flat (see Caveats).

### Data coverage

- 1,200 four-hour closes, 11 March to 26 September 2026 20:00 UTC. 182 coins, 171 still trading at the end. Headline cut-off: 27 August 20:00.
- Fill history checks out: 0 breaks in 339,180 consecutive covered fill pairs. 162 of the 365 pairs that cross a coverage cut-off break, which is why coverage starts there.

| | Profitable traders | Large accounts (control) |
|---|---:|---:|
| Wallets | 278 | 299 |
| With no perpetual fills (never hold a coin here) | 16 | 171 |
| Covered **and** trading perps, from 180 days before the end | 167 | **35** |
| Same, from 30 days before the end | 213 | 69 |
| Headline eligible coin-bars (≥ 5 counted holders) | 8,274 | 1,535 |
| Coins behind them | 35 (BTC, HYPE 1,014 each; ZEC 958; ETH 761; NEAR 585) | **4** (HYPE 870, BTC 406, ETH 235, XRP 24) |
| Distinct wallets holding in them | 175 | **31** |
| Top 10 wallets' share of holder slots | 27% | **70%** |
| Top 3 wallets' share of long value | 45% | 63% |

- **The control cannot support "same" or "not the same".** Most covered large accounts hold no perpetuals. The rest are a few whales on HYPE, BTC and ETH.
- Covered profitable traders grow over time: 182 on 15 April, 214 on 21 August, 252 on 20 September. The most active traders are covered only near the end (see Caveats).

### Coin level: TURN at a top (primary)

Headline, profitable traders: **3 events.**

| Event | z | Long / short 24h before → at | Who moved | 7d excess |
|---|---:|---|---|---:|
| ADA 6 Jul 04:00 | 2.04 | 1 / 4 → 1 / 6 | 2 new shorts; the coin was already net short | −10.59% |
| BTC 21 Aug 12:00 | 4.57 | 27 / 1 → 28 / 4 | 7 toward short, 6 toward long | +0.34% |
| PUMP 23 Aug 20:00 | 3.09 | 17 / 0 → 16 / 2 | 2 closed longs, 2 new shorts | −6.37% |

| Headline, n = 3 | 1 day | 3 days | 7 days |
|---|---|---|---|
| Raw return | −3.61% (67% negative) | −8.33% (67%) | −8.88% (67%) |
| Excess return | −2.96% (100%) | −3.65% (100%) | −6.37% (67%) |
| 90% interval, excess median | −5.92 to −2.53 | −7.19 to −3.04 | **−10.59 to +0.34** |
| Control (same bar, all 3 matched), excess median | +0.03% | −3.17% | +0.55% |
| Gap to control | −3.00 pts | −0.47 pts | −6.91 pts |

- 13 different wallets moved toward short across the 3 events, and none repeats.
- 2 of the 3 events fired on the "2 more shorts" test while wallets long held steady or rose. Read these as "shorts added", not "longs turned".
- **All events (biased, includes the month that picked the wallets):** 10 events. 7 of them fall in 20–25 September, so only the same 3 have 7-day outcomes. The 1-day excess median is −3.13% (80% negative).
  - One wallet (0x0a506b1e) is a new short in 7 of the 10.
  - It shows 34 open positions, above the product's 25-position filter for likely market makers and vaults. Its history is covered only from 19 September.
  - This set is largely one wallet's activity.
- **Large accounts: 0 primary events**, in the headline period and in all events.

### Coin level: TURN at any z (secondary)

| Profitable traders | Events | 1d excess | 3d excess | 7d excess | 7d raw |
|---|---:|---|---|---|---|
| Headline | 47 (40 days) | −0.44% (55% neg.) | +0.45% (40%) | **+0.34% (47%)**, interval −1.13 to +1.75 | −0.91% (55%) |
| All events (biased) | 86 | −0.63% (62%), interval −1.10 to −0.14 | −0.34% (52%) | −0.08% (51%), interval −1.38 to +1.11 | +0.05% (48%) |

- Headline triggers: shorts test 33, share test 9, both 5.
  - In 19 of the 38 events where the shorts test held, wallets long did not fall. Shorts were added alongside steady or rising longs.
  - This test counts shorts in absolute numbers, so it fires more easily on crowded coins. The median event had 13 holders, against 8 on all eligible coin-bars.
- 10 headline events include at least one wallet flipping from long to short. None rests on a single wallet.
- Concentration: 71 different wallets moved toward short. The most frequent (0x956ff3eb) appears in 8 of 47 events (17%), and the top 5 make 22% of the moves.
- A turn at any stretch did not come before weaker prices: the 7-day excess median is about zero.
- Large accounts: 0 headline events; 4 in all events.

### Market level: MARKET TURN

| Profitable traders | Turns | BTC 1 day | BTC 3 days | BTC 7 days |
|---|---:|---|---|---|
| Market turns (headline = all; none after 9 June) | 9 | +0.11% (44% neg.) | +0.89% (44%) | +1.07% (33%), interval −1.38 to +3.53 |
| All 1,014 headline 4-hour bars | | +0.13% | +0.27% | +0.24% |

- None came while BTC's z was 2 or more. For the first 5 (March and early April), BTC's z was not yet available.
- **Every market turn is one large wallet changing its position, not the group turning.**
  - Leaving out the single largest contributor shrinks each drop from 10–17 points to between 0 and 4.1 points.
  - Four wallets cause all 9 turns, and the position value involved is only $2–12M.
  - Counted by positions instead of value, the long share barely moves (for example 78.6% → 76.7% on 22 March).
- Large accounts: 0 market turns.
- On 26 September 20:00 the long share by value, across coins with 5 or more counted holders, was 96.6% for profitable traders and 71.3% for large accounts. Positions on that bar are as of the pull (see Caveats).

### Decision rule, test by test

**Primary (profitable traders, headline):**

| Test | Needed | Result | |
|---|---|---|---|
| 1. Events | ≥ 30 | 3 | fail |
| 2. Median excess at 3d and 7d | ≤ −1.5% | −3.65% and −6.37% | pass |
| 3. Share negative at 3d and 7d | ≥ 60% | 100% and 67% | pass |
| 4. 90% interval of the 7d median | entirely below 0 | −10.59 to +0.34 | fail |
| 5. 7d gap to control, ≥ 30 matched | ≤ −1.5 pts | −6.91 pts on 3 matched | fail |

**Not informative.** Tests 2 and 3 pass on 3 events, which is exactly the small-sample case the event count and the interval exist to catch.

**Market turn (profitable traders, headline):**

| Test | Needed | Result | |
|---|---|---|---|
| 1. Turns | ≥ 30 | 9 | fail |
| 2. BTC median at 3d and 7d | ≤ −1.5% | +0.89% and +1.07% | fail |
| 3. Share negative at 3d and 7d | ≥ 60% | 44% and 33% | fail |
| 4. 90% interval of the 7d median | entirely below 0 | −1.38 to +3.53 | fail |
| 5. 7d median vs all bars | ≥ 1.5 pts lower | +1.07% vs +0.24% | fail |

**Not informative.** Large accounts have no primary events and no market turns, so there is nothing to test. The results stay descriptive, and no threshold was changed after the run.

### Who is doing what (description only)

**D1, by stretch, headline.** Averages per eligible coin-bar. The 24h change compares the same wallets at both ends.

| Band | Coin-bars | Wallets long | Wallets short | Long share, wallets | Long share, value | 24h change in wallets long |
|---|---:|---:|---:|---:|---:|---:|
| Profitable, z below 0 | 3,757 | 9.24 | 1.67 | 83.2% | 85.5% | −0.05 |
| Profitable, 0 to 1 | 1,601 | 8.38 | 1.42 | 84.0% | 86.2% | +0.10 |
| Profitable, 1 to 2 | 1,476 | 10.80 | 1.50 | 86.8% | 88.4% | +0.05 |
| **Profitable, 2 or more** | **702** | **13.17** | **1.06** | **91.1%** | **92.8%** | **+0.59** |
| Large accounts, z below 0 | 787 | 4.89 | 1.88 | 70.3% | 90.8% | −0.02 |
| Large accounts, 2 or more | 162 | 5.26 | 2.16 | 72.9% | 95.4% | −0.17 |

- All events (biased), profitable traders at z ≥ 2: 907 coin-bars, 13.82 wallets long, 91.9% long share, +0.80 wallets long over 24h.
- **The higher long level at z ≥ 2 is mostly an August effect.**
  - 495 of the 702 stretched coin-bars are in August, when more wallets were covered and the market rallied.
  - Within June, stretched coins had fewer longs than unstretched ones: 5.4 against 9.1 wallets long, and a 74% against 87% long share. In July too, stretched coins had fewer wallets long (6.2 against 9.0).
  - Read this band from the 24h change, which compares the same wallets. That change is −0.16 in May, −0.03 in June, +0.28 in July and +0.82 in August (exploratory split).
  - Adding into stretch is clear only in the August rally.
  - An independent check (run before the rounding fix) found the roughly +0.5 change in both wallets with full history and wallets with capped history.

**D2, as a stretch starts (46 headline events; 9.2 long and 1.1 short 24h before):**

| Change in wallets long | Mean | Median | Rose / level / fell |
|---|---:|---:|---|
| 24h before → bar | +0.17 | 0 | 17 / 18 / 11 |
| Bar → 24h after | **+0.87** | **+1** | 24 / 12 / 10 |
| Bar → 72h after | +1.09 | 0 | 20 / 12 / 14 |

- Wallets short barely move (−0.04 to −0.07 on average).

**D3, at tops seen in hindsight (35 headline events; 11.2 long and 0.9 short 24h before):**

| Change | Mean | Median | Rose / level / fell |
|---|---:|---:|---|
| Wallets long, 24h before → top | **+0.83** | **+1** | 21 / 8 / 6 |
| Wallets long, top → 24h after | −0.34 | 0 | 10 / 11 / 14 |
| Wallets long, top → 72h after | **−0.43** | **−1** | 5 / 10 / 20 |
| Wallets short, top → 72h after | +0.17 | 0 | 5 / 28 / 2 |
| Long share by value, top → 72h after | −2.94 pts | 0 | 7 / 18 / 10 |

- They buy into tops and trim slightly after them, mostly by closing longs rather than opening shorts.
- The −2.94-point value figure comes from two events: ADA 22 August (−47 points) and LIT 22 May (−38 points). Without them the mean is −0.53, and the median is 0.
- Large accounts: D2 has 8 events and D3 has 6. Wallets long barely move: at most 2 events change in any window, by one wallet. Shorts rise in 2 of the 6 tops over 72h. Too few to read.
- With the event cut-off moved back so that the 72-hour windows end before the selection month (exploratory), D3 has 31 tops. Wallets long change by −0.39 over 72h (median −1; 18 of 31 fall), so the trim-after-tops reading holds.

**Sensitivity.** Treating positions whose last fill predates a wallet's coverage start as flat changes little:
- eligible coin-bars 8,274 → 8,260;
- the same 47 secondary events, 35 D3 events and 3 primary events;
- large accounts at z ≥ 2 hold 4.83 wallets long instead of 5.26.

No verdict changes.

### Caveats

- **Selection is not fully removed by the 30-day cut.** The roster requires profit this month and profit before this month, and "before this month" covers the whole headline window. It also requires at least $50k account value today, which adds survival bias.
  - 2 of the 3 headline primary events (BTC 21 August and PUMP 23 August) and 5 of the 47 secondary events have 7-day windows ending after the cut-off.
  - With those removed (exploratory), 1 primary event is left (ADA), and the secondary 7-day excess median is +0.96% on 42 events.
- **Which wallets count depends on their later activity.** A wallet counts at t only if it made fewer than 2,000 fills (per list) between t and 26 September. So the older bars include only the less active traders. That tilts the picture towards holding: "they keep their longs" describes the less active profitable traders best.
- **The last bar is stale.** Fills were pulled between about 16:27 and 18:52 UTC on 26 September, so positions at the 20:00 bar are up to about 3.5 hours old. One all-events TURN (ZEC 26 September 20:00) and the "long share now" figures use that bar. The headline does not.
- **Possible phantom holders.** 194 open positions were last filled before their wallet's coverage start. They are carried forward, as the declared rule says, but some have probably closed without a visible fill. The sensitivity above treats them as flat.
- **No market-maker filter.** The study keeps every roster wallet. The product drops wallets with more than 25 open positions, and that would remove 0x0a506b1e.

### What this means for the product

- **Show the Radar's sentiment line and shift arrows as context, not as a top or sell signal.** Nothing here shows that a drop in profitable traders' long share at a stretched coin comes before a fall.
- **Expect a high long share on stretched coins.** The average at z ≥ 2 was 91% long, mostly from the August rally. They add into stretch and into local tops, so a crowded long is not a warning by itself.
- **Describe arrows by what moved.** Show counts next to shares, for example "13 long / 1 short, was 12 / 1 24h ago". When shorts rise while longs hold, say "2 new shorts, longs unchanged" rather than "turning bearish".
- **Use a holder minimum and flag single wallets.**
  - Draw no arrow below 5 holders: with 5 holders, one wallet moves the share by 20 points.
  - Mark a shift driven by one wallet.
  - Prefer wallet counts over value for market-wide arrows, because every value-based market turn here was one whale.
- **Keep the 25-position market-maker filter on everything that feeds the arrows.**
- **Don't present "large accounts vs profitable traders" as a contrast on altcoins.** The large-account group effectively holds HYPE, BTC and ETH through about 30 wallets.
- **Re-test later on the product's own data.** The stored 4-hour lean snapshots avoid the fill caps and blind spots of this reconstruction. The declared test can be re-run on them once they hold 30 or more primary events older than 30 days. Until then the arrows stay descriptive.
