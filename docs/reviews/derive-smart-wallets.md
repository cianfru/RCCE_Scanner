# Derive's Smart options wallets around market turns (exploration, 28 October 2026)

The owner noticed that on Derive, "when big smart wallets start to go short or start buying puts" is when the market rolled over, and asked to see it next to the market history page. This note covers the market history page's Derive drawer (`/market`, "Derive options") and the exploration behind it. **Exploration, not a study: context, not a signal.** Nothing here was declared before the numbers were seen.

Code: `backend/backtest/derive_smart_series.py` (build the daily series from Cowboy's data, then the seed), `backend/seeds/derive_smart_seed.json`, `backend/derive_wallets.py` (`/api/market-history/derive`), `frontend/src/components/DeriveDrawer.jsx`, `frontend/src/utils/deriveWallets.js`.

## Data

- **Source.** Cowboy's records of every Derive options trade since 1 December 2023 (`cianfru/derive_scan`, `data` branch: `history/days`, one file per finished UTC day, per wallet and instrument), read with Cowboy's own code (`derive.history`, `derive.wallet_alias`, `derive.balance_history.Replay`), so wallets, classes and tiers match its app. 1,062 days to 27 October 2026, none missing.
- **Smart wallets.** Cowboy's Smart cohort: profitable directional options wallets (market makers, income sellers, hedgers and occasional wallets left out), ranked by options PnL. Today it is the top tier, 483 wallets.
- **Two rankings.**
  - *Ranked at the time* (point in time): classes and tiers recomputed at every close from the trades up to it (`Replay`, as Cowboy's balance backfill does). A day's new puts use the cohort of the close before.
  - *Today's, looking back* (hindsight): today's 483 wallets, each in its past.
- **Open book.** Each wallet's positions are the running sum of its buys minus sells since December 2023, held to expiry, re-valued at each 00:00 UTC close with Black-76 at the close price and the last traded implied volatility (21 days for the instrument, else 7 days near the money). A wallet counts **net long** or **net short** of a coin from $1,000 of open delta, as Cowboy counts; all coins together sum a wallet's delta over its coins.
- **New puts.** Premium on net new long puts: a wallet's long put position growing that day, times its average buy price that day. Buying back sold puts is left out. Summed per week (from Monday) in the drawer.
- **Price.** Derive's daily index close from 31 October 2024; before, the next day's 08:00 UTC settlement, then the day's average index (median gap to the candle close 0.5-0.8%).
- **Tops** (dashed lines): the highest close within 30 days either side, followed by a fall of 15% or more within 90 days. Found with the closes after them: they mark where tops were. Ten for BTC: 13 Mar 2024, 4 Jun 2024, 28 Jul 2024, 17 Dec 2024, 21 Jan 2025, 13 Aug 2025, 6 Oct 2025, 14 Jan 2026, 16 Mar 2026, 10 May 2026.
- **Checks** (run with the build): today's Smart open contracts match Cowboy's `history/positions.json` on all 763 instruments; the point-in-time book reproduces `history/balance.json`'s modelled closes.

## What the exploration showed

The pattern the owner saw appears mostly with hindsight.

- **6 October 2025 (BTC's high, before a fall of 30%+).** Today's Smart wallets, looking back: 14 net long and 24 net short on BTC options (20 and 23 a month before). The Smart wallets as ranked at the time: 24 long and 17 short (27 and 11 a month before), and 26 long and 9 short at the 22 November low.
- **Puts.** In the week of 22 December 2025 today's Smart wallets opened $2.29M of new puts; the wallets ranked Smart at the time, $12K. The large week came from a wallet that ranked Smart only later.
- **Nine BTC tops with 16 weeks of history before them** (BTC options; the 4 weeks before each top against the 12 weeks before that; share of all days from April 2024 to September 2026 in brackets):

| Before the top | Today's Smart wallets | Ranked at the time |
|---|---|---|
| sold delta (net) in the 4 weeks | 7 of 9 (44% of days) | 2 of 9 (31%) |
| more net-short than net-long wallets than 4 weeks earlier | 6 of 9 (45%) | 2 of 9 (44%) |
| put premium three times the earlier weekly average | 3 of 9 (22%) | 2 of 9 (20%) |

Why: today's ranking is on all trades so far, including the falls these wallets caught, so the wallets that were short before a fall rank high now. Ranked as they stood at the time, the Smart wallets were short before a top about as often as on any day, and their put buying mostly came after the turn. Nine tops are far too few to read either way.

Two more cautions: dollar flows are concentrated (the largest wallet makes 29-89% of each half-year's Smart BTC delta), so the drawer counts wallets, not dollars; and in 2026 one wallet's deep in-the-money calls move the dollar book by tens of millions when a leg expires.

## Updating

The drawer reads only the seed; nothing in Reflex reads Derive or Cowboy at run time, so it ends on the seed's last day (shown in the drawer). To extend it: a sparse copy of Cowboy's `data` branch (`history/`, `candles/`, about 40 MB), then from `backend/`:

```
python -m backtest.derive_smart_series build DATA_DIR series.json --derive-scan /path/to/derive_scan/backend
python -m backtest.derive_smart_series seed series.json
```

A daily update would need Cowboy to publish the compact series with its app files (about 170 bytes a day), which changes Cowboy's feed; Cowboy's public files today carry only the Smart balance for the last 30 closes. Derive data in Reflex goes against Cowboy's rule of 1 October 2026 ("Do not change the Reflex repo for Derive work"); the owner asked for it here on 28 October 2026.
