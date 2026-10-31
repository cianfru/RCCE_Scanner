"""
Public daily series for research/turn_signs.py (docs/reviews/turn-signs-study.md), fetched once:

- funding: Hyperliquid's funding history for BTC and ETH (from May 2023), summed per UTC day (each record is one
  payment: 8-hourly at first, hourly later), as a yearly rate;
- dvol: Deribit's BTC volatility index (the options market's implied volatility, from April 2021), daily close;
- stables: DefiLlama's total stablecoin supply in USD, daily.

    python -m research.fetch_turn_data --out PATH          (from backend/; network)
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path

DAY_MS = 86_400_000
HL = "https://api.hyperliquid.xyz/info"
DVOL = ("https://www.deribit.com/api/v2/public/get_volatility_index_data?currency=BTC&start_timestamp={a}"
        "&end_timestamp={b}&resolution=1D")
STABLES = "https://stablecoins.llama.fi/stablecoincharts/all"
UA = {"User-Agent": "reflex-research/1.0", "Content-Type": "application/json"}


def _get(url: str, body: dict | None = None):
    data = None if body is None else json.dumps(body).encode()
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, data=data, headers=UA)
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read())
        except Exception:
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"failed: {url}")


def funding(coin: str, start_ms: int, end_ms: int) -> dict:
    """{day: summed funding that day} for one coin."""
    out, t = {}, start_ms
    while t < end_ms:
        rows = _get(HL, {"type": "fundingHistory", "coin": coin, "startTime": t})
        if not rows:
            break
        for r in rows:
            d = int(r["time"]) // DAY_MS
            out[d] = out.get(d, 0.0) + float(r["fundingRate"])
        nxt = int(rows[-1]["time"]) + 1
        if nxt <= t:
            break
        t = nxt
        time.sleep(0.15)
    return out


def dvol(start_ms: int, end_ms: int) -> dict:
    out, a = {}, start_ms
    while a < end_ms:
        b = min(end_ms, a + 500 * DAY_MS)
        for row in _get(DVOL.format(a=a, b=b))["result"]["data"]:
            out[int(row[0]) // DAY_MS] = float(row[4])
        a = b
    return out


def stables() -> dict:
    out = {}
    for row in _get(STABLES):
        v = (row.get("totalCirculatingUSD") or {}).get("peggedUSD")
        if v:
            out[int(row["date"]) // 86_400] = float(v)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    now = int(time.time() * 1000)
    today = now // DAY_MS
    res = {"fetched": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())}
    for coin in ("BTC", "ETH"):
        f = funding(coin, 1_683_000_000_000, now)
        res[f"funding_{coin.lower()}"] = {str(d): round(v * 365, 6) for d, v in sorted(f.items()) if d < today}
    res["dvol"] = {str(d): v for d, v in sorted(dvol(1_617_235_200_000, now).items()) if d < today}
    res["stables"] = {str(d): v for d, v in sorted(stables().items()) if d < today}
    Path(a.out).write_text(json.dumps(res))
    print({k: (len(v), min(v), max(v)) if isinstance(v, dict) else v for k, v in res.items()})


if __name__ == "__main__":
    main()
