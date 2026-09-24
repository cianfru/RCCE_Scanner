# Detection engine and CTO audit implementation

This branch implements the eight audit corrections and the staged CTO integration. CTO is **shadow by default**. No policy has earned promotion, and no deployment or trade execution is implied by the historical study.

## Audit action map

| Audit action | Implementation |
|---|---|
| Eliminate lookahead | Completed 4h, daily, weekly and benchmark timestamps; unfinished final historical candles are excluded. |
| Unify candle/cache semantics | Confirmed decisions have `decision_price`, `signal_bar_close_time` and content-derived `decision_input_id`. Revisions invalidate cache; live price stays separate. |
| Fix synthesis exceptions / raw fallback | Moderate MARKUP uses the defined condition count. Pipeline errors produce unavailable WAIT, never an unchecked raw entry. |
| Prevent modifier bypasses | Final constraints follow synthesis and agent filters, including strong-entry caps and mandatory macro blocks. |
| Repair hidden opportunity pairs | Backend unified decision, weaker mixed-strength long pairs, symmetric shorts, independent exit warnings, lifecycle-aware frontend selection. |
| Distinguish unknown evidence | Pass/fail/unknown checks, source/observation/freshness metadata and evidence coverage. Stale/future/missing optional inputs do not earn confirmation. |
| Align scores and history | Weighted denominator; final signal score/age/OI interpretation; symbol/timeframe history; repeated candle observations cannot manufacture persistence or chop. |
| Integrate CTO safely | Shared numeric chart/scanner CTO, eight shadow policies, chronological research harness and gated policy artifacts. |

## Shared evaluation and provenance

`decision_pipeline.evaluate_decision` receives explicit engine inputs, context, observation time and history; it performs freshness filtering, synthesis, agent filters, constraints, scoring and CTO policies. Crypto, TradFi and historical replay call this function. Recorded snapshots include the pre-decision history, context, anomalies, positions, input quality, engine version and candle identity; `replay_recorded` reproduces an isolated evaluation without network access.

The scanner uses up to 599 completed primary/reference candles and 199 completed weekly candles. CTO uses the same 599-bar window in chart and scanner. A chart/scanner comparison requires identical candle identity, timeframe and close time. Historical source revisions can legitimately change the identity. CTO state ages are bounded by that history window.

Freshness limits are explicit defaults in `decision_pipeline.MAX_AGE`: funding/CVD/derivatives/HyperLens/global totals 30 minutes, macro 24 hours, daily sentiment/stablecoins 36 hours. Candle freshness is one timeframe plus five minutes. These are operational defaults, not optimized trading thresholds. Provider observation time can describe collection time rather than original economic publication time. Older historical context is not reconstructed from today's feed.

The chart's colored CTO arrays contain completed candles only. `cto_preview` is separately labeled provisional and is never used for confirmed decisions. Structured CTO includes direction/strength, slopes, ATR-normalized spread, ordering conflict, state/direction ages, transition close, history count, quality and input identity. Gapped/invalid/insufficient CTO data is unavailable.

## Opportunity contract

The API/UI expose emerging, confirmed, blocked, invalidated, expired, unavailable, and separate risk-warning states. Coin detail views show reason, direction/setup, trigger and candle times, coverage, blockers, CTO shadow assessments, source freshness, invalidation and execution feasibility. The dashboard includes a reassessment watchlist and persisted recent state changes.

A setup records its first trigger and ten-completed-bar price extreme. Its initial expiry is three timeframe bars; repeated polls do not move it forward. A completed close crossing the frozen extreme invalidates the episode. Expired/invalidated episodes require a changed baseline trigger to rearm. These are visibility/lifecycle rules; they are not validated stop-loss or execution instructions. Raw engine labels remain separately inspectable. Risk warnings remain visible independently of entry agreement.

The journal emits changes in status/direction/setup/signal, not another notification for an unchanged poll. First observations per symbol/timeframe/candle/version are immutable. State survives restart; full scanner history starts fresh on process restart, while recorded snapshots preserve enough state to reproduce each stored evaluation. Journal write failure is logged and exposed by `opportunity_persisted=false`; it does not break scanning.

`OPPORTUNITY_DB_PATH` overrides storage. Otherwise use `RAILWAY_VOLUME_MOUNT_PATH/opportunities.db`, falling back to `backend/data/opportunities.db`. `OPPORTUNITY_RETENTION_DAYS` defaults to 90 (0 disables pruning). Export/archive observations before pruning when building a longer research history. Recent transitions: `GET /api/opportunities/transitions?limit=100`.

No current spread/depth is fabricated. Execution feasibility is unknown unless a supplied execution observation is at most 60 seconds old.

## Research and promotion

See [CTO study protocol](cto-study-protocol.md) for schemas, CLI commands, costs and limitations. Policies compare corrected baseline, ranking only, directional confirmation, and opposing-direction veto. Confirmation and veto test one, two and three completed direction bars. Reversal candidates awaiting CTO alignment remain emerging. Missing CTO cannot pass a confirmation/veto policy. Exit warnings take precedence in every policy.

A deterministic 60/20/20 chronological split selects a variant using training only, compares all variants in validation, and evaluates only the fixed choice plus baseline on holdout. Labels crossing boundaries are purged. Fees, slippage, delayed next-open fills, stops/gaps, directional funding, excursions, sample sizes, losing-signal fraction, filtered winners/losers and asset/regime/setup/direction cohorts are explicit. Ranking uses a fixed top-K capacity. Weekly paired bootstrap blocks retain temporal and cross-asset dependence when testing incremental expectancy.

Promotion requires an untouched final window, recorded parity, complete context/funding, minimum sample/asset coverage, positive expectancy and incremental edge in validation and holdout, no worse basket drawdown, and no materially sampled losing cohort. The defaults are conservative research gates, not proof of future returns. A checked report can create a versioned, checksummed artifact, scoped to tested assets/timeframe. Absent/invalid artifacts retain baseline/shadow. The artifact is loaded at process start; rollback is removal of `CTO_POLICY_PATH` and restart.

The exploratory BTC/ETH/SOL study downloaded on 2026-09-24 is a smoke test, not promotion evidence. It lacks historical external context/funding and live state, and its final window was reused during implementation. No CTO variant is enabled on that basis.

## Validation

Backend unit/regression tests cover audited failures, actual-engine unfinished-bar invariance, chart/scanner CTO parity, JSON-recorded replay parity, freshness, repeated polls, restart/deduplication, lifecycle expiry/invalidation, next-open and gap fills, funding sign, chronological isolation and promotion refusal. Frontend Node tests cover mixed long pairs, shorts, independent warnings and lifecycle filtering. The production build and undefined-name checks pass. Vite retains its existing large-chunk advisory.
