# Do the coins whales are long in beat the other coins the next week? (declared 17 November 2026, before any position was read)

Owner's go-ahead (17 November 2026): "Go for it" to a count of how far back Hyperliquid's records reach, then "Sure" to declaring this study and starting the reads.

Everything below is fixed before the positions are read. The counts (`shape`) and the test of the bars on made-up returns (`power`) are added before the run, and the results after it. Nothing in the app changes. Until a row meets its bar and the held-out months confirm it, whales by coin stay **context, not a signal**.

Code: `backend/research/whale_coins.py` (tests `backend/tests/test_whale_coins.py`). Run from `backend/`: `python -m research.whale_coins census | funding | candles | shape | power | run`. The reads are kept in `backend/data/whale_coins_cache/` (not in the repo). They run outside the production server and cost nothing.

## Why

- Every rule tested so far used data any chart has (price, volume, levels) and none met its bar. The wallets are the one thing this app has that a chart does not.
- The turn-signs study left one lead: over the one year recorded, the whales' net position went with the typical coin's next 30 days (+0.34). The owner dropped its forward test because it meant waiting a year.
- **That market-wide question cannot be settled with the history that exists** (counted on 17 November, below). One reading a day that barely moves from week to week gives too few independent cases.
- **Per coin it can.** Each day has dozens of coins, each with its own reading and its own next week.

## What was counted before declaring (17 November 2026; no price and no return was read)

- **A record without a cut-off.** Hyperliquid's `userFunding` gives, for any wallet, one row per coin per day back to the wallet's first day: the day's mean position size and how many funded hours it rests on (hourly rows for the wallet's last 8 days or so). The wallet-history rebuild reads fills, which stop at a wallet's latest 10,000.
- **It matches the fills.** On 17 wallet-days without a trade in the coin, the row's size was the position before the wallet's next fill in 14. The other 3 were one wallet that also trades with timed orders, which the check did not read.
- **Today's leaderboard keeps wallets that fell.** 48,116 wallets; 29,215 did not trade this month; half hold under $400; 749 lost $1M or more and now hold under $100K.
- **Whales by month** (from a sample of 1,067 wallets; $1M+ of perp equity): none before May 2024, about 40 in August 2024, 80 in November 2024, 130 in December 2024, 200 in March 2025, 310 in June 2025, 390 in August 2025, 260 now. About 9 in 10 whale-months have a position on record. From November 2024, 23 to 43 coins a month had 5 or more whales holding them.
- **The market-wide question on made-up data** (a reading as slow as the stored whales series, a 30-day outcome, the turn-signs test): with no relation at all, one year gives anything from -0.39 to +0.44, and the test passes 1 time in 9. With a true relation of 0.34 it passes about half the time on 600 days and 7 times in 10 on 1,000.
- **The per-coin question on made-up data** (30 coins a week, 100 weeks): a rank correlation of 0.05 shows 84 times in 100, 0.03 shows 44 times, none shows 4 times.

## Data

- **Wallets read.** Today's leaderboard (17 November 2026), without market makers (month volume over 100 times the account value, as the live registry): every wallet with **$100M or more traded all-time, or $500K or more made or lost all-time**. 8,800 wallets, all read.
  - Not today's balance. A wallet that is large today because its past positions paid would be read, and its twin that lost would not. Volume, or the size of the result whatever its sign, lets both in alike.
- **Whale on a day.** The wallet's latest perp-equity point at or before the day's close (00:00 UTC of the next day) is $1M or more and at most 21 days old. Points come from Hyperliquid's `portfolio` (7 to 14 days apart, about daily in the last month).
  - The latest point, not a line to the next one. The next point is not known at the close, and it is higher for the wallets whose positions went on to pay. The wallet-history rebuild draws that line; a study of what followed cannot.
- **Positions.** Each whale's `userFunding` rows between its first and last day as a whale. A wallet **holds** a coin on a day when its row rests on 12 or more of the day's 24 funded hours and its mean size is not zero; long or short by the sign.
  - Builder-dex markets are left out. A wallet holding more than 25 markets on a day (builder-dex ones counted) is left out that day, as the live rule does.
  - A wallet read to the cap of 80 pages counts up to the day before its last row.
- **Prices.** Hyperliquid's daily candles of the coins held. A day's close is at 00:00 UTC of the next day.

## The two readings (each known at the day's close)

- **Level:** whales long the coin minus whales short it, over whales holding it (-1 to +1). A coin has a level with 5 or more whales holding it.
- **Change:** the level minus the level 7 days before (both needed).

## What is measured

- **The next week:** the coin's close 7 days later over the day's close, less 1. **The last week:** the day's close over the close 7 days before, less 1.
- **A day counts** with 15 or more coins that have the reading and both returns.
- **The day's rank correlation:** across those coins, between the reading and the next week (Spearman, ties sharing their rank). Ranks within the day, so it asks which coins did better than the others, not whether the market rose.
- **Beyond the last week's price:** the same with the last week's return held fixed (partial rank correlation). Whales may simply sit in the coins that just rose.
- **The trade:** every 7 days from the period's first day, long the third of the coins with the highest reading, short the third with the lowest (ties by name), equal weights, held 7 days. Net of 0.40%: 0.20% a round trip on each of its two legs, as if every coin were replaced every week. Funding is not counted.
- **Intervals:** 90%, from a moving-block bootstrap of the daily values in runs of 28 days (the weekly values in runs of 4), 2,000 draws, fixed seed. Neighbouring days share most of their next week.

## Periods

- **In sample:** reading days 1 December 2024 to 31 May 2026.
- **Held out:** 1 June 2026 to 8 November 2026 (the last reading day whose week had closed when the reads began). Run only after the in-sample result is written down.

## Rows and bars

| Row | Claim | Bar, in sample |
|---|---|---|
| **R1** | Coins with a higher **level** did better the next week | 300 or more days; mean daily rank correlation +0.03 or more; its interval above 0; above 0 in each half; beyond the last week's price, the interval still above 0 |
| **R2** | Coins whose level **rose** over the week did better the next week | the same |
| **T1** | The trade on the level pays | 50 or more weeks; mean net return above 0; its interval above 0; above 0 in each half |
| **T2** | The trade on the change pays | the same |

- **Confirmed** when a row that met its bar also holds on the held-out months: the mean rank correlation above 0, with and without the last week held fixed (R rows); the mean net return above 0 (T rows).
- A row that does not meet its bar gets no verdict, whatever the held-out months show. The other direction (whales' coins doing worse) is reported and would need its own declared test.
- If a row is confirmed, it is a proposal to the owner. Nothing is shown as a signal without the owner's approval.

## Reported, never deciding

- Each row by half and by quarter; the top third and the bottom third against the day's middle coin.
- The rank correlation measured from the next day's close (a day's delay).
- The level in dollars held instead of wallets.
- How much each reading follows the last week's return.

## Known before running

- From the turn-signs study: market-wide, the whales' net position went with the typical coin's next 30 days over one year (+0.34), and with its last 30 days (+0.37). The profitable traders' share long follows the last month's prices (0.83).
- Never computed: any per-coin relation between any wallet group's positions and what the coin did next against the other coins.
- The count above read positions only to check that the record exists and matches the fills. No price was read.
- My expectation, stated before running: both rank correlations within 0.02 of zero. The level may lean negative, because some whale shorts are hedges of coins held on spot, which are not a view on price.

## Limits

- **Hedges count as shorts.** A short covered by the same coin held on spot or staked is a funding trade, not a bet. The live counts take those out; the past spot holdings are not on record.
- **Equity is known every 7 to 14 days** before the last month, so a wallet can pass $1M up to two weeks before it counts, and count for up to two weeks after it fell.
- **Today's leaderboard.** A wallet that never traded $100M and never made or lost $500K is not read, even if it once held $1M. Today's market-maker flag decides who is a market maker throughout.
- **Coins with fewer than 5 whales have no reading.** The result is about the 25 to 45 coins whales hold most, mostly the larger ones.
- **Two years, one exchange.** December 2024 to November 2026 holds one long rally and one long fall.
- **The day's mean position**, not the position at the close. A wallet that reversed during the day reads by the side it held longer.

## Shape and power

To be added before the run.

## Result

To be added after the run.
