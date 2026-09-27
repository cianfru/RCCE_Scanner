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

## Results

### Part M: market timing

Each cell shows compounded return / worst-window drawdown / median window Sharpe.

| | Primary (10 coins) | Confirmation (30 coins) | Avg exposure |
|---|---|---|---:|
| M0 today's coin-by-coin | +43% / -10% / 0.32 | +45% / -15% / -0.80 | 9.6% |
| T1 (BTC regime) + basket | +171% / -50% / 0.10 | -19% / -63% / 0.00 | 56.2% |
| T1 + BTC only | +151% / -38% / 0.00 | +151% / -38% / 0.00 | 56.2% |
| T2 (breadth) + basket | +51% / -55% / 0.00 | -53% / -70% / 0.00 | 60.3% |
| T2 + BTC only | +90% / -41% / 0.00 | +110% / -41% / 0.00 | 60.3% |
| Buy and hold basket | -45% / -65% / -0.63 | -85% / -66% / -0.76 | 100.0% |
| Buy and hold BTC | +5% / -56% / -0.18 | +5% / -56% / -0.18 | 100.0% |

Per window (primary):
- T1 + BTC: -22%, 0%, +67%, -14%, +130%, -34%, +35%, +24% and -12%;
- buy and hold BTC: -38%, -53%, +59%, -10%, +152%, -10%, +40%, +38% and -42%;
- today's backtest: +1%, 0%, +5%, -2%, +36%, -10%, +12%, +6% and -6%.

**Verdict: nothing is recommended.**
- No timing variant has a higher median Sharpe than M0 on the primary set (0.00-0.10 against 0.32). The rule's first condition fails there.
- Timing does cut the worst losses of buy-and-hold. It stays in cash through 2022 (0% against -53% for BTC), and T1 + BTC's worst window is -38% against -56%.
- But it whipsaws in choppy markets. In window 6 (April to October 2024), T1 + BTC lost 34% while holding BTC lost 10%.
- Its big compounded numbers come mostly from one window (late 2023 to early 2024, +130%), at 56% average exposure.
- Today's coin-by-coin trading earns less but with far smaller drawdowns (-10% to -15%). Per unit of risk it is the better use of the same signals.

### Part X: bearish signals

7-day return after the signal, in excess of the set's average coin, as mean / median / share positive:

| | Primary n | Primary | Confirmation n | Confirmation |
|---|---:|---|---:|---|
| After Trim | 75 | -1.7% / -3.2% / 35% | 89 | +0.4% / -4.9% / 34% |
| After Light short | 402 | -0.4% / -0.4% / 47% | 478 | +0.2% / -0.9% / 44% |

Short strategies, as compounded / median window Sharpe / trades:

| | Primary | Confirmation |
|---|---|---|
| X1: short on Light short | -3.5% / -0.56 / 107 trades | -1.8% / -0.47 / 135 trades |
| X2: short on Trim | -1.0% / 0.00 / 40 trades | +0.3% / 0.00 / 53 trades |

**Verdict:**
- **Trim is a good exit.** On both sets the median coin trails the market by 3-5% in the 7 days after it, and only about a third beat the market. Keeping the Trim exit is well supported.
- **Shorting after Trim (X2) is not supported.** It is roughly flat (-1.0% and +0.3%), with too few trades and no positive Sharpe.
- **Light short carries no edge.** Its 7-day excess return is near zero on both sets.
- **X1 (shorting on Light short) loses on both sets** (-3.5% and -1.8%). That meets the declared rule: **the recommendation is to stop the live executor's Light short entries.** This is a change to live trading, so it waits for the owner's approval.
