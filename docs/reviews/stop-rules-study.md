# Stop rules: fixed 8%, breakeven, wider and volatility-scaled stops (declared 26 September 2026, before running)

Question: are the exit rails too tight for crypto's volatility? The live executor closes a long at −8%, and at its entry price once the trade has been +5% (breakeven). Would wider stops, stops scaled to each coin's volatility, or no breakeven do better? Does the answer depend on how volatile the coin is?

## What earlier work already says

- **Exit-scenario search** (docs/reviews/larsson-study.md): 78 exit variants, including 8%, 12% and no stop.
  - No statistically real edge (Reality Check p = 0.58).
  - The consistent direction was to hold longer, use a wider stop, and exit less eagerly.
- **Stop reconstruction on the executor's recorded entries** (historical-stop-reconstruction.md, exploratory):
  - Removing the +5% breakeven exit changed the result from −$122 to +$421.
  - A 2× range stop instead of the fixed 8% changed it by only $15.
- **The backtest position manager has no breakeven rule.** Its baseline differs from the live executor, which is why S1 below adds it.

## Setup

- **Signals:** the 4H replay of today's live logic (Overheated switch off, cool-off off), windows 1-9 only. The holdout after 29 March 2026 is not touched.
  - Primary: the 10 primary coins.
  - Confirmation: the 30 secondary coins (listed before 2020-02, chosen by volume before W1).
- **Scoring:** the same costed PositionManager and BTC weekly-band entry block as every replay study, with fresh capital per window.
  - Only the stop rules change. Entries, sizing and signal exits (TRIM, TRIM_HARD, NO_LONG, RISK_OFF, the 20-bar decay) stay the same.
  - Stops are checked on 4H closes, from the average entry.
  - Notional is not changed when a stop is wider, so wider stops carry more risk per trade, and drawdown is reported next to return.
- **Volatility:** ATR14 on completed 4H candles, as a percentage of the close, taken at the entry bar and fixed for the trade.

## Variants (fixed now)

| | Hard stop | Breakeven |
|---|---|---|
| S0 | 8% | none (the backtest's current rule) |
| S1 | 8% | armed at +5% (the live executor's rules) |
| S2 | 8% | armed at +10% |
| S3 | 12% | none |
| S4 | 16% | none |
| S5 | none (signal exits and decay only) | none |
| S6 | 3 × ATR14 at entry, kept within 6% to 25% | none |
| S7 | 3 × ATR14 at entry, kept within 6% to 25% | armed at +10% |

A breakeven stop, once armed, closes the trade on the first 4H close at or below the average entry.

## Reported

For each variant and coin set:
- compounded return over windows 1-9, and per window;
- worst-window drawdown, median Sharpe;
- trades, win rate, and exits by reason;
- the largest single-trade losses.

**Volatility brackets.** Coins are split into thirds by their median ATR14 over windows 1-9 (low, middle, high volatility), and each variant's P&L is reported per third. This is descriptive: it shows whether wider or volatility-scaled stops help mainly on the volatile coins.

## Decision rule (fixed now)

- **Baseline:** S1, the live executor's rules.
- **A variant replaces it** only if, on both coin sets:
  - its compounded return is at least 5 points higher;
  - its worst-window drawdown is no more than 2 points deeper;
  - on the primary set, it beats S1 in at least 6 of the 9 windows.
- **If several pass,** the one with the higher primary return wins.
- **If none pass,** nothing changes in the executor and the results are reported.
- **No variants are added** after seeing the results. A new idea would need its own declaration.

## Results: primary set (10 coins), confirmation pending

S0 reproduces the earlier replay baseline exactly (+43.1%), so the variant code matches the PositionManager's own stop.

| | Rule | Compounded | Worst-window DD | Median Sharpe | Trades | Win rate | Worst 3 trades | Windows beating S1 |
|---|---|---:|---:|---:|---:|---:|---|---:|
| S0 | 8%, no BE | +43.1% | -10.4% | 0.32 | 314 | 42% | -153, -96, -87 | |
| **S1** | **8%, BE +5% (live)** | **+46.2%** | **-10.6%** | 0.36 | 367 | 33% | -153, -87, -84 | |
| S2 | 8%, BE +10% | +43.5% | -11.0% | 0.33 | 326 | 39% | -153, -96, -87 | |
| S3 | 12%, no BE | +41.7% | -11.4% | 0.18 | 294 | 45% | -153, -131, -129 | |
| S4 | 16%, no BE | +44.9% | -11.4% | 0.52 | 288 | 47% | -153, -131, -129 | |
| S5 | no stop | +49.2% | -11.4% | 0.69 | 284 | 47% | -144, -133, -117 | |
| S6 | 3×ATR (6-25%), no BE | +56.0% | -10.5% | 0.56 | 310 | 44% | -96, -93, -87 | 6 of 9 |
| S7 | 3×ATR (6-25%), BE +10% | +55.7% | -10.7% | 0.54 | 321 | 41% | -96, -93, -92 | 7 of 9 |

Median ATR14 on 4H is 1.4% (BTC) to 2.7% (SOL) on these coins. 3×ATR is therefore 4-8%, and with the 6% floor the volatility stop is tighter than 8% on the calmer coins (BTC, BNB, ETH at about 6%) and about 8% on SOL.

On this set:
- S6 and S7 both meet the primary part of the rule: +9.8 and +9.5 points over S1, with no deeper drawdown, beating S1 in 6 and 7 of 9 windows.
- Plain wider stops (12%, 16%) do not help.
- No stop (S5) is +3 points.
- The live +5% breakeven is slightly better than none here (+3 points), unlike in the executor reconstruction.

Whether anything ships depends on the 30-coin confirmation set, which is more volatile; its replay is running.
