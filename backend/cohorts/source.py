"""Where wallet states come from.

ApiSource polls clearinghouseState (weight 2) per wallet. A future hl-node snapshot
reader only has to implement the same fetch() (or override fetch_many) to replace it.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

import aiohttp

HL_INFO_URL = "https://api.hyperliquid.xyz/info"
WEIGHT = 2                     # clearinghouseState, per Hyperliquid's rate-limit docs


class RateLimited(Exception):
    pass


Raw = Tuple[float, List[Tuple[str, float, bool]]]      # (perp equity, [(coin, usd, long)])


def parse(data: dict) -> Raw:
    from hl_intelligence import _normalize_coin
    equity = float((data.get("marginSummary") or {}).get("accountValue", 0) or 0)
    positions = []
    for ap in data.get("assetPositions", []) or []:
        p = ap.get("position", {}) or {}
        szi = float(p.get("szi", 0) or 0)
        if not szi:
            continue
        usd = abs(float(p.get("positionValue", 0) or 0)) or abs(szi) * float(p.get("entryPx", 0) or 0)
        positions.append((_normalize_coin(p.get("coin", "")), usd, szi > 0))
    return equity, positions


class ApiSource:
    weight = WEIGHT

    def __init__(self, session: aiohttp.ClientSession, on_raw=None):
        self.session = session
        self.on_raw = on_raw            # (address, raw response): lets HyperLens reuse the same poll

    async def fetch(self, address: str) -> Optional[Raw]:
        try:
            async with self.session.post(HL_INFO_URL, json={"type": "clearinghouseState", "user": address}) as resp:
                if resp.status == 429:
                    raise RateLimited()
                if resp.status != 200:
                    return None
                data = await resp.json(content_type=None)
            if self.on_raw is not None:
                try:
                    self.on_raw(address, data)
                except Exception:
                    pass
            return parse(data)
        except RateLimited:
            raise
        except Exception:
            return None
