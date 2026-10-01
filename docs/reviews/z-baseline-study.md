# z-score baseline after a long trend (declared 1 October 2026, before running)

## Diagnosis

- `_calc_zscore_hybrid` in `backend/engines/rcce_engine.py` (mirrored in `tradingview/reflex_rcce.pine`, `f_rcce`) measures the deviation of the log close from its 300-bar regression line (`LEN_REGRESSION`), then re-centres it on that deviation's own 200-bar mean (`LEN_LONG`) and divides by its 200-bar standard deviation: `z = (dev − mean200(dev)) / std200(dev)`.
- After a long convex run, the 200-bar mean deviation is large and positive (the price spent months above a straight line fitted through a curve). A coin then sitting on its trend line, or above it, reads deeply negative.
- **Example, HYPE 1D on the 30 September 2026 close (Hyperliquid candles).** The mean deviation over 200 days was +28.8%. Price was +1.9% above its regression line and +32% above the weekly band, within 7% of its 90-day high. The engine read z −1.22, REACC (pullback), 7/11 checks, Accumulate.
- A cross-section of the Radar coins on the same close found 7 of 70 daily charts more than 15% above the weekly band with z below 0, and 44 of 76 on 4H.

## Variants

- **C:** today's logic (baseline).
- **G:** C plus a sign guard. Where z has the opposite sign to the raw deviation from the line (`dev`: the log close minus the regression line, or the SMA(200) fallback before 300 bars exist), z = 0. Nothing else changes.
- **F1:** no re-centring: `z = dev / std200(dev)`. Same line, same window, thresholds unchanged.

Only `_calc_zscore_hybrid` differs. Everything downstream (warm-up dampening, regime model, persistence, synthesizer, confluence, the position manager) is today's code.

## Harness (windows 1–9 only, ends 2026-03-29; the holdout is never replayed)

`backend/backtest/live_logic_replay.py` → `backend/backtest/live_logic_check.py`, the same harness as the Overheated and after-the-spike studies, with a new `--zbase {current,G,F1}` switch that swaps the z function in-process.

Runs, in this order:

1. **Deciding run:** the 10 primary coins (BTC, ETH, SOL, BNB, XRP, ADA, AVAX, DOGE, DOT, LINK), 4H Binance history, the same costed PositionManager (5+5 bps fees, 5+5 bps slippage, its own stops, exits and sizing) and the same BTC weekly-band entry block.
2. **Confirmation:** the study's 30-coin secondary set, 4H, otherwise identical.
3. **Confirmation:** both coin sets on 1D. The replay gets a `--tf 1d` switch: the daily chart becomes the primary timeframe (the bars the manager trades), with the same 500-bar warm-up. Daily data starts on 2019-01-01 so the warm-up ends before window 1; a coin listed later joins once it has 500 daily bars. The manager's bar-count rules (20 Wait bars before a stale exit) are unchanged, so on 1D they span days instead of hours. This run is reported, not decided on.

## Reported per variant and run

- Compounded return over windows 1–9, worst-window drawdown, median Sharpe, trades, per-window returns.
- Regime mix and signal mix (share of coin-bars inside windows 1–9).
- **Contradiction share:** among coin-bars inside windows 1–9 where the close is more than 15% above the weekly band (the scanner's `deviation_pct`) and within 10% of its 90-bar high (highest close of the last 90 bars of that timeframe, this bar included), the share with z < 0.
- For information only, not part of the rule: the same share without the 90-bar-high condition (the cross-section's measure).

## Decision rule (fixed now)

All three conditions are judged on the deciding run (primary coins, 4H):

1. the variant cuts the contradiction share by at least half (variant ≤ 0.5 × C);
2. against C, it does not lower the compounded return by more than 5 points;
3. against C, it does not deepen the worst-window drawdown by more than 2 points.

- If both G and F1 pass, G ships (the smaller change).
- If neither passes, nothing ships, and the finding is labelled "context, not a signal".
- The secondary and 1D runs are confirmation; they are reported in full and do not change the verdict.

If a variant ships it goes in behind a constant so it can be rolled back, mirrored in the Pine script, with tests, and it waits for the owner's approval before release.

## Results (windows 1–9, costed PositionManager, run 1 October 2026)

Today's logic (C) on the deciding run reproduces the earlier studies' baseline exactly (+43.1%, −10.4%, 314 trades), so the harness changes did not move it.

### Deciding run: 10 primary coins, 4H

| | C (today) | G (sign guard) | F1 (no re-centring) |
|---|---:|---:|---:|
| Contradiction share (declared) | 40.2% (5,944 of 14,801 bars) | 27.2% (4,023) | 33.4% (4,948) |
| Cut vs C (needs ≥ 50%) | | 32% | 17% |
| Compounded return | +43.1% | +44.4% (+1.2) | +55.6% (+12.5) |
| Worst-window drawdown | −10.4% | −9.9% (+0.5) | −11.8% (−1.4) |
| Median Sharpe | 0.32 | 0.17 | 0.00 |
| Trades | 314 | 288 | 310 |
| Regime mix (Uptrend / Re-accumulating / Accumulation) | 48 / 44 / 8% | 45 / 42 / 13% | 47 / 44 / 9% |
| Signal mix (Wait / Light long / Accumulate) | 82.3 / 13.4 / 1.9% | 85.3 / 11.5 / 1.3% | 82.3 / 13.3 / 2.0% |
| Contradiction share without the 90-bar-high condition (information) | 51.5% | 40.2% | 46.9% |

### Confirmation runs

| | C | G | F1 |
|---|---:|---:|---:|
| **30 secondary coins, 4H** | | | |
| Contradiction share (cut vs C) | 32.1% | 19.4% (40%) | 24.6% (23%) |
| Compounded return | +45.3% | +43.9% (−1.4) | +44.3% (−1.0) |
| Worst-window drawdown | −14.6% | −13.5% (+1.2) | −11.1% (+3.5) |
| Median Sharpe / trades | −0.80 / 725 | −0.68 / 703 | −0.34 / 707 |
| **10 primary coins, 1D** | | | |
| Contradiction share (cut vs C) | 13.1% | 2.8% (79%) | 4.3% (67%) |
| Compounded return | +36.6% | +30.7% (−5.9) | +46.4% (+9.8) |
| Worst-window drawdown | −14.0% | −14.0% (−0.1) | −18.7% (−4.7) |
| Median Sharpe / trades | −0.30 / 138 | 0.00 / 137 | 0.00 / 164 |
| **30 secondary coins, 1D** | | | |
| Contradiction share (cut vs C) | 3.4% | 0.8% (77%) | 2.6% (24%) |
| Compounded return | +4.9% | +12.8% (+7.9) | +24.7% (+19.8) |
| Worst-window drawdown | −20.0% | −19.8% (+0.3) | −21.4% (−1.3) |
| Median Sharpe / trades | −0.42 / 398 | −0.19 / 363 | −1.35 / 392 |

Per-window returns, C / G / F1 (%):

| Run | W1 | W2 | W3 | W4 | W5 | W6 | W7 | W8 | W9 |
|---|---|---|---|---|---|---|---|---|---|
| Primary 4H | +1.2 / +0.5 / +5.3 | 0 / 0 / 0 | +5.0 / +5.7 / +5.3 | −1.9 / −4.5 / −4.1 | +35.6 / +35.5 / +42.1 | −9.9 / −5.7 / −5.8 | +11.8 / +9.1 / +15.6 | +6.4 / +8.2 / −0.5 | −5.6 / −5.7 / −5.0 |
| Secondary 4H | −3.8 / −3.4 / −1.7 | 0 / 0 / 0 | +2.7 / +0.2 / +0.4 | −2.6 / −3.7 / −4.6 | +40.9 / +39.7 / +35.7 | −8.5 / −7.0 / −6.1 | +24.4 / +25.5 / +29.7 | −3.6 / −2.9 / −4.7 | −2.3 / −2.4 / −2.7 |
| Primary 1D | −8.8 / −5.1 / −2.6 | 0 / 0 / 0 | −1.9 / −0.3 / −0.4 | −5.9 / −5.9 / −8.9 | +50.2 / +43.5 / +69.3 | −4.0 / −4.1 / −5.3 | +14.8 / +10.7 / +12.0 | +9.1 / +7.0 / +3.0 | −10.1 / −10.0 / −10.4 |
| Secondary 1D | −17.0 / −10.4 / −8.0 | 0 / 0 / 0 | +0.7 / +1.0 / −0.6 | −0.5 / −0.2 / −6.0 | +36.0 / +34.4 / +47.8 | −2.7 / −2.2 / −5.4 | +6.7 / +7.0 / +17.7 | −7.9 / −8.5 / −9.5 | −3.0 / −3.0 / −2.7 |

Window 2 has no trades in any run: the BTC weekly-band block holds all entries. Its Sharpe of 0 is why some medians read 0.00.

## Verdict: nothing ships. Context, not a signal.

On the deciding run neither variant meets the first condition. G cuts the contradiction share by 32% and F1 by 17%; the bar is 50%. Both pass the return and drawdown conditions there, but all three are required. The confirmation runs do not change the verdict, and they do not point one way either:
- G's cut clears 50% on both daily runs, but there it costs 5.9 points on the primary coins and adds 7.9 on the secondary coins.
- F1 raises the compounded return in three of four runs, but deepens the worst-window drawdown in three of four (by 4.7 points on primary 1D).

## Reading

- **On 4H, most of the declared contradiction is not the re-centring artefact.** After the sign guard, 27% of the bars still read z < 0. In all of them the close is below its own 300-bar regression line (50 days on 4H), even though it is more than 15% above the weekly band and within 10% of its 90-bar (15-day) high. That is a real pullback on the 4H scale, measured against a much shorter horizon than the weekly band. The declared measure mixes the two horizons on 4H.
- **On 1D, the artefact is the main source.** The guard removes 79% (primary) and 77% (secondary) of the contradiction bars, so most daily cases are the HYPE pattern: price on or above its line, z below 0 because of the re-centring. The effect on returns is mixed in sign, so the replay gives no evidence that removing it helps or hurts trading.
- **The guard sets z to 0. It does not make the read an Uptrend.** At z = 0 the regime model leans to Accumulation (Accumulation's share rises from 8% to 13% of bars on 4H). HYPE moves from Re-accumulating / Accumulate to Re-accumulating / Wait, not to Uptrend.
- **F1 restores the Uptrend read on long trends,** but it lets z run higher everywhere, and with the thresholds unchanged the drawdowns deepen.
- Any further change, such as a guard on the daily chart only, would be a new hypothesis. It would need its own declared study before anything is computed.

## Reads on today's Hyperliquid candles (context only; nothing changed)

On the 30 September 2026 daily close, with the scanner's own path and no tracked-wallet input (so checks are out of 9):

| Coin, 1D | Above weekly band | Off 90-day high | C (today) | G | F1 |
|---|---:|---:|---|---|---|
| HYPE | +32.2% | −6.5% | −1.22 Re-accumulating, Accumulate | 0.00 Re-accumulating, Wait | +0.10 Uptrend, Strong long |

Of the 48 daily charts more than 15% above the weekly band and within 10% of their 90-day high, 4 read z < 0 today under C (HYPE, ORDI, NOT, INJ) and none under G or F1.

## Deviations from the declaration

- The secondary runs import their coin list from `backtest`, so they were run with `PYTHONPATH=.` from `backend/`. The first launch failed on that import before computing anything. Nothing else changed.
- The verdict on the deciding run was known before the confirmation runs finished. They were still run in full, as declared.
