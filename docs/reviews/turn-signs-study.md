# Which readings come before the market turns? (declared 29 October 2026, before running)

Owner (29 October 2026): "run any test you think makes sense ... we have fear and greed, number of coins, Bitcoin positioning, smart traders, and we can probably test how those indicators intercorrelate with each other to give us some sort of signs ... if we can find any other possible angle, let's explore those angles."

A broad search finds things by chance: with 16 readings and several views of each, some will look good on any history. So the whole menu, the outcome, the split and the bar are fixed here before any outcome is computed, every reading is reported (not only the ones that pass), and a reading counts only if it holds in both halves of its history. Whatever passes is still description in sample and needs the forward check from 30 October 2026. Everything else: **context, not a signal**.

Code: `backend/research/turn_signs.py` (tests `backend/tests/test_turn_signs.py`); the new series come from `research/fetch_turn_data.py`. Run from `backend/`: `python -m research.turn_signs --rows ROWS --live LIVE --extra EXTRA --wallets WALLETS`.

## Data

- **The page's daily rows** (as in the late-uptrends and turning-points studies), 1 May 2021 to 27 October 2026: the share of coins in uptrend and in downtrend, the median z, BTC and its weekly band, Fear & Greed, Market heat; the typical coin (median coin, today's list) from `market_history.make_alt_ret`.
- **New public series**, fetched once on 29 October 2026 (`fetch_turn_data.py`):
  - funding: Hyperliquid's BTC and ETH funding, summed per day as a yearly rate, from 12 May 2023 (1,266 days each);
  - DVOL: Deribit's BTC implied volatility index (what options price for BTC's moves over the next 30 days), daily close from 1 April 2021 (2,037 days);
  - stablecoin supply: DefiLlama's total in USD, daily from November 2017 (3,256 days).
- **Wallet groups** (smart money, whales, their BTC positions, the profitable traders), one year from September and October 2025: described, not tested (one market cycle cannot be split in two).

## Known before running

- From the earlier studies: the profitable traders' share long tracks BTC's last 30 days (0.77) and not the next 30 (-0.05); the typical coin fell after 9 of 10 Cooling arrows; late, greedy broad uptrends came before the weakest months (3 runs); the median z turned down before every roll-over; extreme fear early in a downturn came before more falls (5 of 5). The share of coins in uptrend, Fear & Greed, Market heat and the median z have been seen on the page against BTC.
- Not computed before this declaration: any relation of DVOL, funding, stablecoin supply, the share in downtrend, BTC's distance over its band, the divergence reading or the 14-day changes to what followed.
- Coverage (`--shape`): every reading has 1,896 to 1,946 days with an outcome, except funding (1,231 days, from May 2023).

## The menu (each known at the day's close)

| Reading | Group |
|---|---|
| Share of coins in uptrend; its 14-day change | structure |
| Median z; its 14-day change | structure |
| Share of coins in downtrend | structure |
| Typical coin's change over the last 30 days (also the control below) | structure |
| BTC's change over the last 30 days | structure |
| BTC over its weekly band's lower edge (%) | structure |
| Divergence: BTC's place in its 90-day range (0 to 1) minus the share's place in its own | structure |
| Fear & Greed; its 14-day change; Market heat | sentiment |
| DVOL; its 14-day change | options |
| BTC and ETH funding, 7-day mean | leverage |
| Stablecoin supply, 30-day change (%) | liquidity |

**Outcome** (deciding): the typical coin's change over the next 30 days. Reported, never deciding: BTC's next 30 days and the share's change over 30 days.

## The checks

For each reading, its days with an outcome are split in two halves by date.

1. **Rank correlation** (Spearman) with the outcome in each half, with a 90% interval from a moving-block bootstrap (30-day blocks, 2,000 draws; neighbouring days share most of their future).
2. **Beyond the last month:** the same, as a partial rank correlation with the typical coin's last 30 days held fixed. Most of these readings follow the last month's prices; this asks whether one says anything the last month's move does not.
3. **Extremes:** the days in the first half's top and bottom 10% of the reading (cut points from the first half, applied to both): their median outcome against the half's median.
4. **How the readings move together** (description): the rank correlation of every pair on the same day.
5. **Turn profiles** (description): each reading's percentile against its whole history on the 11 roll-over days and the 8 turn-up days of the earlier studies, and 14 days before.
6. **Wallets, one year** (description): the rank correlation of each group's net position with the next and the last 30 days.

## Decision rule

- A reading **survives** if its rho has the same sign in both halves, at least 0.15 in size in each, with both 90% intervals excluding 0.
- It **adds beyond the last month** if its partial rho passes the same test.
- An **extreme** (top or bottom 10%) counts if its median outcome is at least 5 points from the half's median, in the same direction, in both halves.
- With 16 readings, requiring both halves keeps the chance of a pass by luck small (a reading with no relation passes about 1 time in 200 under these rules), but a pass in sample is still description; it becomes a candidate for a declared forward test from 30 October 2026, and nothing is shown as a signal before that test.

## Limits

- About two market cycles plus 2026, and funding only from May 2023: the halves are not independent cycles.
- Today's coin list (dead coins missing) and Binance spot closes for the typical coin.
- Correlations are about the typical day; a reading can matter only at its extremes (check 3) or only at turns (check 5).
- The new series are third-party public data as fetched once; the fetch date and counts are above.

## Result (run 29 October 2026, after the rules above were committed at ed3d70d)

`python -m research.turn_signs` on the page's rows to 27 October 2026 and the series fetched the same day. In sample: description.

### The everyday test: nothing survives

Rank correlation with the typical coin's next 30 days, first half / second half (split late January 2024; funding late January 2025). Bold: the half's 90% interval excludes 0.

| Reading | First half | Second half | With the last month held fixed | Survives |
|---|---:|---:|---|---|
| Share of coins in uptrend | -0.10 | 0.00 | -0.11 / 0.01 | no |
| Its 14-day change | +0.07 | +0.15 | +0.07 / **+0.19** | no |
| Median z | -0.08 | +0.07 | -0.11 / +0.11 | no |
| Its 14-day change | +0.03 | **+0.20** | +0.03 / **+0.23** | no |
| Share of coins in downtrend | -0.08 | +0.02 | -0.10 / +0.01 | no |
| Typical coin, last 30 days | +0.02 | -0.02 | — | no |
| BTC, last 30 days | +0.15 | +0.01 | **+0.26** / +0.06 | no |
| BTC over its weekly band | +0.01 | -0.13 | +0.01 / -0.14 | no |
| Divergence (BTC's range place minus the share's) | +0.18 | -0.18 | +0.18 / -0.18 | no (flips) |
| Fear & Greed | +0.05 | -0.09 | +0.05 / -0.10 | no |
| Its 14-day change | +0.10 | +0.12 | +0.10 / **+0.14** | no |
| Market heat | -0.10 | -0.04 | -0.15 / -0.04 | no |
| DVOL | -0.05 | -0.06 | -0.04 / -0.06 | no |
| Its 14-day change | **+0.22** | -0.04 | **+0.22** / -0.04 | no |
| BTC and ETH funding, 7-day mean | -0.11 | **-0.30** | -0.11 / **-0.31** | no |
| Stablecoin supply, 30-day change | -0.03 | -0.17 | -0.03 / -0.17 | no |

No reading has a stable everyday relation with the typical coin's next month in both halves, with or without the last month held fixed. Several held in one half and vanished or flipped in the other (BTC's last month, DVOL's change, the divergence). On BTC's next 30 days (reported) none survives either.

### Extremes: one passes

- **Stablecoin supply growing fast** (top 10%: 7.8% or more in 30 days): the typical coin's next 30 days were 12.5 points (first half) and 17.6 points (second half) under the half's median; BTC's too (reported). It rests on 6 episodes, each followed by a lower typical coin: May-June 2021 (median -28%), September 2021 (-2%), November 2021 to January 2022 (-20%), April 2024 (2 days, -24%), November-December 2024 (-20%), February 2025 (-28%). It has not recurred since February 2025.
- No other extreme passes in both halves. **Very high funding** (top 10%: 47% a year or more) came before a lower typical coin in 4 of 5 episodes in 2023-24 (the exception November 2023), but funding has not reached that level since, so the second half has no case; low funding (bottom 10%) was mixed.

### The share of coins in uptrend (reported outcome)

For what the share itself does next month, several readings survive in both halves, also with the last month held fixed: the median z's 14-day change (+0.38 / +0.50), funding (-0.48 / -0.39), Market heat (-0.47 / -0.39), the share's own level (-0.48 / -0.38, it comes back toward the middle), its 14-day change and Fear & Greed's (positive). The median z leads the share, as in the turning-points study; high funding came before coins leaving their uptrends. None of this carried over to prices in both halves.

### How the readings move together (same day)

- Two families. **BTC's:** Fear & Greed and BTC's distance over its band (0.90), BTC's last month (0.70 with Fear & Greed), funding (0.69 with Fear & Greed, 0.71 with the band). **The coins':** the share in uptrend and the median z (0.93), Market heat (0.87 with the share).
- Between the families the link is weak: the share in uptrend and Fear & Greed 0.20. The share of coins in uptrend is the only reading here that is not a version of BTC's trend.
- DVOL moves with almost nothing else (under 0.4 with every reading); stablecoin growth goes with Fear & Greed and the band (0.33) and funding (0.36).

### Before the turns (description)

- 14 days before the 11 roll-overs: the share in uptrend stood higher than on 80% of days, the median z 74%, Market heat 78%, stablecoin growth 79%; Fear & Greed only 57% and BTC's last month 48%. Ahead of roll-overs the coins and the stablecoin inflow were stretched, BTC and Fear & Greed were not.
- 14 days before the 8 turn-ups: the share 21%, the median z 26%, funding 16% (5 cases): little leverage. Fear & Greed 44%: not at an extreme.

### Wallets, one year (description, one cycle)

| Group | Next 30 days, typical coin / BTC | Last 30 days, typical coin / BTC |
|---|---|---|
| Smart money, net long | -0.05 / +0.06 | +0.44 / +0.44 |
| Smart money in BTC | +0.08 / +0.14 | +0.48 / +0.46 |
| Whales, net long | +0.34 / +0.38 | +0.37 / +0.32 |
| Whales in BTC | +0.23 / +0.34 | +0.28 / +0.28 |
| Profitable traders, share long | +0.03 / -0.03 | +0.83 / +0.81 |

The profitable traders and smart money follow the last month; whales are the only group whose position went with the next month in this year. One year (about 13 independent months) cannot be split, so this is a lead to watch, not a result.

### Reading (in sample; context, not a signal)

- No single reading, old or new, tells the typical coin's next month day to day. Most of them restate the last month's prices (Fear & Greed is mostly BTC against its trend; the traders follow price).
- What showed up is conditional: stablecoin supply surging (6 of 6 episodes followed by lower coins), very high funding (4 of 5, 2023-24), and from the earlier studies, greed late in a broad uptrend and fear two to three months into a downturn. These are rare states, so each rests on a handful of cases.
- For the coins' own breadth, the median z's change and funding say something both halves agree on: coins tended to leave their uptrends after funding was high and the median z had turned down.
- Candidates for a forward test from 30 October 2026, if the owner approves: stablecoin surges, funding at its extremes, and whales' net position.

### Stablecoins: they follow the market (owner's check, 29 October 2026)

Owner: stablecoins are now too big to move price and, like ETF inflows, "kind of follow whatever the market is doing". Checked on the same data (description):

| Rank correlation | 2021-05 to 2026-09 | 2021-05 to 2023-12 | 2024-01 to 2026-09 |
|---|---:|---:|---:|
| Stablecoin growth over the next 30 days vs BTC's last 30 days | +0.21 | +0.16 | +0.28 |
| Stablecoin growth over the last 30 days vs BTC's next 30 days | -0.07 | -0.09 | -0.08 |
| Stablecoin growth over the next 30 days vs the typical coin's last 30 days | +0.15 | +0.18 | +0.17 |
| Stablecoin growth over the last 30 days vs the typical coin's next 30 days | -0.14 | -0.12 | -0.16 |

- Supply grew after rallies and said nothing for BTC's next month: it follows. The six surges came at the end of big rallies, so they restate what greed and a long broad uptrend already say.
- Scale: 7.8% in 30 days was $6.6 billion in May 2021 and would be $23.5 billion now (supply $302 billion on 27 October 2026); supply stayed flat through 2026 ($305 billion in December 2025), including the 148-day broad uptrend from March. A fixed percentage does not mean the same thing across these years.
- Decision: stablecoin supply is dropped from the forward-test candidates and is not added to the chart. Funding and whales' net position remain candidates.

### Funding in the Chart view (added and removed, 29 October 2026)

A Funding pane (BTC and ETH on Hyperliquid, 7-day mean as a yearly rate, with a server feed) was added at the owner's request and removed the same day ("too generic, makes the indicator busier"). The research fetch (`research/fetch_turn_data.py`) and the numbers above stay.

### Forward test (approved by the owner, 29 October 2026)

A forward test of funding and the whales' net position was declared (docs/reviews/funding-whales-forward-test.md) and withdrawn by the owner the same day, before any forward day had an outcome: a year was too long to wait. Both remain context, not a signal.
