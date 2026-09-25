"""Binance spot kline history for offline studies (completed bars only).

Uses Binance's public market-data mirror (data-api.binance.vision), which is
reachable where api.binance.com is geo-restricted. Pairs that were delisted
and later re-used a ticker (old LUNA) are read from the monthly archive dumps
on data.binance.vision instead. Results are cached per pair/interval as CSV
under ``backend/data/larsson_cache/`` (gitignored) so studies are
reproducible offline once fetched.
"""
from __future__ import annotations

import csv
import io
import json
import os
import ssl
import time
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

import numpy as np

API = "https://data-api.binance.vision/api/v3/klines"
ARCHIVE = "https://data.binance.vision/data/spot/monthly/klines/{sym}/{iv}/{sym}-{iv}-{ym}.zip"
INTERVAL_MS = {"1d": 86_400_000, "4h": 14_400_000, "1w": 604_800_000}
CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "larsson_cache"
FIELDS = ("timestamp", "open", "high", "low", "close", "volume")


def _ssl_context() -> ssl.SSLContext:
    cafile = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    return ssl.create_default_context(cafile=cafile) if cafile else ssl.create_default_context()


def _get(url: str, retries: int = 4) -> bytes:
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=30, context=_ssl_context()) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if 400 <= exc.code < 500 and exc.code != 429:   # bad/unknown symbol: retrying cannot help
                raise
            if attempt == retries - 1:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries - 1:
                raise
        time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


def _to_ms(date: str) -> int:
    return int(datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)


def _rows_to_arrays(rows) -> Dict[str, np.ndarray]:
    rows = sorted({int(r[0]): r for r in rows}.values(), key=lambda r: int(r[0]))
    return {
        "timestamp": np.array([float(r[0]) for r in rows]),
        "open": np.array([float(r[1]) for r in rows]),
        "high": np.array([float(r[2]) for r in rows]),
        "low": np.array([float(r[3]) for r in rows]),
        "close": np.array([float(r[4]) for r in rows]),
        "volume": np.array([float(r[5]) for r in rows]),
    }


def _fetch_api(symbol: str, interval: str, start_ms: int, end_ms: int):
    rows, cursor = [], start_ms
    while cursor < end_ms:
        url = f"{API}?symbol={symbol}&interval={interval}&startTime={cursor}&endTime={end_ms - 1}&limit=1000"
        batch = json.loads(_get(url))
        if not batch:
            break
        rows.extend(batch)
        nxt = int(batch[-1][0]) + INTERVAL_MS[interval]
        if nxt <= cursor:
            break
        cursor = nxt
        time.sleep(0.15)
    return rows


def _fetch_archive(symbol: str, interval: str, start_ms: int, end_ms: int):
    rows = []
    start = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc)
    end = datetime.fromtimestamp(end_ms / 1000, tz=timezone.utc)
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        url = ARCHIVE.format(sym=symbol, iv=interval, ym=f"{y:04d}-{m:02d}")
        try:
            blob = _get(url)
        except urllib.error.HTTPError:
            blob = None
        if blob:
            with zipfile.ZipFile(io.BytesIO(blob)) as zf:
                for name in zf.namelist():
                    for r in csv.reader(io.TextIOWrapper(zf.open(name))):
                        if r and r[0].isdigit():
                            ts = int(r[0])
                            ts = ts // 1000 if ts > 10 ** 14 else ts   # newer dumps use microseconds
                            rows.append([ts] + r[1:6])
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return [r for r in rows if start_ms <= int(r[0]) < end_ms]


def load(symbol: str, interval: str = "1d", start: str = "2017-01-01", end: Optional[str] = None,
         *, archive: bool = False, refresh: bool = False, now_ms: Optional[int] = None) -> Optional[Dict[str, np.ndarray]]:
    """Completed OHLCV bars for a Binance spot pair (``BTCUSDT``), oldest first.

    ``end`` is exclusive (bar open time). ``archive=True`` reads the monthly
    dumps, for pairs whose ticker was re-used after a delisting.
    """
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    start_ms = _to_ms(start)
    end_ms = _to_ms(end) if end else now_ms
    tag = "archive" if archive else "api"
    path = CACHE_DIR / f"{symbol}_{interval}_{start}_{end or 'latest'}_{tag}.csv"
    if path.exists() and not refresh and (end or time.time() - path.stat().st_mtime < 6 * 3600):
        with path.open() as fh:
            rows = [r for r in csv.reader(fh)][1:]
        data = _rows_to_arrays(rows) if rows else None
    else:
        rows = (_fetch_archive if archive else _fetch_api)(symbol, interval, start_ms, end_ms)
        data = _rows_to_arrays(rows) if rows else None
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(FIELDS)
            if data is not None:
                for i in range(len(data["timestamp"])):
                    w.writerow([int(data["timestamp"][i])] + [repr(float(data[f][i])) for f in FIELDS[1:]])
    if data is None:
        return None
    done = data["timestamp"] + INTERVAL_MS[interval] <= min(end_ms, now_ms)
    return {k: v[done] for k, v in data.items()}
