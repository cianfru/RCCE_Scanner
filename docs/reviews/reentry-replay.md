# Re-entry calibration study — September 9, 2026

**Conclusion:** blanket re-entry removal makes this historical sample worse. Signal reset plus four hours has the strongest result among the tested filters, but improves gross return by only 0.41 percentage points and underperforms for the later entry cohort. This is not enough evidence to change production settings.

## Method and scope

This is a chronological **fixed-trade-path entry-filter replay**, not a full strategy backtest. It uses the same 771 closed trades and 94 priced open positions as the reviewed executor. The five known malformed closures and four unresolved open positions remain excluded in every variant. Starting capital is $10,000.

For each market, accept or reject each recorded entry in chronological order. A cooldown starts at the last accepted trade’s exit. Skipped trades do not restart the clock. Retained trades keep their recorded entry prices, position sizes, exits and final marks. Freed capital stays idle. Initial entries are allowed; one-entry mode forbids every later entry in that exact ledger symbol. Market aliases are not silently merged.

Signal reset requires a non-entry state after the previous accepted exit, or already active at that exit. The next candidate is still an actually recorded entry. All 865 candidate entry signals match the latest logged 4-hour state; the log has 13,798 transitions back to March. This validates the filter inputs, not a tick-by-tick reconstruction of every scan.

## Results

| Rule | Closed | Open | Realized | Unrealized | Combined | Return | Change vs baseline |
|---|---:|---:|---:|---:|---:|---:|---:|
| Recorded baseline | 771 | 94 | $-991.93 | $1,713.80 | $721.88 | 7.22% | $+0.00 |
| 4-hour cooldown | 525 | 71 | $-581.14 | $1,323.66 | $742.52 | 7.43% | $+20.64 |
| 24-hour cooldown | 477 | 70 | $-783.52 | $1,308.29 | $524.77 | 5.25% | $-197.11 |
| 48-hour cooldown | 440 | 65 | $-724.35 | $1,292.54 | $568.19 | 5.68% | $-153.69 |
| 7-day cooldown | 343 | 56 | $-578.54 | $1,089.87 | $511.34 | 5.11% | $-210.54 |
| 24 hours after a losing exit | 484 | 72 | $-815.09 | $1,487.48 | $672.39 | 6.72% | $-49.49 |
| One entry per token | 108 | 10 | $-272.03 | $689.40 | $417.37 | 4.17% | $-304.51 |
| Signal reset required | 488 | 71 | $-501.68 | $1,243.48 | $741.80 | 7.42% | $+19.92 |
| Signal reset + 4-hour cooldown | 476 | 70 | $-480.14 | $1,243.48 | $763.34 | 7.63% | $+41.46 |

The 24-hour cooldown avoids $530.38 of losses but forfeits $727.48 of gains. Its skipped winners include a closed VVV trade (+$295.38) and open ZEREBRO (+$153.17) and PUMP (+$96.86) positions. No-re-entry forfeits $1,408.83 of gains while avoiding $1,104.33 of losses.

## Transaction-cost sensitivity

Assumed cost on each side of entry/exit notional; open positions include an entry cost and a terminal-liquidation cost reserve. These are sensitivity assumptions, not quoted exchange fees. No funding, price impact or financing costs are simulated.

| Rule | No costs | 5 bps per side | 10 bps per side |
|---|---:|---:|---:|
| Recorded baseline | $721.88 | $682.65 | $643.43 |
| 4-hour cooldown | $742.52 | $715.50 | $688.48 |
| 24-hour cooldown | $524.77 | $499.87 | $474.96 |
| 48-hour cooldown | $568.19 | $544.68 | $521.17 |
| 7-day cooldown | $511.34 | $492.63 | $473.92 |
| 24 hours after a losing exit | $672.39 | $646.84 | $621.29 |
| One entry per token | $417.37 | $410.12 | $402.87 |
| Signal reset required | $741.80 | $716.94 | $692.08 |
| Signal reset + 4-hour cooldown | $763.34 | $738.87 | $714.40 |

At 10 bps per side, reset + four hours improves the result by approximately $70.97 versus baseline. That is 0.71 percentage points of starting capital, not a forecast of improvement.

## Stability check

The first two-thirds and last third below are grouped by entry date; outcomes still use the same final snapshot. They are descriptive cohorts, **not unseen validation** or period-specific portfolio returns. Earlier entries have longer holding opportunities, and the executor’s rules may have changed during history.

| Rule | Earlier entry cohort P&L | Later entry cohort P&L |
|---|---:|---:|
| Recorded baseline | $248.95 | $472.93 |
| 4-hour cooldown | $396.69 | $345.83 |
| Signal reset required | $466.76 | $275.04 |
| Signal reset + 4-hour cooldown | $488.30 | $275.04 |

The apparent filter improvement comes from the earlier cohort. Reset + four hours underperforms baseline by about $197.89 in the later cohort. It is not a stable improvement across this simple split.

## Actual price-path check

Fetched native Hyperliquid 4-hour candles. 836 of 865 candidate entries have a candle covering entry and a uniquely validated price unit. Daily horizon values use completed candles, exclude the partial entry candle and reject missing or incomplete horizons. Legacy k-contract entries are checked separately for native versus per-token units; no guessed token migration or exchange substitution is used.

For entries rejected by a four-hour cooldown:

| Horizon after entry | Usable paths | Positive | Median price return |
|---|---:|---:|---:|
| 1 days | 257 | 107 | -0.86% |
| 7 days | 244 | 96 | -4.66% |
| 30 days | 190 | 53 | -12.62% |

Seven-day paths have a median −4.66%, yet 96 of 244 are positive. These are price-path diagnostics, not realized trades or a promise that holding for seven days earns that return. Coverage varies by horizon and delisted markets can have incomplete history.

## What this can and cannot calibrate

- Supported now: entry cooldowns, signal-reset entry gates, skipped winners versus avoided losses, original dollar sizing, cost sensitivity and forward price-path diagnostics.
- Not established: a full counterfactual executor return, mark-to-market drawdown, new intrabar fills, optimal stops, portfolio redistribution, or a validated one-year projection.
- A real cooldown can create an entry on a scan that never opened a position historically. This fixed-candidate replay cannot invent that entry. Changing exits, sizing or signal formulas requires a fresh stateful replay and fill assumptions.
- The old backtest position manager is not equivalent to the current executor: it disables ACCUMULATE, adds signal decay and differs in other management rules. Its results should not be presented as a current-executor replay.
- Historic closed records do not contain the full high-water mark/arming history needed to reconstruct break-even behavior at original scan frequency. Four-hour OHLC cannot resolve the order of intrabar high/low touches.

## Recommended next experiment

Keep production unchanged. Shadow the baseline against signal reset + four hours on new data, using the same decision stream and recording accepted/rejected entries, explicit notional, parameter version, state changes and execution costs. Preserve the predefined rule instead of searching dozens of new thresholds against this sample. Then compare net P&L, drawdown, turnover and missed winners on the fresh period. For stop calibration, first implement a research harness around the actual executor state machine with documented gap/intrabar fill assumptions.

## Reproducibility

Scripts: `backend/research/reentry_replay.py` and `fetch_reentry_data.py`. Run with the same exported status/trade/performance snapshots. Results manifest contains SHA-256 hashes of inputs and downloaded candles; CSV files contain summary and per-candidate decisions. Source records and production execution settings are unchanged.

Public sources: `https://api.hyperliquid.xyz/info` (`meta`, `candleSnapshot`, interval `4h`) and the application’s `/api/signals/history?timeframe=4h` endpoint. Reference terminal marks are the same audited snapshot as the executor performance review. Downloads were cached locally; candle rate limits were retried at a slower cadence. No Railway scan jobs were launched.

```sh
PYTHONPATH=backend python backend/research/reentry_replay.py \
  --trades trades.json --performance performance.json \
  --candles candle_directory --signals candle_directory/signals.json \
  --out results.json
```
