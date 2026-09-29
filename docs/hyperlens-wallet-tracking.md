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

## Continuity

Changing the cohort moves the Radar's trader counts and the stored lean series.

- `trader_lean` rows (the 4-hour record per coin and group) have a `roster_version` column: 2 from this change on, empty (NULL) before. Split studies on it.
- `/api/hyperlens/status` shows `roster_version` and the targets.
