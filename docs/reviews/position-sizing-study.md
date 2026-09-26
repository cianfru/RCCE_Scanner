# Position sizing: bigger on some trades than others (declared 26 September 2026, before running)

Question: with the entries and exits unchanged, does putting more money into some trades and less into others beat the current sizing?

## What is already known

- **Sector tilts were tested and did not pass** (docs/reviews/sector-momentum-study.md). This covered avoiding lagging sectors and taking only leading ones. Favouring leading sectors is not repeated here.
- **The stop study** (docs/reviews/stop-rules-study.md) found that the stop rule moves results by only a few points. Most trades end on the engine's own exits and the signal decay.

## Current sizing (Z0, the baseline)

- Capital is split into equal slots, one per coin (1/10 of capital on the primary set, 1/30 on the secondary set).
- An entry takes part of its coin's slot, by signal and confluence:
  - Strong long: 50-100%;
  - Light long: 25-50%;
  - Revival: 0-10%.
- Unused slots sit in cash.

## Variants (fixed now)

| | Change | Question it answers |
|---|---|---|
| Z1 | Every entry takes its full slot | Does sizing by signal strength help at all? |
| Z2 | Z0 × (2.5% ÷ the coin's ATR14 at entry, on 4H), kept within 0.5× to 2× | Bigger on calm coins, smaller on volatile ones (equal risk per trade) |
| Z3 | Z0 × (share of entry checks met ÷ 0.8), kept within 0.5× to 1.5× | Bigger when more of the engine's entry conditions are met |
| Z4 | Slots of 1/5 of capital instead of 1/N, so at most about five full positions | Fewer, bigger positions instead of spreading thin |

Mechanics:
- A position can never use more cash than is free. No leverage.
- ATR is measured from completed candles only, as in the stop study.
- The 2.5% reference is fixed, not fitted: it is close to the primary set's median ATR.

## Setup

The same as the stop study:
- the 4H replay of today's live logic, windows 1-9 only (the holdout is not touched);
- the 10 primary coins and the 30-coin confirmation set;
- the costed PositionManager with its current exits (8% stop on closes, TRIM / TRIM_HARD / NO_LONG, RISK_OFF, decay), and the BTC weekly-band entry block;
- fresh capital per window.

**Reported:** compounded return, per-window returns, worst-window drawdown, median Sharpe, average exposure (share of capital in positions), trades, and the largest single-trade losses.

## Decision rule (fixed now)

- **Baseline:** Z0.
- **A variant ships only if, on both coin sets:**
  - its compounded return is at least 5 points higher;
  - its median Sharpe is at least Z0's;
  - its worst-window drawdown is no more than 3 points deeper.

  Sizing changes risk as well as return, which is why Sharpe and drawdown are part of the rule.
- **If several pass,** the one with the higher median Sharpe on the primary set wins.
- **If none pass,** nothing changes.
- **No variants are added** after seeing results.
