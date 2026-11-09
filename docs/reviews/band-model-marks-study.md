# Band model marks: do they point the right way more often than ordinary days? (declared 9 November 2026, before running)

The owner's words (9 November 2026), after inspecting `tradingview/reflex_band_model.pine` on TradingView: "divergences are the things that I would say hit the price better ... on the 3rd of June on Ethereum, I got a divergence, which was pretty much the bottom of it or very close to it ... What I have is a lot of selling or buying that are a little bit of not really giving a great signals, especially lately ... if I look at it in March 24, it pretty much spotted the maximum pain. So I don't think a buy and sell signals are something that we should probably show ... they can be misleading ... we probably need to measure that, but how many times those signals indicated a good entry point ... I think we need to test it first." And on the blue up mark that fires below the band: "We should have it only if it's above the band."

The question this study fixes: **for each mark the band model draws, on its default settings and daily candles, is the close 90 days after the mark on the side the mark points to (higher after a buy mark, lower after a sell mark) more often than after ordinary days on the same coins, by a clear margin and in every part of the data?**

This describes the past and runs outside the production server. Everything below is fixed before any outcome after a mark is computed; what was seen before is listed under "Known before running". Unless a mark clears its bar, it reads **context, not a signal**. The result decides only what the TradingView script shows by default. The engine and the app do not change either way; any use in the engine needs its own declared study.

Code: `backend/research/band_marks.py` (tests `backend/tests/test_band_marks.py`), run from `backend/`:

- `python -m research.band_marks check` (the data check and counts, no outcomes)
- `python -m research.band_marks run` (the study)

## Data

- **Binance spot daily candles** (high, low, close) for the 40 USDT pairs of the stretch-at-tops study, read through the repository's cached loader (`backtest/binance_history.py`), from each pair's listing (17 August 2017 at the earliest) to the **31 October 2026 close**. A day missing from the feed takes the close before it as its high, low and close.
- **Left out by the same rule as before:** a coin with more than 30 filled days (FTT, 310). No other pair has a filled day.
- **Data check** (`check`, run before this declaration): 39 coins used. SHA-256 of their days, highs, lows and closes: `16cff00c39636e9daf827970dbebdc03304207f796074c98566dc613b806aeed`.

## Known before running

- **ETH, BTC and SOL were seen.** On 9 November 2026 their marks were listed with dates and closes from a copy of the script (no outcomes computed), ETH and BTC were shown as preview charts, and the owner inspected the script on TradingView: ETH by name (the 3 June 2026 bottom divergence near the low; marks near the March 2024 top) and an impression that buy and sell marks were weak "especially lately". The three are reported apart. Which other coins the owner looked at on TradingView is not known (see Limits).
- The ETH Reclaim dates (12 August 2022, 10 May 2025) were seen while checking this code against the earlier copy.
- **The settings** are the script's defaults, chosen on 8 and 9 November as starting points to inspect, without measuring what followed any mark. The 1.6 stretch line is the stretch-at-tops guide: the 95th percentile of the one-sided band z on that study's calibration coins, a level of the reading, not of what came after it. The Reclaim (60 days) was set on 9 November, before the counts below.
- **Counts** (`check`, no outcomes): marks counted (on evaluation days, with 90 days after them):

| | Buy | Take profit | Capitulation turn | Reclaim | Top divergence | Bottom divergence | Lost the band |
|---|---:|---:|---:|---:|---:|---:|---:|
| 36 unseen coins | 878 | 224 | 91 | 19 | 47 | 95 | 494 |
| ETH, BTC, SOL | 80 | 21 | 13 | 4 | 17 | 8 | 39 |

  Counted days: 38,882 on the calibration half, 41,378 on the test half, 7,634 on ETH, BTC and SOL. With 19 marks the Reclaim cannot meet the bar of 30: it is reported, and stays hidden.

## Definitions

- **The script's rules**, as written in the header of `tradingview/reflex_band_model.pine`, on daily candles (one bar a day), at its default settings: entry zone -0.3 to +0.8, stretched at 1.6 either side, fast at speed 2.0, band rising over 28 days, turns 0.5 within 10 days, second leg 1.2 within 60 days, marks of a kind 30 days apart, speed over 20 days against a year's volatility, usual distance over 730 days, Reclaim within 60 days of Capitulating. `band_marks.model` follows the script bar by bar; a test checks it against a plain rewrite of the rules.
- **The marks run over each coin's whole history**, as on a chart: the 30-day gaps and the Buy's once-per-visit rule start from the first candle.
- **Evaluation days:** from the first day with the location, the speed and a year of closes all defined, to the last close. A mark is **counted** when it falls on an evaluation day with 90 days after it (marks to 2 August 2026).
- **The marks judged**, and which way each points:
  - buy marks, right way = the close 90 days later **above** the mark's close: **Buy**, **Capitulation turn**, **Reclaim**, **Bottom divergence**;
  - sell marks, right way = the close 90 days later **below** it: **Take profit** (the one orange mark: Exhausting or second leg), **Top divergence**, **Lost the band**.
- **Right-way rate:** the share of counted marks that went the right way, pooled over the coins.
- **Chance:** the right-way rate of the same coins' counted days in the same era, each coin and era weighted by its marks there. It is what the marks would score if each coin's marks fell on random days of that coin and era. **Chance's median:** the median 90-day return of those days under the same weights.
- **Eras:** marks before 1 January 2022, and from 1 January 2022 (the owner's "lately").
- **Halves:** the stretch-at-tops split with SOL taken out: calibration ADA ATOM BCH BTT CHZ DOGE EOS FET HOT IOTA KAVA LTC NEO ONE TRX WIN XRP (17); test ALGO AVAX BNB CELR DENT DOT ETC FTM HBAR IOST IOTX LINK MATIC OMG QTUM THETA VET XLM XTZ (19). No setting is tuned in this study, so both halves count towards the verdict.

## The bar (read on the 36 unseen coins pooled)

A mark is shown by default when all four hold:

1. at least 30 counted marks;
2. a right-way rate at least **10 points above chance**;
3. the median 90-day return after the marks on the mark's side of chance's median (above it for a buy mark, below it for a sell mark);
4. in **each of the four parts** (calibration half, test half, before 2022, from 2022): at least 5 marks and a right-way rate above that part's chance.

## The decision, fixed now

- **A mark that clears the bar** is shown by default in the script, with what it scored in the header.
- **A mark that does not** is hidden by default, behind the switch now called "Show untested marks" (renamed "Show marks that did not pass the test"). This includes the two **divergences**, shown today: if one fails, it moves behind the switch with the others.
- Take profit is judged as the one orange mark; its two parts (Exhausting, second leg) are reported, not decided on.
- The location line, the zones and the Overheated and Capitulating shading are readings, not marks: they stay.
- Nothing in the engine or the app changes.

## Reported, not decided on

- For each mark, on the unseen coins: marks, right-way rate, chance, median 90-day return and chance's median, median 30-day return, the median worst close in the 30 days after (the lowest for a buy mark, the highest for a sell mark), and the median **timing**: where the mark's close sits between the lowest and the highest close from 30 days before to 90 days after (0 at the low, 1 at the high).
- Each of the four parts.
- ETH, BTC and SOL apart: the same table, and each divergence, Capitulation turn and Reclaim mark with its 90-day outcome (the owner's 3 June 2026 ETH bottom divergence among them).

## Limits

- Marks cluster in time across coins (the 2018 and 2022 falls, the 2021 rise), so they are not independent. The 10-point margin and the four parts are the guard, not a significance test.
- One horizon, 90 days, chosen for marks read on a weekly band. Going the right way at 90 days is not a trade's result: no stops, costs or sizing.
- Seven marks are judged at once: one could clear the bar by luck; needing all four parts makes that harder.
- Binance spot, not Hyperliquid perps; daily candles only. On a 4H chart the script turns days into bars and its marks differ.
- Coins chosen by volume before 2020 include later failures; many fell against USDT over the years, which makes sell marks easier and buy marks harder. Chance is taken per coin and era for that reason.
- The owner may have looked at other coins on TradingView before this declaration.
