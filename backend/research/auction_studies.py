"""
Four more studies of the auction levels (docs/reviews/auction-level-studies.md, declared before running), on the
candles of the 80% rule study (research/value_area_rule.py) plus Binance's 5-minute open interest.

Run from backend/:

  python -m research.auction_studies fetch-oi                 (public open-interest history, data.binance.vision)
  python -m research.auction_studies shape [--out JSON]       (counts only: no outcome is computed)
  python -m research.auction_studies power --shape JSON       (the bars on made-up outcomes)
  python -m research.auction_studies run [--holdout] [--out JSON]
"""
from __future__ import annotations

import io
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from backtest.binance_history import _get
from engines import auction_engine as ae
from research import value_area_rule as V

OI_ARCHIVE = "https://data.binance.vision/data/futures/um/daily/metrics/{sym}/{sym}-metrics-{day}.zip"
OI_FIRST, OI_LAST = "2020-12-01", "2026-10-31"


def parse_oi_day(raw: bytes) -> list:
    """(time ms, open interest in coins) rows of one daily metrics archive."""
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        text = z.read(z.namelist()[0]).decode()
    rows = []
    for line in text.splitlines():
        f = line.split(",")
        if len(f) < 3 or not f[0][:1].isdigit():
            continue                                    # the header line
        try:
            t = datetime.strptime(f[0][:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            rows.append((int(t.timestamp() * 1000), float(f[2])))
        except ValueError:
            continue
    return rows


def fetch_oi(symbols=V.SYMBOLS, cache: Path = V.CACHE_DIR, workers: int = 24) -> dict:
    cache.mkdir(parents=True, exist_ok=True)
    d0 = datetime.strptime(OI_FIRST, "%Y-%m-%d")
    days = [(d0 + timedelta(days=i)).strftime("%Y-%m-%d") for i in range((datetime.strptime(OI_LAST, "%Y-%m-%d") - d0).days + 1)]
    report = {}
    for sym in symbols:
        def one(day: str):
            try:
                return parse_oi_day(_get(OI_ARCHIVE.format(sym=sym, day=day)))
            except Exception:                           # a day the archive does not have
                return None
        with ThreadPoolExecutor(workers) as pool:
            got = list(pool.map(one, days))
        rows = sorted({t: v for day in got if day for t, v in day}.items())
        a = np.array(rows, dtype=np.float64)
        np.savez_compressed(cache / f"{sym}-oi.npz", ts=a[:, 0].astype(np.int64), oi=a[:, 1])
        report[sym] = {"rows": int(len(a)), "days_missing": sum(1 for d in got if not d), "from": V.iso(int(a[0, 0])), "to": V.iso(int(a[-1, 0]))}
        print(sym, report[sym], flush=True)
    return report


# ---------------------------------------------------------------------------
# Shared: the days of one coin, and a trade's path
# ---------------------------------------------------------------------------

HALF = V.HALF_HOUR_MS
DAY = V.DAY_MS
MIN_DIST = 0.0025          # S2: a POC closer to the price than 0.25% is not raced
FRESH_DAYS, OLD_DAYS = 3, 10
ZONE = 0.0025              # S5: other levels within 0.25% of the swept level
NAKED_LOOKBACK = 30        # S5: naked daily POCs from the 30 days before the previous day
WEEK_MIN_BARS = 1915       # of 2,016 five-minute candles
RTH_BARS, RTH_MIN_BARS = 81, 79     # 09:30 to 16:15 New York
GAP = 0.001                # S4, S5: one group's mean net return over the other's, at least 0.10%
ABSORB = 0.10              # S4: taker volume one-sided by at least 10% of the bar's volume, in the sweep's direction
SHARE, SHARE_MIN_N = 0.55, 500      # S2: the POC first in at least 55% of decided races


def day_table(d: dict) -> list:
    """Every UTC day of one coin with nearly all its candles: its slice, its range and its own value area.
    ``ok``: the day has a value area to give the next day (volume, and VAH above VAL), as in the 80% rule study."""
    day = d["ts"] // DAY
    days, start, count = np.unique(day, return_index=True, return_counts=True)
    out = []
    for i in range(len(days)):
        sl = slice(int(start[i]), int(start[i] + count[i]))
        if count[i] < V.MIN_BARS:
            continue
        close = float(d["close"][sl][-1])
        rec = {"day": int(days[i]) * DAY, "start": sl.start, "stop": sl.stop, "open": float(d["open"][sl][0]),
               "high": float(d["high"][sl].max()), "low": float(d["low"][sl].min()), "close": close, "ok": False}
        if d["volume"][sl].sum() > 0:
            step = ae.nice_step(close * V.STEP_FRACTION)
            poc, vah, val = ae.session_levels(d["high"][sl], d["low"][sl], d["volume"][sl], step)
            rec.update(poc=poc, vah=vah, val=val, step=step, ok=bool(vah > val))
        out.append(rec)
    return out


def pairs(table: list, first_ms: int, last_ms: int):
    """(previous day, event day) for event days in [first, last] that follow a day with a value area."""
    for a, b in zip(table, table[1:]):
        if first_ms <= b["day"] <= last_ms and b["day"] == a["day"] + DAY and a["ok"]:
            yield a, b


def trade(d: dict, i0: int, i1: int, direction: int, entry: float, stop: float, target: float | None = None) -> dict:
    """A trade from candle i0 to i1 (exclusive): out at the stop, at the target, or at the last price.
    The stop wins when one candle holds both. Net of 10 bps a side."""
    hi, lo = d["high"][i0:i1], d["low"][i0:i1]
    stopped = (lo <= stop) if direction > 0 else (hi >= stop)
    first = lambda m: int(np.argmax(m)) if m is not None and m.any() else None
    reach = None if target is None else ((hi >= target) if direction > 0 else (lo <= target))
    s, r = first(stopped), first(reach)
    if s is not None and (r is None or s <= r):
        how, exit_ = "stop", stop
    elif r is not None:
        how, exit_ = "target", target
    else:
        how, exit_ = "end", (float(d["close"][i1 - 1]) if i1 > i0 else entry)
    gross = direction * (exit_ - entry) / entry
    return {"gross": gross, "net": gross - V.COST, "r": gross / (abs(entry - stop) / entry),
            "stopped": how == "stop", "reached": how == "target"}


def first_touch(d: dict, i0: int, i1: int, price: float):
    """Offset of the first candle in [i0, i1) whose range holds the price, or None."""
    m = (d["low"][i0:i1] <= price) & (d["high"][i0:i1] >= price)
    return int(np.argmax(m)) if m.any() else None


# ---------------------------------------------------------------------------
# S2. Naked POCs: the POC against a price as far away on the other side
# ---------------------------------------------------------------------------

def race(d: dict, i0: int, t0: int, days: int, poc: float, mirror: float):
    """Which is traded first in the ``days`` after t0: 'poc', 'mirror', 'tie' (one candle holds both) or 'none'.
    None when the window is missing candles."""
    i1 = int(np.searchsorted(d["ts"], t0 + days * DAY))
    if i1 - i0 < days * V.MIN_BARS:
        return None
    a, b = first_touch(d, i0, i1, poc), first_touch(d, i0, i1, mirror)
    if a is None and b is None:
        return "none"
    if b is None or (a is not None and a < b):
        return "poc"
    if a is None or b < a:
        return "mirror"
    return "tie"


def poc_races(sym: str, d: dict, first: str, last: str, outcomes: bool) -> list:
    """Races that start on days in [first, last].
    fresh: at a day's end, its POC against the price as far from the close on the other side, when that price
    is inside the day's own range; 3 days. old: a POC not traded on the following day, raced from that day's
    end against its mirror through that day's close; 10 days."""
    table, lo, hi = day_table(d), V._ms(first), V._ms(last)
    end = hi + DAY                                      # a race must finish inside the period
    rows = []
    for n, rec in enumerate(table):
        if not rec["ok"]:
            continue
        t0, close, poc = rec["day"] + DAY, rec["close"], rec["poc"]
        if lo <= t0 and t0 + FRESH_DAYS * DAY <= end and abs(poc - close) / close >= MIN_DIST:
            mirror = 2 * close - poc
            if rec["low"] <= mirror <= rec["high"]:
                row = {"sym": sym, "kind": "fresh", "t0": t0, "day": int(ae.session_starts([t0], "week")[0]),
                       "dist": abs(poc - close) / close}
                if outcomes:
                    row["outcome"] = race(d, rec["stop"], t0, FRESH_DAYS, poc, mirror)
                rows.append(row)
        nxt = table[n + 1] if n + 1 < len(table) else None
        if nxt is None or nxt["day"] != rec["day"] + DAY:
            continue
        t1 = nxt["day"] + DAY
        if t1 < lo or t1 + OLD_DAYS * DAY > end or first_touch(d, nxt["start"], nxt["stop"], poc) is not None:
            continue                                   # traded on the following day: no longer naked
        c1 = nxt["close"]
        mirror = 2 * c1 - poc
        if abs(poc - c1) / c1 < MIN_DIST or mirror <= 0:
            continue
        row = {"sym": sym, "kind": "old", "t0": t1, "day": int(ae.session_starts([t1], "week")[0]), "dist": abs(poc - c1) / c1}
        if outcomes:
            row["outcome"] = race(d, nxt["stop"], t1, OLD_DAYS, poc, mirror)
        rows.append(row)
    return rows


def revisits(d: dict, first: str, last: str) -> list:
    """Per day's POC in [first, last]: how long after the day's end it was first traded (days; None within 30)."""
    out = []
    for rec in day_table(d):
        t0 = rec["day"] + DAY
        if not rec["ok"] or t0 < V._ms(first) or t0 + 30 * DAY > V._ms(last) + DAY:
            continue
        i1 = int(np.searchsorted(d["ts"], t0 + 30 * DAY))
        if i1 - rec["stop"] < 30 * V.MIN_BARS:
            continue
        k = first_touch(d, rec["stop"], i1, rec["poc"])
        out.append({"day": rec["day"], "dist": abs(rec["poc"] - rec["close"]) / rec["close"],
                    "after": None if k is None else (int(d["ts"][rec["stop"] + k]) - t0) / DAY})
    return out


def share_bar(st: dict) -> dict:
    checks = {"events": st["n"] >= SHARE_MIN_N and st["days"] >= V.MIN_DAYS,
              "share": st.get("value", 0) >= SHARE, "interval": st.get("low", 0) > 0.5,
              "halves": min(st.get("first_half") or 0, st.get("second_half") or 0) > 0.5}
    return {"checks": checks, "met": all(checks.values())}


# ---------------------------------------------------------------------------
# S3. Accepted outside the value area: does it go on?
# ---------------------------------------------------------------------------

def held_until_back_inside(closes: np.ndarray, k: int, vah: float, val: float, entry: float, side: int) -> dict:
    """In at the close of bar k, with the break; out at the first later half-hour close back inside the value
    area, or at the day's last close. Net of 10 bps a side."""
    later = closes[k + 1:]
    later = later[np.isfinite(later)]
    back = np.flatnonzero((later >= val) & (later <= vah))
    exit_ = float(later[back[0]]) if back.size else (float(later[-1]) if later.size else entry)
    gross = side * (exit_ - entry) / entry
    return {"gross": gross, "net": gross - V.COST, "back_inside": bool(back.size)}


def outside_events(sym: str, d: dict, first: str, last: str, outcomes: bool) -> list:
    """Days that opened inside the previous day's value area: the first half-hour bar to close outside an edge,
    and whether the next bar closed outside it too (accepted) or back inside (rejected).
    The trade (accepted only): in at that second close, in the direction of the break; out at the first
    half-hour close back inside the value area, or at the day's last price."""
    rows = []
    for prev, cur in pairs(day_table(d), V._ms(first), V._ms(last)):
        vah, val = prev["vah"], prev["val"]
        if not val <= cur["open"] <= vah:
            continue
        sl = slice(cur["start"], cur["stop"])
        closes, _, lastc = V.buckets(d["ts"][sl], d["close"][sl], cur["day"], HALF)
        out = np.flatnonzero((closes > vah) | (closes < val))
        if not out.size:
            rows.append({"sym": sym, "day": cur["day"], "state": "stayed_inside"})
            continue
        j = int(out[0])
        side = 1 if closes[j] > vah else -1
        nxt = closes[j + 1] if j + 1 < len(closes) else np.nan
        row = {"sym": sym, "day": cur["day"], "side": side, "hour": ((j + 2) * HALF - 1) // V.HOUR_MS}
        if not np.isfinite(nxt):
            row["state"] = "no_next_bar"
        elif (nxt > vah) if side > 0 else (nxt < val):
            stop = vah - prev["step"] if side > 0 else val + prev["step"]
            row.update(state="accepted", entry=float(nxt), stop=stop, gi=cur["start"] + int(lastc[j + 1]), day_end=cur["stop"],
                       entry_one=float(closes[j]), gi_one=cur["start"] + int(lastc[j]))
            if outcomes:
                row.update(held_until_back_inside(closes, j + 1, vah, val, row["entry"], side))
                # Reported only: the same entry with a price stop one row back inside the edge, and the trade
                # taken one bar earlier, at the first close outside.
                row["tight_net"] = trade(d, row["gi"] + 1, row["day_end"], side, row["entry"], stop)["net"]
                row["one_net"] = held_until_back_inside(closes, j, vah, val, row["entry_one"], side)["net"]
                row["closed_outside"] = bool((cur["close"] > vah) if side > 0 else (cur["close"] < val))
        else:
            row["state"] = "rejected"
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# S4 and S5. Sweeps of the previous day's high and low, with open interest, delta and confluence
# ---------------------------------------------------------------------------

def week_table(d: dict) -> dict:
    """Per week (Monday 00:00 UTC) with nearly all its candles: range and value area."""
    wk = ae.session_starts(d["ts"], "week")
    weeks, start, count = np.unique(wk, return_index=True, return_counts=True)
    out = {}
    for i in range(len(weeks)):
        sl = slice(int(start[i]), int(start[i] + count[i]))
        if count[i] < WEEK_MIN_BARS or not d["volume"][sl].sum() > 0:
            continue
        step = ae.nice_step(float(d["close"][sl][-1]) * ae.STEP_FRACTION["week"])
        poc, vah, val = ae.session_levels(d["high"][sl], d["low"][sl], d["volume"][sl], step)
        out[int(weeks[i])] = {"high": float(d["high"][sl].max()), "low": float(d["low"][sl].min()), "poc": poc, "vah": vah, "val": val}
    return out


def open_at(d: dict, t: int):
    """The open of the candle that starts exactly at t, or None."""
    i = int(np.searchsorted(d["ts"], t))
    return float(d["open"][i]) if i < len(d["ts"]) and d["ts"][i] == t else None


def other_levels(d: dict, table: list, n: int, weeks: dict, touched: list) -> dict:
    """The levels known at the start of day table[n], besides the previous day's high and low:
    profile levels (previous day's and previous week's value areas, naked daily POCs) and opens and extremes
    (the day's, week's and month's open, the previous week's high and low)."""
    cur, prev = table[n], table[n - 1]
    week = int(ae.session_starts([cur["day"]], "week")[0])
    month = int(ae.session_starts([cur["day"]], "month")[0])
    profile = [prev["vah"], prev["val"], prev["poc"]]
    plain = [cur["open"]] + [x for x in (open_at(d, week), open_at(d, month)) if x is not None]
    pw = weeks.get(week - 7 * DAY)
    if pw:
        profile += [pw["vah"], pw["val"], pw["poc"]]
        plain += [pw["high"], pw["low"]]
    for m in range(n - 2, -1, -1):
        old = table[m]
        if old["day"] < prev["day"] - NAKED_LOOKBACK * DAY:
            break
        if old["ok"] and (touched[m] is None or touched[m] >= cur["day"]):
            profile.append(old["poc"])
    return {"profile": profile, "plain": plain}


def first_touches(d: dict, table: list) -> list:
    """Per day: the time its POC was first traded after the day's end (within the lookback), or None."""
    out = []
    for rec in table:
        if not rec["ok"]:
            out.append(None)
            continue
        i1 = int(np.searchsorted(d["ts"], rec["day"] + (NAKED_LOOKBACK + 3) * DAY))
        k = first_touch(d, rec["stop"], i1, rec["poc"])
        out.append(None if k is None else int(d["ts"][rec["stop"] + k]))
    return out


def reading(oi: dict | None, t: int):
    """The open-interest reading at t: the last one at or before it, at most 10 minutes old."""
    if oi is None:
        return None
    i = int(np.searchsorted(oi["ts"], t, side="right")) - 1
    return float(oi["oi"][i]) if i >= 0 and t - oi["ts"][i] <= 600_000 else None


def sweep_events(sym: str, d: dict, oi: dict | None, first: str, last: str, outcomes: bool) -> list:
    """Sweeps of the previous day's high and low: the half-hour bar in which price first trades beyond the level
    that day, when that same bar closes back inside it.
    The fade: in at that close, away from the level; stop one row beyond the bar's extreme; out at the previous
    day's POC, at the stop, or at the day's last price."""
    table = day_table(d)
    weeks, touched = week_table(d), first_touches(d, table)
    lo_ms, hi_ms = V._ms(first), V._ms(last)
    rows = []
    for n in range(1, len(table)):
        prev, cur = table[n - 1], table[n]
        if not lo_ms <= cur["day"] <= hi_ms or cur["day"] != prev["day"] + DAY or not prev["ok"]:
            continue
        sl = slice(cur["start"], cur["stop"])
        ts, hi, lo = d["ts"][sl], d["high"][sl], d["low"][sl]
        closes, firstc, lastc = V.buckets(ts, d["close"][sl], cur["day"], HALF)
        levels = None
        for side, level in ((1, prev["high"]), (-1, prev["low"])):
            beyond = np.flatnonzero(hi > level) if side > 0 else np.flatnonzero(lo < level)
            if not beyond.size:
                continue
            b = int((ts[beyond[0]] - cur["day"]) // HALF)
            close = float(closes[b])
            if not ((close < level) if side > 0 else (close > level)):
                continue                                   # the bar closed beyond the level: a break, not a sweep
            a, z = int(firstc[b]), int(lastc[b])
            extreme = float(hi[a:z + 1].max()) if side > 0 else float(lo[a:z + 1].min())
            t_open = cur["day"] + b * HALF
            o0, o1 = reading(oi, t_open), reading(oi, t_open + HALF)
            vol, taker = d["volume"][sl][a:z + 1].sum(), d["taker"][sl][a:z + 1].sum()
            if levels is None:
                levels = other_levels(d, table, n, weeks, touched)
            near = lambda xs: sum(1 for x in xs if abs(x - level) / level <= ZONE)
            row = {"sym": sym, "day": cur["day"], "side": side, "hour": ((b + 1) * HALF - 1) // V.HOUR_MS,
                   "entry": close, "stop": extreme + side * prev["step"],
                   "target": prev["poc"] if ((close > prev["poc"]) if side > 0 else (close < prev["poc"])) else None,
                   "gi": cur["start"] + z, "day_end": cur["stop"],
                   "flush": None if o0 is None or o1 is None else bool(o1 < o0),
                   "absorbed": bool(vol > 0 and (2 * taker - vol) * side / vol >= ABSORB),
                   "k_profile": near(levels["profile"]), "k_plain": near(levels["plain"])}
            row["k"] = row["k_profile"] + row["k_plain"]
            if outcomes:
                row.update(trade(d, row["gi"] + 1, row["day_end"], -side, close, row["stop"], row["target"]))
            rows.append(row)
    return rows


def gap_bar(a: dict, b: dict, diff: dict) -> dict:
    checks = {"events": min(a["n"], b["n"]) >= V.MIN_EVENTS and min(a["days"], b["days"]) >= V.MIN_DAYS,
              "gap": diff["value"] >= GAP, "interval": diff["low"] > 0,
              "halves": min(diff["first_half"], diff["second_half"]) > 0}
    return {"checks": checks, "met": all(checks.values())}


# ---------------------------------------------------------------------------
# S6. The 80% rule on New York hours
# ---------------------------------------------------------------------------

def ny_sessions(first_ms: int, last_ms: int) -> list:
    """(start ms, end ms) of 09:30 to 16:15 New York time on every weekday whose start is in [first, last]."""
    from zoneinfo import ZoneInfo
    ny = ZoneInfo("America/New_York")
    day = datetime.fromtimestamp(first_ms / 1000, tz=timezone.utc).date() - timedelta(days=5)
    out = []
    while True:
        if day.weekday() < 5:
            a = int(datetime(day.year, day.month, day.day, 9, 30, tzinfo=ny).timestamp() * 1000)
            if a > last_ms + DAY:
                break
            out.append((a, int(datetime(day.year, day.month, day.day, 16, 15, tzinfo=ny).timestamp() * 1000)))
        day += timedelta(days=1)
    return out


def session_rows(sym: str, d: dict, first: str, last: str, need: int, outcomes: bool) -> list:
    """The 80% rule's rows (research.value_area_rule.find_event and score) with sessions in place of UTC days:
    the previous weekday's session gives the value area, the session's first price is the open, half-hour bars
    count from 09:30, and the outcome runs to 16:15."""
    lo, hi = V._ms(first), V._ms(last)
    sess = ny_sessions(lo, hi)
    rows = []
    for (pa, pz), (a, z) in zip(sess, sess[1:]):
        if not lo <= a <= hi + DAY - 1:
            continue
        p0, p1, c0, c1 = (int(np.searchsorted(d["ts"], t)) for t in (pa, pz, a, z))
        if p1 - p0 < RTH_MIN_BARS or c1 - c0 < RTH_MIN_BARS or not d["volume"][p0:p1].sum() > 0:
            continue
        ref = float(d["close"][p1 - 1])
        step = ae.nice_step(ref * V.STEP_FRACTION)
        poc, vah, val = ae.session_levels(d["high"][p0:p1], d["low"][p0:p1], d["volume"][p0:p1], step)
        if not vah > val:
            continue
        day = {"start": a, **{k: d[k][c0:c1] for k in ("ts", "open", "high", "low", "close")}}
        ev = V.find_event(day, vah, val, HALF, need)
        ev.update(sym=sym, day=a, poc=poc, vah=vah, val=val, step=step, width=(vah - val) / ref,
                  open_side=(1 if day["open"][0] > vah else -1 if day["open"][0] < val else 0))
        if ev["state"] == "event":
            ev["gi"] = c0 + ev.pop("end")
            ev["day_end"] = c1
            if outcomes:
                ev.update(V.score(d, ev))
        rows.append(ev)
    return rows


# ---------------------------------------------------------------------------
# Counts, the run, and what the bars can see
# ---------------------------------------------------------------------------

def load_oi(sym: str, cache: Path):
    path = cache / f"{sym}-oi.npz"
    if not path.exists():
        return None
    with np.load(path) as z:
        return {"ts": z["ts"], "oi": z["oi"]}


def gather(first: str, last: str, cache: Path, symbols, outcomes: bool) -> dict:
    out = {"races": [], "outside": [], "sweeps": [], "sessions": {name: [] for name in V.READINGS}, "revisits": []}
    for sym in symbols:
        d = V.load(sym, cache)
        out["races"] += poc_races(sym, d, first, last, outcomes)
        out["outside"] += outside_events(sym, d, first, last, outcomes)
        out["sweeps"] += sweep_events(sym, d, load_oi(sym, cache), first, last, outcomes)
        for name, need in V.READINGS.items():
            out["sessions"][name] += session_rows(sym, d, first, last, need, outcomes)
        if outcomes:
            out["revisits"] += revisits(d, first, last)
    return out


def per_cluster(rows: list) -> list:
    n: dict = {}
    for r in rows:
        n[r["day"]] = n.get(r["day"], 0) + 1
    return [n[t] for t in sorted(n)]


def shape(first: str = V.IN_SAMPLE[0], last: str = V.IN_SAMPLE[1], cache: Path = V.CACHE_DIR, symbols=V.SYMBOLS) -> dict:
    """Counts only: nothing after an event's time is read, and no trade or race is scored."""
    g = gather(first, last, cache, symbols, outcomes=False)
    count = lambda rows, sel=lambda r: True: sum(1 for r in rows if sel(r))
    out = {"period": [first, last], "candles_sha256": V.data_hash(symbols, cache)}
    out["S2"] = {kind: {"races": count(g["races"], lambda r: r["kind"] == kind),
                        "per_week": per_cluster([r for r in g["races"] if r["kind"] == kind])} for kind in ("fresh", "old")}
    acc = [r for r in g["outside"] if r["state"] == "accepted"]
    out["S3"] = {"opened_inside": len(g["outside"]), "states": {s: count(g["outside"], lambda r, s=s: r["state"] == s)
                                                                 for s in sorted({r["state"] for r in g["outside"]})},
                 "above": count(acc, lambda r: r["side"] > 0), "below": count(acc, lambda r: r["side"] < 0),
                 "btc": count(acc, lambda r: r["sym"] == "BTCUSDT"), "per_day": per_cluster(acc)}
    sw = g["sweeps"]
    out["S4"] = {"sweeps": len(sw), "high": count(sw, lambda r: r["side"] > 0), "low": count(sw, lambda r: r["side"] < 0),
                 "btc": count(sw, lambda r: r["sym"] == "BTCUSDT"), "with_target": count(sw, lambda r: r["target"] is not None),
                 "flush": {str(v): count(sw, lambda r, v=v: r["flush"] is v) for v in (True, False, None)},
                 "absorbed": {str(v): count(sw, lambda r, v=v: r["absorbed"] is v) for v in (True, False)},
                 "per_day": per_cluster(sw),
                 "per_day_flush": per_cluster([r for r in sw if r["flush"] is True]), "per_day_no_flush": per_cluster([r for r in sw if r["flush"] is False]),
                 "per_day_absorbed": per_cluster([r for r in sw if r["absorbed"]]), "per_day_not_absorbed": per_cluster([r for r in sw if not r["absorbed"]])}
    out["S5"] = {"k": {str(k): count(sw, lambda r, k=k: min(r["k"], 3) == k) for k in range(4)},
                 "profile_level_near": count(sw, lambda r: r["k_profile"] > 0), "plain_level_near": count(sw, lambda r: r["k_plain"] > 0),
                 "per_day_alone": per_cluster([r for r in sw if r["k"] == 0]), "per_day_near": per_cluster([r for r in sw if r["k"] > 0])}
    out["S6"] = {}
    for name, rows in g["sessions"].items():
        block = {"coin_sessions": len(rows), "open": {"above": count(rows, lambda r: r["open_side"] > 0),
                                                      "inside": count(rows, lambda r: r["open_side"] == 0), "below": count(rows, lambda r: r["open_side"] < 0)}}
        for kind in ("rule", "control"):
            mine = [r for r in rows if r["kind"] == kind]
            ev = [r for r in mine if r["state"] == "event"]
            block[kind] = {"states": {s: count(mine, lambda r, s=s: r["state"] == s) for s in sorted({r["state"] for r in mine})},
                           "events": len(ev), "sessions": len({r["day"] for r in ev}), "btc": count(ev, lambda r: r["sym"] == "BTCUSDT"),
                           "per_day": per_cluster(ev)}
        widths = np.array([r["width"] for r in rows])
        block["width_pct_median"] = round(float(np.median(widths)) * 100, 2)
        out["S6"][name] = block
    return out


KEEP = ("n", "days", "value", "low", "high", "first_half", "second_half")
brief = lambda st: {k: st[k] for k in KEEP if k in st}


def run_study(first: str, last: str, cache: Path = V.CACHE_DIR, symbols=V.SYMBOLS, draws: int = V.DRAWS) -> dict:
    g = gather(first, last, cache, symbols, outcomes=True)
    out = {"period": [first, last], "candles_sha256": V.data_hash(symbols, cache)}
    stat = lambda rows, key: brief(V.ratio(rows, key, draws))
    quick = lambda rows, key: brief(V.ratio(rows, key, 2000))

    # S2
    out["S2"] = {}
    for kind in ("fresh", "old"):
        mine = [r for r in g["races"] if r["kind"] == kind and r["outcome"] is not None]
        decided = [{**r, "poc_first": float(r["outcome"] == "poc")} for r in mine if r["outcome"] in ("poc", "mirror")]
        st = stat(decided, "poc_first")
        out["S2"][kind] = {"races": len(mine), "outcomes": {o: sum(1 for r in mine if r["outcome"] == o) for o in ("poc", "mirror", "tie", "none")},
                           "poc_first": st, **share_bar(st),
                           "by_distance": {name: quick([r for r in decided if a <= r["dist"] < b], "poc_first")
                                           for name, a, b in (("0.25-0.5%", 0.0025, 0.005), ("0.5-1%", 0.005, 0.01), ("1-2%", 0.01, 0.02), ("over 2%", 0.02, 9))},
                           "btc": quick([r for r in decided if r["sym"] == "BTCUSDT"], "poc_first")}
    rv = g["revisits"]
    within = lambda rows, k: (sum(1 for r in rows if r["after"] is not None and r["after"] <= k) / len(rows)) if rows else None
    out["S2"]["revisits"] = {"days": len(rv), **{f"within_{k}d": within(rv, k) for k in (1, 3, 7, 30)},
                             "by_distance": {name: {"n": len(sel), **{f"within_{k}d": within(sel, k) for k in (1, 7, 30)}}
                                             for name, sel in ((nm, [r for r in rv if a <= r["dist"] < b]) for nm, a, b in
                                                               (("under 0.25%", 0, 0.0025), ("0.25-1%", 0.0025, 0.01), ("1-2%", 0.01, 0.02), ("over 2%", 0.02, 9)))}}

    # S3
    acc = [r for r in g["outside"] if r["state"] == "accepted"]
    net, btc = stat(acc, "net"), stat([r for r in acc if r["sym"] == "BTCUSDT"], "net")
    out["S3"] = {"net": net, "btc_net": btc, **V.trade_bar(net, btc),
                 "reported": {"gross": stat(acc, "gross"), "back_inside": quick(acc, "back_inside"),
                              "closed_outside": quick(acc, "closed_outside"), "one_close_net": stat(acc, "one_net"),
                              "tight_stop_net": stat(acc, "tight_net"),
                              "by_side_net": {"above": quick([r for r in acc if r["side"] > 0], "net"), "below": quick([r for r in acc if r["side"] < 0], "net")},
                              "by_hour_net": {f"{a:02d}-{b:02d}": quick([r for r in acc if a <= r["hour"] < b], "net") for a, b in V.HOURS},
                              "by_year_net": {y: quick([r for r in acc if V.iso(r["day"])[:4] == y], "net") for y in sorted({V.iso(r["day"])[:4] for r in acc})}}}

    # S4
    sw = g["sweeps"]
    net, btc = stat(sw, "net"), stat([r for r in sw if r["sym"] == "BTCUSDT"], "net")
    out["S4"] = {"R1": {"net": net, "btc_net": btc, **V.trade_bar(net, btc)}}
    for name, key in (("R2", "flush"), ("R3", "absorbed")):
        yes, no = [r for r in sw if r[key] is True], [r for r in sw if r[key] is False]
        a, b, diff = stat(yes, "net"), stat(no, "net"), V.difference(yes, no, "net", draws)
        out["S4"][name] = {"with": a, "without": b, "difference": diff, **gap_bar(a, b, diff)}
    out["S4"]["reported"] = {"gross": stat(sw, "gross"), "r_multiple": quick(sw, "r"), "stopped": quick(sw, "stopped"), "reached_poc": quick(sw, "reached"),
                             "by_side_net": {"high": quick([r for r in sw if r["side"] > 0], "net"), "low": quick([r for r in sw if r["side"] < 0], "net")},
                             "flush_and_absorbed_net": quick([r for r in sw if r["flush"] is True and r["absorbed"]], "net"),
                             "neither_net": quick([r for r in sw if r["flush"] is False and not r["absorbed"]], "net"),
                             "by_hour_net": {f"{a:02d}-{b:02d}": quick([r for r in sw if a <= r["hour"] < b], "net") for a, b in V.HOURS},
                             "by_year_net": {y: quick([r for r in sw if V.iso(r["day"])[:4] == y], "net") for y in sorted({V.iso(r["day"])[:4] for r in sw})},
                             "by_coin_net": {s: quick([r for r in sw if r["sym"] == s], "net") for s in symbols}}

    # S5
    near, alone = [r for r in sw if r["k"] > 0], [r for r in sw if r["k"] == 0]
    a, b, diff = stat(near, "net"), stat(alone, "net"), V.difference(near, alone, "net", draws)
    out["S5"] = {"near": a, "alone": b, "difference": diff, **gap_bar(a, b, diff),
                 "reported": {"by_k_net": {str(k) + ("+" if k == 3 else ""): quick([r for r in sw if min(r["k"], 3) == k], "net") for k in range(4)},
                              "profile_level_near_net": quick([r for r in sw if r["k_profile"] > 0], "net"),
                              "only_plain_level_near_net": quick([r for r in sw if r["k_profile"] == 0 and r["k_plain"] > 0], "net")}}

    # S6
    out["S6"] = {name: V.reading_block(rows, symbols, draws) for name, rows in g["sessions"].items()}
    for name, rows in g["sessions"].items():
        out["S6"][name]["coin_sessions"] = len(rows)
    return out


def power(shape_json: dict, reps: int = 2000, spread: float = 0.015) -> dict:
    """How often each kind of bar is met on made-up outcomes with this study's events per day (or week).
    Events in one day (or week) share one outcome here, the harder case. Normal-approximation intervals."""
    rng = np.random.default_rng(V.RNG_SEED)

    def summary(num, den):
        v = num.sum() / den.sum()
        se = np.sqrt(((num - v * den) ** 2).sum()) / den.sum()
        h = len(num) // 2
        return v, se, num[:h].sum() / den[:h].sum(), num[h:].sum() / den[h:].sum()

    def share(per, grid=(0.50, 0.52, 0.55, 0.57, 0.60)):
        per = np.array(per, dtype=float)
        res = {}
        for p in grid:
            met = 0
            for _ in range(reps):
                v, se, a, b = summary((rng.random(len(per)) < p) * per, per)
                met += v >= SHARE and v - 1.96 * se > 0.5 and min(a, b) > 0.5
            res[p] = round(met / reps, 3)
        return res

    def pays(per, grid=(0.0, 0.0005, 0.001, 0.002, 0.003)):
        per = np.array(per, dtype=float)
        res = {}
        for mean in grid:
            met = 0
            for _ in range(reps):
                v, se, a, b = summary(rng.normal(mean, spread, len(per)) * per, per)
                met += v > 0 and v - 1.96 * se > 0 and min(a, b) > 0
            res[mean] = round(met / reps, 3)
        return res

    def gap(per_a, per_b, grid=(0.0, 0.0005, 0.001, 0.002, 0.003)):
        pa, pb = np.array(per_a, dtype=float), np.array(per_b, dtype=float)
        res = {}
        for g in grid:
            met = 0
            for _ in range(reps):
                v, se, a, b = summary(rng.normal(g, spread, len(pa)) * pa, pa)
                w, se2, c, e = summary(rng.normal(0, spread, len(pb)) * pb, pb)
                met += v - w >= GAP and v - w - 1.96 * np.hypot(se, se2) > 0 and min(a - c, b - e) > 0
            res[g] = round(met / reps, 3)
        return res

    s = shape_json
    return {"spread": spread,
            "S2_fresh": share(s["S2"]["fresh"]["per_week"]), "S2_old": share(s["S2"]["old"]["per_week"]),
            "S3": pays(s["S3"]["per_day"]), "S4_R1": pays(s["S4"]["per_day"]),
            "S4_R2": gap(s["S4"]["per_day_flush"], s["S4"]["per_day_no_flush"]),
            "S4_R3": gap(s["S4"]["per_day_absorbed"], s["S4"]["per_day_not_absorbed"]),
            "S5": gap(s["S5"]["per_day_near"], s["S5"]["per_day_alone"]),
            "S6_trade": pays(s["S6"]["two_closes"]["rule"]["per_day"])}


def main() -> None:
    import argparse
    import json
    import sys
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("fetch-oi", "shape", "power", "run"):
        p = sub.add_parser(name)
        p.add_argument("--cache", type=Path, default=V.CACHE_DIR)
        p.add_argument("--out", type=Path)
        if name == "shape":
            p.add_argument("--holdout", action="store_true")
        if name == "power":
            p.add_argument("--shape", type=Path, required=True)
        if name == "run":
            p.add_argument("--holdout", action="store_true", help="the held-out months instead of the in-sample period")
    a = ap.parse_args()
    if a.cmd == "fetch-oi":
        fetch_oi(cache=a.cache)
        return
    if a.cmd == "shape":
        res = shape(*(V.HOLDOUT if a.holdout else V.IN_SAMPLE), cache=a.cache)
    elif a.cmd == "power":
        res = power(json.loads(a.shape.read_text()))
    else:
        res = run_study(*(V.HOLDOUT if a.holdout else V.IN_SAMPLE), cache=a.cache)
    if a.out:
        a.out.write_text(json.dumps(res, indent=1, default=float))
    strip = lambda x: ({k: strip(v) for k, v in x.items() if not str(k).startswith("per_")} if isinstance(x, dict) else x)
    json.dump(strip(res), sys.stdout, indent=1, default=float)
    print()


if __name__ == "__main__":
    main()
