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
