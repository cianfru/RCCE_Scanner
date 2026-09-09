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


def parse_markets(meta, spot, contexts=None):
    markets = {}
    for asset in meta["universe"]:
        name = asset["name"]
        if asset.get("isDelisted") or ":" in name:
            continue
        symbol = f"{name.upper()}/USDT"  # Existing engine key; HL perps settle in USDC.
        markets[symbol] = {"symbol": symbol, "coin": name, "base": name, "quote": "USDC", "kind": "perpetual"}
    tokens = {t["index"]: t for t in spot["tokens"]}
    # Keep perpetual and spot identities distinct; prefer one USDC pair per token.
    from spot_quality import volume_reason
    context_by_coin = {c["coin"]: c for c in (contexts or [])}
    seen_tokens = set()
    names = {}
    for token in tokens.values():
        names[token["name"]] = names.get(token["name"], 0) + 1
    pairs = sorted(spot["universe"], key=lambda x: (tokens[x["tokens"][1]]["name"] != "USDC", x["index"]))
    for pair in pairs:
        if pair.get("isDelisted"):
            continue
        base, quote = [tokens[i] for i in pair["tokens"]]
        if base["index"] in seen_tokens:
            continue
        seen_tokens.add(base["index"])
        label = base["name"] if names[base["name"]] == 1 else f'{base["name"]}~{base["index"]}'
        symbol = f'{label}/{quote["name"]}'.upper()
        markets[symbol] = {"symbol": symbol, "coin": pair["name"], "base": label, "quote": quote["name"], "kind": "spot", "token_id": base.get("tokenId")}
        market = markets[symbol]
        market["volume_24h_usd"] = context_by_coin.get(pair["name"], {}).get("dayNtlVlm")
        market["exclusion_reason"] = volume_reason(market)
    if not markets:
        raise ValueError("Hyperliquid returned an empty universe")
    return markets


def apply_universe(cache):
    from spot_quality import volume_reason
    allowed = {s for s, m in MARKETS.items() if not volume_reason(m)}
    cache.symbols = [s for s in MARKETS if s in allowed]
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
            meta, spot_data = await asyncio.gather(fetch("meta"), fetch("spotMetaAndAssetCtxs"))
        markets = parse_markets(meta, spot_data[0], spot_data[1])
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
    while True:
        await asyncio.sleep(900)
        await refresh(cache)
