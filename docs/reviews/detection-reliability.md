# Detection reliability corrections

Confirmed technical decisions now use completed 4h/daily candles and completed weekly/reference inputs. Live price remains separate from `decision_price` and `signal_bar_close_time`. The engine cache hashes completed input data, so live ticks do not change a confirmed setup, while historical revisions and updated reference data invalidate the cache.

Signal synthesis no longer raises on the moderate MARKUP branch or substitutes an unchecked raw entry on failure. Crypto and TradFi share fail-closed result handling. Computation failures produce WAIT with `signal_status=unavailable`, zero score and an explanation; agent filters cannot revive that entry.

Mandatory strong-entry restrictions survive CVD/whale upgrades and agent inertia. This includes regime instability, excess heat, crowded-long funding, bearish divergence and MARKUP's existing strict band. Missing funding/sentiment/stablecoin inputs no longer earn points and prevent STRONG_LONG. Checklist items expose available/status, and the UI distinguishes unknown evidence from failed checks. Provider sentinel values (neutral CVD and smart-money ratio 1.0) conservatively remain unconfirmed rather than being credited as positive evidence.

Weighted scores use the weighted denominator. Signal score, age and OI interpretation are finalized after agent adjustments. History is scoped by symbol/timeframe; repeated observations of a completed candle replace that observation rather than counting as additional confirmation bars. Short-entry stalling uses heat computed for the previous completed candle, including the weekly information available at that close; TradFi no longer compares current heat with itself.

The backend supplies one unified cross-timeframe decision across scanner modes. Mixed-strength long pairs and aligned shorts are represented correctly. The opportunity bar consumes the unified decision, chooses the weaker long in its compatibility fallback, and keeps exit warnings visible without requiring agreement or a minimum factor score. Opposing long/short pairs and unavailable decisions are not promoted into unified entries.

## Historical replay

Replay evaluates at the 4h close, includes daily/weekly candles only after they close, refreshes daily results at actual day boundaries, and synthesizes both timeframes before computing signal agreement. Benchmark and weekly macro-filter timestamps now follow the same close-time convention. Date-only sentiment uses the prior day rather than assuming same-day publication was already available. The removed public exchange factory has been restored so backtest modules import successfully and public-data clients retain explicit ownership/cleanup.

Replay remains a technical baseline: historical positioning, stablecoin supply, HyperLens and live agent state are not reconstructed. It does not establish live execution performance; existing close-price fills and execution-cost assumptions still need separate study before strategy optimization. Old backtest statistics are not directly comparable with this corrected pipeline.

## Validation

- Backend unittest suite: 101 tests passed, including new regression tests covering the audited failures, real-engine invariance to an unfinished candle, replay timing and repeated-poll behavior.
- Frontend Node tests: 17 passed, including mixed long pairs, shorts, exit warnings and unavailable/blocked decisions.
- Frontend production build passed; Vite reports its existing large-chunk advisory.
- Python compilation and `git diff --check` passed.

No live market backtest, profitability claim, deployment or trade execution is part of this change. CTO remains chart-only pending a separately evaluated integration. Missing context can reduce strong signals, especially for assets without comparable macro/derivative coverage; this is an explicit evidence policy, not a calibrated win probability.
