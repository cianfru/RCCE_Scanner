# Executor gap: which of the backtest's management rules would help the executor? (declared 10 November 2026, before running)

The owner's go-ahead (10 November 2026): open the rule-lab PR and study the gap between the backtest and the executor.

## Why

Every replay study scores signals with the backtest position manager. The executor trades the same entries, sizing, 8% stop and signal exits, but differs in four management rules:

| Rule | Executor | Backtest manager |
|---|---|---|
| Decay exit (bars of Wait before a position is closed) | none | 20 bars |
| BTC weekly-band entry block | none | yes |
| Breakeven stop once a position has been +5% | yes | none |
| Risk-off closes | that coin's position | every position |

So replay results describe the rules, not the account. The rule-lab study (`rule-lab-study.md`) found that the decay exit is worth 11 to 18 points on 4H in the backtest manager. This study asks whether that, or any of the other three, holds when the rest is as the executor trades.

Correction to `rule-lab-study.md`: it says the executor enters on Accumulate. It does not; that entry was removed after `entry-quality-study.md`. The Accumulate recommendation in that document is withdrawn.

## Method

- `backend/backtest/executor_gap.py`: a costed position manager with each of the four rules set either way; tests in `backend/tests/test_executor_gap.py` (one checks the constants against `executor.py`).
- Rows: the live rules on 4H, windows 1–9, from the rule-lab captures (10 primary coins, 30 secondary coins). The executor reads the 4H scan. Signals are the same in every variant; only position management changes.
- Scoring: `backtest/rule_lab.score` (10 bps a side, equal allocation per coin, compounded window returns).
- Check done before any variant was computed: with the backtest's four rules the new manager reproduces the reference exactly (+57.31% and +35.14% over windows 1–9, same exits per window).

## Variants

| Name | Rules |
|---|---|
| X0 | The executor as it is: no decay, no band block, breakeven, Risk-off closes one coin. The baseline. |
| X1_decay20 | X0 plus the decay exit after 20 bars of Wait (3.3 days). |
| X1_decay42 | X0 plus the decay exit after 42 bars (7 days). The neighbouring level. |
| X2_band | X0 plus the BTC weekly-band entry block. |
| X3_riskoff_all | X0, and Risk-off on any coin closes every position. |
| X4_no_breakeven | X0 without the breakeven stop. |
| X5_decay20_band | X0 plus decay 20 and the band block. |
| B | The backtest manager (reference only). |

## Bar (fixed now)

Gains are in points of compounded return against X0, on the two coin sets.

**Selection, windows 1–6.** All must hold: both sets gain; the mean gain is at least +3 points; in neither set is the worst window more than 3 points worse than X0's. For X1_decay20 the neighbour X1_decay42 must have the same sign of mean gain.

**Confirmation, windows 7–9.** Mean gain above zero and neither set loses.

**No holdout.** Window 10 was read on 9 November for these data sets and is not read again. A variant that passes is therefore a recommendation with in-sample support only.

**What a pass leads to.** Nothing changes in the executor. A passing rule is put to the owner as a recommendation; if approved, the sensible first step is to log what the rule would have done alongside the live executor (a shadow record) before it trades.

**If nothing passes:** context, not a signal; the executor's management rules stand as they are.

## Known limits, stated before the results

- Bar closes only. The executor checks stops on every scan, so its stops and breakeven exits trigger earlier than a 4H close. `stop-rules-study.md` and `historical-stop-reconstruction.md` cover that difference.
- Equal allocation across 10 or 30 coins and 10 bps a side; the executor's whitelist, leverage and fills differ.
- Windows 1–9 are heavily used; X1 and X2 were chosen knowing the backtest manager does better with them.
- Stops themselves are not reopened (`stop-rules-study.md` stands). X4 only measures the breakeven stop in executor-like conditions, where that study measured it in backtest conditions.

## Results (10 November 2026)

**Verdict: two variants pass the bar. The weekly-band entry block passes on its own (X2), and the band block with the 20-bar decay exit passes together (X5). The decay exit on its own (X1) fails the neighbour rule. Nothing is changed in the executor; these are recommendations for the owner.**

Compounded return, % (worst window over windows 1–9):

| Variant | Primary 4H: W1–6, W7–9, W1–9 | Secondary 4H: W1–6, W7–9, W1–9 |
|---|---|---|
| X0 executor as it is | +28.1, +13.6, +45.5 (−8.0) | +9.3, +3.7, +13.4 (−11.1) |
| X1_decay20 | +30.8, +15.9, +51.6 (−6.9) | +13.4, +16.1, +31.7 (−7.9) |
| X1_decay42 | +28.2, +18.3, +51.6 (−7.5) | +3.5, +16.2, +20.2 (−9.7) |
| X2_band | +35.2, +15.1, +55.6 (−8.6) | +10.4, +5.2, +16.2 (−10.7) |
| X3_riskoff_all | same as X0 | same as X0 |
| X4_no_breakeven | +24.1, +12.3, +39.4 (−10.1) | +14.5, −1.0, +13.4 (−11.5) |
| X5_decay20_band | +36.6, +16.9, +59.7 (−6.2) | +16.8, +17.4, +37.1 (−8.3) |
| B backtest manager | +36.0, +15.6, +57.3 (−7.8) | +16.7, +15.8, +35.1 (−7.7) |

The bar, gain against X0 in points (primary, secondary):

| Variant | Selection W1–6 | Mean | Worst window | Confirmation W7–9 | Result |
|---|---|---|---|---|---|
| X1_decay20 | +2.7, +4.1 | +3.4 | better in both | +2.3, +12.4 | **fails**: the neighbour (42 bars) has the opposite sign on windows 1–6 (+0.1, −5.8) |
| X2_band | +7.1, +1.1 | +4.1 | −0.6, +0.4 | +1.5, +1.5 | **passes** |
| X3_riskoff_all | 0.0, 0.0 | 0.0 | same | 0.0, 0.0 | fails (no change: these rows contain no Risk-off exit of a held position) |
| X4_no_breakeven | −4.0, +5.2 | +0.6 | −2.1, −0.4 | −1.3, −4.7 | fails |
| X5_decay20_band | +8.5, +7.5 | +8.0 | better in both | +3.3, +13.6 | **passes** |

What this says:
- **The executor as it trades scores well below the backtest**: +45.5% against +57.3% on the primary coins and +13.4% against +35.1% on the secondary coins over windows 1–9. The replay studies have been describing a better manager than the one that trades.
- **The weekly-band entry block** (no new long while BTC is below its weekly band) passes cleanly on its own. It removes stop-outs: 130 to 113 on primary, 375 to 321 on secondary.
- **The decay exit** helps in both sets and both periods at 20 bars, but the 7-day level loses on the secondary set in windows 1–6. By the declared rule it does not pass alone. Its cost is visible in the strongest window (window 5): +64.8% without decay, +46.0% with it on primary; it gives up part of a strong run and gains in the weak windows.
- **The two together** are the strongest set and the closest to the backtest manager: +14.1 and +23.7 points over windows 1–9, with a better worst window in both sets. X5 contains the rule that failed alone; its pass rests on the combination.
- **The breakeven stop stays.** Removing it loses in both sets in windows 7–9. This agrees with `stop-rules-study.md`.
- **Risk-off scope** makes no difference in these rows.

Limits that matter for the decision: no untouched window remains for these data sets, the test is on bar closes, and both passing rules were chosen knowing the backtest manager does better with them. The support is in-sample and consistent across two coin sets and two periods; it is not an out-of-sample result.

### Recommendation (owner's decision; the executor is unchanged)

1. Record, alongside the live executor, what the band block and the decay exit would have done on each scan (a shadow record; no orders). This is the only clean test left, because it uses data that does not exist yet.
2. If the owner prefers to act now: the band entry block is the lower-risk change. It only withholds entries and passed the bar on its own.
