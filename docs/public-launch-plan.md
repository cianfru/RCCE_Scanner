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
3. **User accounts.** Per-user follow lists and Telegram alerts. The backend polls the union of followed wallets once (150 users × 5 follows is at most 750 wallets, far fewer in practice) and fans alerts out per user. Cap follows per user.
4. **Rate limits on expensive endpoints** so one user or a bot cannot exhaust the Hyperliquid budget (profiles, fills, history, ladder).
5. **Graceful degradation.** When Hyperliquid is slow or limiting, serve the last stored data with its timestamp instead of empty panels.
6. **Row deltas for the scan.** The scan body changes every pass (~140 KB gzip per pass per visible scanner tab). Send only changed rows (or drop unused fields such as the large `trading_setups` block from the list view) for about another 80% less.

Expected result: about $10–20 a month in total for 150 active users, and no Hyperliquid limit problems.

## Not needed while the app has one user

None of the above is needed today. Revisit this file when the launch date is set.
