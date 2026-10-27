# Hosting costs (Railway)

Written 27 October 2026, after the Sep 27 – Oct 27 cycle: the backend cost $18.76. RAM averaged about 1.4 GB, rising from about 1 GB to 1.7 GB over the month. Egress was 71 GB, almost all of it in the first three days.

## What Railway bills

| Resource | Price | This service |
|---|---|---|
| RAM | about $10 per GB-month | the bill |
| vCPU | about $20 per vCPU-month | about 0.05 vCPU on average, about $1 |
| Egress | $0.05 per GB | about 0.3 GB a month since #183 and #189 (the 71 GB was the full-state WebSocket push before them) |
| Volume | about $0.15 per GB-month | under 1 GB |

## Where the RAM goes

Railway's memory figure is the container's cgroup memory. That includes the kernel's **page cache**: every page of a volume file the app has read or written stays charged until the kernel needs the room. A service with a volume cannot have a memory limit, so the kernel never needs the room.

The growing files are:
- `fills.db`, about 270 MB;
- `hyperlens.db`, about 140 MB;
- `opportunities.db`, about 1,500 full scan rows a day;
- `cohorts.db`;
- the OHLCV pickle, 27 MB, rewritten every 10 minutes.

These made the bill grow with uptime. The process itself, RSS, was 560–580 MB and flat.

Since the October change (`backend/memlog.py`):

- **Page-cache release.** Every 5 minutes the clean cached pages of the volume's files are dropped with `posix_fadvise(DONTNEED)`. Nothing on disk changes, and SQLite re-reads what it needs. Descriptors of SQLite database files stay open for the life of the process, because closing one would release SQLite's locks.
- **One log line every 10 minutes**, also shown under `container` in `/api/admin/memory-snapshot`:
  ```
  memlog rss=.. anon=.. | cgroup=.. anon=.. file=.. (active, inactive, mapped) | released=.. | heap allocated=.. resident=.. | volume=.. (largest files) | threads=.. up=..h
  ```
  `cgroup` is the figure Railway charges. `cgroup file` is the page cache. `rss` and `heap` are the process's own memory.
- **Libraries no longer loaded in the server:**
  - ccxt: the Bybit fallback is now one REST call.
  - yfinance and pandas: HIP-3 has no DXY or VIX candles, so every TradFi pass still needs yfinance. It now runs in a short-lived child process (`backend/yf_source.py`). When the child exits, the server drops the cached pages of the library files it read (about 40 MB).

  Together that is about 90 MB of the server's own memory. Each child costs about 165 MB for a few seconds, 2–3 times per TradFi pass.
- **jemalloc** runs with `background_thread:true,max_background_threads:1,narenas:2`, so freed memory goes back to the OS.
- **View caches** (trader profiles, stored fills, portfolio answers, clearinghouse states) drop entries once they are past their reuse window.

## Settings

| Variable | Default | Effect |
|---|---|---|
| `MEMLOG` | on | `0` stops the log line |
| `MEMLOG_INTERVAL_S` | 600 | seconds between log lines |
| `CACHE_RELEASE` | on | `0` stops the page-cache release |
| `CACHE_RELEASE_S` | 300 | seconds between releases |
| `MALLOC_CONF` | set in the Dockerfile | jemalloc options |

## Not done, and why

- **Railway cron jobs.** The service must stay up: it runs the drip scan, wallet tracking, alerts, the WebSocket and the API. Every periodic job feeds in-process state, and a volume attaches to one service only. So no job is worth a separate cron service.
- **float32 candles.** That would save about 11 MB, but it changes engine outputs that reach signals and the executor.
- **Pruning OHLCV series of markets no longer scanned.** About 16 MB. The executor's price guard and the position monitor read stored candles for symbols that can be outside the scan, and the executor stays as it is.
- **Compressing `opportunities.db` rows.** About 4× smaller. It changes the stored format the research tools read. With the page-cache release the file no longer costs RAM, only volume space (cents).
- **The paper-ledger reload and the executor state rewrite.** Both need the owner's approval: paper and live trading code.
- **Idle mode while only hidden tabs are open.** Counting only visible tabs would cut CPU, but it would also slow the synthesis pass, where the executor's stop checks and the position alerts run. So an open hidden tab still keeps the app on the active cadence.
