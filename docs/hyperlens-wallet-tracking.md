# HyperLens wallet tracking (roster version 2)

How the backend picks the Hyperliquid wallets it follows and how often it reads them.
Constants live in `backend/hl_intelligence.py` (roster) and `backend/hl_cadence.py` (reading cadence).

## Roster rules

Built once a day from the Hyperliquid leaderboard download. Market makers (monthly volume over 100 times the account value) are removed first.

**Profitable traders** (`money_printer`, "profitable traders" in the app). All of:

| Rule | Value | Version 1 |
|---|---|---|
| Monthly ROI | at least 30%, and meaningful (the month did not start from under $1K) | same |
| Monthly profit | at least $10K | same |
| In profit before this month | all-time PnL at least this month's PnL | same |
| Leaderboard account value | at least $10K | $50K |
| Perp account | at least $5K of perp equity at the latest reading, or at any HyperLens reading in the last 7 days (only checked when a reading is on hand) | none at build time; tracked wallets under $25K were evicted later |
| How many | the best `MP_TARGET` = **600** by monthly ROI | 300 |

The profit rules are unchanged. The group grows by taking more ranks and by dropping the $50K account floor. The perp check removes wallets that keep everything in spot or vaults: they pass the profit rules but have no perp positions to follow.

**Large accounts** (`smart_money`). Leaderboard account value at least $1M and the same perp check, ranked by account value. Profit is not checked. The group is every elite wallet plus the largest others, up to `SM_TARGET` = **60** wallets in all (was 300).

**Elite.** A profitable trader that ranks within the top `ELITE_KEEP_RANK` = 300 large accounts (the old depth). Elite wallets always stay in the large-account group, so cutting it to 60 never drops one.

`HYPERLENS_MP_TARGET` and `HYPERLENS_SM_TARGET` override the two sizes without a code change. They replace `HYPERLENS_COHORT_SIZE`, which is no longer read.

**Perp floor.** One number, `_MIN_PERP_EQUITY` = $5K, is used three times: at the roster build (above), for evicting a tracked wallet, and for counting a wallet in consensus and the roster view (was $25K eviction and $50K counting).

**Dry run on the 29 September 2026 leaderboard** (46,777 rows, 39,975 after removing market makers; perp equity read from Hyperliquid the same day):

| | Version 1 | Version 2 |
|---|---|---|
| Profitable traders | 300 picked, 263 left after evictions | 869 pass the profit rules, 583 have a perp account: all 583 kept |
| Large accounts | 300 | 60 |
| Elite | 6 | 16 |
| Unique wallets | 536 | 627 |

Two of the six version 1 elite wallets had an empty perp account that day. The 7-day lookback keeps a tracked wallet that sold everything and moved its cash to spot for a few days.

## Reading cadence

Until version 2 the cohort sweep read every focus wallet (about 2,800 whales and proven traders) and the whole HyperLens roster every 30 minutes, whatever they were doing. Now each wallet's next reading depends on what its last one showed (`backend/hl_cadence.py`):

| Wallet | Read every |
|---|---|
| Followed (the Follow list, Telegram alerts) | 5 min, also while nobody is viewing |
| Positions changed at the last reading | 10 min |
| Unchanged since, holding positions | 15, 30, 45, then 60 min |
| Unchanged and flat | 2 h |
| Elite | at least every 15 min |

- **Changed** means a coin opened, closed or flipped, or a coin's size moved by more than 1% and more than $500. Positions under $500 are ignored. Closing everything counts as a change (10 min), then the wallet is flat (2 h).
- The sweep looks for due wallets every 5 minutes, so "10 min" means 10 to 15. Intervals of 30 minutes or more get plus or minus 10% so wallets do not bunch into bursts.
- Wallets outside the focus set keep their one check a day.
- At deploy every focus and roster wallet is due at once, so the first tick reads them all (like one old sweep, about 15 minutes at the sweep's rate budget). Then they start on the 60-minute step (2 hours if flat), spreading out with the jitter. The first reading of a wallet never read before counts as a change.

**Records at their boundaries.** A reading counts as current for up to 2.5 hours (the slowest tier plus a tick and the 20-minute pause after each 4-hour close; was 75 minutes). The 4-hour trader record and the 30-minute cohort snapshots use the readings on hand: an unchanged wallet's last reading is its current position (its dollar value is at the price when it was read). No extra reading is made at the boundary. Only when the cohort sweep is off and nobody has been viewing does HyperLens read every roster wallet at the 4-hour close, as before.

**Slower detection.** A wallet that trades after holding still for hours is seen up to about 70 minutes later (up to about 2 hours 20 minutes if it was flat), plus up to 20 minutes if that falls in the pause after a 4-hour close. It was 30 to 50 minutes. New-position markers, convergence alerts and the Radar's counts follow the same delay. Followed wallets are unchanged (5 minutes).

## Wallets that trade together

Some traders split one book across several wallets. The size study found three wallets holding 84% of the profitable traders' BTC longs, buying and selling the same lots. Counted separately they look like three traders agreeing. Now such a group counts as **one trader**; its dollars are still summed. Rule and constants: `backend/hl_entities.py`.

**Data.** Each time a tracked wallet's reading differs from its previous one (the cadence's change test), the coins that moved are logged in `position_changes` in hyperlens.db: size before and after, price, and the window between the two readings. Fills are not stored, so timing is at the resolution of the readings. Kept 30 days, about 1,300 small rows a day for the version 2 roster (about 4 MB).

**First start.** The log starts empty, and a group like the BTC wallets trades only a few times a month, so it would take weeks to be recognised. On the first start (empty log only, never again) a background task rebuilds the last 30 days from each roster wallet's fills: one `userFills` request per wallet, about 630 in all, one at a time on the coin-page entries' rate budget (it takes an hour or two), then regroups.

**Rule** (recomputed daily with the roster, and at start, over the last 30 days). Two wallets are linked when all of these hold:

1. **Traded together.** A wallet's changes to one coin in one direction within 2 hours of each other are one move. A move matches the other wallet's move in the same coin and direction within 48 hours (closest pairs first). Each wallet has at least 2 matched moves, at least 70% of each wallet's moves are matched, and the median time between matched moves is 6 hours or less.
2. **Held together.** Each wallet's position in every coin either of them held, in dollars at one price per coin, sampled every 4 hours over the 30 days: the two series correlate at 0.8 or more. Same coins, same side, sizes rising and falling in proportion.

Linked wallets are joined into one group (A with B and B with C make a group of three). The id is `grp-` plus the start of the smallest address.

**Where a group counts once:** consensus counts and trends (`long_count`, per-cohort counts, participation), the positioning map's per-coin `n` (the Radar's "profitable traders net long" and its trails), the price ladder's counts, the 4-hour trader record (`trader_lean`), new-position counts in the last 24 hours and convergences. In the positioning map a group sits on the side of its combined dollars, at its dollar-weighted entry, and is in profit when its combined unrealised PnL is. `usd` fields, `money` and the ladder's dollars still add every wallet. The cohort sweep's Cohorts tab still counts wallets.

**Shown:** `entity` on `/api/hyperlens/wallet/{address}`, `/api/traders/{address}` (id, size, members, note: "Part of a group of 3 wallets that trade together") and on roster, symbol-position and ladder rows (the id). The trader page and the wallet dialog show the note. `/api/hyperlens/status` shows the number of groups.

**Check on real fills.** Two replays over the 30 days to 26 September 2026, using each wallet's real fills:

| Wallets | Replay | Readings | Logged changes | Groups found |
|---|---|---|---|---|
| 573 (roster of the size study) | adaptive cadence | 339,000 | 21,000 (711 a day) | 1 of 3: the study's BTC wallets (0x2371...0883, 0x93ab...11f8, 0xec7f...df39) |
| 573 | first-start seed from fills | | 19,900 | the same group of 3 |
| 627 (roster version 2, dry run) | adaptive cadence | 474,000 | 37,900 (1,264 a day) | 1 of 2: BTC and ETH, same-minute trades |
| 627 | first-start seed from fills | | 37,300 | 1 of 2: NEAR only, same-minute trades |

The two version 2 pairs trade at the same minutes; each passes in one replay and misses the share test (67-70%) in the other, so pairs near the thresholds can come and go from day to day. A pair of BTC buyers adding every day, 13 hours apart on the median, is kept apart by the gap test. Two of the three study wallets are not in the version 2 dry run: their perp accounts were empty on 29 September and the dry run had no 7-day HyperLens history (production does).

## Cost

Hyperliquid info calls per minute (`clearinghouseState`, all from the cohort sweep in production). Before: production on 29 September 2026. After: the version 2 roster and the readings per wallet from the replay above (25.8 a day for a positioned wallet, 14.3 for a flat one; 48 a day before).

| | Before | After |
|---|---|---|
| Focus and roster wallets | about 105 (every wallet each 30 minutes) | about 51 (2,907 wallets, 93% positioned) |
| Elite floor | | about 1 |
| Daily checks (other leaderboard wallets) | about 11 | about 11 |
| **Total** | **116** | **about 62 (-46%)** |
| Roster alone | 18 (536 wallets) | 12 (627 wallets) |
| Each followed wallet | 0.2 | 0.2 |

With the sweep off (`COHORTS_ENABLED=0`), HyperLens reads the roster itself while someone is viewing: 54 a minute before (536 wallets every 10 minutes), about 12 after. `/api/hyperlens/status` shows the live rate per request type (`api_calls`).

Each reading costs about 2 ms of CPU, so the saving is small in money: well under a second of CPU a minute. New memory: the call counter (a few KB), the own polling plan for followed wallets (about 100 bytes each), queued change-log rows (a few per tick), the group maps (a few entries); the daily regrouping loads the 30-day change log for a few seconds (a few MB, in a worker thread). Database: the change log adds about 4 MB to hyperlens.db (71 MB, 30-day retention); cohorts.db keeps one more number per position and about 4,000 sweep-run rows (14 days).

## Coin keys

Positions, cohorts, the trader record and the Radar key a coin by the scanner's base ticker. Hyperliquid's "k" markets (kPEPE, kBONK ...: perps quoted per 1,000 tokens) are keyed `KPEPE`, as the scan row `KPEPE/USDT` is; Hyperliquid is asked by its own name (`kPEPE`), and stored fills and snapshots keep it. Prices stay per 1,000 tokens; the bare `PEPE` is never mapped to the k market. `backend/ticker_renames.py` holds the mapping and the one-time rename of records written as `PEPE` before October 2026.

## Stored fills

Trader profiles, their fills and closed positions, the coin page's trader entries and the leaderboard's win rates need each wallet's fills. Until October 2026 every uncached page view asked Hyperliquid for them (`userFills` and the timed-order slices: 40 to 240 weight, against 2 for a position reading). Now the roster's fills are kept in our database (`backend/hl_fills.py`) and those pages read them from there.

**Store.** `fills.db`, next to `hyperlens.db` (or `FILLS_DB_PATH`). One row per perpetual fill: time, coin, side, price, size, position before, direction, closed PnL, fee, and whether it is a timed-order slice; the fields the open/add/trim/close/flip classification, the chart marks and the round trips need. The key is (wallet, time, trade id, side, slice flag), so a fill read twice is stored once and a wallet's fills are one range of the key in time order. Spot and builder-dex fills are not kept. Kept 180 days and at most the newest 10,000 per wallet; a wallet off the roster for 7 days is dropped. Freed pages go back to the disk every 6 hours.

**Reading.** One wallet at a time, in the background:

| When | What |
|---|---|
| First time (backfill) | `userFillsByTime` from 180 days ago, 2,000 a page (Hyperliquid serves a wallet's 10,000 latest), and its timed-order slices |
| The position poller sees the wallet's positions change | only the fills since the last stored one (`userFillsByTime`, `userTwapSliceFillsByTime`) |
| A profile's live positions differ from the stored fills | the same, at most once per wallet every 10 minutes; the profile waits up to 4 seconds for it |
| Every 12 hours (plus or minus 10%) | the same, for trades opened and closed between two position readings |

**Budget.** The store has its own share of Hyperliquid's 1,200 weight a minute: 300, of which the backfill may use 240, so reads after a change always have room. The backfill also pauses in the 20 minutes after each 4-hour close and for the first 10 minutes after a start, while the scanner loads every market's candles (`FILLS_BACKFILL_AFTER_START_S`). Every page is saved with its cursor as it arrives, so a read cut short by a 429, a timeout or a restart continues from the last page instead of starting the wallet again. Two older shares shrink to keep the total of all shares where it was: leaderboard win rates 240 to 60 (they come from the store now), trader entries 480 to 360 (the coin page's holders are tracked wallets).

| Share (weight a minute) | Before | After |
|---|---|---|
| Cohort sweep | 400 | 400 |
| Trader entries and live profiles | 480 | 360 |
| Leaderboard win rates | 240 | 60 |
| Fills store | | 300 (backfill up to 240) |
| **Sum of shares** | **1,120** | **1,120** |

**Measured on 30 September 2026** (60 wallets sampled from that day's roster rules; 18 of them read into a test store):

| | |
|---|---|
| Fills in 180 days, per wallet | median 296, mean 1,085 (perp only: mean 781); 15% also have 2,000+ timed-order slices |
| Backfill weight per wallet | median about 60, mean about 200, largest about 750 |
| Backfill of the roster (about 620 wallets) | about 120,000 weight: 8 to 12 hours at 240 a minute, pauses included |
| A read after a change | 40 weight (two requests, few fills) |
| Steady state | about 1 read a minute after changes and 0.9 a minute from the sweep: about 60 weight a minute |
| Disk | 86 bytes a fill: about 90 MB after the backfill, 100-250 MB after 180 days, at most about 530 MB (every wallet at 10,000) |
| Largest wallet (10,000 fills) | read from disk in 40 ms, classified in 120 ms (once per stored version) |
| Same classification as the live path | on the window both cover, 12 wallets: 10 identical, 2 differing by 1 and 3 fills at the edge of the live path's 2,000-slice window |

Before, each uncached profile view of a tracked wallet cost 40 to 240 weight in fills and each coin page's trader entries up to 6 times that; now both cost none.

**Shared budget (October 2026).** The shares above are each consumer's own limit; on top of them every Hyperliquid call in the process now draws on one bucket of 1,000 weight a minute (`hl_calls.budget`, `HL_WEIGHT_PER_MIN`), below the 1,200 per-IP limit. Waiting consumers are served in this order, each up to a cap: scanner candles (800), positions (the HyperLens roster in the cohort sweep, followed wallets, books: 300), the fills store (300), the rest of the cohort sweep and backfills (400). Page views and market metadata never wait and are counted as "other". A 429 halves the bucket's rate for a minute for everyone. Before, the scanner alone used 2,000 to 2,800 a minute for 10 to 15 minutes after each start (102 candle requests a minute), so every caller met 429s; a start now reads only candles not read since the last close and scans the rest from the stored candles. Use per consumer: `api_calls.budget` in `/api/hyperlens/status` and `hyperliquid_budget` in `/api/net-stats`.

**Wallets not on the roster** (a pasted address) are still read live, shared between viewers for 3 minutes, one read per wallet at a time, and at most 6 such reads a minute across all users (`TRADER_LIVE_LOADS_PER_MIN`). Past that the profile, fills and history endpoints answer 503 "Busy, try again shortly" with a `Retry-After`, and the profile page retries after it.

**Shown:** `/api/hyperlens/status` has `fills_store` (wallets backfilled and pending, time left, rows, file size, the store's weight a minute, queued reads, live reads refused; `state`, the read in progress in `current` with its pages, fills and weight so far, `last_attempt` with its outcome, `last_exception`). The counts are read from the database file from the first second after a start and `api_calls` now counts weight per request type (`weight_per_min_5m`).

**Off:** `FILLS_STORE_ENABLED=0` returns every page to live reads as before.

## Daily record for the market history page

Once a day, after the 00:00 UTC close, `backend/wallet_history.py` reads the sweep's all-market snapshot nearest the close for two groups, smart money (the Smart Money and Money Printer PnL cohorts) and whales (Tidal Whale and Leviathan), and keeps one row per group: wallets, positioned, long, short and their dollars. The rows go to `wallet_history_live.json` next to hyperlens.db, so they outlive `cohort_snapshots`' 180 days. Days before the sweep began are rebuilt from Hyperliquid's public records (`backend/backtest/wallet_history_rebuild.py`). It also sums HyperLens's own per-coin record (`trader_lean`, the bar closing at 00:00 UTC) into the profitable traders' long and short positions that day. The page draws each group as long and short shares from zero under the Uptrend share; method and limits in docs/reviews/wallet-history.md. No extra Hyperliquid calls.

## Continuity

Changing the cohort moves the Radar's trader counts and the stored lean series.

- `trader_lean` rows (the 4-hour record per coin and group) have a `roster_version` column: 2 from this change on, empty (NULL) before, and 3 from 31 Oct 2026 (net-exposure counting, below). Split studies on it.
- Cohort snapshots (the Cohorts tab, every 30 minutes) carry `"roster_version": 2` inside their data.
- `position_opens` and `convergences` rows have a `roster_version` column (NULL before). The convergence forward test (docs/reviews/trader-convergence-forward-test.md) was declared on version 1: 300 wallets, $50K accounts, readings every 30 minutes, a 2-hour gap limit (now 2.5 hours, to cover the flat tier). Version 2 rows are a different variant and need their own declaration and count.
- `/api/hyperlens/status` shows `roster_version`, the targets and the cadence.

## Coin page: long and short over time

Each coin page has a "Long and short" card: wallets (or dollars) long above a line and short below it, every 4 hours, for four groups. `GET /api/coin-positioning?coin=BTC&days=30` (an edge feed, cached a minute) returns them.

| Group | Who | Record |
|---|---|---|
| Profitable traders | the monthly list (roster rules above) | `trader_lean` `coin:<COIN>` rows, every coin they hold, 400 days. A recorded close without the coin is 0/0. |
| All-time winners | cohort sweep wallets up $100K+ all time (Smart Money and Money Printer cohorts) | `coin_positioning` in cohorts.db |
| All-time losers | cohort sweep wallets with an all-time loss (the four Rekt cohorts) | same |
| Whales | cohort sweep wallets with $1M+ perp equity (Tidal Whale, Leviathan) | same |

- **`coin_positioning`** (cohorts.db, `WITHOUT ROWID`, key `(coin, ts)`): per group, wallets long and short and USD long and short, written at the first cohort snapshot of each 4h candle for every coin held (`assign.coin_groups`), with a `''` row for all markets that also marks the time as recorded. About 65 KB a day, kept 400 days. When the table is first created it is filled once from the per-symbol cohort rows already stored (the 40 largest coins); those times carry `full = 0`, so another coin missing there is a gap, not a zero.
- **Live point:** each group's latest reading is appended (profitable traders from the current readings, the cohort groups from the last 30-minute snapshot), marked `live`.
- **`roster_rebuilds`** (hyperlens.db): when the profitable-trader list was rebuilt and how many wallets joined and left. A step in the counts at a rebuild is the list changing, not trading; the chart marks rebuilds where 5 or more wallets changed. Rebuilds before the table existed are estimated once from the hourly snapshots (hours in which 5 or more tracked wallets had their first snapshot; who left is not known).
- Builder-dex (`xyz:`) coins have no rows in either record.

## Net exposure: shorts covered by spot or staked HYPE (31 Oct 2026)

A perp short covered by the same coin the wallet holds on Hyperliquid spot, or (for HYPE) staked, is a funding trade: the wallet collects funding without a bet on price. On 31 Oct 2026, 109 of the 150 profitable traders short HYPE held staked HYPE, and two thirds of the holders' HYPE short value was covered on spot.

Since then tracked traders (profitable traders and large accounts) are counted by net exposure (`backend/hl_hedges.py`):

- a short covered for more than 80% of its size is not counted; a partly covered one counts for its uncovered part; longs are unchanged;
- spot tokens map to perp coins by name (HYPE, PURR), Unit tokens by "U" + coin (UBTC, UETH, USOL; UFART is FARTCOIN), and k markets at 1/1000 (UBONK covers KBONK);
- it applies to the consensus (the signal's tracked-wallet check, approved by the owner), the 4h trader record, the positioning map and Radar, the per-coin lists and the coin chart. Opens, convergences, trader entries and profiles still show the raw positions. The cohort sweep's groups (all-time winners, losers, whales) are not netted (their spot is not read);
- only Hyperliquid is visible: a hedge on another exchange still counts as a short.

Readings: `spotClearinghouseState` (weight 2) for every tracked wallet holding a short, at most once an hour, and `delegatorSummary` (weight 20) when it is short HYPE; up to 60 wallets per HyperLens loop tick, through the "positions" weight budget (about 35 weight a minute). Holdings are kept in hyperlens.db (`wallet_hedges`, a few hundred rows) and reloaded after a restart.

Records: `trader_lean` rows written since carry `roster_version` 3. The switch is a `roster_rebuilds` row with note `hedges`, shown on the coin chart as a dot with its explanation.
