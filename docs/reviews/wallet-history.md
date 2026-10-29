# Smart money, whales and profitable traders, long and short, at each daily close (method note, 28 October 2026)

What the market history page (`/market`) draws under the Uptrend share and Fear & Greed: how many Hyperliquid smart-money wallets and whales were net long and net short at each 00:00 UTC close, and how the profitable traders HyperLens follows (Outrider's crowd) split their positions. The owner asked to see it next to the share of coins in Uptrend, without a study. It is a description of who held what. **Context, not a signal**: no test, no verdict, nothing here says what follows.

Code: `backend/wallet_history.py` (the feed, `/api/market-history/wallets`), `backend/backtest/wallet_history_rebuild.py` (the rebuilt days), `backend/seeds/crowd_share_seed.json` (Outrider's rebuilt profitable-trader days), `frontend/src/utils/walletHistory.js` (shares), `frontend/src/pages/MarketPage.jsx`.

## Groups

The live cohort sweep's own groups (`backend/cohorts/assign.py`), as each wallet stood on the day:

| Group | Rule | Sweep cohorts |
|---|---|---|
| Smart money | all-time PnL $100K or more, perp equity $10K or more | Smart Money + Money Printer |
| Whales | perp equity $1M or more | Tidal Whale + Leviathan |
| Profitable traders | the best 600 by monthly return (30%+, $10K+ monthly profit, in profit before the month) | HyperLens's roster (not a sweep cohort) |

A wallet can be in more than one. Market makers are out: monthly volume over 100 times the account value (as the live registry), or more than 25 open positions (as `cohorts.assign`).

## Counting

- Each wallet counts once per group: **long** or **short** by the sign of its net dollar position over all perpetual markets at the close (position size times the coin's daily close), as the sweep's `long_wallets` / `short_wallets`. Wallets with no position count in the total, as flat.
- **Shares**: long wallets and short wallets as a share of the group's wallets that day. Shares, not counts, so a group that grows (more wallets reach $100K of PnL) does not read as more longs.
- **Drawn from zero** (owner, 28 October 2026: a z-score made "no longs" read −2): the long share rises above the zero line in green, the short share falls below it in red. No longs reads 0; more shorts reach lower. Each panel has its own scale, named by its ticks. The readout gives the counts behind the shares.
- **One group at a time** (owner, 28 October 2026: "the overwhelm of data"): the page opens on smart money; tabs in the panel's header switch to whales or profitable traders, and to one main coin. The past-paths fan is off until "What followed similar days" is pressed, and the episodes and the forward test sit under "More history".
- **Profitable traders** count positions, not wallets: each open wallet-coin position once, long or short, as Outrider's pulse and study S2 do. Their two shares sum to 100% (flat wallets have no position to count).
- **Main coins** (BTC, ETH, SOL, HYPE): the same, with long or short meaning a position in that coin (the sweep's per-coin rows); wallets without one count in the group's total. A wallet can be short BTC and net long overall.

## Sources

**Recorded (from 26 September 2026).** The cohort sweep writes an all-market snapshot every 30 minutes (`cohort_snapshots`, kept 180 days). Once a day `wallet_history.update` takes the snapshot nearest each close (within an hour) and keeps the row in `wallet_history_live.json` next to hyperlens.db, so the history outlives the sweep's retention. Tiny: two rows a day.

**Rebuilt (1 September 2025 to the seed's last day).** Hyperliquid keeps no history of anyone's positions, so they are rebuilt from public records (`python -m backtest.wallet_history_rebuild`):

1. Candidates: today's leaderboard without market makers, with $100K+ all-time PnL, a $1M+ account or $100M+ all-time volume (to catch wallets that were large once).
2. Sample: a fixed hash of the address picks 10% of the candidates and 35% of the likely whales ($1M+ account or $1B+ all-time volume). Every count is weighted by one over the wallet's chance of being picked, so the rebuilt counts estimate the whole group; `sampled` says how many wallets each day rests on.
3. Membership by day: Hyperliquid's `portfolio` history gives each wallet's perp equity (weekly, finer in the last month) and all-time PnL (weekly), interpolated at each close. A wallet is in a group only on the days it met the rule then, not because it meets it today.
4. Positions: current positions, regular fills and timed-order slices since 1 September 2025. Each fill carries Hyperliquid's record of the position just before it, so a position at a close is the one right after the last fill before it or right before the next one (the current position when none follows); where a fill was not read and the two differ, the nearer in time. Leftovers under 1e-6 of a coin are flat (float noise of a full close).
5. Very active wallets are read for their newest fills only (the latest 2,000 plus 2 more pages of regular fills, 1 more of slices; 2,000 a page), and Hyperliquid itself serves only about a wallet's latest 10,000 fills. Before the first fill read such a wallet is uncovered that day: left out, and the covered wallets' shares stand for it.

**Profitable traders.** Recorded days come from HyperLens's own record (`trader_lean`, per coin at every 4-hour close since 26 September 2026, roster version 2 only): the bar closing at 00:00 UTC (or the nearest within 4 hours), long and short positions summed over the coins. The days before are Outrider's study S2, part B (Agent repository, `docs/studies/S2-lean-vs-price.md`; the daily series in `synth/data/research.json`), copied into `seeds/crowd_share_seed.json`: the same share rebuilt from public fills for Reflex's roster rule applied to the 10 October 2026 leaderboard. S2 dates a row by its 00:00 UTC reading; the seed dates it by the day that reading closes (one day earlier), as Reflex does. Where the two overlap by a week or more, the rebuilt shares are shifted by their mean difference (`crowd.overlap`).

**Joining the two.** The page shows recorded days wherever the sweep has them and rebuilt days before them (and in any gap). The rebuilt counts are an estimate from a sample, so their level can sit a few points off the recorded one; left as is, the seam would read as wallets changing side in exactly the most recent days. Where the two overlap by a week or more, the rebuilt days are moved to the recorded level: each share (positioned, long, short) shifted by its mean difference over the overlap (`overlap.offset`, in points). The feed also gives the mean absolute gap before the shift (`overlap.long_pts`, `overlap.short_pts`), and the page's (i) quotes it.

## Outrider's numbers beside these (checked 28 October 2026)

The owner saw the two apps disagree. They count different people in different ways; where they count the same people (Outrider's crowd and HyperLens's profitable traders) the numbers are the same data.

| Name on screen | App | Who | Counted as | How often |
|---|---|---|---|---|
| "Smart money" (Telegram pulse and its picture), "Crowd long" (desk) | Outrider | HyperLens's profitable traders: the best 600 by monthly return (30%+, $10K+ monthly profit, in profit before the month) | positions: each trader-coin position once; long ÷ (long + short), flat traders not counted | every poll (minutes), from `/api/hyperlens/positioning` |
| "Profitable traders" (HyperLens, this page's third panel) | Reflex | the same roster | the same positions | the sweep; this page at each 00:00 UTC close |
| "Big money" | Outrider | leaderboard account value $500K+ (spot and vaults included), in profit all-time, market makers out; one owner's wallets merged | one vote per owner per coin, from a $25K net position; long votes ÷ all votes | once a day |
| "Smart money" (this page, Cohorts page) | Reflex | $100K+ all-time PnL and $10K+ perp equity (Smart Money and Money Printer cohorts) | wallets: net long or short over all coins; share of all the group's wallets, flat ones included | each 00:00 UTC close |
| "Whales" (this page) | Reflex | $1M+ perp equity, profit not checked | as smart money | each 00:00 UTC close |
| "Large accounts" (HyperLens) | Reflex | leaderboard account value $1M+, the largest 60, profit not checked | traders per coin | the sweep |

What makes the readings differ:

- **Same name, different people.** Outrider's "Smart money" is Reflex's "Profitable traders". Reflex's "Smart money" is the $100K+ all-time PnL cohorts.
- **Positions against wallets.** A trader long five coins is five longs in Outrider's crowd and one long wallet here.
- **Flat counted or not.** For example, 40% long, 29% short and 31% flat of a group's wallets reads as 58% long when flat wallets are left out, as Outrider does.
- **Big money is not whales.** $500K of leaderboard account value and in profit, per owner and per coin, against $1M of perp equity whatever the profit, per wallet over all coins. On the 28 October leaderboard: 3,681 accounts pass Outrider's rule, 2,602 have $1M+ of account value, 7,085 pass the smart-money rule, 645 the profitable-trader rule.
- **A long-leaning population.** The profitable traders held 69.5% of their positions long on average over Outrider's rebuilt year (S2). Levels of different groups are not comparable, only their moves.

## Limits

- **Survivorship.** Candidates come from today's leaderboard. A wallet that has left it is missing from the past.
- **Sampling.** About one in ten smart-money wallets and one in three whales. Day to day the same wallets move, so changes are steadier than levels.
- **Weekly membership.** Equity and PnL are weekly points before the last month; a wallet crossing a threshold mid-week switches group on the interpolated day.
- **Today's market-maker flag** decides who is a market maker over the whole period.
- **Very active traders** drop out of the older days (uncovered); the rest are scaled to their group.
- **Timed orders.** A slice history cut at its oldest end leaves positions built by slices alone unseen before it.
- Recorded rows count readings up to 2.5 hours old at the close (the sweep's cadence); rebuilt rows count the position at the close.
- **Profitable traders' rebuilt days are picked with hindsight**: the wallets are the ones that did well in the month before 10 October 2026 (S2's own bias statement), so before that month they are known winners. HyperLens's record has no such bias: each reading used the roster of its day.

## Refreshing the seed

From `backend/`: `census`, `fills`, `candles`, then `export` (each resumable; the cache defaults to `data/wallet_history_cache/`, gitignored). Raising `--share` adds wallets to the same sample. Recorded days need nothing: the server adds one a day.

## Rebuild run

Run 28-29 October 2026 (seed built 29 October), at 900 weight a minute, about eight hours of reads across several restarts (the cache resumed each time):

- **Candidates:** 14,343 wallets from the 28 October leaderboard (47,783 rows) after the rules above.
- **Sampled:** 2,207 (10% of candidates, 35% of likely whales), all with portfolio history read; 952 were ever in smart money and 394 ever whales on some day, and their fills were read: 1,011 wallets, no errors. 138 hit Hyperliquid's limit of about 10,000 fills, so their oldest days are uncovered.
- **Seed:** 1 September 2025 to 28 October 2026, 423 days, every day present. Each day rests on 149 to 336 sampled smart-money wallets (median 182) and 29 to 104 whales (median 43); the older days have fewer because very active wallets are uncovered before their oldest fill. Estimated group sizes: about 1,500 smart-money wallets and 340 whales (median day), against 7,085 and 2,602 on the leaderboard's account value: most leaderboard accounts keep their money outside perps, and perp equity decides here as in the sweep.

Readings at the year's breadth highs and lows, as rebuilt (the page moves them to the recorded level where the sweep has days, which can shift them by a few points). Long and short as shares of each group's wallets:

| Day | Uptrend share | Fear & Greed | Smart money long / short | Whales long / short |
|---|---|---|---|---|
| 6 Oct 2025 (BTC's high) | 89% | 71 | 61% / 16% | 42% / 24% |
| 15 Dec 2025 (breadth low) | 5% | 16 | 27% / 32% | 22% / 49% |
| 15 May 2026 (breadth high) | 96% | 43 | 39% / 24% | 36% / 34% |
| 30 Sep 2026 (breadth high) | 86% | 71 | 60% / 24% | 76% / 9% |
| 27 Oct 2026 | 42% | 48 | 55% / 24% | 53% / 24% |

Description only: over this year both groups held the most longs near breadth highs and the most shorts near the lows, and their shorts grew after the turns rather than before them. One year, two cycles, a sample: context, not a signal.
