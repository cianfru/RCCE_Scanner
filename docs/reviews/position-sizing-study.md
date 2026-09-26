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

## Results

Z0 reproduces the replay baseline (+43.1% on the primary set).

**Primary set (10 coins)**

| | Compounded | Worst-window DD | Median Sharpe | Avg exposure | Trades | Worst 3 trades ($) |
|---|---:|---:|---:|---:|---:|---|
| Z0 | +43.1% | -10.4% | 0.32 | 9.6% | 314 | -153, -96, -87 |
| Z1 | +86.9% | -19.1% | 0.37 | 18.3% | 314 | -306, -192, -173 |
| Z2 | +34.2% | -13.9% | 0.18 | 12.0% | 314 | -192, -129, -120 |
| Z3 | +37.9% | -10.2% | 0.16 | 8.8% | 314 | -149, -93, -63 |
| Z4 | +84.6% | -19.9% | 0.37 | 18.1% | 314 | -306, -192, -173 |

**Confirmation set (30 coins)**

| | Compounded | Worst-window DD | Median Sharpe | Avg exposure | Trades | Worst 3 trades ($) |
|---|---:|---:|---:|---:|---:|---|
| Z0 | +45.3% | -14.6% | -0.80 | 7.5% | 725 | -42, -41, -36 |
| Z1 | +82.5% | -22.5% | -0.77 | 14.4% | 725 | -84, -81, -73 |
| Z2 | +40.8% | -12.0% | -0.66 | 7.7% | 725 | -45, -45, -34 |
| Z3 | +39.5% | -13.1% | -0.83 | 6.8% | 725 | -34, -34, -30 |
| Z4 | +30.1% | -44.6% | -0.52 | 27.4% | 554 | -252, -218, -213 |

## Verdict: nothing ships

- **Z1 (full slots) roughly doubles the return on both sets (+87% and +83%), but the worst-window drawdown also doubles** (to -19% and -23%). That is 8-9 points deeper, well past the 3-point limit.
- **Z2 (volatility parity) and Z3 (entry-check conviction) lower both return and Sharpe.**
- **Z4 (five big slots) collapses on the 30-coin set.** It reached -45% drawdown, because a few large positions carried whole windows.

**What this shows:**
- **The backtest is mostly in cash.** Average exposure is 10% of capital on the primary set and 8% on the secondary set: small partial slots, and one slot per coin whether or not it has a signal.
- **Returns scale with size, with no gain in quality.** Z1's median Sharpe (0.37 against 0.32, and -0.77 against -0.80) is only marginally better than Z0's, while return and drawdown both double. Sizing by signal strength, as today, does not pick better trades. It only takes smaller ones.
- **No rule for putting more on some coins than others (calmer coins, stronger entry checks) improved risk-adjusted results.**
- **How big to trade is therefore a risk-appetite choice, not an edge found here.** A fixed drawdown budget should set it.
- **The live executor sizes the same way in dollars.** Its order is allocation × size, as here. Leverage (`_LEVERAGE_MAP`, 1-5×) only lowers the margin posted, not the position's size, so its exposure is comparable to Z0.
- It differs from this backtest in two ways: it also trades Accumulate entries (15-25% of a slot) and Light short, both of which the backtest leaves out.
