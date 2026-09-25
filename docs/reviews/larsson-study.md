# Larsson-process study (shadow)

Status: Phase 1 implemented; windows 1-9 run; **holdout (window 10) not run**. Nothing here changes live behaviour: the new engines and manager are research code, `cto_engine.py` and the live signal path are untouched.

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

See the tables below, generated by `backtest.larsson_summary`.

RESULTS_PLACEHOLDER
