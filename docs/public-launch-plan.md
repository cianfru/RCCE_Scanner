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

1. **Edge cache in front of the API.** *Done (30 September 2026), off until the owner switches it on (checklist below).* The heavy read-only feeds (`/api/scan`, its sparklines and single rows, `/api/setup-map`, `/api/market-history`, `/api/hyperlens/consensus`, `/api/hyperlens/positioning`, `/api/traders/leaderboard`, `/api/tradfi`, `/api/universe`, `/api/sectors`) go through Vercel: the page asks `/edge/api/...` on its own host, `frontend/vercel.json` rewrites that to Railway, and Vercel's CDN keeps each answer 30 s, serves it 30 s more while refetching, and up to 10 minutes when Railway errors. ETags are kept. Cached copies are only reachable with the same access a direct request needs, and never for requests that carry a login token. The scan URL carries the pass a scan notice announced, so nobody gets an older scan after a notice. Everything else, and the WebSocket, stays direct to Railway. Chosen over Cloudflare because it needs no DNS change and no new service; Cloudflare stays the fallback if Vercel's included transfer runs short (see backend/edge.py). 150 users then cost roughly one user's egress from Railway per Vercel region.
2. **Store trader fills in our database.** Trader profiles call Hyperliquid `userFills`, which weighs about ten times a position read; only ~60 uncached profile loads a minute fit the budget. Keep each tracked wallet's fills in SQLite and fetch only new ones (`userFillsByTime` since the last stored fill); serve profiles from the database; share one cached profile across users for a few minutes; per-user limit on uncached profile loads.
3. **User accounts.** Per-user follow lists and Telegram alerts. The backend polls the union of followed wallets once (150 users × 5 follows is at most 750 wallets, far fewer in practice) and fans alerts out per user. Cap follows per user. **Built, switched off** (see "Accounts and access tiers" below).
4. **Rate limits on expensive endpoints** so one user or a bot cannot exhaust the Hyperliquid budget (profiles, fills, history, ladder). *Done (30 September 2026).* Per-client token buckets, in memory (backend/ratelimit.py): trader profiles, fills and history 30 at once then 20 a minute per client (120 a minute for everyone together); every other endpoint that reads an exchange per request (ladder, chart, a wallet's positions, cross-exchange...) 60 then 60 a minute (600 a minute together); changes (POST, PUT, PATCH, DELETE) 60 then 60 a minute. Chat, briefing and explain keep their own limits. Over the limit: 429 with Retry-After. Refusals per class show in `/api/net-stats` (`rate_limited`).
5. **Graceful degradation.** When Hyperliquid is slow or limiting, serve the last stored data with its timestamp instead of empty panels. *Done (30 September 2026).* The scan was already served from memory; it now carries `as_of` (the last completed pass) and `stale`. Consensus, positioning, the Radar map, the leaderboard and market history keep their last good body and serve it, marked `stale` with its time, when a rebuild fails or comes back empty (backend/degrade.py). Trader-positioning feeds date from the newest wallet reading, so they turn stale by themselves when reads stop. Pages show a small muted "as of HH:MM" only then; the scanner's header clock already shows the scan's age. The CDN also serves its last copy for 10 minutes when Railway errors.
6. **Row deltas for the scan.** The scan body changes every pass (~140 KB gzip per pass per visible scanner tab). Send only changed rows (or drop unused fields such as the large `trading_setups` block from the list view) for about another 80% less. *Done (30 September 2026), by slimming, not deltas:* every row changes every pass (evaluation time, positioning), so deltas would save little. `/api/scan?view=list` leaves out fields no page reads and per-coin detail (backend/scan_view.py); the sparklines, which change only when a candle closes, have their own feed (an empty 304 between candles); the coin page and the detail panel load one coin's full row. Measured on production data (208 rows): 141 KB → 30 KB gzip per timeframe per pass, 78% less. The WebSocket's signal transitions to current pages are headlines instead of full rows.

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
5. The edge cache (item 1) never serves requests that carry an account session, and signed-in pages read the Radar map directly, so the live and delayed maps are never mixed.

To switch off, unset `ACCESS_TIERS` (everything open again) or `REFLEX_ACCOUNTS` (back to single-owner). Accounts, follows and links stay in `accounts.db` for next time.

## Owner checklist (items 1, 4, 5, 6)

Nothing changes for users until the first two steps; each switch rolls back on its own.

1. Deploy the frontend (Vercel) and the API (Railway) from this branch. With `EDGE_CACHE` unset the pages call Railway directly, as before.
2. On Railway set `EDGE_CACHE=1`. Pages pick it up within 10 minutes (no redeploy).
3. Check it: open the scanner, then in the browser's network panel the `/edge/api/scan?...` requests should show `x-vercel-cache: HIT` or `STALE` after the first one, and `/api/net-stats` on Railway should show `/api/scan` requests growing with passes, not with tabs.
4. In Vercel, Usage: watch Fast Data Transfer and Edge Requests for the first days. If the included amounts run short, the options are Vercel Pro or putting Cloudflare (free) in front instead; the API's cache headers work for both.
5. Roll back: `EDGE_CACHE=0` on Railway (pages go direct within 10 minutes), or build the frontend with `VITE_EDGE_CACHE=0`. Rate limits: `RATE_LIMIT=0`. The list view needs no switch; older pages keep the full scan.
6. Optional tuning (Railway variables): `EDGE_TTL_S` (30), `EDGE_SWR_S` (30), `EDGE_STALE_IF_ERROR_S` (600), `EDGE_KEY_WINDOW_S` (21600); `RATE_LIMIT_TRADER`, `RATE_LIMIT_EXCHANGE`, `RATE_LIMIT_WRITE` as `burst/per_minute` (`off` removes one), each with a `_GLOBAL` twin for all clients together; `RATE_LIMIT_CLIENT_IP` (`xff-first`, `xff-last`, `real-ip`, `peer`) if the platform's forwarding headers change; `DEGRADE_SCAN_STALE_S` (900), `DEGRADE_POSITIONS_STALE_S` (1200).

### Measured (30 September 2026)

| | Before | After |
|---|---|---|
| Scan pass, one timeframe (gzip, headers included) | 141 KB | 30 KB list + 78 B sparkline 304 (17 KB once per closed candle) |
| One visible scanner tab, scan bytes per hour | ~8.5 MB | ~1.8 MB |
| Requests a minute, one visible scanner tab (counted from the page's polling) | ~6.5 | ~7.5 (one more, the sparkline check, mostly an empty 304) |
| Scan requests reaching Railway, N visible tabs, CDN on | ~N a minute per timeframe | a few a minute per timeframe and Vercel region in use, whatever N is |

Bytes are measured through the API (gzip and ETag middlewares) with a production scan of 208 rows; the per-hour figure assumes one pass a minute.

## Invites and usage (the Intel page)

For the invite-only beta: who uses Reflex, how much, from where and which features, so the next steps are decided from numbers.

**Invite codes.** The owner creates one code per person on `/intel` (Invites tab): a label (the person's name), optionally an expiry, copy, revoke. The login screen is unchanged and takes either the shared access code or an invite code. The session token names the invite, so every session belongs to a person; revoking a code, or its expiry, ends its sessions. The shared code keeps working and shows as "shared code" (everyone on it counts as one person).

**What is recorded.** Page views (Scanner, Radar, Traders, a coin page, a trader profile, the other pages by name) and a few actions (search, the Radar's Long/Short/Both, follow, watch, Telegram link, wallet sign-in, theme switch), as counts per day and person, not a click log. Per session: the day, first and last event, country and city, device class (phone, tablet, desktop) and browser family. Per person: first and last seen, wallet signed in yes/no, Telegram linked yes/no. No IP address, user agent, wallet address or coin is stored. Kept 180 days.

**How it travels.** The app queues events and sends one small batch a minute while the tab is visible, plus one when it is hidden (`sendBeacon`), to `POST /api/usage/beacon` (`usage_api.py`, SQLite `usage.db` on the data volume). It does not depend on API logs, so it keeps working behind the edge cache. A browser holding the admin key (the owner's) is not counted.

**Location.** The API is called on Railway directly, so its requests carry no location. The first batch of each session goes through the app's own site instead (`/u/beacon`, a rewrite in `frontend/vercel.json`), which passes Vercel's country and city to the API; later batches go direct. That is one Vercel request per session. If the rewrite is missing, an optional lookup (`REFLEX_USAGE_GEO_LOOKUP=1`) asks a public IP-location service once per visitor per day.

**The page.** `/intel` is listed under More only in the owner's browser and answers only to the admin key (or the owner's wallet session while accounts are on). Top line: active today, 7 and 28 days, logged in out of invited, and the beta bar: the share of people still active in their fourth week (with an (i) on how it is counted). Charts: daily active people (90 days) and a weekly retention grid. Tabs: People (sortable), Features (use, and returning vs one-time people), Places (countries, devices), Invites.

**Cost.** One request a minute per visible tab at most, a few hundred bytes each, and nothing while hidden; the database is a few MB for a beta.

| Variable | Default | What it does |
|---|---|---|
| `REFLEX_USAGE` | on | `0` stops recording (the page still shows what was kept) |
| `REFLEX_USAGE_DAYS` | 180 | How long sessions and counts are kept |
| `REFLEX_USAGE_TZ` | Europe/Rome | The time zone of a "day" |
| `REFLEX_USAGE_GEO_LOOKUP` | off | The fallback location lookup |
| `VITE_USAGE` (Vercel) | on | `0` stops the app sending anything |

## Not needed while the app has one user

None of the above is needed today. Revisit this file when the launch date is set.
