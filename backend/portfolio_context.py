"""
Portfolio page context, per coin (Portfolio v2 spec, section 6.2).

``/api/portfolio/context?coins=BTC,HYPE,xyz:MSTR``: what the scanner shows for each coin (4H and
1D signal, how long it has held, regime, heat and z-score), the weekly support band, the engine's
trend line, the 10-bar swing, the 14-day average daily range (ATR) and where profitable tracked
traders sit on it.

``/api/portfolio/events?coins=...``: the scanner's 4H and 1D signal and regime changes over a fixed
30-day window, plus what each read at the window's start. The page clips them to each position's
open time.

Both are keyed by coin only: the same answer for every visitor, never an address (the page asks
with the coins it holds; no wallet address reaches these endpoints, and nothing here logs or keeps
one). Both read memory (scan results, TradFi results, the candle store, the positioning map) and the
signal log's SQLite tables, read-only; neither calls Hyperliquid. Each answer is kept for a minute per
scan and coin set (BodyCache), with an ETag, and goes through the edge cache (edge.EDGE_PATHS).

On by default. The kill switch: PORTFOLIO_CONTEXT=0 (or false/no/off) on Railway answers both with
404, and the page shows the scanner columns as not answering.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import statistics
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

import logging


class DropPortfolioQuery(logging.Filter):
    """uvicorn's access log without the query string on /api/portfolio/*. The coin set a page asks
    about is close to an identifier (Hyperliquid positions are public), so it is not kept in the log
    next to the client address; the path stays. Installed on the "uvicorn.access" logger by main.py."""

    def filter(self, record: logging.LogRecord) -> bool:
        a = record.args
        if isinstance(a, tuple) and len(a) >= 3 and isinstance(a[2], str) \
                and a[2].startswith("/api/portfolio/") and "?" in a[2]:
            record.args = (*a[:2], a[2].split("?", 1)[0], *a[3:])
        return True


MAX_COINS = 20
ATR_LEN = 14
EVENTS_WINDOW_DAYS = 30
EVENTS_CAP = 60
OPENS_WINDOW_S = 6 * 3600
CACHE_CONTROL = "max-age=60"
_COIN_RE = re.compile(r"^[A-Za-z0-9@:._-]{1,24}$")


def enabled(env: Optional[dict] = None) -> bool:
    """On unless PORTFOLIO_CONTEXT is 0, false, no or off."""
    env = os.environ if env is None else env
    return str(env.get("PORTFOLIO_CONTEXT", "1")).strip().lower() not in ("0", "false", "no", "off")


def parse_coins(raw: Optional[str]) -> List[str]:
    """Raw Hyperliquid names ("kPEPE", "xyz:MSTR", "@107"), deduplicated and sorted so every page asking
    for the same set gets the same answer; at most MAX_COINS; anything malformed is dropped."""
    out = set()
    for part in (raw or "").split(","):
        c = part.strip()
        if c and _COIN_RE.match(c):
            out.add(c)
    return sorted(out)[:MAX_COINS]


def app_key(coin: str) -> Optional[str]:
    """The scanner's key for a raw Hyperliquid name: "kPEPE" -> "KPEPE", "xyz:mstr" -> "xyz:MSTR".
    None for spot pairs ("@107") and builder dexes other than xyz (not scanned)."""
    if coin.startswith("@") or "/" in coin:
        return None
    if ":" in coin:
        dex, name = coin.split(":", 1)
        return f"xyz:{name.upper()}" if dex.lower() == "xyz" and name else None
    if re.fullmatch(r"k[A-Z0-9]+", coin):
        return "K" + coin[1:]
    return coin.upper()


# ------------------------------------------------------------------ pure readings
def atr_wilder(high: Sequence[float], low: Sequence[float], close: Sequence[float], n: int = ATR_LEN) -> Optional[float]:
    """Wilder's average true range over completed bars: the first value is the mean of the first n true
    ranges, then atr = (atr * (n - 1) + tr) / n. None with fewer than n + 1 bars."""
    m = min(len(high), len(low), len(close))
    if m < n + 1:
        return None
    trs = []
    for i in range(1, m):
        h, lo, pc = float(high[i]), float(low[i]), float(close[i - 1])
        trs.append(max(h - lo, abs(h - pc), abs(lo - pc)))
    atr = sum(trs[:n]) / n
    for tr in trs[n:]:
        atr = (atr * (n - 1) + tr) / n
    return atr


def completed(ohlcv: Optional[dict], step_s: int, now: float) -> Dict[str, List[float]]:
    """High, low and close of the store's finished candles (a candle still open is left out)."""
    out: Dict[str, List[float]] = {"high": [], "low": [], "close": []}
    if not ohlcv or ohlcv.get("close") is None or len(ohlcv["close"]) == 0:
        return out
    for t, h, lo, c in zip(ohlcv["timestamp"], ohlcv["high"], ohlcv["low"], ohlcv["close"]):
        t = int(t) // 1000 if t > 1e12 else int(t)
        if t + step_s <= now and c and c > 0:
            out["high"].append(float(h))
            out["low"].append(float(lo))
            out["close"].append(float(c))
    return out


def _num(v, nd: int = 6) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return float(f"{f:.{nd}g}") if math.isfinite(f) else None


def _get(row: Any, key: str):
    return row.get(key) if isinstance(row, dict) else getattr(row, key, None)


def _tf_reading(row: Optional[dict], with_heat: bool) -> Optional[dict]:
    if not row:
        return None
    out = {"signal": _get(row, "signal"), "since": _num(_get(row, "signal_first_seen_at"), 10),
           "regime": _get(row, "regime")}
    if with_heat:
        heat, prev = _get(row, "heat"), _get(row, "previous_heat")
        out.update({"heat": None if heat is None else int(round(float(heat))),
                    "heat_prev": None if prev is None else int(round(float(prev))),
                    "z": _num(_get(row, "zscore"), 3)})
    return out


def _band(b: Optional[dict]) -> Optional[dict]:
    if not b or b.get("lo") is None or b.get("hi") is None:
        return None
    d = b.get("d")
    return {"lo": b["lo"], "hi": b["hi"], "state": b.get("state"),
            "dist_pct": None if d is None else round(100 * float(d), 1)}


def _side(row: Optional[dict], before: Optional[int], opens_6h: int) -> dict:
    row = row or {}
    return {"n": int(row.get("n") or 0), "n_day_ago": before,
            "median_entry": _num(row.get("median_entry")), "in_profit": int(row.get("in_profit") or 0),
            "opens_6h": opens_6h}


@dataclass
class Sources:
    """What the context is built from, all already in memory. ``rows``/``tradfi``: tf -> {key: row};
    ``candles(symbol, tf)``: the candle store; ``band(symbol, price)`` and ``trend(symbol)``: the setup
    map's weekly band and the engine's trend line; ``prof``: positioning_map("profitable")["coins"];
    ``day_ago``: coin -> {"long", "short"} counts a day ago; ``opens``: the tracker's recent opens
    (``coin``, ``side``, ``ts``, ``cohort``, ``address``); ``entity``: wallet -> trader (linked
    wallets count once)."""
    rows: Dict[str, Dict[str, dict]]
    tradfi: Dict[str, Dict[str, dict]]
    candles: Callable[[str, str], Optional[dict]]
    band: Callable[[str, Optional[float]], Optional[dict]]
    trend: Callable[[str], Optional[float]]
    prof: Dict[str, dict]
    day_ago: Dict[str, dict]
    opens: List[dict] = field(default_factory=list)
    entity: Callable[[str], str] = lambda a: a


def _opens_6h(src: Sources, key: str, side: str, now: float) -> int:
    ents = {src.entity(o.get("address") or "") for o in src.opens
            if o.get("coin") == key and o.get("side") == side and o.get("cohort", "profitable") == "profitable"
            and now - float(o.get("ts") or 0) <= OPENS_WINDOW_S}
    return len(ents)


def coin_context(coin: str, src: Sources, now: float) -> dict:
    """One coin's reading (see the module docstring); {"covered": False} when the scanner has no row."""
    key = app_key(coin)
    if key is None:
        return {"covered": False}
    if key.startswith("xyz:"):
        name = key[4:]
        r4, r1 = src.tradfi.get("4h", {}).get(name), src.tradfi.get("1d", {}).get(name)
        if not r4 and not r1:
            return {"covered": False}
        return {"covered": True, "price": _num(_get(r4 or r1, "price")),
                "h4": _tf_reading(r4, True), "d1": _tf_reading(r1, False),
                "band": None, "trend": None, "swing": None, "atr_1d": None, "traders": None, "sector": "TradFi"}
    r4, r1 = src.rows.get("4h", {}).get(key), src.rows.get("1d", {}).get(key)
    if not r4 and not r1:
        return {"covered": False}
    base = r4 or r1
    symbol = _get(base, "symbol") or f"{key}/USDT"
    price = _num(_get(base, "price"))
    st = _get(r4, "structure") if r4 else None
    swing = ({"lo": _num(st.get("swing_low")), "hi": _num(st.get("swing_high"))}
             if isinstance(st, dict) and st.get("swing_low") is not None else None)
    d = completed(src.candles(symbol, "1d"), 86400, now)
    atr = atr_wilder(d["high"], d["low"], d["close"])
    try:
        band = _band(src.band(symbol, price))
    except Exception:
        band = None
    try:
        trend = _num(src.trend(symbol))
    except Exception:
        trend = None
    p = src.prof.get(key)
    before = src.day_ago.get(key)
    traders = None
    if p is not None or before is not None:
        traders = {s: _side((p or {}).get(s), None if before is None else int(before.get(s) or 0),
                            _opens_6h(src, key, s, now)) for s in ("long", "short")}
    elif src.prof:
        traders = {s: _side(None, None, 0) for s in ("long", "short")}
    return {"covered": True, "price": price, "h4": _tf_reading(r4, True), "d1": _tf_reading(r1, False),
            "band": band, "trend": trend, "swing": swing, "atr_1d": _num(atr, 5), "traders": traders,
            "sector": _get(base, "sector")}


class Memo:
    """Per-coin readings memoised for one scan id (a new scan or trader reading starts afresh), and
    each coin's last good reading: a coin whose rebuild fails is answered from it (``stale``)."""

    def __init__(self, max_coins: int = 600) -> None:
        self.scan_id: Optional[str] = None
        self.max_coins = max_coins
        self._d: Dict[str, dict] = {}
        self._good: Dict[str, tuple] = {}
        self._lock = threading.Lock()

    def get(self, scan_id: str, coin: str, build: Callable[[], dict], now: float) -> tuple:
        """(reading, built_at or None when it is fresh from this scan)."""
        with self._lock:
            if scan_id != self.scan_id:
                self.scan_id, self._d = scan_id, {}
            hit = self._d.get(coin)
        if hit is not None:
            return hit, None
        try:
            val = build()
        except Exception:
            with self._lock:
                good = self._good.get(coin)
            if good is None:
                raise
            return good[1], good[0]
        with self._lock:
            if self.scan_id == scan_id and len(self._d) < self.max_coins:
                self._d[coin] = val
            if coin in self._good or len(self._good) < self.max_coins:
                self._good[coin] = (now, val)
        return val, None


def context_body(coins: Iterable[str], src, scan_id: str, as_of: Optional[float], memo: Memo,
                 now: Optional[float] = None) -> dict:
    """``stale`` and an older ``as_of`` when any coin was answered from its last good reading.
    ``src``: the Sources, or a function that builds them (called once, and only when a coin is not
    memoised for this scan)."""
    now = time.time() if now is None else now
    out: Dict[str, dict] = {}
    oldest = None
    built: List[Sources] = []

    def sources() -> Sources:
        if not built:
            built.append(src() if callable(src) else src)
        return built[0]
    for c in coins:
        try:
            val, built_at = memo.get(scan_id, c, lambda c=c: coin_context(c, sources(), now), now)
        except Exception:
            val, built_at = {"covered": False}, None
        out[c] = val
        if built_at is not None:
            oldest = built_at if oldest is None else min(oldest, built_at)
    body = {"as_of": as_of if oldest is None else min(oldest, as_of or oldest), "scan_id": scan_id, "coins": out}
    if oldest is not None:
        body["stale"] = True
    return body


class BodyCache:
    """Whole answers for a short time, keyed by what they depend on (the scan id and the coin set):
    a page polling, or many pages holding the same coins, cost one build per scan. Bounded; the
    oldest entry goes first."""

    def __init__(self, ttl: float = 60.0, max_items: int = 512) -> None:
        self.ttl, self.max_items = ttl, max_items
        self._d: Dict[tuple, tuple] = {}
        self._lock = threading.Lock()

    def get(self, key: tuple, now: Optional[float] = None):
        now = time.time() if now is None else now
        with self._lock:
            hit = self._d.get(key)
            if hit is None or now - hit[0] > self.ttl:
                return None
            return hit[1]

    def put(self, key: tuple, value, now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        with self._lock:
            if len(self._d) >= 32:        # expired answers are never served: drop them now, not at the cap
                for k in [k for k, (t, _) in self._d.items() if now - t > self.ttl]:
                    del self._d[k]
            if key not in self._d and len(self._d) >= self.max_items:
                for k in [k for k, (t, _) in self._d.items() if now - t > self.ttl] or [min(self._d, key=lambda k: self._d[k][0])]:
                    self._d.pop(k, None)
            self._d[key] = (now, value)

    def __len__(self) -> int:
        return len(self._d)


def etag(body: Any) -> str:
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()
    return f'W/"{hashlib.sha1(raw).hexdigest()[:20]}"'


def not_modified(if_none_match: Optional[str], tag: str) -> bool:
    if not if_none_match:
        return False
    return any(t.strip() in (tag, tag.replace('W/', ''), "*") for t in if_none_match.split(","))


# ------------------------------------------------------------------ events (signal log)
def window_start(now: float) -> int:
    """Midnight UTC, 30 days back: fixed for a whole day, so the answer caches well."""
    return (int(now) // 86400 - EVENTS_WINDOW_DAYS) * 86400


def _connect_ro(db_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2)
    con.row_factory = sqlite3.Row
    return con


# The log's timeframes and the page's: main perps log "4h"/"1d"; the TradFi scan logs its own
# ("tradfi_4h"/"tradfi_1d", scanner.run_tradfi_scan) under "NAME/USD".
PERP_TFS = (("4h", "4h", "h4"), ("1d", "1d", "d1"))
TRADFI_TFS = (("tradfi_4h", "4h", "h4"), ("tradfi_1d", "1d", "d1"))


def coin_events(con: sqlite3.Connection, symbol: str, ws: int, tfs=PERP_TFS) -> dict:
    at_start: Dict[str, dict] = {}
    for tf, _, k in tfs:
        s = con.execute("SELECT signal FROM signal_events WHERE symbol=? AND timeframe=? AND timestamp<? "
                        "ORDER BY timestamp DESC LIMIT 1", (symbol, tf, ws)).fetchone()
        r = con.execute("SELECT regime FROM regime_events WHERE symbol=? AND timeframe=? AND timestamp<? "
                        "ORDER BY timestamp DESC LIMIT 1", (symbol, tf, ws)).fetchone()
        at_start[k] = {"signal": s["signal"] if s else None, "regime": r["regime"] if r else None}
    page_tf = {tf: out for tf, out, _ in tfs}
    log_tfs = tuple(page_tf)
    marks = ",".join("?" * len(log_tfs))
    evs = []
    last_id = 0
    for row in con.execute("SELECT id, timestamp, timeframe, prev_signal, signal, price FROM signal_events "
                           f"WHERE symbol=? AND timeframe IN ({marks}) AND timestamp>=? ORDER BY timestamp",
                           (symbol, *log_tfs, ws)):
        last_id = max(last_id, row["id"])
        evs.append({"t": int(row["timestamp"]), "tf": page_tf[row["timeframe"]], "kind": "signal",
                    "from": row["prev_signal"], "to": row["signal"], "px": _num(row["price"])})
    for row in con.execute("SELECT id, timestamp, timeframe, prev_regime, regime, price FROM regime_events "
                           f"WHERE symbol=? AND timeframe IN ({marks}) AND timestamp>=? ORDER BY timestamp",
                           (symbol, *log_tfs, ws)):
        last_id = max(last_id, row["id"])
        evs.append({"t": int(row["timestamp"]), "tf": page_tf[row["timeframe"]], "kind": "regime",
                    "from": row["prev_regime"], "to": row["regime"], "px": _num(row["price"])})
    evs.sort(key=lambda e: (e["t"], e["kind"], e["tf"]))
    truncated = len(evs) > EVENTS_CAP
    return {"at_start": at_start, "events": evs[-EVENTS_CAP:], "truncated": truncated, "_last_id": last_id}


def events_body(coins: Iterable[str], db_path: str, now: Optional[float] = None,
                memo: Optional[Memo] = None, scan_id: str = "") -> dict:
    """The signal log's changes per coin since the window start: main perps under "KEY/USDT", TradFi
    (xyz) under "NAME/USD" with the TradFi scan's timeframes; other venues are not scanned, so they
    get empty lists. ``last_id`` is the newest event id among them: the ETag, so a page asking again
    before anything changed gets a 304."""
    now = time.time() if now is None else now
    ws = window_start(now)
    out: Dict[str, dict] = {}
    last = 0
    con = None
    try:
        for c in coins:
            key = app_key(c)
            if key is None:
                out[c] = {"at_start": None, "events": [], "truncated": False, "_last_id": 0}
            else:
                def build(key=key):
                    nonlocal con
                    if con is None:
                        if not db_path or not os.path.exists(db_path):
                            return {"at_start": None, "events": [], "truncated": False, "_last_id": 0}
                        con = _connect_ro(db_path)
                    if key.startswith("xyz:"):
                        return coin_events(con, f"{key[4:]}/USD", ws, TRADFI_TFS)
                    return coin_events(con, f"{key}/USDT", ws)
                out[c] = memo.get(f"{scan_id}|{ws}", c, build, now)[0] if memo is not None else build()
            last = max(last, out[c].get("_last_id", 0))
    finally:
        if con is not None:
            con.close()
    coins_out = {c: {k: v for k, v in ev.items() if k != "_last_id"} for c, ev in out.items()}
    return {"as_of": int(now) // 60 * 60, "window_start": ws, "last_id": last, "coins": coins_out}


def events_etag(body: dict) -> str:
    """The newest event id with the window and the coin set: unchanged until something new is logged."""
    key = f"{body.get('window_start')}|{body.get('last_id')}|{','.join(sorted(body.get('coins') or {}))}"
    return f'W/"ev-{hashlib.sha1(key.encode()).hexdigest()[:16]}"'
