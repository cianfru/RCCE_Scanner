# The engine as market timing, and its bearish signals as trades (declared 27 September 2026, before running)

The entry-quality study found that the engine's long entries earn about the market's own move, while its value shows in when to be out. This tests two ways to use that directly.

**Data:** the 4H replays of today's live logic, windows 1-9 only (the holdout is not touched). The 10 primary coins and the 30-coin confirmation set. Fresh capital per window, costs of 5 bps fee plus 5 bps slippage per side.

## Part M: market timing

Instead of trading coin by coin, hold a basket while the engine reads the market as risk-on, and hold cash otherwise.

**Risk-on (two definitions, fixed now):**
- **T1:** the BTC weekly band does not block entries (the backtest's existing rule), and BTC's 4H regime is Uptrend, Re-accumulating or Overheated.
  BTC's regime comes from the primary replay, which includes BTC; the timestamps are shared.
- **T2:** the BTC weekly band does not block entries, and at least half of the set's coins are in Uptrend or Re-accumulating on that bar (breadth).

**Holdings when risk-on:**
- **H1:** an equal-weight basket of the set's coins priced on that bar;
- **H2:** BTC only.

**Variants and benchmarks:**

| | Rule |
|---|---|
| M0 | Today's coin-by-coin backtest (the costed PositionManager) |
| M-T1-H1, M-T1-H2, M-T2-H1, M-T2-H2 | Risk-on definition × holding |
| BH-H1, BH-H2 | Buy and hold the basket or BTC for the whole window |

Switching costs apply on every change between invested and cash.

**Decision rule (fixed now):** a timing variant is recommended for a forward test as a portfolio mode only if, on both coin sets:
- its median window Sharpe is higher than M0's;
- its median window Sharpe is higher than its own buy-and-hold's;
- its worst-window drawdown is at least 5 points shallower than its buy-and-hold's.

Sharpe is the comparison because the variants carry very different exposure: M0 averages about 10%, the basket up to 100%. Compounded returns are reported for context.

## Part X: bearish signals as trades

**Stage 1, describe.** After each fresh Trim and each fresh Light short, report the 1-, 3- and 7-day returns, raw and in excess of the set's average coin, with counts, means, medians and share positive.

**Stage 2, short strategies.**
- **X1:** short at each fresh Light short.
- **X2:** short at each fresh Trim.
- Both are sized as the executor sizes Light short (15-30% of a 1/N slot, by confluence).
- A short closes at the first of:
  - the coin's next long entry signal;
  - 42 bars (7 days);
  - an 8% adverse move on a close.

**Decision rule (fixed now):**
- **A short strategy is supported** only if, on both sets:
  - its compounded return is above zero;
  - its median window Sharpe is above zero;
  - its signal's mean 7-day excess return is negative (the coin underperforms after it).
- **The live executor already trades Light short.** If X1's compounded return is below zero on both sets, the recommendation is to stop the executor's Light short entries.
- **Otherwise nothing changes.** A supported X2 would go to a forward test before any executor change.
