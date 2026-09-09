# Executor performance and interface review — 9 September 2026

## Observed production data

The read-only executor snapshot contained 776 closed trades, 98 open positions,
and history from 11 March (182 days). The old 1.4% win rate is 11 profitable closed
trades / 776 closed trades. There are 728 losing and 37 exactly flat records.
442 exits are labelled BE_STOP: the label describes the trigger, not a guarantee
of zero realized loss. Stops execute at observed prices and can finish negative.

The old -4.05% headline divides $-1,385.90 recorded closed P&L by $34,245.48
cumulative traded capital. It is not a portfolio return. The old equity field
falls back to the $10,000 starting balance because PaperEngine.get_portfolio()
returns cash/holdings, not current_value.

A matching daily scanner snapshot valued 86 positions at approximately
$+1,561.96 unrealized. This is partial, not total portfolio performance. Twelve
positions need matching prices or reconciliation. Legacy XMR/BTC and ETH/BTC
records use problematic quote units, and MKR has a recorded peak exceeding two
million percent. These are flagged for review, not rewritten or automatically
counted as enormous gains.

Paper cash differs from starting balance + realized P&L - tracked open cost by
$454.54. HYPE/USDT is tracked but absent from PaperEngine.holdings; its recorded
entry cost is approximately $454.55. Resolving historical accounting requires
reconciling the original state, not deleting the position or resetting history.
No trading settings, historical orders, balances, or positions were changed.

## Implemented presentation

- Separate realized, unrealized, combined ledger P&L and closed-trade win rate.
- Withhold combined return when marks are incomplete. Use starting capital as
  return denominator, not turnover. Estimated equity also requires reconciled cash.
- Use cached matching market prices with six-hour freshness cutoff; no additional
  exchange requests. Display unpriced cost, per-position reasons, and a review filter.
- Preserve cache observation times across restart for honest price freshness.
- Show realized-only historical curve and monthly totals; do not invent a
  historical mark-to-market equity curve from closed trades.
- Collapse engine controls, trading universe and entry rationale. Sort open
  positions by dollar unrealized P&L; paginate closed trades, showing close dates.
- Condense notifications by category/market, position risk first and critical
  anomalies before setups. Show six groups initially and retain full detail.
- Remove on-chain UI/navigation/shared-worker polling and scheduled whale polling.
  Retain backend library/API compatibility, including code used by the HL bridge.

## Selected PR #119 changes

Retained dead assistant context/prompt removal, bounded LRU session retention,
unused landing demo modules/import removal, quieter landing typography and
button corners, and removal of forced capsule corners in the terminal. Fixed a
leftover @staticmethod in that branch which breaks _detect_symbol after removal
of its original method. Also removed decorative landing/scanner dots and the
flashing bell indicator.

Did not import the problematic rate limiter, scheduler signature changes,
HyperLens idle behavior, or unrelated stream changes. PR #119 remains unmerged.
