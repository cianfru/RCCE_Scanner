# CTO study protocol

Run commands from `backend/` using the project's Python environment.

## Recorded observations

```sh
python -m backtest.recorded_decisions /data/opportunities.db recorded.json --timeframe 4h
```

This opens the journal read-only, exports first-observed snapshots and verifies baseline labels with their captured state/context. Preserve all captured inputs and engine versions. Mixed versions must be replayed using the matching version; do not silently reinterpret them. A historical candle replay uses the same evaluation function but cannot reproduce unavailable historical positioning, stablecoin, whale or portfolio context.

## Dataset

Create a JSON object containing:

```json
{
  "decisions": [{"symbol":"BTC/USDT", "timeframe":"4h", "signal":"LIGHT_LONG", "baseline_signal":"LIGHT_LONG", "signal_bar_close_time":1784476800, "evaluated_at":1784476810, "cto":{}}],
  "candles": {"BTC/USDT":[{"time":1784476800,"open":100,"high":102,"low":99,"close":101}]},
  "funding": {"BTC/USDT":[{"time":1784480400,"rate":0.0001}]},
  "funding_coverage": {"BTC/USDT":[1784476800,1790236800]},
  "context_complete": false
}
```

The example is schematic, not sufficient data. Use complete scanner snapshots for recorded parity, with at least 30 distinct decision times and one timeframe per dataset. All times are UTC seconds; candle timestamps are opens. Supply ordered, contiguous future candles. Funding rates are signed fractions at actual settlement times; positive rates cost longs and credit shorts. Coverage bounds assert the funding feed was exhaustively collected throughout that interval; omitted funding is explicitly unknown, not zero-cost evidence. For instruments with no funding, document that fact and supply known coverage with an empty event list. Preserve the data source and collection time in a separate manifest.

## Run once on a fresh final window

```sh
python -m backtest.cto_study dataset.json report.json --horizon 6 --fee-bps 5 --slippage-bps 5 --top-k 3
```

Declare horizon/costs/capacity before exposing the holdout. Fees and slippage are per side. These example costs are assumptions, not a claim about a specific account or venue. Entry is the next available bar open at or after actual evaluation time; a delayed observation cannot fill at an earlier open. Invalid-at-entry and missing/gapped outcomes are excluded and counted. Exit is a fixed horizon or supplied structural invalidation. A stop crossed by a gap fills at the worse opening price. Funding/occupancy extend through the stop bar's close because intra-bar timing is unknown. Favorable excursion excludes the stop bar, whose high/low ordering is unknown. Excursions are price excursions; net returns separately subtract execution costs.

At each decision time, eligibility is evaluated first and eligible candidates are ranked using priority score plus the ranking policy adjustment. Top K new entries are allowed at that time, with no overlapping trades in the same asset. This is not a total portfolio leverage/cash constraint. The reported drawdown is an equal-weight entry-basket compounding proxy, not a mark-to-market portfolio drawdown. Losing-signal fraction means net return <= 0; filtered winners/losers count candidate outcomes and can overlap in time. They are not independent trades or guaranteed missed profits.

The CLI refuses to overwrite an output or reuse the dataset's `.holdout-used` marker. Copying/renaming data does not make its holdout fresh. Python API studies default to exploratory (`holdout_fresh=false`). Any parameter change after inspecting the final window needs new future data before promotion. Validation reports all variants; the holdout reports only the preselected policy and baseline.

## Promotion

```sh
python -m cto_policy report.json policy.json
```

The command fails if the report fails the gate. Keep report and artifact together; deploy the tested revision with `CTO_POLICY_PATH` pointing to the artifact only after the report is reviewable. Runtime verifies the report checksum, engine/study/policy versions, policy choice and tested scope. It recomputes the gate instead of trusting an `approved` boolean. There is no artifact in this PR: CTO stays shadow.

Both validation and holdout need at least 50 trades after excluding within-asset overlap, three assets, full funding coverage, positive net expectancy/lower mean bound, better expectancy than baseline, no worse basket drawdown, and positive paired weekly-bootstrap lower incremental bound across at least ten populated weekly blocks. Material asset/regime/setup cohorts (n >= 10) must have positive expectancy. Recordings must reproduce baseline labels. These gates deliberately fail short, incomplete technical replays. Archive observations beyond default journal retention to assemble enough chronological history.

Unknown execution feasibility, absent funding, selection bias, market regime shifts and data revisions remain material limits. The machinery makes comparisons reproducible; it does not establish profitability by itself.
