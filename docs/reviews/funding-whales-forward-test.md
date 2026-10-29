# Forward test: funding and whales (declared 29 October 2026, before any forward day)

Approved by the owner on 29 October 2026 ("Go ahead please"), after the turn-signs study (docs/reviews/turn-signs-study.md) left two candidates:

- **Funding:** the 7-day mean of BTC and ETH funding went against the typical coin's next 30 days in 2025-26 (partial rank correlation -0.31 with the last month held fixed), and its highest readings came before weaker months 4 times in 5 in 2023-24; it did not hold in the first half.
- **Whales:** over the one year recorded, the whales' net position went with the typical coin's next 30 days (+0.34), the only wallet group that did not simply follow the last month. One year cannot be split, so it was never tested.

Every rule below is fixed now, before the first forward day. Nothing is changed after a result is seen. Until a bar is met the readings stay **context, not a signal**.

## Data (recorded by the production server)

- **Funding:** `funding_history.py` (Hyperliquid's BTC and ETH funding, summed per UTC day as a yearly rate; the 7-day mean of the two coins' average, at least 5 of the 7 days, as the Chart view's pane).
- **Whales:** `wallet_history.py`, the whales group's row at each daily close: net position = (wallets long - wallets short) / wallets in the group.
- **Outcomes:** `market_history.py`, the typical coin (median simple return of the coins other than BTC, at least 20, from the server's per-coin daily closes) and BTC's close.

## Forward days

Days from **30 October 2026** whose next 30 days have closed. A day missing its reading, its outcome or its last month is skipped.

## Tests

For each reading: the partial rank correlation (Spearman) between the reading and the typical coin's change over the next 30 days, with the typical coin's change over the last 30 days held fixed (ranks of the reading and of the outcome each cleared of the rank of the last month), with a 90% moving-block bootstrap interval (30-day blocks, 2,000 draws, fixed seed).

| Test | Reading | Bar (on the first 365 forward days) |
|---|---|---|
| Funding | BTC and ETH funding, 7-day mean | partial rho -0.15 or lower, interval entirely below 0 |
| Whales | Whales' net position | partial rho +0.15 or higher, interval entirely above 0 |

Reported, never deciding: the plain rank correlation; BTC's next 30 days (for whales, against the whales' net position in BTC); for funding, the forward days in the top and bottom 10% of the previous 365 days' 7-day means, their median outcome against every forward day's.

## Schedule

- The server computes the record each day and serves it at `/api/market-history/forward`; the Chart view shows its status under the chart.
- Under 180 forward days: **collecting**. From 180: **interim**, numbers shown, no verdict. At 365 forward days (about late November 2027): the **verdict**, on those 365 days only. The record keeps running afterwards, but the verdict stays the one taken at 365.

## Limits

- Overlapping 30-day windows: 365 forward days hold about 12 independent months, which the block interval accounts for only in part.
- One market path: a year that trends one way can carry either reading.
- The whales group is the recorded group as the server tracks it; its membership changes over time.
