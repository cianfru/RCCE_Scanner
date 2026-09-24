# CTO implementation and historical smoke test

The audit fixes and CTO research workflow are implemented in PR #130. CTO remains in shadow mode: this study does not meet promotion criteria.

The final exploratory run contains 1,203 technical decisions for BTC, ETH and SOL, from 2026-07-19 16:00 UTC to 2026-09-24 08:00 UTC. Data came from Hyperliquid candleSnapshot on 24 September 2026. The engine used completed 4h/daily/weekly candles and 599 primary warmup bars.

Assumptions: one new ranked entry per decision time; no overlapping positions in the same asset; six-bar maximum holding period; reconstructed structural invalidation where available; next executable open; 5 bps fees and 5 bps slippage per side. Historical funding and external context were unavailable. Returns below subtract assumed fees/slippage but cannot include unknown funding. The final window was exposed during development and is explicitly exploratory.

## Validation-window comparison

| Policy | Trades | Mean return after assumed costs, before unknown funding | Losing fraction | Filtered winning candidates |
|---|---:|---:|---:|---:|
| baseline:1 | 16 | -0.26% | 43.75% | 0 |
| cto_ranking:1 | 16 | -0.26% | 43.75% | 0 |
| cto_confirmation:1 | 13 | -1.03% | 69.23% | 24 |
| cto_confirmation:2 | 12 | -1.00% | 66.67% | 25 |
| cto_confirmation:3 | 9 | -0.62% | 55.56% | 26 |
| cto_veto:1 | 16 | -0.26% | 43.75% | 0 |
| cto_veto:2 | 16 | -0.26% | 43.75% | 0 |
| cto_veto:3 | 16 | -0.26% | 43.75% | 0 |

Training selected `baseline:1`. The held-out exploratory window had 0 eligible completed trades for that choice. No positive incremental CTO result was established.

The JSON report includes asset/regime/setup/direction cohorts, price excursions, a basket drawdown proxy, filtered opportunities, sample counts and every failed promotion criterion. These are diagnostic strategy measurements, not calibrated win probabilities or portfolio performance.

## Delivered changes

- Shared closed-candle evaluation, input freshness and reproducible recorded decisions.
- Structured CTO shared with the chart; baseline, ranking, confirmation and veto shadow decisions.
- Opportunity lifecycle, invalidation/expiry, source coverage, unknown execution feasibility, persisted deduplicated changes and a reassessment watchlist.
- Chronological evaluation with costs and promotion artifacts checked against evidence and tested asset/timeframe scope.

Validation: 115 backend tests, 20 frontend tests, production frontend build, Python compilation, undefined-name checks and diff whitespace checks. No merge, production deployment or trading action was performed.

Remaining evidence requirement: collect/export live snapshots and complete funding history, reserve a fresh final window, and pass the documented gate before enabling a CTO policy. This requirement cannot be replaced with a synthetic or incomplete historical backtest.
