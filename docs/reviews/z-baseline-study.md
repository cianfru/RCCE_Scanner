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
