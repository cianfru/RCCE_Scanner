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
- **Layers' data:** SHA-256 recorded at the data check below.

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

- **The split:** a mark's counted marks with a value of the layer are cut into a **high** and a **low** group at the median of those values (ties go high); BTC's band splits into above and below.
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
- **Coverage** (`check`, no outcomes): see the table below.

## Limits

- Many looks at once (see the bar); marks cluster in time across coins.
- Split at the median of the marks: the cut is not a level anyone set in advance and differs by mark; it says which half of a mark's own marks did better.
- The Binance futures layers stand in for Reflex's own funding and open interest readings, which come from Hyperliquid and have no long history. Binance's long/short ratios are Binance accounts, not the traders Reflex follows.
- Reflex's trader layers (profitable traders, smart money, whales) cannot be judged yet. Testing them needs marks recorded live with those layers at the time.
