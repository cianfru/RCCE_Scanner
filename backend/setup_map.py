"""
Setup map: every scanned coin placed by how stretched it is (the engine's z-score) and
how profitable Hyperliquid traders sit on it (long minus short), with a short trail of
the last few closes, plus a watch list that sends Telegram alerts when a watched coin
enters or leaves the box, confirms Uptrend, turns crowded or gets an exit signal.

Built from data the server already holds: the scan results, the candles in the OHLCV
store, the positioning map, the tracker's opens and the stored 4H record of profitable
traders per coin. Nothing here calls an outside API.

Trader counts take wallets that trade as one (hl_entities) once; dollars are summed.

Each coin also carries the profitable cohort's dollars in it (``money``), its own weekly
bull market support band from the stored daily candles (``band``) and where price sits against
the profitable traders' dollar-weighted average long entry (``entry``: the entry zone);
``ladder`` lists that cohort's positions in one coin for the Radar's price ladder.
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
            new[o["side"]].add(o.get("entity") or o["address"])       # a lockstep group opens once
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


def day_ago(lean: Dict[str, Dict[int, tuple]], coins: Iterable[str], now: float) -> Dict[str, dict]:
    """Profitable traders long and short per coin at the stored 4H close nearest to 24 hours ago
    (within 3 hours). A coin missing from that close had nobody in it (0 and 0). Empty when the
    record has no close near enough."""
    bars = {b for rec in lean.values() for b in rec}
    best = min(bars, key=lambda b: abs(b - (now - 86400)), default=None)
    if best is None or abs(best - (now - 86400)) > 3 * 3600:
        return {}
    out = {}
    for c in coins:
        lo, sh = lean.get(c, {}).get(best, (0, 0))
        out[c] = {"long": lo, "short": sh}
    return out


def closes(ohlcv: Optional[dict], tf: str, now: float) -> tuple:
    """(close times, closes) of finished candles only."""
    if not ohlcv or ohlcv.get("close") is None or len(ohlcv["close"]) == 0:    # numpy arrays in the store
        return [], []
    step = TF_S[tf]
    ts, cs = [], []
    for t, c in zip(ohlcv["timestamp"], ohlcv["close"]):
        t = int(t) // 1000 if t > 1e12 else int(t)
        if t + step <= now and c and c > 0:
            ts.append(t + step)
            cs.append(float(c))
    return ts, cs


# ------------------------------------------------------------------ money and the weekly band
SUNDAY = 3               # day % 7 (day 3 = 1970-01-04 was a Sunday), as market_history.btc_band
BAND_WEEKS = 21          # the band needs 21 completed weeks (20-week SMA, 21-week EMA)
BAND_REACH = 0.30        # the halo is empty at 30% or more above the band's top
BAND_STALE_DAYS = 14     # a last weekly close older than this (missing candles): no band


def sig(x: Optional[float], n: int = 6) -> Optional[float]:
    return None if x is None else float(f"{x:.{n}g}")


def money(p: Optional[dict]) -> dict:
    """Dollars the profitable cohort holds in a coin (valued at entry), from its positioning row."""
    p = p or {}
    lu = round((p.get("long") or {}).get("usd") or 0)
    su = round((p.get("short") or {}).get("usd") or 0)
    g = lu + su
    return {"long_usd": lu, "short_usd": su, "gross_usd": g, "net_long_share": round(lu / g, 3) if g else None}


def weekly_closes(ohlcv: Optional[dict], now: float) -> Dict[int, float]:
    """Sunday closes by day number (day 0 = 1970-01-01), completed days only, from stored daily candles."""
    ts, cs = closes(ohlcv, "1d", now)
    return {t // 86400 - 1: c for t, c in zip(ts, cs) if (t // 86400 - 1) % 7 == SUNDAY}


def band_state(lo: float, hi: float, week_close: float, price: Optional[float]) -> dict:
    """Where price sits against the band, for the halo. closed_under: the last weekly close under the lower
    edge (full red); under_now: under it now but not at the close (full violet, red tick); inside (full
    violet); above: fill = clamp(1 - d / 0.30, 0, 1) with d = price / top - 1."""
    px = price or week_close
    d = px / hi - 1
    if week_close < lo:
        state = "closed_under"
    elif px < lo:
        state = "under_now"
    elif px <= hi:
        state = "inside"
    else:
        state = "above"
    fill = 1.0 if state != "above" else max(0.0, min(1.0, 1 - d / BAND_REACH))
    return {"state": state, "d": round(d, 4), "fill": round(fill, 3)}


def weekly_band(ohlcv: Optional[dict], price: Optional[float], now: float) -> Optional[dict]:
    """The coin's weekly bull market support band: [min, max] of the 20-week SMA and the 21-week EMA of its
    Sunday closes (completed weeks only; the EMA starts at the first close, as backtest.risk_on_cycles.
    weekly_rows). None with fewer than 21 weeks or when the last Sunday close in the store is stale."""
    wk = weekly_closes(ohlcv, now)
    if len(wk) < BAND_WEEKS:
        return None
    days = sorted(wk)
    if now / 86400 - (days[-1] + 1) > BAND_STALE_DAYS:
        return None
    ema = None
    for d in days:
        ema = wk[d] if ema is None else (2 / 22) * wk[d] + (1 - 2 / 22) * ema
    sma = sum(wk[d] for d in days[-20:]) / 20
    lo, hi, wc = min(sma, ema), max(sma, ema), wk[days[-1]]
    return {"lo": sig(lo, 5), "hi": sig(hi, 5), "sma20": sig(sma, 5), "ema21": sig(ema, 5), "week_close": sig(wc, 5),
            "week": (days[-1] + 1) * 86400, **band_state(lo, hi, wc, price)}


# ------------------------------------------------------------------ entry zone
# Declared in docs/reviews/radar-forward-test.md (H2 uses the same rule): at least ENTRY_MIN_TRADERS
# profitable traders long (lockstep entities once) and price within ENTRY_BAND of their dollar-weighted
# average long entry.
ENTRY_MIN_TRADERS = 3
ENTRY_BAND = 0.03


def entry(n_long: int, avg_long_entry: Optional[float], price: Optional[float]) -> Optional[dict]:
    """Price against the profitable traders' dollar-weighted average long entry (positioning_map's
    ``avg_entry``, over the traders counted long). None when nobody is long or there is no price."""
    if not avg_long_entry or avg_long_entry <= 0 or not price or price <= 0 or n_long <= 0:
        return None
    d = price / avg_long_entry - 1
    return {"avg_long_entry": sig(avg_long_entry), "dist_pct": round(100 * d, 2),
            "in_zone": n_long >= ENTRY_MIN_TRADERS and abs(d) <= ENTRY_BAND + 1e-12}


def ladder(item: dict, positions: List[dict], mean: Optional[float], now: float) -> dict:
    """One coin's profitable wallets at their entry prices, for the Radar's price ladder: each position
    (hl_intelligence.cohort_positions), counts and dollars per side, the median entry per side, the
    engine's mean (the price at z = 0), and the coin's weekly band and entry zone from the map."""
    import statistics
    sides = {s: [p for p in positions if p["side"] == s] for s in ("long", "short")}
    med = {s: sig(statistics.median(p["entry"] for p in xs)) if xs else None for s, xs in sides.items()}
    traders = {s: len({p.get("entity") or p["address"] for p in xs}) for s, xs in sides.items()}
    return {"coin": item["coin"], "symbol": item["symbol"], "price": item.get("price"), "stage": item.get("stage"),
            "zscore": item.get("zscore"), "updated_at": now, "band": item.get("band"), "entry": item.get("entry"),
            "mean": sig(mean),
            "counts": {"long": traders["long"], "short": traders["short"],
                       "long_wallets": len(sides["long"]), "short_wallets": len(sides["short"]),
                       "long_usd": sum(p["size_usd"] for p in sides["long"]),
                       "short_usd": sum(p["size_usd"] for p in sides["short"])},
            "median_entry": med,
            "positions": [dict(p, entry=sig(p["entry"])) for p in positions]}


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
            "traders": t, "money": money(prof.get(coin)),
            "entry": entry(t["pl"], ((prof.get(coin) or {}).get("long") or {}).get("avg_entry"), r.get("price")),
        }
        try:
            item["band"] = weekly_band(store.get(r["symbol"], "1d") if store else None, r.get("price"), now)
        except Exception as exc:                      # one market's history never blanks the map
            item["band"] = None
            logger.debug("setup map: no band for %s: %s", coin, exc)
        if st != "waiting" or t["pl"] or t["ps"]:
            try:
                ts, cs = closes(store.get(r["symbol"], tf) if store else None, tf, now)
                zs = z_trail(cs, n - 1, z) if cs else None
                if zs:
                    times = ts[-(n - 1):] + [int(now)]
                    zs = zs + [z]
                    ns = trader_trail(times, lean.get(coin, {}), net)
                    item["trail"] = {"t": times, "z": zs, "n": ns}
            except Exception as exc:                  # one market's history never blanks the map
                logger.debug("setup map: no trail for %s: %s", coin, exc)
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
    if not isinstance(_watch, dict):
        _watch = {}
    # Coins watched under a ticker Hyperliquid has since renamed move to the current name (once:
    # the file is saved renamed). A coin watched under both names keeps the current entry.
    from ticker_renames import rename_keys
    _watch, n = rename_keys(_watch)
    if n:
        logger.info("setup map: %d watched coins moved to their current tickers", n)
        _save()


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
    from ticker_renames import current_coin
    _load()
    coin = current_coin(coin)
    if coin not in _watch and len(_watch) >= MAX_WATCHED:
        return False
    _watch[coin] = {"tf": tf if tf in TF_S else "1d", "added": time.time(), "state": None}
    _save()
    return True


def unwatch(coin: str) -> None:
    from ticker_renames import current_coin
    _load()
    coin = current_coin(coin)
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
