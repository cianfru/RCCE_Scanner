"""
Setup map: every scanned coin placed by how stretched it is (the engine's z-score) and
how profitable Hyperliquid traders sit on it (long minus short), with a short trail of
the last few closes, plus a watch list that sends Telegram alerts when a watched coin
enters or leaves the box, confirms Uptrend, turns crowded or gets an exit signal.

Built from data the server already holds: the scan results, the candles in the OHLCV
store, the positioning map, the tracker's opens and the stored 4H record of profitable
traders per coin. Nothing here calls an outside API.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

TF_S = {"4h": 4 * 3600, "1d": 86400}
TRAIL = {"4h": 7, "1d": 6}          # points including now: 24 hours / 5 days back
LONGS = {"STRONG_LONG", "LIGHT_LONG", "ACCUMULATE", "REVIVAL_SEED", "REVIVAL_SEED_CONFIRMED"}
EXITS = {"TRIM", "TRIM_HARD", "NO_LONG", "RISK_OFF"}

# The box: a setup that has not run far from its mean, with a few profitable traders
# long but no crowd. z in [BOX_Z0, BOX_Z1], traders long minus short in [BOX_N0, BOX_N1].
BOX_Z0, BOX_Z1, BOX_N0, BOX_N1 = -0.5, 1.5, 1, 8
STRETCHED_Z = 2.0
STRETCHED_HEAT = 40
CROWD_N = 8
CROWD_PAST = 0.15
EARLY_NEAR = 0.05


# ------------------------------------------------------------------ reading one coin
def stage(row: dict, now: float) -> str:
    """forming | fresh | running | stretched | leaving | waiting."""
    sig = row.get("signal")
    if sig in EXITS:
        return "leaving"
    tr = row.get("regime_transition") or {}
    if tr.get("candidate") == "MARKUP" and row.get("regime") != "MARKUP":
        return "forming"
    if sig in LONGS:
        if (row.get("zscore") or 0) >= STRETCHED_Z or (row.get("heat") or 0) >= STRETCHED_HEAT \
                or row.get("heat_phase") == "Exhaustion":
            return "stretched"
        trig = (row.get("opportunity") or {}).get("trigger_at")
        if trig and now - trig <= 2 * TF_S.get(row.get("timeframe") or "4h", TF_S["4h"]):
            return "fresh"
        return "running"
    return "waiting"


def in_box(z: Optional[float], net: int) -> bool:
    return z is not None and BOX_Z0 <= z <= BOX_Z1 and BOX_N0 <= net <= BOX_N1


def zone(st: str, z: Optional[float], net: int) -> str:
    """watch (the box) | late (stretched) | crowded | quiet (nobody in yet) | outside."""
    if z is not None and z >= STRETCHED_Z:
        return "late"
    if st in ("forming", "fresh", "running") and in_box(z, net):
        return "watch"
    if net > BOX_N1:
        return "crowded"
    if net < BOX_N0 and z is not None and BOX_Z0 <= z <= BOX_Z1:
        return "quiet"
    return "outside"


def crowd(side_long: bool, t: dict, price: Optional[float]) -> str:
    """quiet | against | crowded | early | holding (same rules as the setup drawer)."""
    w, a = (t["pl"], t["ps"]) if side_long else (t["ps"], t["pl"])
    entry = t["ple"] if side_long else t["pse"]
    past = None
    if price and entry:
        past = price / entry - 1 if side_long else 1 - price / entry
    fresh = t["n24l"] if side_long else t["n24s"]
    if not w and not a:
        return "quiet"
    if a >= 2 and a > w:
        return "against"
    if w >= CROWD_N or (w >= 3 and past is not None and past >= CROWD_PAST):
        return "crowded"
    if w >= 1 and fresh >= 1 and (past is None or abs(past) <= EARLY_NEAR):
        return "early"
    return "holding"


def traders(coin: str, prof: dict, large: dict, opens: Iterable[dict], now: float) -> dict:
    p, l = prof.get(coin) or {}, large.get(coin) or {}
    get = lambda d, s, k: (d.get(s) or {}).get(k) or 0
    new = {("long"): set(), ("short"): set()}
    for o in opens:
        if o["coin"] == coin and o["cohort"] == "profitable" and now - o["ts"] <= 86400:
            new[o["side"]].add(o["address"])
    return {"pl": get(p, "long", "n"), "ps": get(p, "short", "n"),
            "ple": (p.get("long") or {}).get("median_entry"), "pse": (p.get("short") or {}).get("median_entry"),
            "ll": get(l, "long", "n"), "ls": get(l, "short", "n"),
            "n24l": len(new["long"]), "n24s": len(new["short"])}


# ------------------------------------------------------------------ trails
def z_trail(close: List[float], n: int, z_now: Optional[float]) -> Optional[List[float]]:
    """The engine's z-score at each of the last n closes, anchored so the last point is
    the scan's own value (the scan may use a slightly longer history)."""
    import numpy as np
    from engines.rcce_engine import _calc_zscore_hybrid, LEN_LONG, LEN_REGRESSION, Z_SMOOTH, Z_SCALE
    if z_now is None or len(close) < LEN_LONG + n:
        return None
    c = np.asarray(close, dtype=float)
    z = _calc_zscore_hybrid(c, len_ma=LEN_LONG, len_reg=LEN_REGRESSION, z_smooth=Z_SMOOTH, z_scale=Z_SCALE)
    z = z * min(1.0, max(0.0, (len(c) - LEN_LONG) / LEN_LONG))
    tail = z[-n:]
    if np.isnan(tail).any():
        return None
    shift = z_now - float(z[-1])
    return [round(float(v) + shift, 3) for v in tail]


def trader_trail(times: List[int], record: Dict[int, tuple], now_net: int) -> List[Optional[int]]:
    """Profitable traders long minus short at each close, from the stored 4H record
    (nearest record within 3 hours); the last point is today's reading."""
    keys = sorted(record)
    out: List[Optional[int]] = []
    for k, t in enumerate(times):
        if k == len(times) - 1:
            out.append(now_net)
            continue
        best = min(keys, key=lambda b: abs(b - t), default=None)
        if best is None or abs(best - t) > 3 * 3600:
            out.append(None)
        else:
            lo, sh = record[best]
            out.append(lo - sh)
    return out


def closes(ohlcv: Optional[dict], tf: str, now: float) -> tuple:
    """(close times, closes) of finished candles only."""
    if not ohlcv or not ohlcv.get("close"):
        return [], []
    step = TF_S[tf]
    ts, cs = [], []
    for t, c in zip(ohlcv["timestamp"], ohlcv["close"]):
        t = int(t) // 1000 if t > 1e12 else int(t)
        if t + step <= now and c and c > 0:
            ts.append(t + step)
            cs.append(float(c))
    return ts, cs


# ------------------------------------------------------------------ the map
def build(rows: List[dict], tf: str, store, prof: dict, large: dict, opens: List[dict],
          lean: Dict[str, Dict[int, tuple]], now: float) -> dict:
    """``lean``: coin -> {bar_close: (long, short)} from the stored 4H record."""
    from hl_intelligence import _normalize_coin
    n = TRAIL[tf]
    out = []
    for r in rows:
        if r.get("market_kind", "perpetual") != "perpetual" or not r.get("symbol"):
            continue
        coin = _normalize_coin(r["symbol"])
        t = traders(coin, prof, large, opens, now)
        net = t["pl"] - t["ps"]
        st = stage(r, now)
        z = r.get("zscore")
        tr = r.get("regime_transition") or None
        item = {
            "coin": coin, "symbol": r["symbol"], "price": r.get("price"), "regime": r.get("regime"),
            "signal": r.get("signal"), "zscore": z, "heat": r.get("heat"), "priority": r.get("priority_score"),
            "sector": r.get("sector"), "trigger_at": (r.get("opportunity") or {}).get("trigger_at"),
            "transition": {"to": tr.get("candidate"), "seen": tr.get("observed_bars"), "need": tr.get("required_bars")} if tr else None,
            "checks": [r.get("conditions_met"), r.get("conditions_total")],
            "sparkline": [round(v, 8) for v in (r.get("sparkline") or [])] if st != "waiting" else [],
            "stage": st, "zone": zone(st, z, net), "crowd": crowd(r.get("signal") not in ("LIGHT_SHORT", "STRONG_SHORT"), t, r.get("price")),
            "traders": t,
        }
        if st != "waiting" or t["pl"] or t["ps"]:
            ts, cs = closes(store.get(r["symbol"], tf) if store else None, tf, now)
            zs = z_trail(cs, n - 1, z) if cs else None
            if zs:
                times = ts[-(n - 1):] + [int(now)]
                zs = zs + [z]
                ns = trader_trail(times, lean.get(coin, {}), net)
                item["trail"] = {"t": times, "z": zs, "n": ns}
        out.append(item)
    return {"tf": tf, "updated_at": now, "box": {"z": [BOX_Z0, BOX_Z1], "n": [BOX_N0, BOX_N1]},
            "stretched_z": STRETCHED_Z, "coins": out}


# ------------------------------------------------------------------ watch list
_dir = Path(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", "")) if os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") \
    else Path(__file__).resolve().parent / "data"
_FILE = _dir / "watched_coins.json"
_watch: Dict[str, dict] = {}
_loaded = False
MAX_WATCHED = 30


def _load() -> None:
    global _watch, _loaded
    if _loaded:
        return
    _loaded = True
    try:
        _watch = json.loads(_FILE.read_text())
    except Exception:
        _watch = {}


def _save() -> None:
    try:
        _FILE.parent.mkdir(parents=True, exist_ok=True)
        _FILE.write_text(json.dumps(_watch))
    except Exception as exc:
        logger.warning("setup map: watch list not saved: %s", exc)


def watched() -> Dict[str, dict]:
    _load()
    return _watch


def watch(coin: str, tf: str) -> bool:
    _load()
    if coin not in _watch and len(_watch) >= MAX_WATCHED:
        return False
    _watch[coin] = {"tf": tf if tf in TF_S else "1d", "added": time.time(), "state": None}
    _save()
    return True


def unwatch(coin: str) -> None:
    _load()
    if _watch.pop(coin, None) is not None:
        _save()


def state_of(item: dict) -> dict:
    return {"zone": item["zone"], "crowd": item["crowd"], "regime": item["regime"], "signal": item["signal"]}


_ZONE_WORD = {"watch": "the box", "late": "stretched", "crowded": "crowded", "quiet": "nobody in yet", "outside": "outside the box"}


def changes(prev: Optional[dict], cur: dict) -> List[str]:
    """What is worth a message between two readings (first reading: nothing)."""
    if not prev:
        return []
    out = []
    if cur["zone"] == "watch" and prev["zone"] != "watch":
        out.append("entered the box")
    elif prev["zone"] == "watch" and cur["zone"] != "watch":
        out.append(f"left the box ({_ZONE_WORD.get(cur['zone'], cur['zone'])})")
    if cur["regime"] == "MARKUP" and prev["regime"] != "MARKUP":
        out.append("confirmed Uptrend")
    if cur["crowd"] == "crowded" and prev["crowd"] != "crowded":
        out.append("turned crowded")
    if cur["signal"] in EXITS and cur["signal"] != prev["signal"]:
        out.append(f"exit signal {cur['signal'].replace('_', ' ').title()}")
    return out


def check(maps: Dict[str, dict]) -> List[str]:
    """Compare each watched coin with its last reading; return the messages to send."""
    _load()
    msgs, dirty = [], False
    for coin, w in _watch.items():
        m = maps.get(w["tf"])
        item = next((c for c in (m or {}).get("coins", []) if c["coin"] == coin), None)
        if item is None:
            continue
        cur = state_of(item)
        what = changes(w.get("state"), cur)
        if what:
            t = item["traders"]
            msgs.append(f"{coin} {w['tf'].upper()}: {', '.join(what)}.\n"
                        f"Stretch {item['zscore'] or 0:.1f} · profitable traders {t['pl']} long, {t['ps']} short · "
                        f"{str(item['signal'] or 'wait').replace('_', ' ').lower()}")
        if cur != w.get("state"):
            w["state"] = cur
            dirty = True
    if dirty:
        _save()
    return msgs
