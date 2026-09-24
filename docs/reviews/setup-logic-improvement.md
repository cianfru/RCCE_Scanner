# Production setup logic improvement

The release adds a confirmed-breakout setup to the running paper platform. Original setups and their records are preserved as controls. No exchange orders are enabled.

## Implemented rules

- BTC, ETH and SOL, 4h closed decisions with completed daily context.
- Require upward 4h/daily regimes and a close above the prior 20-bar high. Retain weekly macro, missing-data, climax and explicit exit-warning restrictions.
- Confirm the setup on that completed close; precommit to the next future 4h opening. Do not wait for an additional future trigger candle.
- Entry must fall between 0.5 ATR below and 1 ATR above the confirmed close. It must still offer at least 1.2R after modeled entry/exit costs.
- Initial stop: 2 ATR below the confirmed close, capped at 12% price risk. Target: 2R from the reference close. Maximum holding period: 12 bars (48 hours).
- No automatic break-even in this setup. CTO remains reference-only. Both decisions follow comparisons rather than an assumption that more filters are better.
- Active new setups appear on the main dashboard and coin/detail cards, with entry timing, price bounds, stop, target, expiry, exit policy and rejection reasons.
- The simulator supports separately frozen protection alternatives and records stop adjustments explicitly. Legacy executor stop rules remain unchanged.

## Historical comparison

September 2024–September 2026. A fully costed trade includes realized funding plus modeled 5 bps fee and 5 bps slippage per side and half the assumed spread. Returns are per independent episode, not account or annualized returns.

| Definition | Closed / fully costed | Mean net return | Mean net R | Losing fraction | Realized drawdown R |
|---|---:|---:|---:|---:|---:|
| Original pullback | 6 / 6 | 0.387% | -0.031 | 33.333% | 1.052 |
| Original reversal | 0 / 0 | — | — | — | — |
| Simple comparator | 49 / 46 | 0.692% | 0.190 | 45.652% | 7.648 |
| New confirmed breakout · 2 bps spread | 103 / 102 | 0.153% | 0.117 | 55.882% | 10.728 |
| New confirmed breakout · 10 bps spread | 102 / 101 | 0.085% | 0.102 | 56.436% | 11.718 |

**Measured improvement:** 102 fully costed trades instead of six for the original pullback; mean risk-normalized outcome improves from -0.031R to +0.117R. BTC, ETH and SOL each have positive aggregate mean R, including under 10 bps spread stress.

**Trade-offs:** the new setup does not dominate the comparator: the comparator retains higher average net return and R per trade and a smaller realized drawdown. The new setup has more losing trades and larger realized drawdown than the original six-trade pullback sample. The benefit is substantially better opportunity coverage with positive average R, not demonstrated higher win rate or uniformly better risk.

## Chronological checks

- Development period: 88 fully costed trades, mean +0.128R.
- Middle period: no entries, because all long decisions were blocked by the weekly macro filter. Relaxing that restriction produced negative outcomes; the release keeps it. No-trade observations provide no estimate of trading expectancy.
- Later period: 14 trades, mean +0.047R at 2 bps spread and +0.025R at 10 bps spread. This is a small, weak positive edge, not strong statistical evidence.

## What was rejected

- Widening pullback eligibility broadly: more trades but negative development expectancy.
- Simultaneous floor/absorption relaxation: still insufficient eligible recovery trades.
- Longer fixed holding periods: inconsistent gains and generally higher drawdowns.
- 1.5 ATR stops, volume filtering and CTO confirmation: impressive development results but negative later results for the selected combinations.
- Weekly macro recovery exception: losses in the middle chronological period.
- Narrower retest entry zone: slightly better aggregate R but its later-period result turned negative under higher spread costs.

## Break-even findings

The legacy executor and new setup engine are different systems. The legacy executor arms break-even at a 5% observed gain; setups-1 has no break-even and exits through frozen stop/target/time rules. The controlled breakout comparisons tested no protection, legacy-style 5% arming, cost-aware 5% arming, delayed 2R protection and trailing protection. None justified adding break-even to the selected setup.

A separate bar-close proxy replay of the production executor compared 5% arming, 8% arming and no break-even, including terminal marks for still-open positions. Removing break-even worsened the equal-notional aggregate; delaying it reduced losses but remained negative. This proxy omits intrabar scans and complete external context, so it does not justify changing all legacy live-position exits.

## Evidence limits

These are retrospective comparisons with repeated historical exposure and multiple candidate tests. Later data informed rejection of candidates; this is not a clean, untouched holdout or proof of a persistent edge. Historical books and external scanner context are incomplete; spread/depth are assumptions, consensus uses three assets, fills use conservative candle-level rules and funding uses fixed entry notional. One closed selected trade lacks full funding coverage and is excluded from net averages. A small positive recent result can disappear with worse execution.

The production release is for paper setups and manual observation. Fresh forward outcomes remain necessary before any decision to enable live execution. The simple comparator stays visible.

## Operations and verification

- `PAPER_SETUP_V2_ENABLED=0` stops creation of new v2 definitions and retains legacy setup creation. Existing committed episodes continue their frozen lifecycle.
- Versioned immutable contracts prevent rewriting old episodes; rollback never deletes evidence.
- Verify `/api/research/setups` exposes the new version and `active_records`, and that old contracts remain identical after deployment.
- 150 backend tests and 23 frontend tests; production frontend build; undefined-name and diff checks.

Raw experiment reports, rejected alternatives, input hashes and trade rows accompany this document.
