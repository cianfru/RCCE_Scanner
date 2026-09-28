# Do profitable traders' positions get bigger into tops and greed? (declared 28 September 2026, before running)

Question from the owner: "On BTC, profitable traders' position size seems to increase as we reach a local top. High greed, then bigger positions. Is there a relationship between greed, local tops and position size?"

The earlier study (docs/reviews/traders-turn-at-tops-study.md) counted **wallets**. This one measures **size**: dollars, coins, and the share of the group's exposure. It reuses that study's data, position rebuild and caveats. It runs outside the production server and describes the past.

Everything below is fixed before any analysis code runs. Only counts were looked at (quoted under "Known before running"). Unless a result clears the bar in "Decision rule", it is **market context, not a trading signal**.

Code: `backend/research/position_size.py`, run as `python research/position_size.py <data dir> <fear-greed file>`.

## Data (reused, not refetched)

- **Wallets, fills, prices:** the pull of 26 September 2026 used by the turn study. 278 profitable traders (`money_printer`) and 299 large accounts (`smart_money`, the control; profit not checked). Latest 2,000 regular fills and 2,000 TWAP slices per wallet; Hyperliquid hourly closes for 182 perpetual coins; data end 26 September 2026 20:00 UTC.
- **Positions:** rebuilt exactly as in `traders_turn.py` (same functions): position after the last fill strictly before the 4-hour close, same-millisecond fills merged, sizes below 1e-6 set to flat, the coverage-start rule for capped lists.
- **Fear & Greed:** alternative.me daily index, as stored by `backend/market_history.py` (`fear_greed`, pairs of UTC day and value). No gaps in the window.
  - The value stamped day D counts as known from the 4-hour close at 00:00 UTC of day D+1. This is later than it is published, so it cannot leak.

## Fixed cohort (panel)

Wallets entering coverage must not look like growth. So:
- **Panel:** a group's wallets whose coverage starts at or before **25 March 2026 00:00 UTC**. Every size figure on every bar is summed over this same fixed set of wallets.
- **Analysis window:** 4-hour closes from **1 April 2026 00:00 UTC** to the data end. Events need their 7-day pre-window inside the panel's coverage, so events start on 1 April.
- The panel is the less active part of each group (see the turn study's coverage caveat). This is the price of a fixed basis.
- **Sensitivity (reported, no verdict):** per-event panels, the wallets covered from the start of each event's window, which admits more of the active traders.

## Size measures

Per coin, per 4-hour close T, per group, over the panel:

| Measure | Definition |
|---|---|
| **Long coins** | sum of long positions, in coins (size of positions > 0) |
| **Long notional (USD)** | long coins × the coin's 4-hour close at T |
| **Share of exposure** | long notional on the coin ÷ the panel's gross notional across all perpetual coins (sum of \|position\| × close, longs and shorts, every coin) at T |
| **Median per-wallet long notional** | median long notional among panel wallets long the coin at T; not defined below 5 such wallets |
| Short notional, wallets long (context) | for reading only |

- **Price effect, fixed now.** Long notional rises with price even when nobody trades, and price rises into a top by definition. So "they add into tops/greed" is read from **long coins** and **share of exposure**. Long notional in USD is reported (it is the owner's question) but never counts alone as adding.
- Changes are in % for coins, notional and per-wallet median (undefined when the start value is 0), and in points for the share.

## Events

All events on a coin need at least 5 panel wallets holding it (either side) 72 hours before the event bar. A second event on the same coin needs 72 hours since the last one.

1. **Local top (hindsight), primary event:** exactly D3 in `traders_turn.py`: a 4-hour close that is the highest from 72 hours before to 72 hours after, with the engine's z of 2.0 or more at that bar.
2. **Local top, any z (secondary):** the same without the z condition.
3. **Stretch start:** exactly D2: the first bar where z reaches 2.0 after being below it.
4. **High greed start:** the first 00:00 UTC close at which the known Fear & Greed value is 70 or more after a known value below 70. Also "high greed days": every day with a known value of 70 or more.

Local tops use later prices, so they can never be a signal. They only describe what size did around them.

**Windows** around the event bar b (same panel wallets at every point):
- before: b − 72h → b and b − 7d → b;
- after: b → b + 72h and b → b + 7d.

**Baseline.**
- **Matched:** the same change measured at every other bar of the same coin within 15 days of the event, excluding bars within 72 hours of it; the event's baseline is their median. "Excess change" = event change − matched baseline. This absorbs slow drift in the panel's holdings (the turn study's "August effect").
- **All bars:** the median change over all analysis bars of the coin in the same period.

**Headline set:** events at or before **20 August 2026 20:00 UTC** (the data end minus 30 days minus 7 days), so every 7-day after-window ends before the month the wallets were picked on. Events up to the data end minus 7 days are reported alongside as "all events (biased)".

## Coins

- **BTC is primary.**
- **Alt pool (secondary):** every non-BTC coin on which at least 5 panel wallets of the profitable group hold a position (either side) on at least 25% of the analysis bars up to the headline cut-off. This uses holdings only. The coins are listed in the results.
- For the pool, per-coin changes are pooled across coins. Pool-level daily series use the median across pool coins of that coin's change.
- Forward returns on alts are **excess** returns (coin minus the equal-weight basket of all coins, as in the turn study). BTC uses raw returns.

## Correlations (daily, at the 00:00 UTC close)

On BTC, over the panel of profitable traders:

| | Pair | Role |
|---|---|---|
| G1 | Fear & Greed level vs long coins, long notional, share of exposure (levels) | description (both trend, so levels can correlate by accident) |
| **G2** | **7-day change in Fear & Greed vs 7-day change in long coins** | **greed–size association** |
| G3 | 7-day change in F&G vs 7-day change in long notional and in share | description |
| **F1** | **7-day change in long coins at T vs BTC return T → T+7d and T → T+14d** | **does size predict price (primary predictor)** |
| F2 | share of exposure level, 7-day change in long notional, F&G level vs the same forward returns | exploratory |

- Spearman rank correlation.
- **Headline sample:** days from 1 April 2026 with the forward window ending at or before the headline cut-off of 27 August 2026 20:00 UTC (the data end minus 30 days). For G1–G3 (no forward window), days up to that cut-off.
- **Interval:** circular moving-block bootstrap over whole days, block length 14 days (the longest horizon, so overlapping windows stay together), 2,000 draws, seed 20260928. The 5th and 95th percentiles give the 90% interval.
- Alts: the same, on each pool coin's own series, pooled across coins. Bootstrap blocks are calendar days, so all coins on a day stay together.

## Robustness fixed now

- **Largest wallet removed:** for each coin, the panel wallet with the largest average long notional over the headline analysis bars is removed, and everything is recomputed. The top-1 and top-3 wallets' share of the coin's long notional is reported.
- **Coin size vs dollars:** every event table shows long coins next to long notional.
- **Market-maker filter (sensitivity):** wallets holding more than 25 open positions at any analysis bar are removed, as the product does.
- **Large-account control:** everything is repeated for `smart_money`.

## Decision rule (fixed now)

Each of these needs its own bar. None is a trading signal unless F1 passes.

**A. Size rises into local tops** (BTC; then alt pool; each on its own):
1. At least 30 independent headline events (distinct UTC days).
2. Median excess change in long coins over 72h before the top above 0, and its 90% day-bootstrap interval (whole UTC days of events drawn with replacement, 2,000 draws, seed 20260928) entirely above 0.
3. The same holds over 7 days before.
4. It still holds (median above 0, interval above 0) with the largest wallet removed.
Otherwise "not informative". The same four tests, with signs reversed, decide **"size is cut after tops"** from the after-windows.

**B. Size rises with greed** (G2, BTC; then alts): at least 120 headline days; ρ of 0.2 or more with the 90% interval entirely above 0; still above 0 with the largest wallet removed. Otherwise "no clear relationship" (if the interval spans 0) or "not informative" (if under 120 days).

**C. Size predicts the next 7–14 days** (F1): at least 120 headline days; |ρ| of 0.2 or more at **both** 7 and 14 days, same sign, both 90% intervals excluding 0; still true with the largest wallet removed. Only then is it more than market context. If the large-account control shows the same, it is big-wallet flow in general, not skill.

- High-greed start events use test A's rules (30 events needed).
- All-events (biased) numbers never count towards a verdict. Nothing is tuned after seeing results; anything added later is labelled exploratory.

## Known before running (counts only)

- Panel: 181 of 278 profitable traders and 196 of 299 large accounts are covered from 25 March. (In the turn study most covered large accounts held no perpetuals.)
- Between 1 April and 20 August there is **1** BTC local top with z ≥ 2 and **17** at any z. Fear & Greed was 70 or more on **18** days from 25 March to 26 September, in **5** runs.
- So on BTC alone, tests A (tops) and the high-greed events cannot reach 30 events. They will be "not informative" by the count rule and read as description. The BTC verdicts rest on B and C. The alt pool may reach 30 tops.

## Results

To be added below after the run. Nothing above changes.
