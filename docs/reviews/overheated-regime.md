# Overheated (BLOWOFF) regime never fires (declared 26 September 2026, before running)

## Diagnosis

- In 192,000 daily coin-days (151 coins, 2019 onward) the engine never resolved a single bar to BLOWOFF, although the z-score was above 2.5 on 2.7% of them, above 3.5 on 0.41% (741 coin-days), and reached 7.4. The signal integrity audit (#139) found the same on 228k bars and left it unchanged.
- **Cause 1: the score.** In `_calc_regime_probabilities` the MARKUP weight is `max(0, z + deadband) × energy_boost` and the BLOWOFF weight `max(0, z − z_blowoff) × gate`. MARKUP grows at least as fast as BLOWOFF and starts 2.5+ points earlier, so it wins at every z when energy is high, which is exactly when a blow-off happens. The original Pine `calc_regime_probabilities` has the same flaw; the Pine scanner module used a direct rule instead (z above the hard-trim line = BLOWOFF).
- **Cause 2: persistence.** Every regime change needs `MIN_REGIME_BARS` = 5 consecutive bars. A spike above the line rarely lasts 5 daily bars.
- **Consequence:** the z-based exits (TRIM above `Z_TRIM × vol_scale`, TRIM_HARD above `Z_TRIM_HARD × vol_scale`) only run inside BLOWOFF and are dead. The only extreme exit is heat ≥ 95 (distance from the weekly band).
- **Example, XMR January 2026 (Hyperliquid candles).** 4H z was 3.7–4.9 from 11 Jan 20:00 to 14 Jan 12:00 (about 15 bars); daily z was 3.3–3.7 on 12–14 Jan, with a high of $801 before the fall to about $330. The engine said MARKUP throughout, heat peaked at 73, and no exit or warning was issued.

## Fix (parameters are the engine's existing constants; nothing is fitted)

- **F1, score:** above the engine's own line (`Z_BLOWOFF × vol_scale`) the MARKUP weight is handed to BLOWOFF through the same smooth gate the model already uses: `g = soft_gate(z, z_blowoff, 0.2)`, `p_markup ← p_markup × (1 − g)`, `p_blowoff ← p_blowoff + p_markup_before × g`. Below the line nothing changes.
- **F2, entry speed:** entering BLOWOFF from the bullish family needs 2 bars instead of 5. It is a caution state, like the bearish regimes the persistence docstring already says should not be delayed. Leaving BLOWOFF uses the existing rules (bullish-family persistence or the dominance override).

## Test (windows 1–9 only, holdout untouched)

Same harness as the MARKDOWN gate (`backtest/live_logic_replay.py` → `live_logic_check.py`): 4H Binance history, the 10 primary coins, one costed PositionManager.

- **C:** today's live logic (baseline).
- **D:** C + F1.
- **E:** C + F1 + F2.

Reported per variant: compounded return, worst-window drawdown, median Sharpe, trades, per-window returns, number of BLOWOFF bars and of TRIM / TRIM_HARD exits. Plus the XMR January 2026 bars on 4H and 1D, as the case the model was built for (not a statistical test).

## Decision rule (fixed now)

- A variant ships only if it flags the XMR spike (BLOWOFF on 4H before the $790 bar) and, against C, it does not lower the compounded return by more than 5 points and does not deepen the worst-window drawdown by more than 2 points.
- If both D and E pass, E ships (it flags earlier). If neither passes, nothing ships and the results are reported as they are.

## Results (windows 1-9, 10 primary coins, 4H, costed PositionManager)

| | C (today) | D (C + F1) | E (C + F1 + F2) |
|---|---:|---:|---:|
| Compounded return | +43.1% | +35.3% | +30.3% |
| Worst-window drawdown | -10.4% | -10.3% | -11.3% |
| Median Sharpe | 0.32 | 0.38 | 0.19 |
| Trades | 314 | 327 | 355 |
| Overheated (BLOWOFF) bars | 0 | 1,353 | 2,603 |
| TRIM / TRIM_HARD bars | 4,036 / 0 | 4,245 / 88 | 4,401 / 139 |
| Window 7 (Oct 2024 to Apr 2025) | +11.8% | +7.8% | +0.8% |

**Verdict: nothing ships.** D gives up 7.9 points of compounded return against C and E gives up 12.9, both beyond the 5-point limit. The XMR condition is therefore moot. The switch stays in the engine, off.

Where the cost comes from: most of it is window 7, the late-2024 alt rally. There, strong trends kept z above 2.5 for weeks and kept going, and the earlier trims cut the winners (DOGE +$505 in C against +$170 in E, ADA +$330 against +$111, DOT +$196 against +$10). The Overheated state catches spikes like XMR, but on these coins it also fires inside trends that were not over. Nothing is tuned from this result: a new variant would need its own declaration and would be exploratory on these windows.

What still holds: the diagnosis is real. The regime scoring cannot reach Overheated, so the scanner keeps calling these bars Uptrend. The after-the-spike cool-off (docs/reviews/after-the-spike-study.md) is tested next, on C as its baseline, since C is what stays live.
