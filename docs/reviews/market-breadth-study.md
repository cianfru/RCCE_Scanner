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
