# Sector momentum study (declared 26 September 2026, before running)

Question: when a sector or ecosystem has beaten BTC recently, does it keep beating BTC over the next 10 days? If yes, relative strength could become a ranking input (Best setups, priority). If not, the race chart and pockets stay descriptive.

## Data

- Coins: every coin in `backend/sectors.py` with a Binance USDT spot pair (k-prefixed Hyperliquid tickers map to the plain ticker, e.g. kPEPE to PEPEUSDT). BTC is the benchmark and is not in any group.
- Daily closes, 2021-01-01 to 2026-03-29 (walk-forward windows 1 to 9). The holdout window (W10) is not touched.
- Groups: the curated sector and ecosystem labels of today. A group counts on a day only when at least 3 of its members have prices that day.
- Known bias: the coin list is today's Hyperliquid universe, so coins that died before 2026 are missing (survivorship). This flatters every group about equally; it does not by itself create momentum, but results should be read as optimistic.

## Measures

For each day t and each group, the group's move is the median daily log return of its members, chained. Its relative move is that minus BTC's log return.

- Past strength: relative move over the L days to t, for L = 7 and L = 30.
- Outcome: relative move over the next 10 days (t to t+10).

Tests, each on non-overlapping 10-day steps (so every observation is independent in time), sectors and ecosystems separately:

1. Rank correlation (Spearman) across groups between past strength and outcome, averaged over steps; t-statistic of the mean.
2. Leader minus laggard: the outcome of the strongest group minus the weakest; mean, share positive, t-statistic.
3. Leader against BTC: the strongest group's outcome alone; mean and share positive.
4. Per window (1 to 9): the mean leader-minus-laggard spread, to see whether any effect is stable or one regime.

## Decision rule (fixed now)

Relative strength becomes a candidate ranking input only if, for at least one of L = 7 or 30, on sectors or ecosystems: the mean rank correlation is positive with t >= 2, the leader-minus-laggard spread is positive with t >= 2, and the spread is positive in at least 6 of the 9 windows. A candidate would still need a separate test inside the signal replay before it touches rankings. Otherwise the views remain descriptive, and the UI keeps saying so.
