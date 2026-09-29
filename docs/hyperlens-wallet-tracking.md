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

**Data.** Each time a tracked wallet's reading differs from its previous one (the cadence's change test), the coins that moved are logged in `position_changes` in hyperlens.db: size before and after, price, and the window between the two readings. Fills are not stored, so timing is at the resolution of the readings. Kept 30 days, about 800 small rows a day for the whole roster (a few MB).

**First start.** The log starts empty, and a group like the BTC wallets trades only a few times a month, so it would take weeks to be recognised. On the first start (empty log only, never again) a background task rebuilds the last 30 days from each roster wallet's fills: one `userFills` request per wallet, about 630 in all, one at a time on the coin-page entries' rate budget (it takes an hour or two), then regroups.

**Rule** (recomputed daily with the roster, and at start, over the last 30 days). Two wallets are linked when all of these hold:

1. **Traded together.** A wallet's changes to one coin in one direction within 2 hours of each other are one move. A move matches the other wallet's move in the same coin and direction within 48 hours. Each wallet has at least 2 matched moves, and at least 70% of each wallet's moves are matched.
2. **Held together.** Each wallet's position in every coin either of them held, in dollars at one price per coin, sampled every 4 hours over the 30 days: the two series correlate at 0.8 or more. Same coins, same side, sizes rising and falling in proportion.

Linked wallets are joined into one group (A with B and B with C make a group of three). The id is `grp-` plus the start of the smallest address.

**Where a group counts once:** consensus counts and trends (`long_count`, per-cohort counts, participation), the positioning map's per-coin `n` (the Radar's "profitable traders net long" and its trails), the price ladder's counts, the 4-hour trader record (`trader_lean`), new-position counts in the last 24 hours and convergences. In the positioning map a group sits on the side of its combined dollars, at its dollar-weighted entry, and is in profit when its combined unrealised PnL is. `usd` fields, `money` and the ladder's dollars still add every wallet. The cohort sweep's Cohorts tab still counts wallets.

**Shown:** `entity` on `/api/hyperlens/wallet/{address}`, `/api/traders/{address}` (id, size, members, note: "Part of a group of 3 wallets that trade together") and on roster, symbol-position and ladder rows (the id). The trader page and the wallet dialog show the note. `/api/hyperlens/status` shows the number of groups.

**Check on real fills.** Replaying the adaptive cadence over the 30 days to 26 September 2026 on the fills of the 573 wallets of the size study: 339,000 readings, 21,000 logged coin changes, 17,000 candidate pairs, 3 pairs passing the traded-together test, and one group of 3: the study's three BTC wallets (0x2371...0883, 0x93ab...11f8, 0xec7f...df39). They made the same three moves up to 31 hours apart; their position series correlate at 0.84 to 0.99.

## Continuity

Changing the cohort moves the Radar's trader counts and the stored lean series.

- `trader_lean` rows (the 4-hour record per coin and group) have a `roster_version` column: 2 from this change on, empty (NULL) before. Split studies on it.
- Cohort snapshots (the Cohorts tab, every 30 minutes) carry `"roster_version": 2` inside their data.
- `position_opens` and `convergences` rows have a `roster_version` column (NULL before). The convergence forward test (docs/reviews/trader-convergence-forward-test.md) was declared on version 1: 300 wallets, $50K accounts, readings every 30 minutes, a 2-hour gap limit (now 2.5 hours, to cover the flat tier). Version 2 rows are a different variant and need their own declaration and count.
- `/api/hyperlens/status` shows `roster_version`, the targets and the cadence.
