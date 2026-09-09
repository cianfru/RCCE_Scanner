"""Exchange-owned crypto universe. HIP-3 is intentionally managed separately."""
import asyncio
import json
import logging
import os
import time
from pathlib import Path
import aiohttp

log = logging.getLogger(__name__)
MARKETS = {}
UPDATED_AT = None
STALE = True
_PATH = Path(os.environ.get("HL_UNIVERSE_PATH", "/data/hyperliquid_universe.json" if Path("/data").is_dir() else "hyperliquid_universe.json"))


def parse_markets(meta, spot):
    markets = {}
    for asset in meta["universe"]:
        name = asset["name"]
        if asset.get("isDelisted") or ":" in name:
            continue
        symbol = f"{name.upper()}/USDT"  # Existing engine key; HL perps settle in USDC.
        markets[symbol] = {"symbol": symbol, "coin": name, "base": name, "quote": "USDC", "kind": "perpetual"}
    tokens = {t["index"]: t for t in spot["tokens"]}
    # A project with a perp already has an analysis; add one native spot market
    # per remaining token, preferring USDC. Preserve identity for duplicate tickers.
    perp_names = {m["base"].upper() for m in markets.values()}
    seen_tokens = set()
    names = {}
    for token in tokens.values():
        names[token["name"]] = names.get(token["name"], 0) + 1
    pairs = sorted(spot["universe"], key=lambda x: (tokens[x["tokens"][1]]["name"] != "USDC", x["index"]))
    for pair in pairs:
        if pair.get("isDelisted"):
            continue
        base, quote = [tokens[i] for i in pair["tokens"]]
        if base["index"] in seen_tokens or base["name"].upper() in perp_names:
            continue
        seen_tokens.add(base["index"])
        label = base["name"] if names[base["name"]] == 1 else f'{base["name"]}~{base["index"]}'
        symbol = f'{label}/{quote["name"]}'.upper()
        markets[symbol] = {"symbol": symbol, "coin": pair["name"], "base": label, "quote": quote["name"], "kind": "spot", "token_id": base.get("tokenId")}
    if not markets:
        raise ValueError("Hyperliquid returned an empty universe")
    return markets


def apply_universe(cache):
    allowed = set(MARKETS)
    cache.symbols = list(MARKETS)
    cache.results = {tf: [r for r in rows if r.get("symbol") in allowed] for tf, rows in cache.results.items()}
    cache._results_by_sym = {s: r for s, r in cache._results_by_sym.items() if s in allowed}


async def refresh(cache):
    global UPDATED_AT, STALE
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
            async def fetch(kind):
                async with session.post("https://api.hyperliquid.xyz/info", json={"type": kind}) as response:
                    response.raise_for_status()
                    return await response.json()
            meta, spot = await asyncio.gather(fetch("meta"), fetch("spotMeta"))
        markets = parse_markets(meta, spot)
        MARKETS.clear()
        MARKETS.update(markets)
        UPDATED_AT, STALE = time.time(), False
        try:
            _PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp = _PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps({"updated_at": UPDATED_AT, "markets": markets}))
            tmp.replace(_PATH)
        except OSError:
            log.warning("Could not persist Hyperliquid universe")
    except Exception as exc:
        STALE = True
        log.warning("Hyperliquid universe refresh failed: %s", exc)
        if not MARKETS and _PATH.exists():
            try:
                saved = json.loads(_PATH.read_text())
                MARKETS.update(saved["markets"])
                UPDATED_AT = saved["updated_at"]
            except (OSError, ValueError, KeyError):
                pass
    # Fail closed if no verified exchange snapshot exists; never restore legacy groups.
    apply_universe(cache)


async def run_refresh(cache):
    from activity import is_active, idle_sleep
    while True:
        # The tradable universe barely moves at rest, so refresh every 15 min
        # while active but stretch to ~hourly when idle (wakes early on
        # activity). Avoids re-fetching + parsing ~480 markets round the clock.
        if is_active():
            await asyncio.sleep(900)
        else:
            await idle_sleep(3600)
        await refresh(cache)
