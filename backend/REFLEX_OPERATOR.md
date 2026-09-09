# Hyperliquid universe and AI Assist

The crypto scanner discovers active native perpetuals (`meta`) and spot-only tokens (`spotMeta`) at startup and every 15 minutes. A token with a perpetual is shown once. Spot-only tokens keep their native pair ID (`@index` or `PURR/USDC`); duplicate ticker names retain token-index suffixes. HIP-3 remains under TradFi.

`GET /api/universe?timeframe=1d` lists every discovered market and whether analysis is ready. Insufficient history / unavailable candles leave a market awaiting analysis; no synthetic signal is created. Discovery failures retain the last verified disk snapshot with a stale flag. With no snapshot, discovery fails closed. Legacy groups are preserved on disk but no longer control the scanner; their mutation endpoints return 409.

AI Assist uses `OPENROUTER_API_KEY` and the operator setting `REFLEX_ASSISTANT_MODEL` (default `google/gemma-4-31b-it:free`). To replace the model, change this environment variable on Railway and redeploy. It must end in `:free` and be listed with zero prompt/completion/request prices. Unknown, paid or retired models fail closed. No Anthropic or paid fallback is used. The public model-selection endpoint returns 403. The old `OPENROUTER_MODEL` setting is no longer used by this assistant.

Free provider quotas are shared by the backend account, not per visitor. OpenRouter currently documents 20 requests/minute and 50/day, or 1,000/day after at least $10 in lifetime credit purchases. There is no guarantee of unlimited free capacity or ongoing model availability. Do not advertise unlimited AI access. For higher sustained usage, a separately budgeted provider or self-hosted inference is necessary.

Assistant prompts use a fresh, explicitly labelled snapshot from the same scan cache and selected timeframe as the terminal. Missing values remain null. News and old conversation memories are not injected as current market evidence. Generated language can still be mistaken; deterministic scanner values remain authoritative.

Validation: `PYTHONPATH=backend python -m unittest discover -s backend/tests -v` and `npm --prefix frontend run build`.
