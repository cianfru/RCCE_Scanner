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

The initial matching daily scanner snapshot valued 86 positions at approximately
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
  exchange requests in the initial implementation. The audit below adds a bounded reference-quote fallback. Display unpriced cost, per-position reasons, and a review filter.
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


## Follow-up audit: price units and recovered marks (September 9)

The recorded closed P&L is −$1,385.90. Recomputing all 776 closures from
entry, exit, volume and side agrees within $0.002. However, five closures mix
prices per 1,000 tokens at entry with prices per single token at exit. Native
Hyperliquid daily candles confirm both sides of each unit mismatch:

| Market | Entry / exit UTC date | Entry price | Recorded exit | Native entry daily range | Native exit daily range |
|---|---|---:|---:|---|---|
| FLOKI | Apr 16 / Apr 17 | .030687 | .00003153 | .028848–.032711 | .030801–.033332 |
| PEPE | May 1 / May 14 | .003951 | .00000410 | .003874–.004028 | .004000–.004217 |
| BONK | Apr 30 / May 14 | .006247 | .00000691 | .006083–.006301 | .006712–.007099 |
| FLOKI | Aug 15 / Aug 20 | .020442 | .00002317 | .020279–.020708 | .021493–.023627 |
| PEPE | Aug 15 / Aug 20 | .002645 | .00000315 | .002615–.002673 | .002878–.003272 |

Source: POST https://api.hyperliquid.xyz/info with type `candleSnapshot`,
interval `1d`, coins `kFLOKI`, `kPEPE`, `kBONK`, covering March 11–September 9,
2026. Multiply each recorded exit by 1,000 to compare with its native range.
Exact symbol, entry/exit timestamps and prices identify these records in
`executor_ledger_audit.py`; a generic large-loss rule would hide real losses.

These five records contribute −$393.98. The remaining closed-trade subtotal is
−$991.93. This is an incomplete subset, **not a corrected strategy return**.
Correct prices could have prevented those exits and changed subsequent trades.
No orders, cash, positions or history were rewritten. The UI preserves recorded
figures, flags the five closures and withholds a complete combined return.

All 442 BE_STOP exits total only −$91.15. They close at the first scanned price
at/below entry after the break-even threshold is armed, not a guaranteed entry
fill. STOP_LOSS exits total −$1,651.56 including the five malformed records.

Large percentage gains use different entry allocations: approximately HYPE
$454.55 at +144% = +$655; ZEC $39.06 at +206% = +$81; PUMP $58.59 at +165% =
+$97. Dollar contribution is shown next to each position's percentage gain.

Recovered eight of the twelve missing marks:
- MOG, ZEREBRO, TON, MANA, VINE: explicitly mapped Kraken USD spot bid/ask midpoint.
- CHILLGUY: Bybit USDT spot bid/ask midpoint, with response-time validation.
- BONK and FLOKI: matching native k-contract scanner prices divided by 1,000,
  restricted to the exact open entries whose token units were verified against
  native daily candles. This does not repair erroneous historical peak values.

Reference quotes require positive two-sided prices and 24-hour volume with a
spread no wider than 10%. Two bounded requests are cached for 15 minutes,
including failures. They only value legacy positions; they never feed signals
or order execution. Existing scanner marks retain the six-hour observation cutoff.
Each position displays its mark source and observation time. USD and USD-pegged
quote currencies are treated as equivalent for these estimates; midpoint marks
are reference valuations, not guaranteed liquidation proceeds.

The reviewed snapshot values 94/98 positions at approximately +$1,713.80
unrealized, with 71 in profit. Four remain unresolved: XMR/BTC and ETH/BTC quote
history, MKR entry units, and YZY. Hyperliquid marks for delisted markets can be
frozen; YZY's Gate futures response had zero bid, ask, volume and open interest,
so its last price was rejected. No fabricated quote fills these gaps.

Primary quote sources: https://api.kraken.com/0/public/Ticker and
https://api.bybit.com/v5/market/tickers (spot category, CHILLGUYUSDT).


## Included-trade view (requested after the audit)

Exclude the five verified bad closures and all currently unpriceable open
positions from the displayed performance sample. Apply the same sample to
realized totals, unrealized totals, combined P&L, win rate, profit factor,
monthly results, curve and position/trade lists. Keep valid losses. At the
reviewed snapshot this is 771 closed trades and 94 open positions: −$991.93
realized, +$1,713.80 unrealized, +$721.88 combined.

A single scope note states the excluded counts. Do not display the excluded
records or their warnings in the main view. Preserve source records for the
executor and keep cash reconciliation against the original ledger; its
accounting note is under expandable details. Do not report account equity or
starting-capital return for this incomplete sample. Open mark eligibility is
re-evaluated with each status response, independently of whether P&L is positive
or negative. An older backend cannot be mislabeled as the included-trade view.
