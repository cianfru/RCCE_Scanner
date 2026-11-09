# Band model marks with Reflex's layers: does a layer at the mark pick out the marks that work? (declared 9 November 2026, before running)

The owner's words (9 November 2026), after the marks study (`docs/reviews/band-model-marks-study.md`): "if it's something that actually works, then we should keep it. Plus, why don't we add all the extra layers that we capture from Reflex to see how precise the ... setting is", and, correcting the transcription, "not old but all".

The question this study fixes: **for each mark of the band model, does any of Reflex's layers, read at the mark, split its marks into a group that goes the right way clearly more often than the mark as a whole, in every part of the data?**

This describes the past and runs outside the production server. Everything below is fixed before any outcome is split by a layer. The marks, their counting, the 90-day outcome ("right way") and the chance are exactly those of the marks study; its results by mark are already known (they are what this study starts from). Unless a group clears the bar, it reads **context, not a signal**. Nothing in the engine, the app or the TradingView script changes either way: a group that clears the bar is listed for the owner as a candidate setup, which would need its own decision to build.

Code: `backend/research/band_marks_layers.py` (tests `backend/tests/test_band_marks_layers.py`), run from `backend/`:

- `python -m research.band_marks_layers check` (the layers' coverage of the marks, no outcomes)
- `python -m research.band_marks_layers run` (the study)

## Data

- **Prices and marks:** as the marks study (36 unseen coins, Binance spot daily candles to the 31 October 2026 close, SHA-256 `16cff00c39636e9daf827970dbebdc03304207f796074c98566dc613b806aeed`). ETH, BTC and SOL are left out: they were seen, and the layers were not looked at on them either.
- **Reflex's market layers**, from the repository's seeds (built from the same Binance daily candles of the 151 market-history pairs): the share of coins in Uptrend or Overheated and the market's median z (`seeds/market_history_seed.json`, the engine's regimes and z), and the share of coins with band z at 1.6 or more (`seeds/band_stretch_seed.json`). Days the seed read on 20 coins or more (the app's charts use 40; 20 keeps 2020 and 2021).
- **Reflex's positioning layers** (report only, see below): profitable traders long, the 600 (`seeds/crowd_share_seed.json`, from 1 October 2025), and smart money and whales long (`seeds/wallet_history_seed.json`, from 1 September 2025): the share of long among their long and short positions, market-wide.
- **Fear and Greed** (alternative.me, the index the Market page shows), by day.
- **Futures layers** (Binance USDT-M perpetuals, public archives on data.binance.vision): funding payments (monthly archives from September 2019), and the daily metrics files (open interest, top traders' and all accounts' long/short ratios) for each mark's day and the day 30 days before.
- **Layers' data** (`check`): Fear and Greed, funding and the metrics read, SHA-256 `6842e690f03e5aa73aa0b04618ef5246125b1898fab4c383e7d742acf6c7c16b`.

## The layers, read at a mark (the mark's daily close; nothing after it)

| Layer | Reading | Split |
|---|---|---|
| Uptrend share (Reflex) | share of coins in Uptrend or Overheated | at the median |
| Coins stretched (Reflex) | share of coins with band z 1.6 or more | at the median |
| Market's median z (Reflex) | the median of the engine's z across coins | at the median |
| Fear and Greed | the index that day | at the median |
| BTC above its weekly band | BTC's close above its band mid | yes or no |
| The coin's z (Reflex engine) | the engine's z on the coin's daily closes | at the median |
| The coin's funding | the time-weighted mean funding rate over the 7 days to the close, per 8 hours (payments covering 120 hours or more) | at the median |
| The coin's open interest | the log change of open interest (contracts) over the 30 days to the close | at the median |
| Top traders' long/short (Binance) | the day's last ratio, by positions | at the median |
| All accounts' long/short (Binance) | the day's last ratio | at the median |
| Profitable traders long (Reflex) | share long, the 600, market-wide | at the median, report only |
| Smart money long (Reflex) | share long, market-wide | at the median, report only |
| Whales long (Reflex) | share long, market-wide | at the median, report only |

- **The split:** a mark's counted marks with a value of the layer are cut into a **high** and a **low** group at the median of those values (ties go high, unless that leaves the low group empty, when ties go low); BTC's band splits into above and below.
- **Judged or reported only:** a layer is judged on a mark when it has a value on at least 90% of that mark's counted marks. The three positioning layers are reported only: their history starts in September and October 2025, so they cover too few marks (none before 2022) to be judged.

## The bar

For each mark and each judged layer, either group clears the bar when all three hold:

1. **at least 30 marks** in the group;
2. its **margin over chance at least 10 points above the margin of all the mark's marks with a value** (margin: right-way rate minus chance, chance as in the marks study: the same coins' days in the same era, each weighted by its marks);
3. in **each of the four parts** (calibration half, test half, before 2022, from 2022), both groups have at least 5 marks and this group's margin is above the other's.

The better group is found after looking; the four parts are what guards against luck. About 7 marks times 10 layers times 2 groups are looked at, so some group could clear the bar by luck: a group that clears it is a candidate to record live, not a finding.

## Reported, not decided on

- For every mark and layer: the cut, the coverage, and each group's marks, right-way rate, chance, margin and median 90-day return.
- The positioning layers the same way, on the few marks they cover.

## Known before running

- The marks study's results by mark (all marks, no split by any layer).
- Layer values were not looked at against any outcome. The owner's idea that a mark works better "if traders are bullish" (8 November) is what the positioning and long/short layers stand for; the direction is not assumed (either group can clear the bar).
- **One rule changed after the data check, before any outcome was read:** with ties going high, a layer whose median is its lowest value left the low group empty (coins stretched: the median was 0% on the Capitulation turn, Reclaim, Bottom divergence and Lost the band). Ties now go low in that case (the split becomes "none stretched" against "some").
- **Coverage** (`check`, no outcomes): marks with a value; **J** = judged (90% or more), the rest reported only.

| Mark | Marks | Uptrend share | Coins stretched | Market z | Fear and Greed | BTC band | Coin z | Funding | Open interest | Top traders | All accounts | Traders, smart money, whales |
|---|---:|---|---|---|---|---|---|---|---|---|---|---|
| Buy | 878 | 851 J | 824 J | 851 J | 878 J | 878 J | 861 J | 784 | 451 | 433 | 466 | 35, 55, 55 |
| Take profit | 224 | 218 J | 210 J | 218 J | 224 J | 224 J | 222 J | 191 | 95 | 96 | 96 | 2, 2, 2 |
| Capitulation turn | 91 | 91 J | 78 | 91 J | 91 J | 91 J | 89 J | 83 J | 67 | 45 | 67 | 23, 23, 23 |
| Reclaim | 19 | 19 J | 14 | 19 J | 19 J | 19 J | 19 J | 17 | 6 | 4 | 6 | 0 |
| Top divergence | 47 | 46 J | 46 J | 46 J | 47 J | 47 J | 47 J | 43 J | 17 | 16 | 16 | 0 |
| Bottom divergence | 95 | 95 J | 95 J | 95 J | 95 J | 95 J | 95 J | 90 J | 90 J | 60 | 90 J | 42, 42, 42 |
| Lost the band | 494 | 475 J | 447 J | 475 J | 494 J | 494 J | 487 J | 424 | 302 | 273 | 320 | 37, 44, 44 |

  The futures layers cover most marks only from 2022 (Binance's metrics files for most of these coins start then), so they are judged on the Bottom divergence alone (all its marks are from 2022). A median split of the Top divergence (47 marks) or the Reclaim (19) leaves groups under 30: only a lopsided BTC band split could reach 30 there.

## Limits

- Many looks at once (see the bar); marks cluster in time across coins.
- Split at the median of the marks: the cut is not a level anyone set in advance and differs by mark; it says which half of a mark's own marks did better.
- The Binance futures layers stand in for Reflex's own funding and open interest readings, which come from Hyperliquid and have no long history. Binance's long/short ratios are Binance accounts, not the traders Reflex follows.
- Reflex's trader layers (profitable traders, smart money, whales) cannot be judged yet. Testing them needs marks recorded live with those layers at the time.

## Results (run 9 November 2026, after the declaration and the data check were committed)

Same data as declared (prices `16cff00c…`, layers `6842e690…`). The passing group was recounted directly from the seed (47 marks, 70.2%; the other half 44 marks, 43.2%).

### Passed: one group

**Capitulation turn, with the market's median z in the high half (−0.84 or above):** 47 marks on 29 coins, 70.2% higher 90 days later against chance 43.0% (margin +27.2, against +15.7 for all its marks), median 90-day return +8.5%. It was ahead of the other half in all four parts. The other half, the whole market deeply oversold (median z under −0.84): 44 marks, 43.2% against 39.8%, margin +3.4.

**Two crashes carry much of it.** All 13 marks from March 2020 are in the passing half, and all 13 went the right way. 22 of the other half's 44 are from May 2022, and 6 of those went the right way. Without March 2020 the passing half is 21 of 34 (61.8%). From 2022 alone: 19 of 33 (57.6%) against 14 of 38 (36.8%). As declared, this is a candidate to record live, not a finding.

### Close, but short of the bar

- **Take profit when the market is less heated** (market's median z under 0.60): 64.2% (109 marks), margin +17.3 against +8.9, ahead in all four parts; 8.4 points of gain, the bar is 10. Fewer coins in uptrend (under 77%) and many coins stretched (20% or more) point the same way: +5.6 and +7.6 points, all parts.
- **Top divergence when the market is not euphoric**: uptrend share under 58%, 19 of 23 right (82.6%); market's median z low, the same; Fear and Greed under 74, 17 of 20 (85.0%). In each case the half that does better has under 30 marks.
- **Capitulation turn with funding not negative**: margin +22.6 against +17.1, all four parts, 5.5 points of gain.
- **Bottom divergence when Fear and Greed is 25 or more**: 60.0% (50 marks), margin +24.6 against +11.5, but the mark has no marks before 2022, so one part is always empty (no layer can pass on it).
- **Buy**: no layer lifts it above chance. The best half, the coin's own z under 0, is 49.3% against chance 49.9%.

### Reported only

- **Futures layers** (most marks from 2022): Take profit with top traders' long/short in the high half, 41 of 48 (85.4%); Lost the band with all accounts' long/short high, 76.2% (160 marks), margin +15.1 against +8.6.
- **Reflex's trader layers** (from September and October 2025; one falling market, a handful of marks): Capitulation turn when the profitable traders were more long (above 36% long), 10 of 13 right against 3 of 10; when whales were more long (above 54%), 11 of 13 against 2 of 10. Bottom divergence with whales more long, 14 of 22 against 3 of 20. Buy did worse the more long these groups were (smart money above 72% long: 2 of 28). A direction, not evidence.

### Every mark and layer

Right way (marks), margin over chance in points; "high" is the half at or above the cut.

**Buy** (all marks: 40.0% right, chance 47.9%, margin -7.9)

| Layer | Cut | High half | Low half | Margin of marks with a value | |
|---|---|---|---|---:|---|
| Uptrend share | 42% | 37% (434), -8.7 | 45% (417), -4.3 | -6.6 |  |
| Coins stretched | 2% | 45% (426), -2.6 | 38% (398), -9.2 | -5.8 |  |
| Market's median z | -0.03 | 38% (433), -8.8 | 45% (418), -4.2 | -6.6 |  |
| Fear and Greed | 52 | 44% (450), -2.0 | 36% (428), -14.1 | -7.9 |  |
| BTC above its band | above / below | 38% (686), -8.4 | 45% (192), -6.2 | -7.9 |  |
| Coin's z | -0.01 | 30% (431), -15.3 | 49% (430), -0.6 | -8.0 |  |
| Funding, 7 days | 0.009% | 44% (392), -3.8 | 38% (392), -8.5 | -6.2 | reported only |
| Open interest, 30 days | -0.7% (log) | 29% (226), -11.2 | 31% (225), -10.5 | -10.9 | reported only |
| Top traders' long/short | 1.36 | 24% (217), -15.7 | 38% (216), -6.1 | -10.9 | reported only |
| All accounts' long/short | 2.18 | 28% (233), -11.8 | 31% (233), -12.6 | -12.2 | reported only |
| Profitable traders long | 59% | 15% (20), -29.6 | 40% (15), -11.1 | -21.7 | reported only |
| Smart money long | 72% | 7% (28), -33.3 | 30% (27), -20.5 | -27.0 | reported only |
| Whales long | 56% | 14% (28), -29.4 | 22% (27), -24.6 | -27.0 | reported only |

**Take profit** (all marks: 60.3% right, chance 50.9%, margin +9.4)

| Layer | Cut | High half | Low half | Margin of marks with a value | |
|---|---|---|---|---:|---|
| Uptrend share | 77% | 59% (116), +4.0 | 61% (102), +14.5 | +8.9 |  |
| Coins stretched | 20% | 64% (106), +14.9 | 53% (104), -0.5 | +7.3 |  |
| Market's median z | 0.60 | 56% (109), +0.5 | 64% (109), +17.3 | +8.9 |  |
| Fear and Greed | 75 | 63% (118), +9.7 | 58% (106), +9.1 | +9.4 |  |
| BTC above its band | above / below | 62% (216), +10.3 | 25% (8), -15.4 | +9.4 |  |
| Coin's z | 1.50 | 61% (111), +8.3 | 59% (111), +10.6 | +9.4 |  |
| Funding, 7 days | 0.037% | 68% (96), +17.0 | 57% (95), +3.0 | +10.0 | reported only |
| Open interest, 30 days | +6.1% (log) | 77% (48), +17.6 | 62% (47), -1.1 | +8.3 | reported only |
| Top traders' long/short | 1.91 | 85% (48), +23.1 | 54% (48), -5.7 | +8.7 | reported only |
| All accounts' long/short | 2.77 | 75% (48), +12.3 | 65% (48), +5.1 | +8.7 | reported only |
| Profitable traders long | 57% | 100% (1), +53.4 | 100% (1), +37.1 | +45.3 | reported only |
| Smart money long | 68% | 100% (1), +53.4 | 100% (1), +37.1 | +45.3 | reported only |
| Whales long | 59% | 100% (1), +53.4 | 100% (1), +37.1 | +45.3 | reported only |

**Capitulation turn** (all marks: 57.1% right, chance 41.5%, margin +15.7)

| Layer | Cut | High half | Low half | Margin of marks with a value | |
|---|---|---|---|---:|---|
| Uptrend share | 11% | 66% (47), +23.4 | 48% (44), +7.4 | +15.7 |  |
| Coins stretched | 0% | 48% (21), +7.0 | 51% (57), +12.4 | +11.0 | reported only |
| Market's median z | -0.83 | 70% (47), +27.2 | 43% (44), +3.4 | +15.7 | **passed: high** |
| Fear and Greed | 11 | 59% (46), +17.2 | 56% (45), +14.1 | +15.7 |  |
| BTC above its band | above / below | 44% (9), +8.0 | 59% (82), +16.5 | +15.7 |  |
| Coin's z | -1.23 | 56% (45), +15.5 | 57% (44), +14.7 | +15.1 |  |
| Funding, 7 days | -0.004% | 62% (42), +22.6 | 54% (41), +11.4 | +17.1 |  |
| Open interest, 30 days | -4.2% (log) | 53% (34), +15.0 | 45% (33), +8.3 | +11.7 | reported only |
| Top traders' long/short | 1.19 | 65% (23), +28.0 | 45% (22), +7.4 | +18.0 | reported only |
| All accounts' long/short | 2.04 | 50% (34), +12.3 | 48% (33), +11.1 | +11.7 | reported only |
| Profitable traders long | 36% | 77% (13), +38.9 | 30% (10), -8.1 | +18.5 | reported only |
| Smart money long | 56% | 65% (17), +28.2 | 33% (6), -9.1 | +18.5 | reported only |
| Whales long | 54% | 85% (13), +48.0 | 20% (10), -19.9 | +18.5 | reported only |

**Reclaim** (all marks: 73.7% right, chance 51.4%, margin +22.3)

| Layer | Cut | High half | Low half | Margin of marks with a value | |
|---|---|---|---|---:|---|
| Uptrend share | 50% | 90% (10), +40.8 | 56% (9), +1.7 | +22.3 |  |
| Coins stretched | 0% | 50% (6), +3.9 | 75% (8), +22.5 | +14.5 | reported only |
| Market's median z | 0.47 | 80% (10), +31.3 | 67% (9), +12.2 | +22.3 |  |
| Fear and Greed | 34 | 70% (10), +21.1 | 78% (9), +23.5 | +22.3 |  |
| BTC above its band | above / below | 82% (11), +31.6 | 62% (8), +9.5 | +22.3 |  |
| Coin's z | 0.78 | 90% (10), +38.9 | 56% (9), +3.8 | +22.3 |  |
| Funding, 7 days | 0.008% | 78% (9), +27.1 | 62% (8), +12.2 | +20.1 | reported only |
| Open interest, 30 days | +26.1% (log) | 33% (3), -8.7 | 100% (3), +55.9 | +23.6 | reported only |
| Top traders' long/short | 1.33 | 50% (2), +6.9 | 100% (2), +60.5 | +33.7 | reported only |
| All accounts' long/short | 1.24 | 67% (3), +26.7 | 67% (3), +20.6 | +23.6 | reported only |
| Profitable traders long | - | - | - | - | reported only |
| Smart money long | - | - | - | - | reported only |
| Whales long | - | - | - | - | reported only |

**Top divergence** (all marks: 68.1% right, chance 46.0%, margin +22.1)

| Layer | Cut | High half | Low half | Margin of marks with a value | |
|---|---|---|---|---:|---|
| Uptrend share | 58% | 52% (23), +2.9 | 83% (23), +39.3 | +21.1 |  |
| Coins stretched | 14% | 61% (23), +17.2 | 74% (23), +25.0 | +21.1 |  |
| Market's median z | 0.31 | 52% (23), +2.2 | 83% (23), +40.0 | +21.1 |  |
| Fear and Greed | 74 | 56% (27), +7.8 | 85% (20), +41.3 | +22.1 |  |
| BTC above its band | above / below | 67% (43), +21.5 | 75% (4), +28.5 | +22.1 |  |
| Coin's z | 0.53 | 67% (24), +20.1 | 70% (23), +24.1 | +22.1 |  |
| Funding, 7 days | 0.044% | 64% (22), +14.4 | 67% (21), +22.3 | +18.2 |  |
| Open interest, 30 days | +32.9% (log) | 89% (9), +35.4 | 62% (8), +4.9 | +21.1 | reported only |
| Top traders' long/short | 1.99 | 88% (8), +28.5 | 62% (8), +15.2 | +21.8 | reported only |
| All accounts' long/short | 2.03 | 100% (8), +37.6 | 50% (8), +6.0 | +21.8 | reported only |
| Profitable traders long | - | - | - | - | reported only |
| Smart money long | - | - | - | - | reported only |
| Whales long | - | - | - | - | reported only |

**Bottom divergence** (all marks: 47.4% right, chance 35.8%, margin +11.5)

| Layer | Cut | High half | Low half | Margin of marks with a value | |
|---|---|---|---|---:|---|
| Uptrend share | 76% | 52% (48), +16.0 | 43% (47), +7.0 | +11.5 |  |
| Coins stretched | 0% | 35% (26), -1.8 | 52% (69), +16.5 | +11.5 |  |
| Market's median z | 0.25 | 45% (49), +9.6 | 50% (46), +13.6 | +11.5 |  |
| Fear and Greed | 25 | 60% (50), +24.6 | 33% (45), -3.1 | +11.5 |  |
| BTC above its band | above / below | 73% (11), +40.5 | 44% (84), +7.7 | +11.5 |  |
| Coin's z | 0.25 | 50% (48), +14.2 | 45% (47), +8.8 | +11.5 |  |
| Funding, 7 days | 0.003% | 56% (45), +19.6 | 40% (45), +4.2 | +11.9 |  |
| Open interest, 30 days | +5.8% (log) | 51% (45), +16.5 | 44% (45), +7.4 | +11.9 |  |
| Top traders' long/short | 1.46 | 50% (30), +14.6 | 50% (30), +14.1 | +14.3 | reported only |
| All accounts' long/short | 2.43 | 47% (45), +10.3 | 49% (45), +13.6 | +11.9 |  |
| Profitable traders long | 55% | 33% (21), -2.7 | 48% (21), +10.4 | +3.9 | reported only |
| Smart money long | 56% | 38% (21), +2.5 | 43% (21), +5.2 | +3.9 | reported only |
| Whales long | 61% | 64% (22), +26.3 | 15% (20), -20.8 | +3.9 | reported only |

**Lost the band** (all marks: 57.5% right, chance 55.8%, margin +1.7)

| Layer | Cut | High half | Low half | Margin of marks with a value | |
|---|---|---|---|---:|---|
| Uptrend share | 42% | 60% (239), +2.1 | 53% (236), -1.1 | +0.5 |  |
| Coins stretched | 0% | 55% (201), -3.6 | 60% (246), +4.8 | +1.0 |  |
| Market's median z | -0.23 | 59% (238), +1.1 | 54% (237), -0.1 | +0.5 |  |
| Fear and Greed | 50 | 57% (261), -1.2 | 58% (233), +5.0 | +1.7 |  |
| BTC above its band | above / below | 59% (317), +2.1 | 55% (177), +0.9 | +1.7 |  |
| Coin's z | -0.34 | 60% (244), +2.5 | 56% (243), +1.3 | +1.9 |  |
| Funding, 7 days | 0.008% | 56% (212), -0.7 | 60% (212), +2.7 | +1.0 | reported only |
| Open interest, 30 days | +2.6% (log) | 68% (151), +5.4 | 68% (151), +6.5 | +5.9 | reported only |
| Top traders' long/short | 1.28 | 66% (137), +3.7 | 69% (136), +8.8 | +6.3 | reported only |
| All accounts' long/short | 2.38 | 76% (160), +15.1 | 63% (160), +2.1 | +8.6 | reported only |
| Profitable traders long | 60% | 68% (19), +9.3 | 78% (18), +21.9 | +15.4 | reported only |
| Smart money long | 61% | 82% (22), +20.4 | 73% (22), +16.5 | +18.5 | reported only |
| Whales long | 54% | 78% (23), +15.9 | 76% (21), +21.3 | +18.5 | reported only |

## Verdict

One group clears the bar: **the Capitulation turn when the market as a whole is not deeply oversold** (its median z at −0.84 or above). Much of it rests on March 2020 and May 2022, so it is a candidate to record live, not a finding. Every other mark and layer is context, not a signal. Nothing in the engine, the app or the TradingView script changed.

## Reading

- **The layers that matter are about the market, not the coin.** Where a split did better, it was the market's state at the mark: a Capitulation turn worked when the rest of the market was not crashing with the coin; a Take profit and a Top divergence worked better when the market was not euphoric. The coin's own z and BTC's band separated little.
- **No layer rescues the Buy at the band.** Every half of every layer stayed at or under ordinary days.
- **Reflex's trader layers point the owner's way on the capitulation side** (marks did better when profitable traders and whales leaned long), and the other way on the Buy. Both rest on one year of one falling market. Judging them needs marks recorded live with those layers at the time.
