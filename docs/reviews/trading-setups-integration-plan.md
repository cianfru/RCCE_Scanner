# Trading setups integration plan

## Objective and boundary

Deliver a usable **research and forward paper-trading** workflow before treating scanner labels as executable trading strategies. This integration does not place orders, connect account credentials, enable CTO filtering, or claim a validated edge.

Initial scope: BTC/USDT, ETH/USDT and SOL/USDT; 4h decisions with completed daily context; long-only continuation pullbacks and confirmed-base reversals. A separately labeled simple trend comparator runs under the same fill/cost rules. Expand direction/universe only after evaluating this version.

## Deliverables in this integration

1. Versioned deterministic strategy definitions: context, trigger, structural stop, target, minimum reward/risk, expiry and maximum holding period. Defaults are research hypotheses, frozen in each record.
2. Full setup cards: eligible/blocked/no-setup/unavailable state and reasons; prices, timing, execution observations, CTO reference and paper-only label.
3. Durable forward ledger: first-observed setup definitions plus append-only events. Record untriggered expiry, cancellation, missed entry, data gaps and ambiguous outcomes as well as wins/losses. No historical backfill into the forward ledger.
4. Causal simulator: future completed-bar triggers, precommitted next-open fills, bounded entry zone, conservative stop-before-target handling, fees/slippage, funding coverage and data-gap detection. Restart must not duplicate fills or rewrite the original contract.
5. Read-only dashboard/API: lifecycle counts, closed sample sizes, net expectancy and R, losing fraction, MFE/MAE, cost coverage, per-strategy/asset/regime cohorts, and the trend comparator. Never pool independent research strategies into claimed portfolio returns.
6. Scanner integration: periodically collect public Hyperliquid books/candles/funding for the restricted universe. Missing execution/context data blocks new paper setups and remains visible.
7. Regression tests: temporal boundaries, immutable definitions, restart/idempotency, gaps, ambiguous OHLCV order, costs/funding, cancellation, expiry and frontend presentation.

## Paper execution assumptions

A trigger must occur in a candle that opened after the setup was observed. The simulator schedules entry at the first 4h boundary at or after observing that trigger; it cannot buy at an already-past opening price. Entry is simulated when that precommitted candle completes. A gap outside the entry zone is a missed trade. Stop/target ordering within OHLCV is unknown: stop wins ties and the ambiguity is reported. Execution cost assumptions and the observed book at setup/trigger time are frozen; future spread and real fills are not known. Funding rates use hourly settlements with explicit coverage; missing funding excludes trades from fully net statistics.

Keep the first observation of every strategy/symbol/candle, including blocked/no-setup records. Do not optimize defaults using the forward test window. Public market API reads require no exchange credentials.

## Acceptance criteria

- Two setup strategies and comparator produce deterministic, reviewable definitions.
- No entry/trigger precedes observation; no duplicate record/fill on repeat scan or restart.
- Missing/stale data cannot quietly become a pass; unknown costs cannot become a net result.
- Paper events and statistics are accessible through the UI and read-only endpoints.
- Tests and production build pass. Existing trading execution remains independent.

## Evidence milestones after integration

Collect observations through deployment; audit feed completeness and paper/live fill differences; evaluate each frozen strategy against the comparator across assets and regimes; reserve fresh chronological validation/holdout periods. Promotion still requires adequate samples and positive incremental performance after costs. A bounded real-execution pilot requires a separate explicit decision and risk configuration; it is not part of this integration.

## Implemented integration

- `trading_setups.py`: deterministic definitions and execution-quality checks. Continuation requires a real pullback from a prior closing-price peak, rather than mistaking the current candle's wick for a pullback. Reversal requires both floor confirmation and absorption. Both retain mandatory scanner restrictions and daily exit warnings.
- `paper_setups.py`: immutable contracts, durable states and append-only observation/entry/exit/cancellation events. One active episode per symbol/strategy; strategies are independent experiments, not a combined portfolio. No-setup and blocked observations are retained.
- `setup_research_service.py`: background public-data collection, throttled to one cycle per minute and never awaited by the scanner's existing execution path. Requests use Hyperliquid candles, order books and realized hourly funding; no order/account endpoints. Existing trading execution is independent.
- Read-only `/api/research/setups` and `/api/research/setups/{id}/events` endpoints; setup cards on coin/detail views and a forward-results dashboard with comparator, lifecycle counts, cohorts and cost coverage.
- Persistent file: `PAPER_SETUPS_DB_PATH`, otherwise the Railway volume's `paper_setups.db`, otherwise `backend/data/paper_setups.db`. `PAPER_SETUPS_ENABLED=0` disables collection. Preserve this database across deployments; this ledger does not automatically delete observations. Back it up before version migrations.

## Defaults and material limits

Definitions are version `setups-1`. Initial paper notional is $1,000 per independent episode. Fee/slippage assumptions are 5 bps each per side plus observed half-spread; these are configurable-in-code research assumptions, not the user's actual fee tier. Quotes must be at most 60 seconds old, spread <= 10 bps, and bid/ask depth within 10 bps of mid at least 10 times paper notional. Stop distance is 0.5–4 ATR; target seeks 2R with at least 1.5R room and may be capped below observed resistance. Actual entry must still satisfy 1.5R after modeled costs. Definitions expire after three 4h intervals; maximum holding period is twelve bars.

A trigger uses a fully future candle that opened after the setup's observation. Because the next opening price cannot be backdated, a trigger collected after a candle boundary normally schedules entry at the following 4h boundary. This intentional delay must be included when judging the strategy. A precommitted opening fill is reconstructed only once its candle completes; its future spread/depth are not observed. This is a candle-level research simulator, not an order-book execution emulator.

Funding completeness requires every expected hourly settlement in the modeled holding interval. Amounts use fixed entry notional; actual settlement marks are not reconstructed. Stop/target exits use bar-close accounting timestamps because intra-bar timing is unknown. Automatic funding reconciliation covers the most recent seven days; older uncovered trades remain explicitly uncosted. A candle outage beyond the supplied history is marked data-gap and excluded from net statistics, rather than silently reconstructed. Missing feeds pause active paper observations or cancel unfilled commitments; they cannot create a fresh eligible setup.

The context/fees/defaults must not be tuned against the forward record. Change the strategy version when changing rules and evaluate the new version separately. Deployment starts collection; elapsed live observations and a successful validation study cannot be manufactured during implementation. No strategy is promoted to real execution by this release.

## Verification completed

- 134 backend tests passed, including 19 additional forward-setup tests covering definition quality, timing, missing data, cost coverage, restart/immutability, cancellation, gap fills, event preservation, repeated polls, background scheduling and shutdown.
- 22 frontend tests passed, including explicit unknown-cost and comparator presentation checks.
- Production frontend build, Python compilation, undefined-name checks and diff whitespace checks passed. Vite retains the pre-existing large-bundle advisory.
- Read-only adapter smoke test returned a fresh Hyperliquid BTC order book and 24 hourly funding records. This tests API parsing/connectivity, not strategy performance.
- No historical results were inserted into the forward ledger, no account credentials were used, and no orders were submitted. Collection begins when this backend revision is deployed and scanning.

Public API schema reference: [Hyperliquid Info endpoint](https://hyperliquid.gitbook.io/Hyperliquid-docs/for-developers/api/info-endpoint).

Comparator interpretation: the simple trend comparator shares the scanner's daily context and mandatory safety gates. It measures the incremental effect of the setup definitions under common controls; it is not evidence that the entire scanner outperforms an independently implemented moving-average strategy.
