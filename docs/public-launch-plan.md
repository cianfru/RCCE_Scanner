# Public launch plan

What has to be done before Reflex is opened to many users (for example 150 people at the same time). Written 29 September 2026, when the app had one user and cost about $4–14 a month on Railway.

## Two costs, two drivers

| Cost | Grows with | Limit |
|---|---|---|
| Hyperliquid reads (free, rate-limited per server IP) | number of wallets tracked | Hyperliquid's per-IP request weight budget |
| Railway bill (mostly network egress) | number of users and how long they keep the app open | money |

The design rule is **fetch once, serve everyone**: wallets are read once into the backend's cache and every user is served that copy. Users must never trigger their own Hyperliquid reads except where unavoidable (trader profiles), and those must be cached and rate-limited.

## Where things stand (after PR #183)

- 621 wallets tracked: 600 profitable traders, 60 large accounts (39 in both), adaptive read cadence (followed 5 min, changed 10 min, unchanged 15→60 min, flat 2 h, elite ≥15 min). About 60 position reads a minute in steady state.
- Egress cut ~90%: ETag/304 on JSON GETs, the WebSocket sends notices and price ticks only (every 5 s, visible tabs only), the worker polls only the feeds on screen. About 9 MB an hour per visible scanner tab; hidden tabs ~0.
- `GET /api/net-stats` shows bytes sent per route and per WebSocket event; `/api/hyperlens/status` shows `api_calls` per type.
- Follows are single-owner (no user accounts).

## Projected egress after PR #183

| Scenario | Egress / month | Cost at Railway rates |
|---|---|---|
| One user | ~5–10 GB | ~$0.50 |
| 150 users, ~2 h a day each | ~80 GB | ~$4 |
| 150 users, ~8 h a day each | ~320 GB | ~$16 |

## To do before a public launch, in this order

1. **Edge cache in front of the API.** Put Vercel's edge or Cloudflare in front of the heavy read-only endpoints (`/api/scan`, `/api/setup-map`, `/api/market-history`, `/api/hyperlens/consensus`, `/api/hyperlens/positioning`, `/api/traders/leaderboard`) with a short TTL (about 30 s) and the existing ETags. 150 users then cost roughly one user's egress from Railway; Cloudflare does not charge for egress.
2. **Store trader fills in our database.** Trader profiles call Hyperliquid `userFills`, which weighs about ten times a position read; only ~60 uncached profile loads a minute fit the budget. Keep each tracked wallet's fills in SQLite and fetch only new ones (`userFillsByTime` since the last stored fill); serve profiles from the database; share one cached profile across users for a few minutes; per-user limit on uncached profile loads.
3. **User accounts.** Per-user follow lists and Telegram alerts. The backend polls the union of followed wallets once (150 users × 5 follows is at most 750 wallets, far fewer in practice) and fans alerts out per user. Cap follows per user. **Built, switched off** (see "Accounts and access tiers" below).
4. **Rate limits on expensive endpoints** so one user or a bot cannot exhaust the Hyperliquid budget (profiles, fills, history, ladder).
5. **Graceful degradation.** When Hyperliquid is slow or limiting, serve the last stored data with its timestamp instead of empty panels.
6. **Row deltas for the scan.** The scan body changes every pass (~140 KB gzip per pass per visible scanner tab). Send only changed rows (or drop unused fields such as the large `trading_setups` block from the list view) for about another 80% less.

Expected result: about $10–20 a month in total for 150 active users, and no Hyperliquid limit problems.

## Accounts and access tiers (item 3)

Built behind flags that are off, so production behaves as before until they are set.

**Tiers the owner chose.** Free: the scanner and the Radar as it was an hour ago. Holder (holds the Reflex token on Hyperliquid): the live Radar and its price ladder, alerts (watched coins), following traders, trader profiles, Telegram and the daily brief.

**What exists**

- Sign in with a wallet from the header (not the login screen, which is unchanged): the wallet signs a sign-in message (EIP-4361 style), the backend checks it with `eth-account` and returns a session the app sends on the few account-aware requests. No wallet SDK: the browser wallet (MetaMask, Rabby) is used directly.
- Accounts in one SQLite file on the data volume (`accounts.db`), created on first sign-in. Per account: up to 10 followed traders and 30 watched coins (`/api/me/follows`, `/api/me/watch`, same shapes as the owner's endpoints).
- The owner's account (`REFLEX_OWNER_ADDRESS`) is the existing data: the owner's followed traders, watch list and Telegram chat are used as they are, nothing is copied. Without that variable the app keeps the single-owner behaviour.
- Telegram per account: the account menu shows a one-time code, the user sends `/start <code>` to the bot, and that chat receives the account's alerts (`/unlink` stops it). Quiet hours and the daily brief can be set in the menu; the daily cap, once-a-day dedupe and held alerts are the same rules as the owner's (`tg_alerts.gate`).
- Fetch once, serve everyone: followed wallets are read once whoever follows them (only tracked wallets are read, as today); each change is stored once and fanned out to each follower. Watched coins are checked every five minutes against the one shared Radar map. The brief is gathered and drawn once and sent per account.
- Tiers (`tiers.py`): holder when the address is in the allowlist or holds at least the threshold of the token on Hyperliquid spot (HyperCore), read from Hyperliquid's public info API (`spotClearinghouseState`, one read per address per 10 minutes at most). A HyperEVM balance check can be added later if the token lives there.
- Free Radar: `/api/setup-map` for the free tier returns a copy of the map at least `REFLEX_FREE_RADAR_DELAY_MIN` old, kept on the data volume so a restart does not empty it. In the app, holder features show a quiet locked line with an (i) on how to get access.

**Flags (Railway variables), all unset today**

| Variable | Default | What it does |
|---|---|---|
| `REFLEX_ACCOUNTS` | off | Wallet sign-in, per-account lists and Telegram |
| `ACCESS_TIERS` | off | Gates holder features (needs `REFLEX_ACCOUNTS`) |
| `REFLEX_OWNER_ADDRESS` | unset | The owner's wallet: its account is the existing single-owner data, and it is a holder |
| `REFLEX_HOLDER_ALLOWLIST` | unset | Comma-separated addresses treated as holders (testers) |
| `REFLEX_TOKEN_NAME` / `REFLEX_TOKEN_INDEX` | unset | The spot token to check, by name (or by token index) |
| `REFLEX_TOKEN_MIN` | unset | Holder threshold, in tokens |
| `REFLEX_FREE_RADAR_DELAY_MIN` | 60 | Age of the free Radar |
| `REFLEX_FOLLOW_CAP` / `REFLEX_WATCH_CAP` | 10 / 30 | Per-account limits |
| `REFLEX_SIWE_DOMAINS` | host of `REFLEX_APP_URL` | The app's host names allowed in the sign-in message |
| `REFLEX_SESSION_DAYS` | 30 | Session length |
| `TELEGRAM_BOT_USERNAME` | from the bot | For the "open" link next to the code |

On Vercel, `VITE_ACCOUNTS=1` adds the header's Sign in entry (a separate 1 KB chunk); without it the app makes no account requests.

**Turning it on**

1. Railway: set `REFLEX_OWNER_ADDRESS` to the owner's wallet, `REFLEX_ACCOUNTS=1`, and `REFLEX_SIWE_DOMAINS` if the app is served from more than its main domain. Vercel: set `VITE_ACCOUNTS=1` and redeploy.
2. Sign in with the owner's wallet: the Following tab and watch list are the same as before. Link a tester's Telegram from the menu and follow a trader to check alerts arrive.
3. When the token exists: set `REFLEX_TOKEN_NAME` (or `REFLEX_TOKEN_INDEX`) and `REFLEX_TOKEN_MIN`; add testers to `REFLEX_HOLDER_ALLOWLIST`.
4. Set `ACCESS_TIERS=1`. Signed-out and free visitors then see the delayed Radar and locked holder features; the owner and holders see everything.
5. Before opening the doors, the edge cache (item 1) must not share `/api/setup-map` between tiers: bypass the cache for requests carrying the account session, or leave that one path uncached.

To switch off, unset `ACCESS_TIERS` (everything open again) or `REFLEX_ACCOUNTS` (back to single-owner). Accounts, follows and links stay in `accounts.db` for next time.

## Not needed while the app has one user

None of the above is needed today. Revisit this file when the launch date is set.
