# Historical stop-loss and re-entry reconstruction

This replaces the forward-experiment request interpretation. The automatic shadow hook and executor-page panel have been removed. The research is retrospective and changes no production order rules.

## What was reconstructed

Start from the recorded entry candidates, then evolve positions through historical native 4H candles and logged 4H signal states. Unlike the earlier entry-filter study, recorded exits are **not** retained: a stop can close a position earlier, or a changed exit can keep it open and block subsequent recorded entries. Cooldowns start at reconstructed exits. Every model uses a common cohort of **798 entry candidates across 104 markets**, selected for complete candle paths and pre-entry volatility history.

The source sample contains 865 entries (771 closed, 94 marked open), after the previously approved exclusions. A further 67 candidates lack the price coverage or unit validation required for this reconstruction. No model receives a more favorable inclusion list. The retained cohort’s original recorded P&L is **+$665.34**. This is distinct from both the whole dashboard sample and the reconstructed results below.

## Gross combined P&L sensitivity

All dollar results use $10,000 initial virtual capital and original candidate notionals. Wider stops scale notional down by 8% / stop distance; tighter stops do not scale it up. Unused capital is not redistributed. Signal reset means the entry signal must become inactive before a later candidate is accepted.

| Rule | 4H close fills | Open → high → low → close | Open → low → high → close |
|---|---:|---:|---:|
| Current rules: 8%, BE at +5% | $-153.78 | $-160.26 | $-69.94 |
| Reset + 4h: 8%, BE at +5% | $-121.73 | $-37.68 | $-12.81 |
| Reset + 4h: 6%, BE at +5% | $-164.73 | $-82.38 | $-80.66 |
| Reset + 4h: 10%, BE at +5% | $-128.36 | $-31.38 | $-6.11 |
| Reset + 4h: 12%, BE at +5% | $-127.78 | $-61.83 | $-33.27 |
| Reset + 4h: 2× TR stop, BE at +5% | $-107.01 | $-63.72 | $-49.47 |
| Reset + 4h: 8%, BE at +10% | $79.72 | $-186.71 | $-174.96 |
| Reset + 4h: 8%, no BE exit | $420.59 | $364.18 | $364.18 |
| Unfiltered re-entry: 8%, no BE exit | $390.30 | $344.21 | $344.21 |

The two OHLC orderings are alternative assumptions, not guaranteed upper/lower performance bounds. They can change both exits and later entry eligibility. The initial entry candle uses only its post-entry close because its earlier high/low may predate entry.

## Main finding

Break-even behavior is more influential here than modest hard-stop adjustments. In the close-only model, reset + 4h with no automatic break-even exit produces **+$420.59**, versus **−$121.73** with the +5% arming rule. With the same reset policy, the 2× mean-true-range stop produces **−$107.01**, only a $14.72 improvement over fixed 8%.

Removing the BE exit retains the 8% hard stop and all logged signal exits. It does not mean holding without protection. With OHLC intrabar stops, the no-BE reset variant produces +$364.18 under both orderings. A +10% BE arming threshold is not robust: positive under close-only checks but negative under both intrabar assumptions.

The no-BE scenarios were added after diagnosing HYPE, so they are exploratory, not an independent validation result. None of this demonstrates that removing BE will improve future performance or recreate the original account.

## Why the reconstructed baseline differs from the ledger

On the same 798-entry cohort, recorded results are +$665.34; applying current rules from the beginning produces −$153.78 with close-only checks. That **$819.12 discrepancy** is too large to call this an exact replay of the live executor.

- HYPE is the clearest example: its recorded open contribution is about +$654.51, but current +5% BE logic applied retrospectively exits at $35.19 on 2026-04-02 03:59:59 UTC, approximately −$3.84. Under the no-BE reset model its reconstructed contribution is +$309.54, not the original +$654.51.
- Current executor comments describe stop rails decided on April 21. This suggests historical rule changes, but deployment/configuration history is not sufficient to establish their exact activation times. Current rules applied to March are a hypothetical policy experiment.
- Native 4H candles cannot reproduce every original scan price, intrabar peak, or exchange fill. Signal states are sampled at each completed candle; transient states inside a candle can be missed.
- The candidate universe is the historically recorded entries. It cannot introduce a new entry on an unrecorded scan after an alternative exit. Original notionals remain attached to those candidates.

The intended use is to identify sensitive rules and compare hypotheses under controlled assumptions—not replace the dashboard’s historical P&L or publish these percentages as verified strategy returns.

## Close-only risk and cost comparison

Costs assume 5 bps per executed entry/exit side; open positions have no exit-cost reserve. No funding or market-impact model is included. Equity drawdown uses mark-to-market at event times, with simultaneous candle marks grouped before calculation; it is not intrabar maximum drawdown.

| Rule | Closed / open | Gross P&L | After estimated costs | Sampled max drawdown |
|---|---:|---:|---:|---:|
| Current rules: 8%, BE at +5% | 440 / 61 | $-153.78 | $-174.06 | 8.29% |
| Reset + 4h: 8%, BE at +5% | 409 / 59 | $-121.73 | $-140.64 | 7.38% |
| Reset + 4h: 6%, BE at +5% | 433 / 55 | $-164.73 | $-184.61 | 7.10% |
| Reset + 4h: 10%, BE at +5% | 385 / 60 | $-128.36 | $-142.60 | 6.26% |
| Reset + 4h: 12%, BE at +5% | 366 / 60 | $-127.78 | $-139.18 | 5.28% |
| Reset + 4h: 2× TR stop, BE at +5% | 424 / 53 | $-107.01 | $-125.67 | 6.31% |
| Reset + 4h: 8%, BE at +10% | 366 / 65 | $79.72 | $62.30 | 7.65% |
| Reset + 4h: 8%, no BE exit | 297 / 72 | $420.59 | $405.59 | 6.74% |
| Unfiltered re-entry: 8%, no BE exit | 306 / 73 | $390.30 | $374.97 | 6.99% |

Wider stops reduce exposure by construction. Their lower drawdown must not be interpreted as proof of better timing or superior risk-adjusted returns.

## Data and execution rules

- Native Hyperliquid 4H candles through the September 9 snapshot; seven additional pre-entry days fetched for HYPE, TRX and VVV so early entries are not lost for lack of warmup.
- 13,798 recorded 4H signal transitions; no future signal state is used at a candle close.
- Mean true range uses the previous 14 completed 4H ranges with the preceding close. Stop is 2× that mean, bounded to 4–12% and fixed at entry.
- Validate each legacy price unit against its native entry candle (native or divided by 1,000, uniquely matching within 1% tolerance). Reject unexplained mismatches.
- Gap-through stop fills use the candle open. Otherwise intrabar modes fill at the crossed stop level. A previously armed BE stop takes precedence over a lower hard stop. Close-only mode fills at the observed close.
- Entry-bar high/low are never used. No candle history after the final snapshot is used.
- Exclude histories that cannot support an alternative position remaining open until the final snapshot; delisted/incomplete histories are not forward-filled.

Additional exclusions:
- No completed entry candle: 27
- No native market mapping: 2
- Entry unit/range mismatch: 7
- Incomplete candle path through final snapshot: 31

## Decision

Do not deploy the forward experiment or alter active stops from this reconstruction alone. The best-supported research priority is to examine whether automatic return-to-entry exits cut trend winners, rather than assuming a wider hard stop is the answer. Before adopting a setting, reconcile the historical configuration timeline and replay higher-resolution prices where available. Keep the current retrospective results and all assumptions visible.

## Reproduction

`backend/research/stop_reconstruction.py` consumes the prior study JSON, native candle directory and logged signals. Summary, exclusions, modeled closures and an input-hash manifest accompany this report. Tests cover intrabar ordering, gaps, disabled/later BE, future-signal isolation, price units, changed-exit blocking, reset clocks, pre-entry extremes and volatility sizing.

```sh
PYTHONPATH=backend python backend/research/stop_reconstruction.py \
  --source reentry-results.json --candles stop-candles \
  --signals signals.json --out stop-results.json
```
