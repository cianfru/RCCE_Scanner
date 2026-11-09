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

## Results (run 9 November 2026, after the declaration was committed)

Same data as declared (SHA-256 `16cff00c39636e9daf827970dbebdc03304207f796074c98566dc613b806aeed`). Checked a second way: a direct recount of each mark's 90-day outcome, and chance re-estimated by placing each coin's marks on random days of the same coin and era (400 draws), which agrees with the weighted chance within 0.4 points.

### The 36 unseen coins (the verdict)

Right way: higher 90 days later for a buy mark, lower for a sell mark. Worst close: the median lowest (buy) or highest (sell) close in the 30 days after, against the mark's close. Timing: 0 at the low and 1 at the high of the closes from 30 days before to 90 days after.

| Mark | Points | Marks | Right way | Chance | Margin | Median 90 days | Chance's median | Median 30 days | Worst close in 30 days | Timing |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Buy | up | 878 | 40.0% | 47.9% | −7.9 | −11.2% | −2.5% | −7.7% | −16.1% | 0.44 |
| Take profit | down | 224 | 60.3% | 50.9% | +9.4 | −16.8% | −1.2% | −5.7% | +20.1% | 0.55 |
| **Capitulation turn** | up | 91 | **57.1%** | 41.5% | **+15.7** | +3.6% | −9.1% | −10.1% | −18.9% | 0.25 |
| Reclaim | up | 19 | 73.7% | 51.4% | +22.3 | +34.0% | +1.9% | +0.1% | −13.2% | 0.42 |
| **Top divergence** | down | 47 | **68.1%** | 46.0% | **+22.1** | −23.1% | +5.8% | +4.5% | +24.5% | 0.50 |
| Bottom divergence | up | 95 | 47.4% | 35.8% | +11.5 | −3.2% | −13.5% | −2.4% | −8.9% | 0.36 |
| Lost the band | down | 494 | 57.5% | 55.8% | +1.7 | −6.7% | −6.5% | −2.2% | +10.6% | 0.37 |

Take profit's parts (reported): Exhausting 185 marks, 59.5% against 51.9% (+7.6); second leg 39 marks, 64.1% against 45.9% (+18.2).

### The four parts: right way against chance (marks)

| Mark | Calibration half | Test half | Before 2022 | From 2022 |
|---|---|---|---|---|
| Buy | 43.8% / 49.0% (447) | 36.0% / 46.7% (431) | 50.8% / 55.6% (417) | 30.2% / 40.9% (461) |
| Take profit | 62.5% / 51.3% (104) | 58.3% / 50.4% (120) | 52.8% / 42.6% (125) | 69.7% / 61.2% (99) |
| Capitulation turn | 56.8% / 42.2% (44) | 57.4% / 40.8% (47) | 95.0% / 55.2% (20) | 46.5% / 37.6% (71) |
| Reclaim | 66.7% / 49.1% (9) | 80.0% / 53.4% (10) | 76.9% / 55.3% (13) | 66.7% / 43.0% (6) |
| Top divergence | 63.2% / 48.4% (19) | 71.4% / 44.4% (28) | 63.3% / 40.7% (30) | 76.5% / 55.4% (17) |
| Bottom divergence | 44.4% / 36.9% (36) | 49.2% / 35.2% (59) | none (0) | 47.4% / 35.8% (95) |
| Lost the band | 57.7% / 54.8% (241) | 57.3% / 56.7% (253) | 37.9% / 44.6% (177) | 68.5% / 62.0% (317) |

### ETH, BTC and SOL (seen, reported apart)

| Mark | Marks | Right way | Chance |
|---|---:|---:|---:|
| Buy | 80 | 55.0% | 55.2% |
| Take profit | 21 | 47.6% | 44.1% |
| Capitulation turn | 13 | 61.5% | 52.9% |
| Reclaim | 4 | 75.0% | 52.3% |
| Top divergence | 17 | 52.9% | 44.3% |
| Bottom divergence | 8 | 62.5% | 51.4% |
| Lost the band | 39 | 43.6% | 45.4% |

Each mark, with the close 90 days later:

- **Top divergence:** BTC 15 Jun 2019 +17%, 13 Apr 2021 −48%, 19 Oct 2021 −34%, 6 Nov 2024 +29%, 13 Dec 2024 −20%, 21 Jan 2025 −18%, 18 May 2025 +10%, 10 Jul 2025 +6%, 5 Oct 2025 −27%; ETH 25 Jul 2020 +34%, 13 Nov 2020 +275%, 1 Apr 2021 +16%, 25 Oct 2021 −40%; SOL 22 Oct 2021 −35%, 29 Feb 2024 +34%, 10 Nov 2024 −5%, 18 Jan 2025 −49%.
- **Bottom divergence:** BTC 27 May 2022 −25%, 6 Sep 2022 −10%, 9 Nov 2022 +46%, 5 Jun 2026 +33%; ETH 3 Jun 2026 (1,813) +33%; SOL 20 Oct 2022 −26%, 22 Dec 2022 +81%, 2 Jun 2026 +39%.
- **Capitulation turn:** BTC 28 Nov 2018 −11%, 19 Mar 2020 +54%, 24 May 2021 +27%, 7 Jul 2022 −7%, 24 Nov 2025 −23%, 20 Feb 2026 +14%; ETH 30 May 2022 −29%, 8 Aug 2024 +1%, 17 Mar 2025 +32%, 9 Feb 2026 +13%; SOL 15 May 2022 −21%, 10 Nov 2022 +31%, 9 Feb 2026 +11%.
- **Reclaim:** BTC 29 Apr 2020 +24%; ETH 12 Aug 2022 −34%, 10 May 2025 +55%; SOL 14 Jan 2023 +2%.

## Verdict

- **Shown by default: Top divergence and Capitulation turn.** Both clear all four conditions.
- **Hidden by default** (behind "Show marks that did not pass the test"): **Buy** (worse than chance), **Take profit** (+9.4 points, 0.6 short of the margin), **Bottom divergence** (no marks before 2022, so one part cannot be checked), **Reclaim** (19 marks, too few) and **Lost the band** (+1.7 points).
- Applied to `tradingview/reflex_band_model.pine` as declared: the header gives each mark's result. Nothing in the engine or the app changed. Every mark remains context, not a signal.

## Reading

- **The buy mark at the band was worse than ordinary days**: 40% of its marks were higher 90 days later, against 48% for random days on the same coins and eras; from 2022, 30% against 41%. The owner's impression ("especially lately") holds. A rising band and an up close at the band did not separate the start of a rise from a bounce in a falling market on these coins, most of which fell against USDT after 2021.
- **The Capitulation turn is early.** It was higher 90 days later more often than chance in every part, but the median close 30 days after it was 10% lower, and the median lowest close in those 30 days 19% lower. It marks a stretch of oversold days that did better than ordinary days over three months, not the low. This goes against the owner's wish to have no blue up mark below the band. The declared rule shows it; hiding it is the owner's call.
- **The Reclaim**, the version above the band, went the right way 74% of the time against 51% (median +34% against +2%), but 19 marks across 36 coins in seven years are too few to judge. It is context only.
- **The Top divergence is the clearest mark.** It was lower 90 days later 68% of the time against 46% (median −23% against +6%), in every part. On ETH, BTC and SOL (seen) it did less well: 53% against 44%. ETH's three marks from July 2020 to April 2021 came before large rises.
- **The Bottom divergence was better than ordinary days but did not mark bottoms**: price was higher 90 days later after 47% of its marks (chance 36%), and every mark comes from the 2022 fall, so the earlier years cannot check it. On ETH, BTC and SOL the June 2026 marks went the right way (ETH 3 June 2026: +33%); the mid-2022 marks did not.
- **Take profit came close** (+9.4 points, every part above chance); its second-leg part did better (+18.2, 39 marks). Both read as context.
