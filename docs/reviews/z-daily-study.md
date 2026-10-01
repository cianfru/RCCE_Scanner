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

## Results (windows 1–9, costed PositionManager, daily chart traded, run 1 October 2026)

C and G1d reproduce the previous study's daily numbers exactly on both coin sets (primary C +36.6% / −14.0% / 138 trades, G +30.7%; secondary C +4.9% / −20.0% / 398 trades, G +12.8%). The harness change did not move them.

### Primary: 10 coins, 1D (decides)

| | C (today) | G1d (sign guard) | K1d (re-centring capped at 1 std) |
|---|---:|---:|---:|
| Contradiction share (declared) | 13.1% (283 of 2,155 bars) | 2.8% (60) | 10.3% (223) |
| Cut vs C (needs ≥ 50%) | | **79%** pass | **21%** fail |
| Compounded return (needs ≥ −5 points) | +36.6% | +30.7% (**−5.9**) fail | +41.6% (+5.0) pass |
| Worst-window drawdown (needs ≥ −2 points) | −14.0% | −14.0% (−0.1) pass | −13.9% (+0.1) pass |
| Median Sharpe | −0.30 | 0.00 | −0.29 |
| Trades | 138 | 137 | 150 |
| Regime mix (Uptrend / Re-accumulating / Accumulation / Markdown) | 45 / 43 / 8 / 5% | 41 / 41 / 13 / 5% | 44 / 43 / 8 / 5% |
| Signal mix (Wait / Light long / Accumulate) | 78.4 / 18.5 / 1.5% | 80.6 / 17.4 / 0.3% | 77.3 / 19.6 / 1.5% |
| Share without the 90-bar-high condition (information) | 18.1% | 5.2% | 15.8% |

### Secondary: 30 coins, 1D

| | C | G1d | K1d |
|---|---:|---:|---:|
| Contradiction share (cut vs C) | 3.4% (117 of 3,460) | 0.8% (77%) | 2.1% (39%) |
| Compounded return (needs ≥ −5 points) | +4.9% | +12.8% (+7.9) pass | +13.4% (+8.5) pass |
| Worst-window drawdown | −20.0% | −19.8% (+0.3) | −19.3% (+0.7) |
| Median Sharpe / trades | −0.42 / 398 | −0.19 / 363 | −1.26 / 420 |
| Share without the 90-bar-high condition (information) | 12.2% | 2.7% | 9.7% |

Per-window returns, C / G1d / K1d (%):

| Run | W1 | W2 | W3 | W4 | W5 | W6 | W7 | W8 | W9 |
|---|---|---|---|---|---|---|---|---|---|
| Primary 1D | −8.8 / −5.1 / −8.7 | 0 / 0 / 0 | −1.9 / −0.3 / −2.3 | −5.9 / −5.9 / −7.2 | +50.2 / +43.5 / +50.2 | −4.0 / −4.1 / −4.1 | +14.8 / +10.7 / +21.2 | +9.1 / +7.0 / +9.1 | −10.1 / −10.0 / −10.1 |
| Secondary 1D | −17.0 / −10.4 / −17.0 | 0 / 0 / 0 | +0.7 / +1.0 / +0.3 | −0.5 / −0.2 / −1.9 | +36.0 / +34.4 / +37.2 | −2.7 / −2.2 / −2.7 | +6.7 / +7.0 / +17.0 | −7.9 / −8.5 / −8.2 | −3.0 / −3.0 / −3.0 |

Window 2 has no trades in any run: the BTC weekly-band block holds all entries.

Caveat, as declared: the position manager counts bars, so on the daily chart its rules span days (20 Wait bars before a stale exit is 20 days, not 80 hours). The manager was not changed; the daily results are what that manager does on daily bars, not what the executor would do.

## Verdict: nothing ships. Context, not a signal.

- **G1d fails condition 2.** It cuts the contradiction share by 79% but lowers the primary compounded return by 5.9 points (limit 5). This was known before the run (see above); the re-run confirms it.
- **K1d fails condition 1.** It cuts the share by 21% on the primary coins (39% on the secondary), against a bar of 50%. It passes the other three conditions.

Nothing was changed in the engine, the Pine script or the tests. The conditional 4H confluence run was not needed.

## Reading

- **The cap at one unit is too loose to remove the daily artefact.** A coin sitting on its line can still read down to z −1 under K1d. HYPE on the 30 September close: price +1.9% above its line, `mean_dev` 1.32 std; K1d reads −0.90, against −1.22 under C. z depends on prices only, so the 2,155 primary bars are the same in every run: about 60 of K1d's 223 remaining bars are below their line (G1d's remainder), and the other ~160 sit above it by less than one std, where a one-unit cap still leaves z below 0.
- **K1d's return gain sits in one window.** On both coin sets, almost all of it comes from window 7 (primary +14.8 → +21.2, secondary +6.7 → +17.0); the other windows move by about a point either way. It is not evidence that capping the re-centring helps trading.
- **G1d removes the artefact but costs return on the primary coins and adds it on the secondary coins**, as in the previous study. Setting z to 0 moves bars into Accumulation (8% → 13% of bars) and cuts Accumulate signals (1.5% → 0.3%), not into Uptrend.
- A tighter cap (for example 0.5 std) or a guard plus cap would be a new hypothesis and needs its own declared study.

## Today's reads (Hyperliquid candles, the 30 September 2026 close; context only, nothing changed)

Scanner's own path, fixed market context, no tracked-wallet input (checks out of 9). 108 Radar coins on 1D, 105 on 4H.

| | z changes | Regime changes | Signal changes |
|---|---:|---:|---:|
| G1d, 1D | 11 | 5 | **5**: APE, POPCAT, PNUT, HYPE, SPX |
| K1d, 1D | 45 | 7 | **13**: APE, INJ, GMX, KAS, TIA, JUP, POPCAT, EIGEN, CELO, PURR, PNUT, SPX, LAYER |
| G1d and K1d, 4H | 0 | 0 | 0 (the "1D only" scope holds) |

| Coin, 1D | Price vs line | `mean_dev` / std | Above weekly band | Off 90-day high | C (today) | G1d | K1d |
|---|---:|---:|---:|---:|---|---|---|
| HYPE | +1.9% | 1.32 | +32.2% | −6.5% | −1.22 Re-acc, Accumulate 6/9 | 0.00 Re-acc, Wait 7/9 | −0.90 Re-acc, Accumulate 6/9 |
| BTC | +24.7% | 0.90 | +16.4% | −3.5% | +1.30 Uptrend, Light long 8/9 | same | same |
| ETH | +39.9% | 0.69 | +24.3% | −3.3% | +1.35 Uptrend, Light long 8/9 | same | same |
| SOL | +51.8% | 0.85 | +32.3% | −3.4% | +1.51 Uptrend, Light long 8/9 | same | same |
| APE | +21.9% | 1.27 | +6.9% | −10.2% | −0.53 Re-acc, Accumulate 6/9 | 0.00 Uptrend, Light long 8/9 | −0.26 Re-acc, Wait 7/9 |
| INJ | +37.7% | 1.43 | +37.8% | −9.5% | −0.17 Uptrend, Light long 8/9 | 0.00 Uptrend, Light long 8/9 | +0.26 Uptrend, Strong long 8/9 |
| GMX | +22.3% | 1.89 | +17.0% | −6.1% | +0.38 Uptrend, Strong long 8/9 | same as C | +1.27 Uptrend, Light long 8/9 |
| KAS | +53.8% | 1.42 | +35.8% | −9.1% | +2.23 Uptrend, Light long 8/9 | same as C | +2.64 Uptrend, Wait 7/9 |
| TIA | +29.9% | 1.74 | +15.8% | −15.1% | −0.29 Uptrend, Light long 8/9 | 0.00 Uptrend, Light long 8/9 | +0.45 Uptrend, Strong long 8/9 |
| JUP | +51.4% | 1.68 | +51.1% | −11.5% | +0.86 Uptrend, Strong long 8/9 | same as C | +1.54 Uptrend, Light long 8/9 |
| POPCAT | +26.4% | 2.02 | +4.5% | −13.0% | −0.37 Re-acc, Accumulate 7/9 | 0.00 Accumulation, Strong long 8/9 | +0.65 Uptrend, Strong long 8/9 |
| EIGEN | +41.8% | 1.34 | +13.2% | −11.2% | −0.07 Uptrend, Light long 8/9 | 0.00 Uptrend, Light long 8/9 | +0.27 Uptrend, Strong long 8/9 |
| CELO | +60.9% | 1.73 | +31.9% | 0.0% | +1.78 Uptrend, Light long 8/9 | same as C | +2.52 Uptrend, Wait 7/9 |
| PURR | +46.5% | 1.15 | +56.8% | −2.8% | +0.48 Accumulation, Strong long 8/9 | same as C | +0.63 Re-acc, Wait 7/9 |
| PNUT | +32.9% | 1.59 | +12.9% | −6.8% | +0.08 Re-acc, Wait 7/9 | +0.08 Accumulation, Strong long 8/9 | +0.67 Uptrend, Strong long 8/9 |
| SPX | +19.7% | 1.76 | +9.0% | −27.0% | −0.81 Re-acc, Accumulate 6/9 | 0.00 Accumulation, Strong long 8/9 | −0.04 Accumulation, Strong long 8/9 |
| LAYER | +43.4% | 2.11 | +5.5% | −7.5% | +0.65 Uptrend, Strong long 8/9 | same as C | +1.75 Uptrend, Light long 8/9 |

(PNUT's G1d regime differs from C with the same z: the regime model's persistence follows the whole z history, which the guard changes on earlier bars.)

Of the 51 daily charts more than 15% above the weekly band and within 10% of their 90-day high, 4 read z < 0 under C (INJ, ORDI, NOT, HYPE), none under G1d and 2 under K1d (ORDI, HYPE).

On the unclosed 1 October daily candle (the read in the brief: HYPE $88.86, line $89.81, `mean_dev` +28.6%), HYPE is below its line, so G1d leaves it at −1.36 and K1d reads −1.05. Both are Re-accumulating, Accumulate 6/9, as under C.

## Deviations from the declaration

- The runs were launched with `PYTHONPATH=.` from `backend/`, as in the previous study, and read the same cached Binance history.
- In addition to the declared closed-candle reads, HYPE, BTC, ETH and SOL were also read on the unclosed 1 October candle, to match the numbers in the brief. This is labelled above and plays no part in the verdict.
- The verdict was known once the primary run finished. The secondary run was still completed in full, as declared.
