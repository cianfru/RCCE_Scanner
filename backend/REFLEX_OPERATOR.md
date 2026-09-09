# Hyperliquid universe and AI Assist

The crypto scanner discovers active native perpetuals (`meta`) and spot-only tokens (`spotMeta`) at startup and every 15 minutes. A token with a perpetual is shown once. Spot-only tokens keep their native pair ID (`@index` or `PURR/USDC`); duplicate ticker names retain token-index suffixes. HIP-3 remains under TradFi.

`GET /api/universe?timeframe=1d` lists every discovered market and whether analysis is ready. Insufficient history / unavailable candles leave a market awaiting analysis; no synthetic signal is created. Discovery failures retain the last verified disk snapshot with a stale flag. With no snapshot, discovery fails closed. Legacy groups are preserved on disk but no longer control the scanner; their mutation endpoints return 409.

AI Assist uses `OPENROUTER_API_KEY` and the operator setting `REFLEX_ASSISTANT_MODEL` (default `google/gemma-4-31b-it:free`). To replace the model, change this environment variable on Railway and redeploy. It must end in `:free` and be listed with zero prompt/completion/request prices. Unknown, paid or retired models fail closed. No Anthropic or paid fallback is used. The public model-selection endpoint returns 403. The old `OPENROUTER_MODEL` setting is no longer used by this assistant.

Free provider quotas are shared by the backend account, not per visitor. OpenRouter currently documents 20 requests/minute and 50/day, or 1,000/day after at least $10 in lifetime credit purchases. There is no guarantee of unlimited free capacity or ongoing model availability. Do not advertise unlimited AI access. For higher sustained usage, a separately budgeted provider or self-hosted inference is necessary.

Assistant prompts use a fresh, explicitly labelled snapshot from the same scan cache and selected timeframe as the terminal. Missing values remain null. News and old conversation memories are not injected as current market evidence. Generated language can still be mistaken; deterministic scanner values remain authoritative.

Validation: `PYTHONPATH=backend python -m unittest discover -s backend/tests -v` and `npm --prefix frontend run build`.

## Scan resource budget

`scan_schedule.py` schedules one market at a time, at most one start per second.
All verified listings receive an initial attempt. Subsequent candle checks use
wall-clock intervals: favorites and BTC/ETH 15 min; ordinary perps and
spot-only 60 min; cold 60 min; deep cold 4 h. Failed or unavailable-history checks
back off to at least 60 min. Idle periods impose a 60 min minimum. Intervals are
minimum spacing, not freshness guarantees: startup and queue load add delay.
Oldest attempts run first to avoid starvation. Listing removal prunes scheduling
state. The 60-second synthesis and existing position monitoring are unchanged;
prices update independently. Slower candle refresh can delay new signal discovery.

This limits incremental scanning work, not total Railway spend. The September 9
production snapshot used about 367 MB RSS, with about 26 MB in scanner/OHLCV data;
runtime and other background services contribute to the baseline. Compare Railway
CPU, memory and egress over a full day before and after release. A free allowance
is not guaranteed. No billing limits, service plans or execution settings change.


## Token membership and personal watchlists: next implementation boundary

The existing favorites store is global. It is not wallet authentication or a
private user watchlist. Do not use a wallet address supplied by the client as
proof of ownership. Before launching membership:

- Authenticate with a signed, single-use, expiring wallet challenge bound to the
  app domain and chain, then issue a secure session.
- Verify the required token balance server-side using the confirmed token
  contract/network and access threshold. Cache checks briefly with explicit
  expiry and recheck access; holding a token is not permission to move it.
- Store favorites by authenticated wallet. Enforce an operator-configured limit
  per wallet and derive a deduplicated priority set from eligible memberships.
  Personal list visibility and changes must never mutate another user's list.
- Run one shared scan per market/timeframe, irrespective of the number of users
  following it. Never start a scanner per wallet or per browser connection.
- Retain a bounded global worker/refresh budget as favorites grow. The 15-minute
  priority target is best effort, not a contractual freshness guarantee. Show
  actual candle-check times and retain hourly broad-market discovery.
- Separate app preferences from the existing global favorites used by Telegram
  alerts/execution. Do not expose execution privileges through membership.

The token network/contract, required balance, per-wallet favorite allowance and
membership recheck/grace rules must be settled before enabling this layer. A
permanent free AI/provider or hosting allowance cannot be guaranteed by gating.
