# Position Monitor & TG Push Notifications — Implementation Plan

## Overview

Two features:
1. **Active Position Monitoring** — Track user's open Hyperliquid positions and push TG alerts when regime/signal changes affect held coins
2. **Signal Change Alerts** — Push TG notifications when any scanned pair changes signal (e.g. LIGHT_LONG → WAIT), with periodic overview summaries

## Architecture

### New file: `backend/position_monitor.py`

A singleton `PositionMonitor` that:
- Stores registered wallet addresses + their linked TG chat IDs (persisted to JSON)
- Every scan cycle, fetches open HL positions for each registered address via the public Hyperliquid API (`clearinghouseState`)
- Compares current scan results against positions: detects regime changes and signal transitions for held coins
- Sends targeted TG push notifications for:
  - **Regime changes** on positions the user holds (e.g. "⚠️ BTC regime changed: MARKUP → DISTRIBUTION — you have a $5,200 LONG open")
  - **Signal downgrades** on held positions (e.g. "🔻 ETH signal downgraded: LIGHT_LONG → TRIM — consider reducing exposure")
  - **Signal upgrades** on held positions (e.g. "🟢 SOL signal upgraded: WAIT → LIGHT_LONG")
  - **New opportunities** — any pair going to STRONG_LONG or LIGHT_LONG (configurable)
- Sends periodic **portfolio overview** (every 6h or on-demand via `/overview` command)

### Changes to existing files

**`backend/telegram_bot.py`** — Add new commands:
- `/watch <wallet_address>` — Register wallet for monitoring (links to current TG chat)
- `/unwatch` — Stop monitoring
- `/positions` — Show current open HL positions with scanner context (regime, signal, conditions)
- `/overview` — Full portfolio overview: open positions + their signals + market context + opportunities

**`backend/scanner.py`** — After `log_signals()`, call `position_monitor.on_scan_complete()` to trigger notification checks

**`backend/main.py`** — Initialize PositionMonitor in lifespan, add API endpoint `POST /api/monitor/register` for frontend registration

**`backend/hyperliquid_data.py`** — Add `fetch_clearinghouse_state(address)` function to fetch user positions from HL public API (no auth needed — just the address)

### Notification format examples

**Regime change on held position:**
```
⚠️ REGIME CHANGE — BTC
MARKUP → DISTRIBUTION
You hold: LONG 0.15 BTC ($9,420) @ 3x
Signal: LIGHT_LONG → TRIM
Action: Consider reducing exposure
```

**Signal opportunity:**
```
🟢 NEW OPPORTUNITY — HYPE
Signal: WAIT → STRONG_LONG
Regime: ACCUMULATION | Z: -0.8 | Heat: 22
Conditions: 7/8 met | Confluence: STRONG
```

**Portfolio overview (/overview):**
```
📊 PORTFOLIO OVERVIEW

Open Positions (3):
├ BTC LONG 0.15 @ $62,400 (3x) — PnL: +$312
│ Signal: LIGHT_LONG | Regime: MARKUP | Heat: 45
├ ETH LONG 2.1 @ $3,180 (2x) — PnL: -$84
│ Signal: WAIT | Regime: ACCUMULATION | Heat: 28
└ SOL SHORT 40 @ $148 (5x) — PnL: +$160
  Signal: TRIM | Regime: DISTRIBUTION | Heat: 71

Alerts:
⚠️ ETH signal downgraded to WAIT — no active long bias
⚠️ SOL heat elevated (71) — exhaustion risk

Top Opportunities:
🟢 HYPE — STRONG_LONG (7/8 conditions)
🟢 AVAX — LIGHT_LONG (6/8 conditions)
```

## Data flow

```
Scanner (every 5 min)
  └─→ log_signals() [existing — detects changes]
  └─→ PositionMonitor.on_scan_complete(results, changes)
        ├─→ For each registered wallet:
        │     ├─→ Fetch HL positions (cached 60s)
        │     ├─→ Cross-reference held coins with signal/regime changes
        │     └─→ Send TG notifications for relevant changes
        └─→ Check if periodic overview is due (every 6h)
              └─→ Send overview to all registered chats
```

## Implementation steps

1. Add `fetch_clearinghouse_state(address)` to `hyperliquid_data.py`
2. Create `backend/position_monitor.py` with PositionMonitor class
3. Update `telegram_bot.py` with /watch, /unwatch, /positions, /overview commands
4. Hook PositionMonitor into scanner.py post-scan flow
5. Wire up initialization in main.py lifespan
6. Add frontend registration option (optional — can use TG /watch for now)

## Persistence

Registered wallets stored in `data/monitor_registry.json`:
```json
{
  "watchers": [
    {
      "chat_id": 123456789,
      "address": "0xabc...",
      "registered_at": 1710000000,
      "notify_regime_changes": true,
      "notify_signal_changes": true,
      "notify_opportunities": true,
      "overview_interval_hours": 6,
      "last_overview_ts": 1710000000
    }
  ]
}
```

## Key design decisions

- **No API keys needed**: HL clearinghouse state is a public read endpoint (just needs wallet address)
- **Notification deduplication**: Track last-notified signal/regime per symbol per chat to avoid spam
- **Rate limiting**: Max 10 notifications per scan cycle per chat; batch if more
- **Overview cadence**: Every 6 hours by default, adjustable. Also on-demand via /overview
- **Opportunity filter**: Only notify for STRONG_LONG and LIGHT_LONG by default (configurable)
