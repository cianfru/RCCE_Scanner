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
