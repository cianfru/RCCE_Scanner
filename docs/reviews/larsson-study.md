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
