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

### Run 28 September 2026 (data pulled 26 September)

Result: `python research/position_size.py <data dir> <fear-greed file>`, saved as `size/result.json` in the session scratchpad. Changes are medians in %, the share in points, and [brackets] are 90% intervals. "Excess" means minus the matched baseline (same coin, bars within 15 days).

**Verdicts against the declared bar:**

| Test | BTC | Alt pool | Why |
|---|---|---|---|
| A. Size rises into tops / is cut after | not informative | not informative | 1 BTC top with z ≥ 2 and 9 alt tops, against 30 needed |
| B. Size rises with greed (G2) | no clear relationship | no clear relationship | BTC ρ +0.13 [−0.11, +0.38]; alts ρ +0.13 [+0.05, +0.22], under 0.2 |
| C. Size predicts the next 7–14 days (F1) | no predictive relationship shown | no predictive relationship shown | BTC ρ +0.04 and +0.10; alts +0.08 and +0.10 |

Nothing met the bar. **Everything below is market context, not a trading signal.**

#### Data

- **Panel (fixed):** 181 profitable traders, of whom 161 hold perpetuals at some point from 25 March. The large-account panel has 196 wallets, but only **23** of them hold perpetuals.
- **Alt pool (rule-picked):** ADA, ENA, ETH, HYPE, LIT, NEAR, SOL, SUI, TAO, ZEC.
- **Daily samples:** 149 headline days for greed (1 April to 27 August), 142 days for 7-day forward returns and 135 for 14-day.
- **Fear & Greed ≥ 70 is a late-sample event.** It happened on 17 days, all from 22 August on. Only 4 of those days fall in the headline sample, and none come before the event cut-off, so there are **0 headline high-greed start events**.
- **Who holds BTC:** the top wallet has 31% of the panel's BTC long value, and the top 3 have **84%**.
  - Those 3 wallets (0x2371...0883, 0x93ab...11f8, 0xec7f...df39) trade in lockstep: same 4-hour bars, round lots of 100–400 BTC, never another coin. Treat them as one entity.

#### BTC, profitable traders

**The whale entity.** It was not the one adding into greed:
- It bought about 800 BTC between 25 June and 6 July at $58.6–63.5k, with Fear & Greed at 15–27.
- It sold everything on 24–25 August at $79–80k, with F&G at 73. That bar is a hindsight local top (z 2.6).
- It bought back on 28 August at $78.3k and added 300 BTC on 8 September.
- It sold everything again on 22–23 September at $86.2–86.7k, with F&G at 70–78.

**The rest of the panel** (top 3 removed, same wallets throughout), every 7 days:

| | Apr–mid Aug | 26 Aug | 2 Sep | 16 Sep | 23 Sep |
|---|---|---|---|---|---|
| BTC price | $58.6–80.9k | $78.5k | $77.4k | $75.6k | $86.2k |
| F&G (known) | 10–50 | 74 | 69 | 69 | 78 |
| Long BTC (coins) | 31–62, one reading of 113 | 121 | 121 | 179 | 233 |
| Wallets long | 6–14 | 18 | 24 | 23 | 21 |
| BTC share of their exposure | 12–70%, drifting down | 21% | 17% | 18% | 15% |

- On greed days (all days, biased), they held a median 122 BTC, against 56 on other days. Their USD long was $9.8M against $3.8M.
- BTC's share of their book did not rise: 18% on greed days against 21% on other days. They grew everything, not BTC in particular.

**Around the 17 headline local tops (any z)**, all panel wallets:

| Window | BTC price | Long USD | Long coins | Coins, excess | Coins, excess, top 3 removed |
|---|---|---|---|---|---|
| 72h before | +2.6% | **+4.8%** [+1.2, +12.7] | **+0.9%** [−0.3, +7.4] | +2.5 [−0.8, +8.7] | +2.8 [−12.6, +8.7] |
| 7d before | +3.8% | +5.5% [+3.2, +12.1] | +1.1% [−2.9, +13.2] | +1.1 [−4.0, +11.3] | +0.1 [−7.3, +11.3] |
| 72h after | −2.6% | −4.5% [−8.9, −2.4] | −1.2% [−5.6, +0.3] | −1.8 [−5.5, −0.0] | −5.5 [−11.2, −2.6] |
| 7d after | −3.2% | −3.4% [−7.2, −1.1] | −1.5% [−7.6, +1.5] | −2.9 [−10.6, +1.5] | −6.6 [−13.7, +4.8] |

- The median per-wallet long value is +10.1% in the 72h before (on 17 events), and share of exposure +0.6 points [−1.9, +1.7].
- The one z ≥ 2 top (15 June) had +30% coins in the 72h before. A single event decides nothing.

**Correlations (headline, daily):**

| | All panel | Top 3 removed (exploratory) |
|---|---|---|
| G1 F&G level vs long coins | +0.37 [−0.02, +0.66] | +0.47 [+0.16, +0.71] |
| G1 F&G level vs long USD | +0.43 [+0.07, +0.69] | +0.54 [+0.24, +0.75] |
| **G2 7d ΔF&G vs 7d Δ long coins** | **+0.13 [−0.11, +0.38]** (largest wallet removed: +0.14) | +0.33 [+0.11, +0.52] |
| G3 7d ΔF&G vs 7d Δ long USD | +0.25 [+0.00, +0.47] | +0.42 [+0.22, +0.59] |
| G3 7d ΔF&G vs 7d Δ share | +0.01 [−0.26, +0.30] | +0.25 [+0.04, +0.45] |
| **F1 7d Δ long coins vs BTC next 7d / 14d** | **+0.04 [−0.21, +0.25] / +0.10 [−0.13, +0.33]** | −0.07 / +0.01 |

- On all days (biased, includes the greed weeks), G2 is −0.07 [−0.33, +0.21] for the whole panel and +0.23 [−0.02, +0.46] with the top 3 removed.
- F2 is exploratory, with 6 predictor-horizon pairs:
  - BTC's share of exposure vs the next 14 days: +0.39 [+0.02, +0.60].
  - F&G level vs BTC's next 7 / 14 days: −0.23 / −0.30, with both intervals touching 0.

#### Alt pool, profitable traders

- **Local tops, any z:** 75 events on 41 days. The declared rules applied to this secondary set give "not shown" both ways.

| Window | Price | Long USD | Long coins | Coins, excess |
|---|---|---|---|---|
| 72h before | +6.0% | +10.2% [+6.4, +16.3] | +1.9% [+0.2, +6.2] | **0.0 [−1.3, +2.3]** |
| 7d before | +6.1% | +29.1% | +14.1% [+5.0, +19.9] | +2.0 [−10.9, +13.7] |
| 72h after | −5.2% | −4.0% | +0.6% [−1.0, +3.8] | −1.3 [−5.9, 0.0] |
| 7d after | −6.2% | −5.2% | +1.5% | −2.9 [−15.3, +1.2] |

- **Tops with z ≥ 2:** 9 events. In the 72h before, coins +6.2%, excess −0.7 [−7.8, +10.4].
- **Correlations, pooled coin-days:**
  - G2 +0.13 [+0.05, +0.22], and +0.13 [+0.01, +0.26] with the largest wallet removed. Positive, but under the declared 0.2.
  - The pool-median series gives G2 +0.38 [+0.20, +0.55] (description).
  - F1 +0.08 [+0.03, +0.13] at 7 days and +0.10 [+0.03, +0.16] at 14 days.

#### Large-account control

- Only 23 panel wallets hold perpetuals, 3 to 7 of them long BTC. The top 3 hold 86% of the BTC long.
- They have essentially no alt positions.
- G2 on BTC is +0.14 [−0.14, +0.39], and F1 is +0.18 and +0.14, with both intervals spanning 0.
- **There is no usable contrast.**

#### Sensitivities

- **Market-maker filter:** it removes 1 profitable wallet and 0 large accounts, and no number moves.
- **Per-event panels** (more of the active traders):
  - BTC tops, long coins: +2.0% in the 72h before (fixed panel +0.9%), +3.3% in the 7d before (+1.1%), −2.8% in the 72h after (−1.2%), −3.3% in the 7d after (−1.5%).
  - Same direction, a bit larger.

### Plain reading

- **Dollars rise into BTC tops mostly because price rises.**
  - In the 72h before a local top, the cohort's BTC long value grew about 5% while BTC rose about 2.6%. The coin count grew about 1%, which cannot be told apart from zero.
  - After tops, the dollars fall with price, plus a small cut in coins.
  - With 17 tops (1 stretched), this is not enough to call.
- **On alts it is the same.** Long dollars +10% into a top on +6% price, and coin size flat against its own recent trend.
- **Greed: the observation is real for the recent rally, but it is one episode.**
  - Leave out the one whale entity. The rest of the profitable panel roughly doubled its BTC coins and wallet count as Fear & Greed went above 70 in late August and September. Their 7-day coin changes track greed changes: ρ +0.33 on the headline sample, exploratory.
  - They grew all their positions, so BTC's share of their book did not rise.
  - Every greed reading falls in the month the roster was picked on. The list is chosen for being in profit now, so it is full of wallets that were long this rally.
  - The largest holder did the opposite: it bought in fear and sold into both greed tops.
- **Size does not predict the next 7–14 days.** BTC ρ is +0.04 to +0.10. Alts are +0.08 to +0.10, tiny, and in the direction the profit-based selection would create anyway.

### Deviations from the declared rules

1. **Added after seeing the first run (exploratory, no verdict uses them).**
   - Top-3 removal: the declared "largest wallet removed" takes out only one of three lockstep wallets on BTC, so it cannot test one-entity dominance.
   - Week-block intervals: 7-day windows of events 72 hours apart overlap. Drawing whole calendar weeks widens a few intervals slightly and changes no reading.
   - A 7-day BTC timeline, all-days (biased) G2, and greed-day levels.
   - The run was repeated with these added. Every declared number and verdict is identical to the first run (checked).
2. **Matched baseline for headline events.** Baseline windows must also end by the headline cut-off. The declaration did not say so. It keeps the selection month out of the baseline.
3. **Per-event panel sensitivity.** It reports raw changes only, without a matched baseline: earlier baseline bars would fall before those wallets' coverage.
4. **Alt G2.** The declaration named both a pool-median series and pooled coin-days. The verdict uses pooled coin-days (the Correlations section), and the median series is description.

### Caveats (skeptic's review)

- **Lookahead.**
  - Positions at T use fills strictly before T (tested), and Fear & Greed is lagged a day (tested).
  - Hindsight tops, "after" windows and the matched baseline read later data. They are description only.
  - The coverage rule reads a later fill's recorded start position. That reconstructs the true position at T. It is not information the traders lacked.
- **Price.** Dollar size is mostly price. Only coins or share of exposure show adding.
- **One entity.** Three wallets are 84% of the panel's BTC long value. Any BTC dollar or coin total in the product is mostly them.
- **Survivorship and selection.**
  - The roster requires profit this month and before, and at least $50k today. Wallets that added into a top and lost are not in it.
  - The headline cut removes the last 30 days, but the "profit before this month" rule still spans the whole window.
- **Fixed panel.** It keeps the less active traders (capped fill histories start late). The per-event panels agree in direction.
- **Autocorrelation.** Daily 7- and 14-day changes overlap. The 14-day block bootstrap allows for this, but 149 days still hold only about 10 independent 14-day stretches.
- **Many comparisons.** F2 and the exploratory cuts test many pairs. A single interval that just clears 0 there means little.
- **No leverage data.** Share of exposure is the relative measure, not leverage on equity.

### What this means for the product

- **Show size in coins next to price, not dollars alone.** A size-versus-price overlay on the coin chart: the cohort's long size in coins, with the long value as a faint line, so rising dollars from a rising price are not read as conviction.
- **Add a concentration badge,** for example "top 3 wallets = 84% of this".
- **Show share of book,** so "they hold more BTC" is not confused with "they are more concentrated in BTC".
- **Keep it as context.** Nothing here supports a greed or size alert.
