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
