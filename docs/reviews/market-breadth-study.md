# Market breadth history (declared 26 September 2026, before running)

Question: when a given share of the market is in Uptrend (the number behind the RISK-ON label), what did BTC and the typical alt do next? Is high breadth followed by continuation or by a pullback, compared with an ordinary day?

## Rebuild

- Coins: every coin in `backend/sectors.py` with a Binance USDT spot pair (the sector studies' list, about 155), plus BTC.
- Daily closes from 2019-01-01. At every closed daily candle the live engine (`compute_rcce`) runs on the trailing window, up to 600 candles as the scanner does; coins with fewer than 200 candles of history are left out that day.
- Per day: number of coins, count in each regime, share in Uptrend (breadth), share Overheated, median z-score. Fear & Greed from alternative.me (daily, from 2018).
- Known limits: today's coin list (survivorship: coins that died are missing, early years have fewer coins); Binance spot prices, not Hyperliquid perps; the live scanner universe differs slightly. The chart shows the coin count so early thin periods are visible.

## Test (windows 1-9 only: outcomes measured up to 2026-03-29; the holdout is not used)

Outcomes: BTC return and the typical alt's return (median of the coins' simple returns) over the next 10, 30 and 60 days, from the close of the reading day.

1. Breadth bands: under 25%, 25-40, 40-55, 55-70, 70-85, 85% and over. Per band: every day's outcome distribution (median, quartiles, share positive) against all days (the base rate).
2. Episodes: a run of consecutive days in the same band (gaps of up to 5 days merged) is one episode, outcome measured from its first day. Per band: the list of episodes with their outcomes. Episodes, not days, are the unit of evidence: neighbouring days share the same future.
3. Changes: a thrust (breadth up 25 points or more within 10 days) and a fade (breadth down 20 points or more within 10 days from above 70%): the same outcomes, per episode.

## Decision rule (fixed now)

- The product always shows the history and the episode list as they are, with the number of episodes.
- It states a direction ("historically followed by continuation" or "by a pullback") for a band only if that band has at least 6 episodes and at least 75% of them moved the same way against the base rate over 30 days (median alt, and BTC checked separately). Otherwise it says the record is mixed or too thin.
- No probabilities are shown.

## Results (run 26 September 2026; outcomes measured up to 2026-03-29)

151 coins rebuilt, 2,626 days; days with 40+ coins start 2021-05-01. Today (25 Sep 2026) the rebuilt breadth is 81% in Uptrend (the live scanner, on its own universe, shows 77%), higher than 75% of days since May 2021.

Base rate, all days: BTC 30 days later median +0.3% (up 51% of the time); the typical alt median -7.4% (up 34%). Alts drift down against a flat BTC on an ordinary 30 days, so "better than an ordinary day" is not the same as "up".

| Uptrend share | Days | Episodes | Typical alt, 30d median | BTC, 30d median | Episodes where alts beat the base | Rule |
|---|---:|---:|---:|---:|---:|---|
| under 25% | 749 | 16 | -6.7% | -0.2% | 6/16 | mixed |
| 25-40% | 197 | 24 | +3.8% | +6.3% | 11/24 | mixed |
| 40-55% | 199 | 20 | -7.8% | +2.9% | 8/20 | mixed |
| 55-70% | 133 | 22 | -20.3% | -6.0% | 7/22 | mixed |
| **70-85% (today)** | 205 | 18 | -9.1% | +1.8% | 9/18 | mixed |
| 85% and over | 311 | 9 | -8.1% | -1.0% | 7/9 | alts: meets the letter of the rule; BTC mixed |

Thrusts (breadth up 25 points in 10 days, 11 cases) and fades (down 20 from above 70%, 8 cases): no clear edge; fades were followed by weak alts (30d median -11.7%, 2 of 8 up) on 8 cases.

## Reading

- **Today's band has no direction.** In the 18 past episodes at 70-85% Uptrend, the typical alt beat an ordinary 30 days 9 times and BTC 10 times. This band preceded both the November 2021 top (typical alt -31% over 30 days) and the late-October 2024 rally (+65%).
- **85% and over technically meets the rule for alts (7 of 9), but it is fragile:** three of the nine episodes are 1-4 day fragments of one early-2023 stretch, and "beat the base" there often means falling less than usual (e.g. -5%). Recommendation: the product states the count ("in 7 of 9 past episodes above 85% the typical alt did better than an ordinary 30 days") rather than the word "continuation".
- **What the data does support showing:** where today sits in the history (percentile, the chart), and the list of past episodes at similar readings with what followed, unfiltered. No probabilities, no direction for the 70-85% band.

## In the product (26 September 2026)

The scanner's history drawer (chart icon beside Market consensus) shows this history: the share of coins in Uptrend with BTC, today's percentile, and the episode table for each band with the counts above. It never states a direction. The seed is `backend/data/market_history_seed.json` (`python -m backtest.breadth_history export`); one row is appended after each daily close with the same method (checked equal to the rebuild on 23-25 September). Episode outcomes stop at 2026-03-29; later episodes are listed without them.
