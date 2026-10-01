# Daily z-score: sign guard or capped re-centring (declared 1 October 2026, before running)

Follows `docs/reviews/z-baseline-study.md`, which shipped nothing. That study found that on the daily chart most of the contradiction it measured (z below 0 while price is far above the weekly band and near its high) comes from the re-centring, not from real pullbacks. This study tests changes on the daily chart only. The 4H z stays exactly as today.

## Diagnosis (unchanged)

`_calc_zscore_hybrid` in `backend/engines/rcce_engine.py` (mirrored in `tradingview/reflex_rcce.pine`) computes `z = (dev − mean_dev) / std_dev`, where `dev` is the log close minus its 300-bar log regression line (SMA(200) fallback before 300 bars exist), and `mean_dev` / `std_dev` are that deviation's 200-bar mean and standard deviation. After a long convex run `mean_dev` stays large, so a coin sitting on its line reads well below 0.

## Variants (1D only)

- **C:** today's logic on every timeframe.
- **G1d:** on the daily chart, where z has the opposite sign to `dev`, z = 0 (the previous study's G). 4H unchanged.
- **K1d:** on the daily chart, the re-centring is capped: `mean_dev` is clipped to ±X before it is subtracted, with **X = `std_dev`**, the same 200-bar standard deviation of `dev` that z is divided by, on the same bar. So `z = (dev − clip(mean_dev, −std_dev, +std_dev)) / std_dev`, equivalently `z = dev/std_dev − clip(mean_dev/std_dev, −1, +1)`: the re-centring can move z by at most one unit. Where `|mean_dev| ≤ std_dev`, K1d equals C. 4H unchanged.

Why X = 1 standard deviation, fixed now, before anything is computed:
- it is in the units z is already measured in, so the cap is the same for every coin whatever its volatility, and needs no data to set;
- it has no tuning: one unit is the smallest round cap that still lets the re-centring remove an ordinary offset, while an offset larger than the coin's own typical swing is treated as trend, not as baseline;
- the alternative (a fixed percentage such as the median absolute `mean_dev` across coins) would have to be measured on data first, and a single percentage would bind volatile coins far harder than BTC.

Only the daily z function differs. Everything downstream (warm-up dampening, regime model, persistence, synthesizer, confluence, the position manager) is today's code.

## What is already known (disclosed before running)

On a daily replay every z the engine computes is a daily z, so C and G1d there are the same computations as the previous study's C and G on 1D, whose results are published:
- primary 1D: C +36.6% / −14.0%, G +30.7% (−5.9 points) / −14.0%, contradiction 13.1% → 2.8% (79% cut);
- secondary 1D: C +4.9%, G +12.8% (+7.9 points).

By the rule below, G1d therefore fails the return condition (−5.9 against a 5-point limit) unless the re-run differs. Only K1d is blind. C and G1d are re-run anyway with the same data and code to confirm the numbers; any difference is reported as a deviation.

## Harness (windows 1–9 only, ends 2026-03-29; the holdout is never replayed)

`backend/backtest/live_logic_replay.py` → `backend/backtest/live_logic_check.py`, the harness of the previous study, with `--tf 1d` and two new `--zbase` values, `G1d` and `K1d`. They swap the z function only while the engine is computing a series whose bars are at least 12 hours apart (the daily chart); a 4H series keeps today's z.

Runs, both with `--tf 1d` (the daily chart is the traded timeframe; 500-bar warm-up; daily data from 2019-01-01; a coin listed later joins once it has 500 daily bars):

1. **Primary:** the 10 primary coins (BTC, ETH, SOL, BNB, XRP, ADA, AVAX, DOGE, DOT, LINK), Binance daily history, the same costed PositionManager (5+5 bps fees, 5+5 bps slippage, its own stops, exits and sizing) and the same BTC weekly-band entry block.
2. **Secondary:** the study's 30-coin secondary set, otherwise identical.

Caveat carried over, reported and not changed: the manager counts bars (20 Wait bars before a stale exit, and its other bar-count rules), so on the daily chart those rules span days instead of hours.

## Measure (fixed now)

Per coin set, among daily coin-bars inside windows 1–9 where the close is more than 15% above the weekly band (the scanner's `deviation_pct`) and within 10% of its 90-bar high (highest daily close of the last 90 bars, this bar included), the **share with z < 0**. Cut = 1 − variant share / C share.

Also reported, not part of the rule: the same share without the 90-bar-high condition; compounded return over windows 1–9; worst-window drawdown; median Sharpe; trades; per-window returns; regime and signal mix.

## Decision rule (fixed now)

On the **primary** 1D run, a variant ships only if all four hold:

1. it cuts the contradiction share by at least 50% (variant ≤ 0.5 × C);
2. it does not lower the compounded return by more than 5 points versus C;
3. it does not deepen the worst-window drawdown by more than 2 points versus C;
4. on the **secondary** 1D run, it does not lower the compounded return by more than 5 points versus C.

- If both variants pass, the one with the higher primary compounded return ships.
- If neither passes, nothing ships, and the finding is labelled "context, not a signal".

## Today's reads (reported, not part of the rule)

On the latest closed daily candle at run time (the 30 September 2026 close), Hyperliquid candles, every Radar coin with enough history, the scanner's own per-symbol path and synthesizer with the same fixed market context as the previous study (no tracked-wallet input):
- for each variant, the number of coins whose daily signal differs from C, and whose daily regime differs from C;
- the 4H reads under each variant, which must equal C (a check of the "1D only" scope);
- HYPE, BTC, ETH and SOL in full.

## If a variant ships

- In `rcce_engine.py`, for the daily chart only, behind a constant (on only if it passed), so it can be switched off; `compute_rcce` learns the timeframe from the scanner.
- Mirrored in `tradingview/reflex_rcce.pine` for the daily chart.
- Tests; the full backend test suite run five times.
- One further run, for information only (it does not change the verdict): the primary coins on 4H with the variant on the daily input. The 4H z is unchanged, but the 4H confluence label reads the daily regime and signal, and the position manager (and the executor) sizes entries by that label, so 4H results can still move. The change in 4H return, drawdown and confluence-label mix is reported.
- It waits for the owner's approval before release.
