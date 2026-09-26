# After the spike: how prices come back from extreme z-scores (declared 26 September 2026, before running)

Question: when a coin's z-score goes to an extreme, what happens after the peak? How far does price fall, how fast, does it return to where the spike started, and how do longs taken as z comes back below the line do? This follows the Overheated fix (docs/reviews/overheated-regime.md). There the engine exited XMR on the way up in January 2026 but still offered a Light long at $678 on the way down, before the fall to about $280.

## Stage 1: describe (windows 1-9 only, ends 2026-03-29)

**Data**
- Daily: the 151 coins of the market history rebuild (Binance daily closes, the scanner's engine; per coin per day regime and z).
- 4H: the replay of today's logic on the 10 primary coins (price, z, regime, signal per bar).

**A spike event** is a bar where z ≥ T while z stayed below T for the previous 20 bars. It is reported for T = 2.5, 3.0 and 3.5. The spike ends at the first bar with z < 1.5, or after 60 bars. The peak is the highest close from the event to the spike's end. The pre-spike level is the close 20 bars before the event.

**Measured from the peak, over the next 60 bars:**
- the deepest drawdown from the peak close, and the bars it took;
- the share of the spike given back: (peak − trough) / (peak − pre-spike level);
- the share of events that fell below the pre-spike level;
- the lowest z, and the bars until z fell below 1 and below 0.

**Re-entry.** The re-entry bar is the first bar after the peak where the regime is Uptrend and z is back below 2.0 (the synthesizer's entry line before volatility scaling). From there, the returns over the next 10 and 30 bars are compared with all other Uptrend bars with z between 1 and 2 that are not within 60 bars after a spike.

Reported as medians and quartiles, per threshold and timeframe, with event counts. Descriptive only: no rule is chosen from it by fitting numbers.

## Stage 1 results (1D, 151-coin rebuild, windows 1-9)

| | z ≥ 2.5 | z ≥ 3.0 | z ≥ 3.5 |
|---|---:|---:|---:|
| Spikes (markets) | 334 (86) | 198 (71) | 114 (56) |
| Rise into the peak, median | +80% | +122% | +139% |
| Deepest drawdown from the peak within 60 days, median (q25 to q75) | -37% (-52 to -27) | -39% (-55 to -28) | -40% (-55 to -29) |
| Days from the peak to that low, median | 38 | 38 | 38.5 |
| Share of the spike given back, median | 86% | 78% | 72% |
| Fell below the pre-spike level | 38% | 27% | 22% |
| Lowest z within 60 days, median | -0.3 | -0.4 | -0.5 |
| z back below 1 within 60 days (median days) | 91% (18) | 95% (20) | 98% (21) |
| z back below 0 within 60 days (median days) | 63% (37) | 70% (39.5) | 74% (40.5) |
| Uptrend re-entry with z < 2, days after the peak, median | 4 | 6 | 7.5 |
| Return 30 days after that re-entry, median (share positive) | -11% (32%) | -11% (35%) | -8% (39%) |
| Ordinary Uptrend bars with z 1 to 2, 30 days, median (share positive) | -3% (44%) | -4% (42%) | -4% (42%) |

Reading:
- A spike is usually followed by a deep, slow unwind. The low comes more than a month after the peak, most of the move is given back, and z typically returns to about the mean (slightly below it).
- The engine offers an Uptrend entry again within days of the peak, as z drops under 2, long before the unwind is done. Those entries do markedly worse than ordinary Uptrend entries at the same z. The XMR Light long at $678 is the normal case, not bad luck.

## Stage 2: cool-off rules (declared 26 September 2026 after stage 1, before running them)

The rule follows the structure stage 1 shows (reversion to the mean), with no fitted numbers. It is computed from the engine's own window, so live and replay behave the same.

- **A spike** is the last bar in the window with z ≥ `Z_BLOWOFF` (2.5). Its run is the consecutive bars around it with z ≥ 2.0, and the spike peak is the highest close in that run.
- **Cooling off** holds from the spike until either of these happens:
  - **K0:** z has closed below 0 (price back at its regression mean);
  - **K1:** z has closed below 1 (most of the stretch unwound).

  In both, a close above the spike peak ends the cool-off early, because the trend has resumed.
  - **K0d:** as K0, but judged on the daily chart and applied to 4H entries. Added before any run: on XMR the 4H z returned to 0 about three days after the January 2026 peak, and 4H Accumulate signals then fired at $505 to $462, above the $293 low. Stage 1 puts the unwind at weeks, the daily scale.
- **While cooling off**, new long entries (Strong long, Light long, Accumulate) become Wait, with the reason stated. Exits are untouched.

**Test.**
- On the 4H replay harness, 10 primary coins, windows 1-9, costed PositionManager.
- **Baseline:** whichever of C/E the Overheated study ships.
- **Variants:** baseline + K0, baseline + K1, and baseline + K0d.
- **Confirmation:** the same on the study's 30-coin secondary set.

**Decision rule (fixed now).**
- A variant ships only if, on both coin sets, it does not lower the compounded return by more than 2 points and does not deepen the worst-window drawdown.
- If more than one passes, the one with the higher compounded return on the primary set ships.
- If neither passes, nothing ships and the result is reported.

