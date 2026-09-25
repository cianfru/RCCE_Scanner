# Historical forward replay of setups-1

This study accelerates evaluation of the frozen setup definitions through historical data. It does not replace the running forward ledger, reconstruct missing historical context, or establish an untouched out-of-sample result.

## Frozen protocol

- BTC, ETH and SOL Hyperliquid perpetual candles, 4h with closed daily and weekly context; 599 primary bars warm up the engine.
- Original `setups-1` continuation pullback, confirmed reversal and trend comparator rules; no parameter optimization or winner selection.
- Causal replay through the shared engine and decision pipeline. Only completed bars enter each decision. Historical external inputs are unavailable. Consensus uses the three-asset study universe.
- Observe each decision 60 seconds after the bar closes. Reuse the production setup builder, cancellation logic, trigger/fill simulation and funding settlement. No live database writes.
- Evaluate strict missing-book conditions and two explicit constant-spread scenarios: 2 bps and approximately 10 bps, both assuming sufficient depth. Fee and slippage remain 5 bps each per side, plus half-spread. Scenario books are synthetic assumptions, not archived quotes.
- Hourly realized funding, fetched through the public API; only settled funding is exposed at each replay time. Unknown funding excludes an outcome from fully costed statistics.
- Disjoint 90-day reporting windows, purging realized outcomes that cross a reporting boundary. Trades remain continuous across windows; this is frozen-rule rolling evaluation, not a parameter-refitting exercise.
- Keep blocked, unavailable, cancelled, expired, missed and censored outcomes. No forced end-of-history liquidation.
- CTO directional cohorts are descriptive. Differences do not prove that adding a CTO gate improves an independently replayed strategy.

## Limits

Rules were designed after historical exposure. None of these partitions is declared an untouched holdout. Finalized historical candles may differ from the original live snapshots. The historical full scanner universe, intra-bar scans, external input changes, actual books, fills and account-specific fee tiers are not reconstructed. Funding uses the production fixed-entry-notional approximation and bar-close accounting timestamps. Results are conditional on these assumptions. No automatic live promotion is permitted by this study.

## Reproduction

From `backend`, run:

```sh
python -m backtest.setup_walkforward --candles HISTORY.json --funding FUNDING.json --as-of-ms CUTOFF_MS --output REPORT.json
```

The optional `--decisions` JSONL cache contains causal `time`, `rows` and `daily` snapshots emitted by `run_replay(on_decision_bar=...)`. Input file SHA-256 hashes are recorded. Pin the code revision and cutoff to reproduce a run. `--output` is a separate report, never the production ledger.

The memory ledger is an offline storage adapter. Regression tests compare its complete states with the production SQLite ledger and verify future-candle invariance. The engine's batched percentile implementation is tested for exact equality against the original window-by-window calculation, including missing values.

Data API specification: [Hyperliquid Info endpoint](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint). The candle endpoint exposes the most recent 5,000 candles; the run records actual returned coverage rather than assuming the requested dates were all supplied.
