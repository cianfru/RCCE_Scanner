# A crowd of profitable traders, nearly all long, in greed: what followed? (declared 6 November 2026, before running)

The owner's question (6 November 2026), on the Market page's new count of the profitable traders' open positions: "we went from 2,232 positions on September 29th to 1,232 today ... it shows that market participants are out of the market ... when we have [over 2,000] players ... it might also signal some sort of local top, when you have a crowded long position and the market is just about ready to roll over. We have fear and greed at very high levels." And: "before I open a position when everybody's long and we have a greed market and so much leverage, then maybe it's time to wait a little bit."

The question this study fixes: **when many profitable-trader positions are open, nearly all long, with Fear & Greed high and a broad uptrend under way, did a roll-over follow more often than on other greedy days of a broad uptrend, and did the typical alt do worse?**

This describes the past and runs outside the production server. Everything below is fixed before any outcome is computed. Only a data check and counts were looked at; both are quoted below. Unless a result clears its bar, it reads **context, not a signal**.

Code: `backend/research/crowd_size.py` (tests `backend/tests/test_crowd_size.py`), run from `backend/`:

- `python -m research.crowd_size check --feed WALLETS.json` (the data check, no outcome)
- `python -m research.crowd_size shape --snapshot MH.json --feed WALLETS.json` (counts only)
- `python -m research.crowd_size run --snapshot MH.json --feed WALLETS.json --closes CLOSES.json` (the study)

## Data

- **Rebuilt positions.** `backend/seeds/crowd_share_seed.json` (`backtest.crowd_history_rebuild`, built 29 October 2026, SHA-256 `69896527004010824ce0d366354c08d2abf4f6aadb4336e915bc6a4008888e7b`). For each day from 1 October 2025 to 28 October 2026 (393 days, none missing): HyperLens's daily pick (the best 600 by 30-day return) applied to the wallet rebuild's sample, the list's long and short positions at the 00:00 UTC close, each wallet-coin position once, weighted by one over each wallet's chance of being sampled. Method and limits: docs/reviews/wallet-history.md.
- **Recorded positions.** A saved `/api/market-history/wallets` response from 6 November 2026, SHA-256 `d9c3759b0759335c00e365527973aca3958612c25c2fd17e5b793218684c43c3`: its `crowd` rows with counts, HyperLens's own record (trader_lean), 29 September to 5 November 2026.
- **The market.** The saved `/api/market-history` response the uptrend-band study used (6 November 2026, SHA-256 `6954f924cde373d2958c3f59e7578485be6ca9ed79fad2fe9b6420e433fa3e19`): the share of coins in uptrend, BTC's close and the daily Fear & Greed index.
- **The typical alt.** As in the uptrend-band study and by its code: the market seed's paths to 2026-01-28, then the public daily candles that study fetched (SHA-256 `f03a57b3f260db6d7b7d858742ae380c46283d582eff12960abd36991caf3949`), behind the same data check (it passed there).
- None of these saved responses are kept in the repository; the hashes identify them.

## Known before running

- **Earlier studies on the same rebuilt year.** The positioning-extremes study (29 October 2026) read the share long alone: 6 extreme-long episodes at 86.0% or more, too few to read. The late-uptrends study marks "traders mostly long" at 86%. The share's relation to price has been seen (its correlation with BTC's past month, 0.77). The rebuilt **counts** have not been studied against prices.
- **The owner's own episode was seen before this declaration.** The recorded days from 29 September 2026: about 2,000 positions, 84-92% long, Fear & Greed 65-74 and 84-86% of coins in uptrend to 6 October; on 7 October the long positions fell from 1,794 to 725 as BTC fell 2.6%; the broad uptrend ended on 22 October. Any episode reaching into 29 September to 6 November 2026 is therefore reported apart, never counted.
- **The data check** (`check`, run before this declaration; its pass mark was set in the code before it ran: 14 or more days, and both rank correlations at 0.6 or more). The rebuilt and recorded counts on the 30 days both cover, 29 September to 28 October 2026:
  - long positions rank alike, Spearman 0.943, at about the same level (recorded / rebuilt: median 1.04, quartiles 0.89 and 1.18);
  - all positions do not: Spearman 0.554, under 0.6 (the rebuilt short side follows the recorded one loosely);
  - the share long: recorded 3.3 points under rebuilt on average.

  **The check did not pass.** As declared in the code, the rebuilt and recorded series are not joined: the in-sample study reads the rebuilt year alone, and the out-of-sample run reads the recorded days alone, once each day has 60 readings in its 90 days (from about 27 November 2026). The page does not draw the rebuilt counts either.
- **Counts** (`shape`, no outcome), on the rebuilt year:
  - Crowding is readable from 29 November 2025 (60 days in the window): 334 days. 65 of them crowded.
  - Fear & Greed was 70 or more on only 27 of the broad-uptrend days in that span. 13 of them were crowded too.
  - Hot crowded stretches: 21-27 August, 4-7 September and 25 September to 1 October 2026. Counted episodes: **1** (21 August 2026); the others start within 30 days of the one before.
  - The wider layer (crowded in any broad uptrend, no greed needed): 219 readable broad-uptrend days, 56 crowded; 4 stretches; counted episodes 7 April, 3 July and 20 August 2026, and 25 September 2026 reported apart (the owner's episode).
- So the in-sample year cannot reach the bar: the run is description. The verdict waits for episodes from 7 November 2026.

## Definitions

- **Long positions** and **share long**: a day's long positions, and long / (long + short), at the 00:00 UTC close.
- **Crowded**: on a day with 60 or more readings in its 90 days (itself included), both the long positions and the share long at or above 80% of those days (the share of the window's days at or below the day's value is 0.8 or more). Measured against the series' own recent past, so its level (rebuilt or recorded) does not matter.
- **Hot**: Fear & Greed 70 or more that day (the engine's own greed line) and a broad uptrend under way by the 55% rule's own state that day (`research/late_uptrends.runs`: it starts on the first day at 55% or more of coins in uptrend and ends on the first of 5 days in a row under; dip days 1-4 stay in it).
- **Episode**: hot crowded days with gaps of up to 5 days form a stretch. Its first day is an episode when the 6 days before it all have both readings (else its start is unknown), and no stretch began in the 30 days before.
- **Rolled over within 30 days**: in the 30 days after the episode's close, the broad uptrend under way rolled over or ended. Its roll-over is the page's mark, once per run: the first day the share is 20 points or more under the run's high so far. A run that rolled over on or before the day counts only its end. Unknown while the 30 days are not over.
- **Prices**: the typical alt (the median coin other than BTC) and BTC over 30 and 14 days from the close.

## The deciding question

**Comparison days**: hot days whose crowding is readable and not crowded, outside the 30 days after any stretch's first day, with the outcome known. Greedy broad-uptrend days without the crowd: they isolate what the crowd adds to the heat.

**Deciding outcomes**: (1) rolled over within 30 days; (2) the typical alt over 30 days.

**The bar.** A verdict ("a greedy crowd of profitable traders, nearly all long, came before roll-overs, and the typical alt did worse") needs both:

1. **Roll-over**: at least 8 episodes with the outcome known; a roll-over after at least 75% of them; that rate at least 25 points above the comparison days' rate; no more than 5% of 10,000 random draws (as many comparison days as episodes) with as many roll-overs or more; and the episodes' rate above the comparison rate in both the first and the second half of the episodes by date.
2. **The typical alt over 30 days**: the uptrend-band study's checks (`price_block`) on the declared side, lower: at least 8 episodes; at least 75% of them under the comparison days' median; a median excess of 5 points or more under it; no more than 5% of 10,000 random draws at or under the episodes' median; the excess under it in both halves.

Otherwise: context, not a signal. A result on the other side, however large, is reported only.

## Also reported (no verdict)

- Every episode with its long positions, share long, Fear & Greed, share of coins in uptrend, the run's day, the roll-over outcome and the four price changes; the owner's episode apart.
- BTC over 30 days and both prices over 14 days with the same checks (edges 5 and 3 points).
- **The wider layer**: crowded episodes in any broad uptrend (no greed needed) against the broad-uptrend days that were not crowded, with the same outcomes and checks.
- Broad-uptrend days, and the greedy ones among them, by where that day's long positions sat in its 90 days (lower, middle, upper third): the roll-over rate within 30 days and the price medians. The days overlap, so this is description.

## Out of sample

From 7 November 2026, the same code with `run --oos` on later saved responses, reading the recorded days alone (the data check did not pass). Episodes starting on or after that day count toward the bar once their 30 days are over. The recorded series needs 60 days before crowding is readable, so from about 27 November 2026. The traders behind the positions (how many hold any, how many are net long or short) are recorded from the same day the change ships; they are reported with later runs and decide nothing here. At the in-sample pace, about one hot crowded episode a year, 8 take years. The wider layer, about three a year, is reported alongside.

## Limits

- One rebuilt year, from a sample of about 60 wallets a day that were in smart money or whales at some point, weighted up; smaller accounts are missing. Its short side tracks the record loosely (the data check).
- Positions, not traders: a trader in five coins counts five times. The list is re-picked every day by the last 30 days' return, so after a fall it fills with the traders who were short: the crowd follows the month that made it.
- Fear & Greed of 70 or more is rare in this year (27 broad-uptrend days), so the deciding question has almost no in-sample cases.
- The recorded counts changed method on 2 November 2026 (counted by net exposure: shorts covered by spot are left out). Long positions are unaffected; the share long steps up a little.
- Episodes in one cycle are not independent.

## Results

To be added below after the run. Nothing above changes. Any later change is listed under Deviations, with its reason and whether it came before or after the first result.

Computed once on 6 November 2026 by `run` at commit 654f4c4, the commit that holds this declaration. Inputs: the files named above (same SHA-256). The typical alt's data check passed. Every number is in sample (the rebuilt year), so this is description against the declared bar.

**Verdict: not met.** The year holds one hot crowded episode, against 8 needed, and no comparison day was left for it. Context, not a signal.

### The deciding question

| Episode | Long positions | Share long | Fear & Greed | Coins in uptrend | Run day | Rolled over within 30 days | Typical alt 30 / 14 days | BTC 30 / 14 days |
|---|---:|---:|---:|---:|---:|---|---|---|
| 21 Aug 2026 | 1,133 (the most of its 90 days) | 79.3% | 72 | 57.2% | 2 | no | +7.3% / -3.7% | +3.6% / +1.7% |

Comparison days: none. Every hot day of the year was crowded or fell within 30 days after a crowded stretch began, so no check could be computed beyond the count (1 of 8).

### The wider layer: crowded in any broad uptrend (reported, never deciding)

| Episode | Long positions | Share long | Fear & Greed | Coins in uptrend | Run day | Rolled over within 30 days | Typical alt 30 days | BTC 30 days |
|---|---:|---:|---:|---:|---:|---|---:|---:|
| 7 Apr 2026 | 500 | 68.4% | 11 | 76.6% | 19 | no | +13.6% | +11.2% |
| 3 Jul 2026 | 564 | 83.2% | 21 | 67.1% | 106 | no | -11.2% | +1.6% |
| 20 Aug 2026 | 976 | 87.8% | 62 | 55.2% | 1 | no | +18.5% | +11.3% |
| 25 Sep 2026 (the owner's, reported apart) | 1,599 | 87.4% | 71 | 80.7% | 37 | yes | -20.0% | -4.7% |

Against the 89 broad-uptrend days that were not crowded (outside the month after a stretch began):

| | Counted episodes | Comparison days | Needed for a verdict |
|---|---|---|---|
| Rolled over within 30 days | 0 of 3 | 52.8% | 8 episodes, 75%, 25 points over |
| Typical alt, 30 days (median) | +13.6% | -3.2% (excess +16.8 points, the other side) | 8 episodes, 5 points under |
| BTC, 30 days (median) | +11.2% | +4.3% | reported |

### Broad-uptrend days by their long positions (the days overlap: description)

Where each day's long positions sat in its own 90 days, 29 November 2025 to 28 September 2026:

| Long positions | Days | Rolled over within 30 days | Typical alt 30 days (median) | BTC 30 days (median) |
|---|---:|---:|---:|---:|
| Lower third | 35 | 80% | +13.3% | +20.3% |
| Middle third | 38 | 47% | -2.6% | +4.5% |
| Upper third | 119 | 19% | -3.2% | +2.1% |
| Greedy days among them (all 20 in the upper third) | 20 | 45% | +2.0% | +3.0% |

### Reading

- In this year a big, long crowd came with strength, not just before roll-overs. Most broad-uptrend days had the long positions in the upper third of their 90 days, and those were the days least often followed by a roll-over within 30 days (19%). Roll-overs were most common after days when the long positions had already fallen to the lower third (80%).
- The one crowded episode followed by a roll-over is the owner's own, late September 2026, which this study saw before declaring and does not count.
- That fits the owner's second observation, the crowd leaving, more than the first. The crowd falling as a sign was not declared here; it would need its own study, rules first.
- One rebuilt year, a sample of wallets, overlapping days: none of this is a signal.

### Deviations

None.
