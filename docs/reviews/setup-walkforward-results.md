# Historical forward-replay results

Period: **2024-09-21 to 2026-09-24** after warm-up; BTC, ETH and SOL; 4,401 decision times and 13,203 asset decisions.

Status: **exploratory historical test, not validated for live trading**. Frozen `setups-1` rules, with no tuning or strategy selection during the run. The live paper ledger was not modified.

## What this tells us

- Confirmed reversal never became eligible for a trade: only 39 observations met its context, and all were blocked by reward/risk or mandatory scanner restrictions. The replay cannot demonstrate an edge for this definition.
- Continuation pullback produced only six completed trades in two years. Average net return was positive at 0.387%, but average risk-normalized outcome was negative at -0.031 R. Returns and R use different weighting because stop distances vary. This sample is too small to validate the setup.
- The comparator produced 49 closed trades, of which 46 had complete funding: average modeled net return 0.692% and average 0.190 R. Two early populated 90-day windows lost money; two later full windows produced no completed trades. Aggregate profitability is insufficient evidence of robustness.
- 78 continuation and 361 comparator entries were missed because the scheduled opening lay outside the frozen entry zone. Investigate whether the delayed bar-close trigger, narrow entry zone and short expiry work together as intended before defining a new strategy version. Do not change this version after seeing these results.
- CTO-up had no completed continuation trades. Comparator CTO-up trades averaged 0.612%, versus 0.694% for down and 0.889% for neutral, on small, unequal samples. This descriptive split does not support making CTO a mandatory confirmation gate.
- The comparator shares scanner context and safety restrictions. It is not an independent buy-and-hold or moving-average benchmark.

Next research step: diagnose reversal eligibility and execution timing, then preregister a separate version and compare it on fresh data. Keep the live `setups-1` record unchanged.

## Conditional modeled-execution results

Average net return is per closed, fully funded paper trade after modeled fees, slippage, spread and realized funding. It is not a portfolio or annualized return.

| Scenario | Strategy | Closed / fully costed | Average net return | Average net R | Losing trades | Realized drawdown (R) |
|---|---|---:|---:|---:|---:|---:|
| strict_missing_books | confirmed_reversal | 0 / 0 | — | — | — | — |
| strict_missing_books | continuation_pullback | 0 / 0 | — | — | — | — |
| strict_missing_books | trend_comparator | 0 / 0 | — | — | — | — |
| assumed_2bps_spread | confirmed_reversal | 0 / 0 | — | — | — | — |
| assumed_2bps_spread | continuation_pullback | 6 / 6 | 0.387% | -0.031 | 33.333% | 1.052 |
| assumed_2bps_spread | trend_comparator | 49 / 46 | 0.692% | 0.190 | 45.652% | 7.648 |
| assumed_10bps_spread | confirmed_reversal | 0 / 0 | — | — | — | — |
| assumed_10bps_spread | continuation_pullback | 6 / 6 | 0.307% | -0.045 | 33.333% | 1.063 |
| assumed_10bps_spread | trend_comparator | 49 / 46 | 0.612% | 0.169 | 47.826% | 7.931 |

Drawdown is a sequence of realized outcomes with fixed one-unit risk per independent episode. It is not marked-to-market portfolio drawdown.

## Setup lifecycle — assumed 2 bps spread

- **confirmed_reversal:** 13,203 observations; no_setup: 13164, blocked: 39.
- **continuation_pullback:** 13,203 observations; blocked: 5732, no_setup: 7048, expired: 216, invalidated: 115, missed: 83, closed: 6, cancelled: 1, pending: 2.
- **trend_comparator:** 13,203 observations; expired: 338, blocked: 5335, no_setup: 7046, missed: 361, invalidated: 72, closed: 49, cancelled: 2.

## Disjoint reporting windows — assumed 2 bps spread

Trades are assigned by first setup observation. Outcomes crossing window boundaries are excluded from the window summaries; overall summaries retain completed trades. No parameters are fitted in these windows.

| Window | Strategy | Fully costed trades | Average net return |
|---|---|---:|---:|
| 2024-09-21 – 2024-12-20 | confirmed_reversal | 0 | — |
| 2024-09-21 – 2024-12-20 | continuation_pullback | 0 | — |
| 2024-09-21 – 2024-12-20 | trend_comparator | 12 | -1.039% |
| 2024-12-20 – 2025-03-20 | confirmed_reversal | 0 | — |
| 2024-12-20 – 2025-03-20 | continuation_pullback | 2 | 1.504% |
| 2024-12-20 – 2025-03-20 | trend_comparator | 5 | -1.776% |
| 2025-03-20 – 2025-06-18 | confirmed_reversal | 0 | — |
| 2025-03-20 – 2025-06-18 | continuation_pullback | 0 | — |
| 2025-03-20 – 2025-06-18 | trend_comparator | 7 | 0.618% |
| 2025-06-18 – 2025-09-16 | confirmed_reversal | 0 | — |
| 2025-06-18 – 2025-09-16 | continuation_pullback | 2 | -0.616% |
| 2025-06-18 – 2025-09-16 | trend_comparator | 11 | 3.351% |
| 2025-09-16 – 2025-12-15 | confirmed_reversal | 0 | — |
| 2025-09-16 – 2025-12-15 | continuation_pullback | 2 | 0.274% |
| 2025-09-16 – 2025-12-15 | trend_comparator | 4 | 0.126% |
| 2025-12-15 – 2026-03-15 | confirmed_reversal | 0 | — |
| 2025-12-15 – 2026-03-15 | continuation_pullback | 0 | — |
| 2025-12-15 – 2026-03-15 | trend_comparator | 0 | — |
| 2026-03-15 – 2026-06-13 | confirmed_reversal | 0 | — |
| 2026-03-15 – 2026-06-13 | continuation_pullback | 0 | — |
| 2026-03-15 – 2026-06-13 | trend_comparator | 0 | — |
| 2026-06-13 – 2026-09-11 | confirmed_reversal | 0 | — |
| 2026-06-13 – 2026-09-11 | continuation_pullback | 0 | — |
| 2026-06-13 – 2026-09-11 | trend_comparator | 7 | 1.643% |
| 2026-09-11 – 2026-09-24 | confirmed_reversal | 0 | — |
| 2026-09-11 – 2026-09-24 | continuation_pullback | 0 | — |
| 2026-09-11 – 2026-09-24 | trend_comparator | 0 | — |

## Asset breakdown — assumed 2 bps spread

| Strategy | Asset | Fully costed trades | Average net return |
|---|---|---:|---:|
| confirmed_reversal | BTC/USDT | 0 | — |
| confirmed_reversal | ETH/USDT | 0 | — |
| confirmed_reversal | SOL/USDT | 0 | — |
| continuation_pullback | BTC/USDT | 2 | -0.265% |
| continuation_pullback | ETH/USDT | 0 | — |
| continuation_pullback | SOL/USDT | 4 | 0.713% |
| trend_comparator | BTC/USDT | 14 | 0.207% |
| trend_comparator | ETH/USDT | 16 | 0.617% |
| trend_comparator | SOL/USDT | 16 | 1.193% |

## CTO at setup observation — descriptive only

Cohorts do not replay a separate CTO-filtered strategy; filtering changes later opportunity availability. These comparisons cannot justify a CTO gate by themselves.

| Strategy | CTO direction | Fully costed trades | Average net return |
|---|---|---:|---:|
| confirmed_reversal | up | 0 | — |
| confirmed_reversal | down | 0 | — |
| confirmed_reversal | neutral | 0 | — |
| confirmed_reversal | unavailable | 0 | — |
| continuation_pullback | up | 0 | — |
| continuation_pullback | down | 3 | 0.462% |
| continuation_pullback | neutral | 3 | 0.312% |
| continuation_pullback | unavailable | 0 | — |
| trend_comparator | up | 27 | 0.612% |
| trend_comparator | down | 8 | 0.694% |
| trend_comparator | neutral | 11 | 0.889% |
| trend_comparator | unavailable | 0 | — |

## Interpretation and limits

- Historical books unavailable; scenario spread/depth are assumptions.
- Historical external scanner context unavailable; technical-only shared decision pipeline.
- Consensus computed over fixed BTC/ETH/SOL universe, not the full historical live universe.
- No training or parameter selection: frozen rules tested in successive 90-day windows.
- Rules were designed with prior historical exposure; these are not untouched holdout results.
- First observed per completed bar at fixed latency; intrabar polling/context changes not reconstructed.
- OHLCV fills use production conservative rules; funding uses fixed entry notional and bar-close exit accounting.
- CTO cohorts are descriptive selection effects, not causal evidence for adding a filter.
- Ongoing end-of-history episodes remain censored; no artificial close.
- Strict mode cannot validate execution eligibility without archived books. Scenario books assume adequate depth and constant spreads; historical liquidity was not observed.
- Fees and slippage are 5 bps each per side, plus half of the scenario spread. Observation is 60 seconds after close; the production simulator may wait a further full bar for an eligible entry.
- Funding coverage, input hashes, candle gaps and individual trades are included in the JSON report.

## Reproduction and verification

Code revision: `b06dfac499886f7c402802c6a926489e91902d0e`. All 140 backend tests passed, including exact percentile parity, SQLite/memory lifecycle parity and future-candle invariance. Source changes are kept on a separate research branch; they have not been deployed to the running study.

Source schema: [Hyperliquid Info API](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint).
