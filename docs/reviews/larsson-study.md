# Larsson-process study (shadow)

Status: Phase 1 implemented; windows 1-9 run; acceptance criteria 1 and 2 fail; **holdout (window 10) not run**. Nothing here changes live behaviour: the new engines and manager are research code, `cto_engine.py` and the live signal path are untouched.

## What was built

| Module | File | Version | Tests |
|---|---|---|---|
| A. Larsson Line ribbon | `backend/engines/larsson_engine.py` | `larsson-2.51` | `tests/test_larsson_engine.py` |
| B. Levels and events | `backend/engines/levels_engine.py` | `levels-1` | `tests/test_levels_engine.py` |
| C. Position manager | `backend/backtest/larsson_manager.py` | — | `tests/test_larsson_manager.py` |
| Study CLI | `backend/backtest/larsson_study.py` | `larsson-study-1` | `tests/test_larsson_study.py` |
| Summary | `backend/backtest/larsson_summary.py` | — | — |
| Data | `backend/backtest/binance_history.py` | — | via the above |

**Module A parity** (official v2.51 flips, Binance daily, bar-open dates UTC): BTCUSDT 8/8, ETHUSDT 8/8, LTCBTC gold flip 2026-09-24, LUNA gold 2022-03-01 → grey warning 2022-05-01 at 82.23 → blue flip 2022-05-09 at 30.29. Grey never flips; flips alternate strictly.

## Protocol

```sh
cd backend
python -m backtest.larsson_study --out <run>            # windows 1-9, full declared grid
python -m backtest.larsson_summary <run>                 # tables, selection, acceptance checks
python -m backtest.larsson_study --out <run> --holdout --frozen frozen.json   # once, ever
```

- **Data**: Binance spot daily from 2019-01-01 via the public market-data mirror; warm-up ≥ 600 bars before a coin is traded. A windows 1-9 run loads data only up to the end of window 9.
- **Windows** (frozen, 180 days, fresh capital each):

| W | Start | End | Note |
|---|---|---|---|
| 1 | 2021-10-21 | 2022-04-19 | |
| 2 | 2022-04-19 | 2022-10-16 | LUNA, 3AC |
| 3 | 2022-10-16 | 2023-04-14 | FTX collapse and the early-2023 rebound |
| **4** | **2023-04-14** | **2023-10-11** | **highlighted per spec ("post-FTX recovery")** |
| 5 | 2023-10-11 | 2024-04-08 | |
| 6 | 2024-04-08 | 2024-10-05 | |
| 7 | 2024-10-05 | 2025-04-03 | |
| 8 | 2025-04-03 | 2025-09-30 | |
| 9 | 2025-09-30 | 2026-03-29 | |
| 10 | 2026-03-29 | 2026-09-25 | **holdout — not run** |

- **Universe**: `DEFAULT_BACKTEST_SYMBOLS` (BTC ETH SOL BNB XRP ADA AVAX DOGE DOT LINK). The 30-pair secondary set is not run yet.
- **Costs**: 5 bps fee + 5 bps slippage per side, spot, leverage 1, for every strategy including B0 and B1.
- **Grid** (declared, nothing else tuned): risk_pct {0.5, 1, 2}% × tol {1, 1.5}% × max_last {30, 60} × b {1, 1.5}%. Declared defaults: 1%, 1.5%, 30, 1%. Selection: best **median-window** Sharpe per variant.
- **Holdout guard**: `--holdout` needs frozen parameters, writes a marker on first use and refuses a second run; outputs are never overwritten; window 10 cannot be requested as a walk-forward window.

## Assumptions and interpretations (please confirm)

1. **Window layout.** Ten 180-day windows counted back from the last complete bar (2026-09-24) is the only layout matching all three spec facts: ten windows, a W4 after FTX, and a holdout of about 2026-03 → 2026-09. With it, W3 contains FTX itself and W4 is the mid-2023 chop.
2. **Stops on trend flips.** A flip has no event level, so its stop is the 12% fallback.
3. **Window start.** Each window starts with fresh capital. If a coin's last actionable state is already gold on its first eligible bar, it is entered as a late gold flip (`enter_at_start`); otherwise a trend system would sit in cash through whole windows purely because of how the test is cut.
4. **Order-placement levels.** Nearest support (second tranche) and resistance (exit tranche) use every ≥ 2-touch level in the lookback; the `max_last` filter applies to event levels only.
5. **Trailing.** "Latest broken level" is the most recent breakout level since entry.
6. **L2 range breakdown** is a breakdown on a bar right after a bar in range mode.
7. **L3 range entries** are one full tranche with the stop at the event level × (1 − 1%).
8. **L4** trims only outside range mode; restoring requires the state to be gold again within 15 bars.
9. **L5 gate.** RCCE regimes contain no "RISK_OFF"; the gate blocks new longs when the replay's signal for the coin is `RISK_OFF` or the BTC BMSB filter is blocked (completed weeks).
10. **BTC pair.** Levels and the ribbon are computed on ALT/BTC (Binance pair, else synthetic ALT/USDT ÷ BTC/USDT), but the variants trade and stop on the USD chart. The spec does not say how the pair "votes"; it is not used in entries yet.
11. **Alts** for the correlation budget: 90-day daily-return correlation to BTC > 0.6, BTC excluded.
12. **B1 fairness fixes.** Unmodified RCCE rules, but (a) the same costs, and (b) weekly inputs and the BMSB filter use completed weeks only. The existing runner reads the in-progress week, which leaks up to six days of future data.
13. **Fear & Greed** for B1 comes from alternative.me (the runner's CoinGlass source needs a key).
14. **Pro-agreement diagnostic skipped for now**: all Pro history (Apr-Sep 2026) lies inside the holdout window.

## Known limits

- Survivorship: the universe is today's large caps.
- Scale: at 1% risk and a 12% stop a trend position is at most ~8% of equity and alt risk is capped at 5%, so L-variant returns are small in absolute terms next to B0 (fully invested). Compare Sharpe, drawdown and exposure-adjusted return.
- On `main`, `backtest.runner` cannot be imported (its data loader imports a helper missing from `data_fetcher`); the study carries exact copies of the two BMSB helpers.

## Results (windows 1-9)

Run `primary_w1-9` (10 primary coins, windows 1-9, full 24-point grid). Holdout not run.

### Verdict against the acceptance criteria (windows 1-9)

| # | Criterion | Result |
|---|---|---|
| 1 | L-best beats B1 on median-window Sharpe **and** on max drawdown in >= 6 of 10 windows | **Fail.** No variant beats B1's median Sharpe in any of the 24 grid points (B1 median 0.00, pulled up by a flat W2; best L median 0.00 for L5 for the same reason). L-best's drawdown is better than B1's in 1 of 9 windows. |
| 2 | W4 result >= B1 W4 | **Fail.** Every L variant loses more than B1 in W4 (B1 -7.7%; L1 -14.0%, L5 -18.6% at declared parameters). |
| 3 | Holdout: positive expectancy, drawdown <= B1 | Not run. Criteria 1 and 2 already fail. |
| 4 | No single-asset dependence | Not run; moot while criterion 1 fails. |

Phase 2 gate ("L2 or L3 adds value over L1 in windows 1-9"): **not demonstrated.** L2 is almost identical to L1 (adds rarely fire). L3 raises median-window Sharpe (-1.00 vs -1.12 declared) but deepens drawdowns (median -21.8% vs -14.3%) and lowers compounded return at declared parameters.

### Aggregate view (context, not an acceptance criterion)

Per-window medians hide a skewed payoff: most trades are small stop-outs, a few trend trades are large. Pooled across the nine windows:

| Strategy | Params | Compounded 9 windows | Mean window return | Positive windows | Pooled R / trade | Worst window DD |
|---|---|---:|---:|---:|---:|---:|
| B0 buy & hold | - | -46.1% | 15.4% | 4/9 | - | -63.4% |
| B1 RCCE baseline | - | 53.9% | 6.9% | 4/9 | - | -24.4% |
| B2 CTO Line Adv. via L1 | declared | 43.0% | 7.2% | 2/9 | 0.39 | -21.1% |
| B3 RCCE + LL veto | - | 27.7% | 4.0% | 4/9 | - | -21.4% |
| L1 trend only | declared | 51.5% | 8.5% | 3/9 | 0.69 | -21.5% |
| L2 + level adds | declared | 54.9% | 9.7% | 3/9 | 0.23 | -24.4% |
| L3 + range mode | declared | 45.7% | 11.1% | 2/9 | 0.15 | -26.1% |
| L4 + grey trim | declared | 44.1% | 10.8% | 2/9 | 0.19 | -25.7% |
| L5 L3 gated by RCCE | declared | 79.0% | 13.2% | 3/9 | 0.44 | -21.8% |
| L5 | median-selected | 9.8% | 8.2% | 3/9 | -0.21 | -37.8% |

Readings:
- **Indicator swap (B2 -> L1, same mechanics):** the Larsson ribbon beats CTO Line Advanced on compounded return (51.5% vs 43.0%), pooled R (0.69 vs 0.39) and median Sharpe (-1.12 vs -1.28), with similar drawdown.
- **Window-end exits truncate trends.** For L1, trades force-closed at a window's end average +3.1R; stop-outs are 74% of exits (median -1.15R). Fresh capital every 180 days cuts exactly the long trends this process is built to hold.
- **Selection is unstable.** For L5 the median-Sharpe choice compounds +9.8% while the declared parameters compound +79%: the grid mostly measures noise at this sample size (113-142 trades per variant over nine windows).
- **Exposure differs.** Median average exposure: B1 16%, L1 13%, L3 24%, L5 19%, B0 100%.

### Per-window tables

**Sharpe (annualised, daily) — declared parameters**

| Window | B0 | B1 | B2 | B3 | L1 | L2 | L3 | L4 | L5 |
|---|---|---|---|---|---|---|---|---|---|
| W1 | -0.72 | -1.90 | -1.28 | -1.73 | -1.33 | -1.31 | -1.00 | -0.88 | -1.00 |
| W2 | -1.63 | 0.00 | -3.55 | 0.00 | -1.12 | -1.12 | -1.28 | -1.19 | 0.00 |
| W3 | 0.96 | 0.62 | -0.87 | 0.05 | -0.28 | -0.17 | 0.08 | -0.22 | 0.38 |
| **W4** | **-0.99** | **-1.77** | **-3.11** | **-2.87** | **-2.89** | **-2.94** | **-3.63** | **-3.63** | **-3.26** |
| W5 | 4.03 | 4.60 | 3.45 | 4.59 | 3.27 | 3.28 | 3.28 | 3.30 | 3.28 |
| W6 | -0.93 | -0.73 | -4.19 | -1.57 | -3.07 | -3.17 | -4.13 | -4.05 | -3.94 |
| W7 | 1.19 | 1.94 | 2.20 | 1.91 | 1.68 | 1.69 | 2.51 | 2.56 | 2.51 |
| W8 | 1.76 | 1.20 | -0.02 | 0.83 | 0.49 | 0.37 | -0.43 | -0.31 | -0.13 |
| W9 | -2.16 | -1.35 | -1.43 | -1.28 | -1.57 | -1.68 | -2.15 | -2.11 | -1.81 |
| median | -0.72 | 0.00 | -1.28 | 0.00 | -1.12 | -1.12 | -1.00 | -0.88 | -0.13 |

**Return % — declared parameters**

| Window | B0 | B1 | B2 | B3 | L1 | L2 | L3 | L4 | L5 |
|---|---|---|---|---|---|---|---|---|---|
| W1 | -33.8 | -18.2 | -5.6 | -15.1 | -6.7 | -8.6 | -8.7 | -7.6 | -8.7 |
| W2 | -57.4 | 0.0 | -5.6 | 0.0 | -1.4 | -1.4 | -3.3 | -2.9 | 0.0 |
| W3 | 23.1 | 3.5 | -6.4 | 0.0 | -2.8 | -2.6 | -1.7 | -6.5 | 2.8 |
| **W4** | **-25.0** | **-7.7** | **-15.5** | **-8.8** | **-14.0** | **-14.9** | **-22.4** | **-22.3** | **-18.6** |
| W5 | 224.5 | 60.8 | 76.4 | 46.1 | 90.7 | 103.4 | 108.1 | 105.4 | 108.1 |
| W6 | -29.9 | -3.1 | -10.6 | -3.2 | -14.0 | -14.9 | -22.4 | -21.8 | -21.4 |
| W7 | 38.3 | 21.6 | 40.9 | 18.0 | 35.0 | 40.7 | 74.7 | 75.4 | 74.7 |
| W8 | 57.5 | 13.3 | -1.2 | 7.2 | 3.5 | 2.3 | -4.5 | -3.3 | -1.9 |
| W9 | -58.3 | -8.3 | -7.6 | -7.8 | -14.0 | -16.8 | -19.7 | -18.9 | -16.4 |
| median | -25.0 | 0.0 | -5.6 | 0.0 | -2.8 | -2.6 | -4.5 | -6.5 | -1.9 |

**Max drawdown % — declared parameters**

| Window | B0 | B1 | B2 | B3 | L1 | L2 | L3 | L4 | L5 |
|---|---|---|---|---|---|---|---|---|---|
| W1 | -52.0 | -24.4 | -10.6 | -21.4 | -11.7 | -14.7 | -17.2 | -16.2 | -17.2 |
| W2 | -62.5 | 0.0 | -5.6 | 0.0 | -1.7 | -1.7 | -3.3 | -2.9 | 0.0 |
| W3 | -39.5 | -7.0 | -11.8 | -6.4 | -10.9 | -14.9 | -26.1 | -25.7 | -14.1 |
| **W4** | **-33.7** | **-9.6** | **-16.7** | **-9.5** | **-15.1** | **-16.0** | **-23.4** | **-23.4** | **-19.7** |
| W5 | -22.5 | -6.6 | -11.5 | -4.9 | -17.0 | -17.9 | -18.5 | -18.4 | -18.5 |
| W6 | -39.3 | -6.0 | -10.9 | -3.8 | -14.3 | -15.2 | -22.5 | -21.9 | -21.5 |
| W7 | -47.0 | -11.9 | -21.1 | -10.5 | -21.5 | -24.4 | -21.8 | -20.2 | -21.8 |
| W8 | -26.2 | -9.8 | -10.6 | -7.3 | -10.7 | -9.1 | -11.9 | -9.8 | -11.9 |
| W9 | -63.4 | -11.6 | -9.0 | -11.1 | -16.3 | -19.1 | -23.0 | -22.2 | -19.7 |
| median | -39.5 | -9.6 | -10.9 | -7.3 | -14.3 | -15.2 | -21.8 | -20.2 | -18.5 |

**Sharpe (annualised, daily) — parameters selected on median-window Sharpe**

| Window | B0 | B1 | B2 | B3 | L1 | L2 | L3 | L4 | L5 |
|---|---|---|---|---|---|---|---|---|---|
| W1 | -0.72 | -1.90 | -1.07 | -1.73 | -1.34 | -1.35 | -0.55 | -0.43 | -1.24 |
| W2 | -1.63 | 0.00 | -3.54 | 0.00 | -1.12 | -1.12 | -2.23 | -2.17 | 0.00 |
| W3 | 0.96 | 0.62 | -0.80 | 0.05 | -0.24 | -0.86 | 0.44 | 0.18 | 0.13 |
| **W4** | **-0.99** | **-1.77** | **-3.25** | **-2.87** | **-2.75** | **-2.89** | **-3.53** | **-3.53** | **-1.49** |
| W5 | 4.03 | 4.60 | 3.62 | 4.59 | 3.19 | 3.18 | 3.42 | 3.44 | 3.02 |
| W6 | -0.93 | -0.73 | -4.20 | -1.57 | -3.06 | -3.15 | -3.29 | -3.19 | -3.99 |
| W7 | 1.19 | 1.94 | 2.19 | 1.91 | 1.33 | 1.28 | 1.62 | 1.89 | 1.66 |
| W8 | 1.76 | 1.20 | 0.66 | 0.83 | 0.23 | -0.12 | 1.13 | 1.07 | 0.98 |
| W9 | -2.16 | -1.35 | -1.38 | -1.28 | -1.55 | -1.69 | -1.80 | -1.74 | -1.81 |
| median | -0.72 | 0.00 | -1.07 | 0.00 | -1.12 | -1.12 | -0.55 | -0.43 | 0.00 |

**Return % — parameters selected on median-window Sharpe**

| Window | B0 | B1 | B2 | B3 | L1 | L2 | L3 | L4 | L5 |
|---|---|---|---|---|---|---|---|---|---|
| W1 | -33.8 | -18.2 | -7.5 | -15.1 | -3.4 | -4.6 | -3.8 | -3.0 | -13.9 |
| W2 | -57.4 | 0.0 | -10.8 | 0.0 | -0.7 | -0.7 | -6.1 | -5.8 | 0.0 |
| W3 | 23.1 | 3.5 | -9.1 | 0.0 | -1.3 | -4.9 | 4.6 | 0.1 | -0.2 |
| **W4** | **-25.0** | **-7.7** | **-24.2** | **-8.8** | **-7.6** | **-8.5** | **-20.1** | **-20.0** | **-28.2** |
| W5 | 224.5 | 60.8 | 140.9 | 46.1 | 44.1 | 57.9 | 114.6 | 112.2 | 117.1 |
| W6 | -29.9 | -3.1 | -20.9 | -3.2 | -7.2 | -7.7 | -17.5 | -16.9 | -37.5 |
| W7 | 38.3 | 21.6 | 50.4 | 18.0 | 15.7 | 18.4 | 31.9 | 36.6 | 41.1 |
| W8 | 57.5 | 13.3 | 7.6 | 7.2 | 0.8 | -0.9 | 17.5 | 16.4 | 15.0 |
| W9 | -58.3 | -8.3 | -11.0 | -7.8 | -7.6 | -8.9 | -17.3 | -16.4 | -19.2 |
| median | -25.0 | 0.0 | -9.1 | 0.0 | -1.3 | -4.6 | -3.8 | -3.0 | -0.2 |

**Max drawdown % — parameters selected on median-window Sharpe**

| Window | B0 | B1 | B2 | B3 | L1 | L2 | L3 | L4 | L5 |
|---|---|---|---|---|---|---|---|---|---|
| W1 | -52.0 | -24.4 | -15.1 | -21.4 | -6.0 | -8.0 | -10.3 | -9.5 | -23.3 |
| W2 | -62.5 | 0.0 | -11.1 | 0.0 | -0.8 | -0.8 | -6.1 | -5.8 | 0.0 |
| W3 | -39.5 | -7.0 | -17.7 | -6.4 | -5.9 | -8.6 | -24.1 | -23.6 | -19.7 |
| **W4** | **-33.7** | **-9.6** | **-25.9** | **-9.5** | **-8.4** | **-9.3** | **-21.3** | **-21.2** | **-28.8** |
| W5 | -22.5 | -6.6 | -15.8 | -4.9 | -10.4 | -12.7 | -17.5 | -17.4 | -23.6 |
| W6 | -39.3 | -6.0 | -21.5 | -3.8 | -7.3 | -7.9 | -17.7 | -17.0 | -37.8 |
| W7 | -47.0 | -11.9 | -24.9 | -10.5 | -13.8 | -17.1 | -20.9 | -18.1 | -22.0 |
| W8 | -26.2 | -9.8 | -9.6 | -7.3 | -5.4 | -6.8 | -12.5 | -13.2 | -19.3 |
| W9 | -63.4 | -11.6 | -13.4 | -11.1 | -9.0 | -10.2 | -20.0 | -19.2 | -22.9 |
| median | -39.5 | -9.6 | -15.8 | -7.3 | -7.3 | -8.6 | -17.7 | -17.4 | -22.9 |

## Follow-up: RCCE entries with Larsson Line exits (declared before running)

Question: do RCCE's entries do better when exits are handed to the Larsson Line? Declared 2026-09-25, before any result was seen. Windows 1-9, primary universe, same data, costs and fill convention as B1 (signal-bar close), holdout untouched.

Entries, sizing, BMSB gate and costs are exactly B1's. Entries are skipped while the ribbon is blue, since "hold until it turns blue" cannot apply to a trade opened in blue; that makes **B3 the exact control** (same entries, same veto, B1's exits). Only the exit rule changes:

| ID | Exit rule |
|---|---|
| X1 | First daily close with the ribbon blue. No price stop, no RCCE exit signals, no decay exit. |
| X2 | X1 plus a 12% catastrophe stop checked on the close. |
| X3 | X1 plus RCCE's own exit signals (TRIM, TRIM_HARD, NO_LONG, RISK_OFF); no 8% stop, no decay exit. |

No parameters are tuned; these three are the whole test.

### Results (run `exits_w1-9`)

| | Compounded W1-9 | Worst window DD | Trades | Win rate | Avg hold (bars) | Exits |
|---|---:|---:|---:|---:|---:|---|
| B1 RCCE baseline | +53.9% | -24.4% | 228 | 28% | 27 | 8% stop 139, RISK_OFF 21, TRIM 18, decay 8, window end 42 |
| B3 control (blue veto, B1 exits) | +27.7% | -21.4% | 206 | 28% | 26 | 8% stop 130, RISK_OFF 13, TRIM 18, decay 7, window end 38 |
| X1 ribbon-blue exit only | +31.6% | -17.8% | 106 | 33% | 57 | blue 66, window end 40 |
| X2 X1 + 12% stop | +30.8% | -18.3% | 147 | 29% | 38 | blue 49, 12% stop 58, window end 40 |
| X3 X1 + RCCE exit signals | +28.5% | -17.8% | 131 | 37% | 44 | blue 63, TRIM 18, RISK_OFF 12, window end 38 |

Per window, return % (Sharpe):

| W | B1 | B3 | X1 | X2 | X3 |
|---|---|---|---|---|---|
| 1 | -18.2 (-1.90) | -15.1 (-1.73) | -11.1 (-1.32) | -11.8 (-1.37) | -11.1 (-1.32) |
| 2 | 0.0 (0.00) | 0.0 (0.00) | 0.0 (0.00) | 0.0 (0.00) | 0.0 (0.00) |
| 3 | 3.5 (0.62) | 0.0 (0.05) | 2.5 (0.47) | 2.2 (0.41) | 2.5 (0.47) |
| **4** | **-7.7 (-1.77)** | **-8.8 (-2.87)** | **-8.0 (-1.70)** | **-8.5 (-1.96)** | **-8.0 (-1.70)** |
| 5 | 60.8 (4.60) | 46.1 (4.59) | 49.5 (3.04) | 49.0 (3.02) | 44.9 (4.91) |
| 6 | -3.1 (-0.73) | -3.2 (-1.57) | -5.5 (-1.98) | -5.0 (-2.17) | -5.7 (-2.04) |
| 7 | 21.6 (1.94) | 18.0 (1.91) | 11.8 (1.06) | 10.2 (0.93) | 12.8 (1.63) |
| 8 | 13.3 (1.20) | 7.2 (0.83) | 5.2 (0.72) | 7.6 (0.93) | 5.2 (0.72) |
| 9 | -8.3 (-1.35) | -7.8 (-1.28) | -5.4 (-0.95) | -5.6 (-0.96) | -5.4 (-0.95) |

Reading:
- **Against the exact control, Larsson exits help a little**: +31.6% vs +27.7% compounded, a shallower worst drawdown (-17.8% vs -21.4%), half the trades and twice the holding time. The gain comes from the bear windows (W1, W9); the bull windows W7-W8 give some back.
- **The blue-entry veto is what hurts**, not the exits: B1 -> B3 costs 26 points of compounded return. RCCE's valuable entries often come while the ribbon is still blue, near bottoms, before a trend indicator can confirm.
- Differences of a few points over nine windows and 100-230 trades are within noise. None of this touches the holdout.

## Scenario search: RCCE entries × exit rules (declared before running)

Declared 2026-09-25, before any of these results were seen. Windows 1-9 only; the holdout stays locked. Same data, costs, sizing, BMSB gate and fill convention as B1. Every scenario below is run and reported; nothing outside this list is tuned.

**Named hypothesis (H1):** entries unchanged (no ribbon veto); exit on the first blue bar after the ribbon has been gold since entry (for a trade opened in blue: gold first, then blue); 12% catastrophe stop; RCCE exit signals off.

**Family** (all combinations; decay exit off in every scenario):

| Dimension | Levels |
|---|---|
| Entry filter | F0 = B1 entries · F1 = skip entries while the ribbon is blue |
| Trend exit | `flip` blue after gold-since-entry · `grey` first grey or blue after gold-since-entry · `blue` first blue bar (F1 only) · `e32` first close below EMA32 after a close above it since entry · `atr3` close below highest close since entry − 3×ATR(14) · `t30` / `t60` time exit after 30 / 60 bars (controls for "just hold longer") |
| Safety stop (on close, from average entry) | none · 12% · 8% |
| RCCE exit signals (TRIM, TRIM_HARD, NO_LONG, RISK_OFF) | off · on |

That is 36 F0 + 42 F1 = 78 scenarios, against B1 and B3.

**Statistics**
- Per scenario: compounded return over W1-9, worst window drawdown, median-window Sharpe, windows beating B1, and a stationary-bootstrap p-value for its mean daily excess return over B1 (naive, uncorrected).
- Multiple testing: White's Reality Check over all 78 scenarios (stationary bootstrap, mean block 10 days, 2,000 resamples) on daily excess returns versus B1. A "real edge" needs Reality Check p < 0.10.

**Confirmation on unseen coins:** the three scenarios with the highest compounded return, the one with the best median-window Sharpe if different, and H1 are rerun on a secondary universe of 30 Binance USDT pairs chosen by quote volume in the 90 days before W1 (information available at the time; stablecoins, fiat, wrapped and leveraged tokens and the primary ten excluded; listed before 2020-02 so they are warmed up by W1). A candidate is confirmed only if it also beats B1 there on compounded return and worst drawdown.

**Diagnostic:** the same candidates run once without window resets (one capital from W1 start to W9 end) to show how much the 180-day resets truncate trend trades. Not an acceptance criterion.

### Results: primary universe (run `scen_primary`)

**White's Reality Check over all 78 scenarios: family p = 0.58** (best: `F0-t60-s12-nosig`). The declared bar for a real edge is p < 0.10: **not met**.

Top 12 by compounded return, then B1/B3, then the bottom 3 (all 80 rows are in `summary.json`):

| Scenario | Compounded W1-9 | Worst window DD | Windows beating B1 | Trades | Win rate | Avg hold | Naive p vs B1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| F0-t60-s12-nosig | +83.4% | -19.8% | 5.0/9 | 211 | 36% | 31 | 0.09 |
| F0-t60-s8-nosig | +70.6% | -20.0% | 3.0/9 | 244 | 30% | 25 | 0.19 |
| F0-t60-nostop-nosig | +69.9% | -18.1% | 4.0/9 | 151 | 45% | 48 | 0.30 |
| F0-t60-s12-sig | +67.5% | -19.3% | 4.0/9 | 238 | 37% | 26 | 0.22 |
| F0-grey-s8-nosig | +64.5% | -21.1% | 4.0/9 | 209 | 30% | 30 | 0.20 |
| F0-grey-s12-nosig | +62.0% | -20.6% | 4.0/9 | 178 | 33% | 37 | 0.24 |
| F1-t60-s12-nosig | +60.1% | -17.0% | 2.0/9 | 194 | 37% | 30 | 0.41 |
| F0-flip-s12-nosig | +58.4% | -23.9% | 3.0/9 | 153 | 33% | 44 | 0.31 |
| F0-grey-s8-sig | +57.1% | -21.1% | 3.0/9 | 258 | 30% | 23 | 0.35 |
| F0-t60-s8-sig | +56.4% | -20.0% | 3.0/9 | 273 | 30% | 22 | 0.46 |
| F0-grey-s12-sig | +56.1% | -20.1% | 4.0/9 | 221 | 33% | 28 | 0.39 |
| F0-t60-nostop-sig | +55.2% | -18.1% | 4.0/9 | 175 | 44% | 40 | 0.52 |
| B1 | +53.9% | -24.4% | 0.0/9 | 228 | 28% | 27 | - |
| B3 | +27.7% | -21.4% | 2.0/9 | 206 | 28% | 26 | - |
| F1-t30-s8-nosig | +13.1% | -18.2% | 2.0/9 | 302 | 37% | 17 | 0.96 |
| F1-t30-s12-sig | +11.1% | -15.1% | 1.0/9 | 279 | 39% | 18 | 0.96 |
| F1-t30-s8-sig | +9.0% | -18.2% | 2.0/9 | 316 | 37% | 16 | 0.97 |

Named hypothesis H1 (`F0-flip-s12-nosig`): +58.4% vs B1 +53.9%, worst drawdown -23.9% vs -24.4%.

Readings:
- The best scenario is a **time-exit control**, not a Larsson rule: hold 60 bars, 12% stop, ignore RCCE's exit signals.
- The consistent pattern across the top rows is *hold longer, use a wider stop, and ignore TRIM / RISK_OFF*. It matches the earlier exit study (8% stops and early breakeven cut winners).
- The Larsson flip exit with a 12% stop (H1) is roughly level with B1; the ribbon adds nothing a 60-bar hold does not.
- With 78 variations tried, the best result is well within luck (family p = 0.58).

### Diagnostic: no window resets (run `scen_continuous`, 2021-10-21 to 2026-03-29, one capital)

| Scenario | Total return | Max drawdown | Trades | Win rate | Avg hold |
|---|---:|---:|---:|---:|---:|
| F0-t60-s8-nosig | +63.6% | -27.4% | 214 | 26% | 30 |
| F0-t60-s12-nosig | +62.2% | -27.6% | 180 | 32% | 37 |
| B1 | +48.7% | -31.7% | 185 | 22% | 35 |
| F0-flip-s12-nosig | +39.4% | -31.8% | 115 | 30% | 64 |
| F0-t60-nostop-nosig | +35.6% | -33.5% | 127 | 44% | 60 |
| B3 | +27.1% | -31.4% | 170 | 21% | 34 |
| F0-flip-nostop-nosig | +21.8% | -40.1% | 72 | 43% | 148 |

Without resets the 60-bar holds still lead (+62-64% vs B1 +48.7%, drawdown -27% vs -32%); the Larsson flip exits fall behind B1, so window truncation was not what held them back.
