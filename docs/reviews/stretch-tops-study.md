# Stretch at tops: which scaling of the distance from the weekly band marks tops most cleanly (declared 7 November 2026, before running)

The owner's question (7 November 2026), after the band stretch indicator went on TradingView (`tradingview/reflex_band_stretch.pine`): "We need to basically identify a way to detect market stretching, basically bubble territory where price is much higher than ... its average ... if I go back in November 2021 at Ethereum peak, the Z-score were just 1.16. And that was the real peak ... I was wondering if we can probably tune it in a way that based on past price performance, we can identify those peaks more cleanly."

The question this study fixes: **at the same number of alarm days, does a different scaling of the distance from the weekly band catch more tops than the script's two-year scaling, without more of its alarms falling away from tops? And does a divergence mark (a new high, less stretched than an earlier stretched high) catch tops the scaling misses?**

This describes the past and runs outside the production server. Everything below is fixed before any reading at a top is computed, except the ETH and BTC readings listed under "Known before running", which is why those two coins are reported apart. Unless a result clears its bar, it reads **context, not a signal**. Nothing in the engine changes either way: a result that clears its bar changes the TradingView script only, and any use in the engine needs its own declared study.

Code: `backend/research/stretch_tops.py` (tests `backend/tests/test_stretch_tops.py`), run from `backend/`:

- `python -m research.stretch_tops check` (the data check and counts, no readings at tops)
- `python -m research.stretch_tops run` (the study)

## Data

- **Binance spot daily closes** for 40 USDT pairs, read through the repository's cached loader (`backtest/binance_history.py`, the public market-data mirror), from each pair's listing (17 August 2017 at the earliest) to the **31 October 2026 close**. A day missing from the feed takes the close before it.
- **Coins:** the 10 primary coins (BTC ETH SOL BNB XRP ADA AVAX DOGE DOT LINK) and the 30-coin secondary set of the earlier studies (top Binance quote volume before their first window, listed before February 2020; later-delisted or renamed coins kept): FTM MATIC FTT ATOM LTC ETC TRX EOS VET THETA ALGO OMG XTZ CHZ BCH ONE CELR IOTX KAVA DENT XLM BTT IOST HBAR IOTA FET NEO WIN HOT QTUM.
- **Left out by rule, fixed at the data check:** a coin with more than 30 filled days. FTT has 310 (no Binance trading from 15 November 2022 to 22 September 2023, after FTX failed); a flat stretch that long would distort its readings and the guides.
- **Data check** (`check`, run before this declaration): all 40 pairs have data; no missing day on any pair but FTT; delisted pairs end at their delisting (BTT January 2022, OMG June 2024, MATIC September 2024, FTM January 2025, EOS May 2025, DENT April 2026). SHA-256 of the 39 coins' closes used: `4eaec6a275653ae5c13e966b54253d78cad32e2d841fa24af7a3a29c6f6acdab`.

## Known before running

- **ETH and BTC readings were seen** (7 November 2026, before this declaration): the band distance and the script's band z (scaling A) at their tops on Binance closes since 2017 and on Hyperliquid closes since 2022, and the engine's z on Hyperliquid closes since 2023. Among them: ETH 8 November 2021 +45% from the band, band z +1.15 (+111% and +2.28 at the May 2021 top); BTC 8 November 2021 +37%, +1.17; BTC 6 October 2025 +11%, +0.62; the two-year usual distance 31-39% in 2021 against 16-25% in 2024-25. Scalings B and C and the mark D were not computed on any coin.
- **Where the candidates come from.** B and C answer the swollen two-year scale seen in 2021; D answers the less stretched second tops seen on ETH and BTC (November 2021 twice, October 2025). Both ideas come from those two coins, so ETH and BTC are in neither half and are reported apart.
- **Counts** (`check`, no readings): tops counted for hits **94 on the calibration coins, 99 on the test coins**, 11 on ETH and BTC (BTC 26 June 2019, 13 April 2021, 8 November 2021, 6 October 2025; ETH 26 June 2019, 14 February 2020, 11 May 2021, 8 November 2021, 11 March 2024, 8 December 2024, 22 August 2025). Evaluation days: 39,860 calibration, 40,520 test, 5,718 ETH and BTC.

## Definitions

- **The band**, as the scanner's heatmap engine and the TradingView script: the 20-week SMA and the 21-week EMA of weekly closes, the week under way counted at the day's close, weeks starting Thursday 00:00 UTC (as Hyperliquid's); the EMA seeded with the SMA of its first 21 weeks. Its **mid** is their average.
- **Stretch** on a day: the log of the close over the band mid (0 on the band).
- **The scalings** (each from data up to that day only):
  - **A:** stretch divided by the root mean square of the stretch over the last 730 days (all of it while there is less). The script as it is.
  - **B:** stretch divided by the root mean square of the stretch over the coin's whole history so far.
  - **C:** stretch divided by the standard deviation of daily log returns over the last 730 days (all of them while there are fewer).
  - **E**, reported only: the engine's z today (`_calc_zscore_hybrid`, daily closes).
- **Evaluation days:** from the first day with 365 days of stretch and 365 daily returns (A, B and C all defined) to the last close.
- **Guide:** for each scaling, the 95th percentile of its values over all the calibration coins' evaluation days, pooled. An **alarm day** is a day at or above the guide. So each scaling alarms on about 5% of calibration days, and they are compared at about the same number of alarm days.
- **The divergence mark D** on a scaling X, on day t: the close is the highest of the last 365 days (t included); some day 30 to 365 days back had X at or above X's guide; X today is above 0 and under the highest X of those days. "X with D" alarms on X's alarm days and D's days.
- **A top:** a day whose close is the highest of the 180 days before it (itself included, with 180 days of data before it), after which the close falls 40% or more within 365 days before any close at or above it (a later equal close takes the top over, so each fall has one top). A top is **counted** for hits when its hit window lies in the evaluation days.
- **Caught:** a counted top with an alarm on the top day or in the 14 days before it. **Hit rate:** caught tops over counted tops, pooled over the coins of a half.
- **Episodes:** alarm days with up to 7 days between them form one episode. An episode is **at a top** when any top (counted or not) falls from its first day to 14 days after its last. Only episodes ending at least 379 days (14 + 365) before the last close count, so any top after them has had its year to be confirmed. **Precision:** episodes at a top over episodes counted, pooled.
- **Chance**, reported only: each coin's alarm days shifted in time at random within its evaluation days (200 shifts per coin, seed 20261107); the mean number of tops the shifted alarms catch.

## The split

The 38 coins other than ETH and BTC, in alphabetical order, alternately: **calibration** ADA ATOM BCH BTT CHZ DOGE EOS FET (FTT, left out) HOT IOTA KAVA LTC NEO ONE SOL TRX WIN XRP; **test** ALGO AVAX BNB CELR DENT DOT ETC FTM HBAR IOST IOTX LINK MATIC OMG QTUM THETA VET XLM XTZ. The guides are set on the calibration coins; the verdicts are read on the test coins.

## The bars (read on the test coins)

**Question 1, the scaling.** B, or C, replaces A in the script when all four hold against A:
1. at least 25 counted tops;
2. a hit rate at least 10 points above A's;
3. a precision no more than 5 points under A's;
4. no more than 1.25 times A's alarm days (the guides are set on the calibration coins, so on the test coins the scalings can alarm on different numbers of days; a scaling must not win by alarming more).

If both pass, the one with the higher hit rate; a tie, B. If neither passes, the script keeps A.

**Question 2, the divergence mark**, on the scaling question 1 leaves in the script (call it X). D is added to the script when "X with D", against X alone:
1. at least 25 counted tops;
2. a hit rate at least 10 points higher;
3. a precision no more than 5 points lower;
4. no more than 1.5 times X's alarm days.

Otherwise: context, not a signal, and the script stays as it is.

## Reported, not decided on

- Every scaling, with and without D, on both halves: tops, hits, hit rate, episodes, precision, alarm days and share, chance.
- The engine's z (E) the same way, at its own guide.
- ETH and BTC apart: each counted top with each reading's highest value in its hit window.
- What share of calibration days the script's current guide line (+2) marks, against the 95th-percentile guide.

## Limits

- Out of sample by coin, not by time: the halves share the market's cycles (2018, 2021, 2024-25 tops fall on many coins at once), so the test coins are not independent of the calibration coins.
- The rule for a top (180 days, 40% within a year), the hit window (14 days), the episode gap (7 days), the 95th-percentile guide and the bars are choices fixed now without data; other choices could rank the scalings differently.
- Binance spot closes, not Hyperliquid perps; weeks start Thursday as on Hyperliquid, not Monday as on Binance.
- A top is known only afterwards. The study asks which reading stood out before tops, not whether a top can be called at the time.
- Coins chosen by volume before 2020 include later failures and leave out later listings.
