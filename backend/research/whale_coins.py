"""
Do the coins whales are long in beat the other coins over the next week?
(docs/reviews/whale-coins-study.md, declared before running)

Whales: wallets with $1M or more of perp equity on the day (the live rule, cohorts.assign). Their positions on
each past day come from Hyperliquid's funding record, which has one row per wallet, coin and day back to the
wallet's first day (the fills the wallet-history rebuild reads stop at a wallet's latest 10,000).

Run from backend/:

  python -m research.whale_coins census  [--leaderboard JSON] [--minutes N]   (who was a whale when)
  python -m research.whale_coins funding [--minutes N]                        (their positions, day by day)
  python -m research.whale_coins candles                                      (daily closes of the coins they held)
  python -m research.whale_coins status
  python -m research.whale_coins shape [--holdout] [--out JSON]      (counts only: no return is read)
  python -m research.whale_coins power --shape JSON                  (the bars on made-up returns)
  python -m research.whale_coins run [--holdout] [--out JSON]

Reads go through Hyperliquid's public API at about 1,000 weight a minute (1,200 allowed per IP) and are kept in
--db, so a run cut short continues where it stopped. Nothing here runs on the production server.
"""
from __future__ import annotations

import argparse
import bisect
import datetime
import json
import sqlite3
import sys
import time
import urllib.request
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from backtest import wallet_history_rebuild as R

DAY = R.DAY
URL_LEADERBOARD = R.LEADERBOARD
DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "whale_coins_cache" / "read.db"

WHALE_EQ = R.WHALE_EQ                    # $1M of perp equity on the day
CAND_VLM, CAND_PNL = 100_000_000, 500_000   # wallets read: $100M+ traded all-time, or $500K+ made or lost all-time
MAX_AGE = 21                             # days: an equity point older than this says nothing about today
MM_VLM_RATIO = R.MM_VLM_RATIO            # market makers out: month volume over 100 times the account value
MAX_POSITIONS = R.MAX_POSITIONS          # a wallet holding more than 25 markets on a day is left out that day
MIN_HOURS = 12                           # a wallet holds a coin on a day if it held it for 12 of the 24 funding hours
MIN_HOLDERS = 5                          # a coin has a reading with 5 whales holding it
MIN_COINS = 15                           # a day counts with 15 coins that have a reading and both returns
HORIZON = 7                              # days: the return that follows, the change in the reading, the last week
PAGE, PAGE_CAP = 500, 80                 # funding rows a page; a wallet is read for 80 pages at most
RATE, WORKERS = 1000, 6

day_of = lambda s: int(datetime.datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc).timestamp() * 1000) // DAY
iso = lambda d: datetime.datetime.fromtimestamp(d * DAY / 1000, datetime.timezone.utc).strftime("%Y-%m-%d")

IN_SAMPLE = ("2024-12-01", "2026-05-31")     # reading days
HOLDOUT = ("2026-06-01", "2026-11-08")       # the last reading day's week closed on 15 November 2026
READ_FROM = day_of(IN_SAMPLE[0]) - HORIZON - 1
READ_TO = day_of(HOLDOUT[1])

IC_BAR = 0.03                # the mean daily rank correlation a reading needs
MIN_DAYS, MIN_WEEKS = 300, 50
BLOCK_DAYS, BLOCK_WEEKS = 28, 4
DRAWS, SEED = 2000, 20261117
COST = 0.0040                # the trade: 0.20% a round trip on each of its two legs, turned over every week


# ---------------------------------------------------------------------------
# Reads (Hyperliquid's public records)
# ---------------------------------------------------------------------------

def info(body: dict):
    out = R.info(body)
    if body["type"] == "userFunding" and isinstance(out, list) and len(out) >= 20:      # +1 weight per 20 rows
        R.BUCKET.take(len(out) // 20)
    return out


def db(path) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE IF NOT EXISTS wallets (addr TEXT PRIMARY KEY, av REAL, vlm REAL, eq BLOB)")
    conn.execute("CREATE TABLE IF NOT EXISTS funding (addr TEXT PRIMARY KEY, rows BLOB, pages INT, truncated INT, first INT, last INT)")
    conn.execute("CREATE TABLE IF NOT EXISTS candles (coin TEXT PRIMARY KEY, rows BLOB)")
    conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
    return conn


pack = lambda o: zlib.compress(json.dumps(o, separators=(",", ":")).encode())
unpack = lambda b: json.loads(zlib.decompress(b)) if b else None


def candidates(leaderboard: dict) -> list:
    """(address, account value, all-time volume) of the wallets to read, in a fixed order (the address's hash).

    Not today's balance: a wallet that is large today because its past positions paid would be read, and its twin
    that lost would not. Volume, or the size of the all-time result whatever its sign, lets both in alike."""
    out = []
    for r in leaderboard["leaderboardRows"]:
        w = dict(r["windowPerformances"])
        av, vlm, pnl = float(r["accountValue"] or 0), float(w["allTime"]["vlm"] or 0), float(w["allTime"]["pnl"] or 0)
        if av > 0 and float(w["month"]["vlm"] or 0) / av > MM_VLM_RATIO:
            continue
        if vlm >= CAND_VLM or abs(pnl) >= CAND_PNL:
            out.append((r["ethAddress"].lower(), av, vlm))
    return sorted(out, key=lambda x: (R.skey(x[0]), x[0]))


def equity(portfolio) -> list:
    """Perp equity through time: [(ms, dollars)], points 7 to 14 days apart, about daily in the last month."""
    return [list(p) for p in R.series(dict(portfolio), ("perpAllTime", "perpMonth"), "accountValueHistory")]


def whale_on(eq: list, d: int) -> bool:
    """A whale at day d's close (00:00 UTC of d + 1): its latest equity point at or before the close is $1M or more
    and at most MAX_AGE days old. The latest point, not a line to the next one: the next point is not yet known at
    the close, and it is higher for the wallets whose positions went on to pay."""
    t = (d + 1) * DAY
    i = bisect.bisect_right(eq, [t, float("inf")]) - 1
    return i >= 0 and t - eq[i][0] <= MAX_AGE * DAY and eq[i][1] >= WHALE_EQ


def whale_days(eq: list, first: int = READ_FROM, last: int = READ_TO) -> list:
    return [d for d in range(first, last + 1) if whale_on(eq, d)]


def _pool(todo, fn, minutes):
    """fn over todo on a few threads, results in order, until the time is up."""
    end = time.time() + minutes * 60
    guarded = lambda x: None if time.time() > end else fn(x)
    with ThreadPoolExecutor(WORKERS) as ex:
        for res in ex.map(guarded, todo):
            if res is None:
                break
            yield res


def census(conn, leaderboard: dict, minutes: float) -> None:
    cand = candidates(leaderboard)
    done = {r[0] for r in conn.execute("SELECT addr FROM wallets")}
    conn.execute("INSERT OR REPLACE INTO meta VALUES ('candidates', ?)", (str(len(cand)),))
    conn.execute("INSERT OR REPLACE INTO meta VALUES ('addresses', ?)", (json.dumps([x[0] for x in cand]),))
    conn.commit()

    def one(x):
        a, av, vlm = x
        return a, av, vlm, pack(equity(info({"type": "portfolio", "user": a})))
    for row in _pool([x for x in cand if x[0] not in done], one, minutes):
        conn.execute("INSERT OR REPLACE INTO wallets VALUES (?,?,?,?)", row)
        conn.commit()


def add_page(rows: list, page: list) -> int:
    """Adds to rows the rows of a page that are not there yet; returns how many were new. A page can end in the
    middle of the rows that share one time (a day's row for every coin held), so the next page starts at that time
    again and brings back some rows already held."""
    last = rows[-1][0] if rows else None
    have = {r[1] for r in rows if r[0] == last}
    new = [r for r in page if not (r[0] == last and r[1] in have)]
    rows += new
    return len(new)


def funding(conn, minutes: float) -> None:
    """Every funding row of each wallet between its first and its last day as a whale."""
    done = {r[0] for r in conn.execute("SELECT addr FROM funding")}
    listed = conn.execute("SELECT value FROM meta WHERE key='addresses'").fetchone()
    wanted = set(json.loads(listed[0])) if listed else None            # the wallets of the declared rule only
    todo = []
    for a, eq in conn.execute("SELECT addr, eq FROM wallets ORDER BY addr"):
        days = whale_days(unpack(eq)) if a not in done and (wanted is None or a in wanted) else None
        if days:
            todo.append((a, days[0], days[-1]))
    todo.sort(key=lambda x: (R.skey(x[0]), x[0]))

    def one(x):
        a, first, last = x
        rows, t, end, pages, trunc = [], first * DAY, (last + 1) * DAY - 1, 0, 0
        while True:
            page = info({"type": "userFunding", "user": a, "startTime": t, "endTime": end})
            pages += 1
            new = add_page(rows, [[r["time"], r["delta"]["coin"], r["delta"]["szi"], r["delta"].get("nSamples")] for r in page])
            if len(page) < PAGE:
                break
            if pages >= PAGE_CAP:
                trunc = 1
                break
            t = page[-1]["time"] + (0 if new else 1)        # the same time again, unless that brought nothing new
        return a, pack(rows), pages, trunc, first, last
    for row in _pool(todo, one, minutes):
        conn.execute("INSERT OR REPLACE INTO funding VALUES (?,?,?,?,?,?)", row)
        conn.commit()


def is_dex(coin: str) -> bool:
    """Builder-dex markets ("xyz:GOLD") are left out, as everywhere in the app."""
    return ":" in coin


def candles(conn) -> None:
    coins = set()
    for (blob,) in conn.execute("SELECT rows FROM funding"):
        coins.update(r[1] for r in unpack(blob) if not is_dex(r[1]))
    done = {r[0] for r in conn.execute("SELECT coin FROM candles")}
    start, end = (READ_FROM - HORIZON - 3) * DAY, (READ_TO + HORIZON + 2) * DAY
    for coin in sorted(coins - done):
        out = info({"type": "candleSnapshot", "req": {"coin": coin, "interval": "1d", "startTime": start, "endTime": end}})
        rows = [[int(c["t"]) // DAY, float(c["c"])] for c in out or [] if int(c["t"]) % DAY == 0]
        conn.execute("INSERT OR REPLACE INTO candles VALUES (?,?)", (coin, pack(rows)))
        conn.commit()


def status(conn) -> dict:
    n = lambda q: conn.execute(q).fetchone()[0]
    return {"candidates": int((conn.execute("SELECT value FROM meta WHERE key='candidates'").fetchone() or [0])[0]),
            "census": n("SELECT COUNT(*) FROM wallets"), "funding": n("SELECT COUNT(*) FROM funding"),
            "funding_pages": n("SELECT COALESCE(SUM(pages), 0) FROM funding"), "cut_at_cap": n("SELECT COALESCE(SUM(truncated), 0) FROM funding"),
            "candles": n("SELECT COUNT(*) FROM candles")}



# ---------------------------------------------------------------------------
# Positions and readings (everything known at the day's close)
# ---------------------------------------------------------------------------

FLAT = R.FLAT_BELOW


def day_positions(rows: list) -> dict:
    """{day: {coin: (mean size, hours)}} from a wallet's funding rows [(ms, coin, size, samples)].

    A daily row is stamped at the day's 00:00 UTC and carries the mean position size over the day's funded hours
    and how many they were. The hourly rows of a wallet's last days (samples None) are averaged the same way."""
    acc = {}
    for t, coin, size, n in rows:
        k = 1 if n is None else int(n)
        s, h = acc.get((int(t) // DAY, coin), (0.0, 0))
        acc[(int(t) // DAY, coin)] = (s + float(size) * k, h + k)
    out = {}
    for (d, coin), (s, h) in acc.items():
        if h > 0:
            out.setdefault(d, {})[coin] = (s / h, h)
    return out


def held(pos: dict):
    """{coin: size} of what a wallet holds on a day: positions held for MIN_HOURS or more. None when it holds more
    than MAX_POSITIONS markets (builder-dex ones counted): the live rule leaves such wallets out."""
    live = {c: s for c, (s, h) in pos.items() if h >= MIN_HOURS and abs(s) > FLAT}
    if len(live) > MAX_POSITIONS:
        return None
    return {c: s for c, s in live.items() if not is_dex(c)}


def load(conn) -> tuple:
    """(table, closes, counts) from the cache.

    table[day][coin] = [whales long, whales short, dollars long, dollars short] over the whales of that day;
    closes[coin][day] = the coin's close at 00:00 UTC of day + 1;
    counts[day] = [whales, with positions read, left out for holding over MAX_POSITIONS markets, holding something]."""
    closes = {coin: {int(d): c for d, c in unpack(blob)} for coin, blob in conn.execute("SELECT coin, rows FROM candles")}
    listed = conn.execute("SELECT value FROM meta WHERE key='addresses'").fetchone()
    wanted = set(json.loads(listed[0])) if listed else None
    fund = {a: (blob, trunc) for a, blob, trunc in conn.execute("SELECT addr, rows, truncated FROM funding")}
    table, counts = {}, {}
    for a, eqb in conn.execute("SELECT addr, eq FROM wallets ORDER BY addr"):
        if wanted is not None and a not in wanted:
            continue
        days = whale_days(unpack(eqb))
        if not days:
            continue
        pos, until = None, READ_TO
        if a in fund:
            rows = unpack(fund[a][0])
            pos = day_positions(rows)
            if fund[a][1] and rows:                      # cut at the page cap: its last day may be half read
                until = int(rows[-1][0]) // DAY - 1
        for d in days:
            c = counts.setdefault(d, [0, 0, 0, 0])
            c[0] += 1
            if pos is None or d > until:
                continue
            c[1] += 1
            h = held(pos.get(d, {}))
            if h is None:
                c[2] += 1
                continue
            c[3] += bool(h)
            for coin, size in h.items():
                cell = table.setdefault(d, {}).setdefault(coin, [0, 0, 0.0, 0.0])
                usd = abs(size) * closes.get(coin, {}).get(d, 0.0)
                if size > 0:
                    cell[0] += 1
                    cell[2] += usd
                else:
                    cell[1] += 1
                    cell[3] += usd
    return table, closes, counts


def level(cell, usd: bool = False):
    """Whales long minus whales short over whales holding the coin (-1 to +1); None under MIN_HOLDERS holders.
    usd: the same in dollars held."""
    if cell is None or cell[0] + cell[1] < MIN_HOLDERS:
        return None
    if usd:
        return (cell[2] - cell[3]) / (cell[2] + cell[3]) if cell[2] + cell[3] > 0 else None
    return (cell[0] - cell[1]) / (cell[0] + cell[1])


def reading(table: dict, d: int, coin: str, kind: str):
    """level: the day's level. change: the level minus the level HORIZON days before. usd: the level in dollars."""
    cell = table.get(d, {}).get(coin)
    if kind == "level":
        return level(cell)
    if kind == "usd":
        return level(cell, usd=True)
    a, b = level(cell), level(table.get(d - HORIZON, {}).get(coin))
    return None if a is None or b is None else a - b


def cross_section(table: dict, closes: dict, d: int, kind: str, lag: int = 0, returns: bool = True) -> list:
    """[(coin, reading, next week's return, last week's return)] for the coins with a reading on day d and closes
    HORIZON days before, on the day and HORIZON days after. The next week runs from the close of d + lag.
    returns=False leaves both returns at 0 (the shape step counts coins without reading a return)."""
    out = []
    for coin in sorted(table.get(d, {})):
        x, px = reading(table, d, coin, kind), closes.get(coin)
        if x is None or px is None:
            continue
        p = [px.get(d - HORIZON), px.get(d), px.get(d + lag), px.get(d + lag + HORIZON)]
        if None in p or min(p) <= 0:
            continue
        out.append((coin, x, p[3] / p[2] - 1 if returns else 0.0, p[1] / p[0] - 1 if returns else 0.0))
    return out


# ---------------------------------------------------------------------------
# The numbers
# ---------------------------------------------------------------------------

def ranks(x) -> np.ndarray:
    """Ranks from 1, ties sharing their mean rank."""
    x = np.asarray(x, dtype=float)
    order = np.argsort(x, kind="mergesort")
    sx, r, i = x[order], np.empty(len(x)), 0
    while i < len(x):
        j = i
        while j + 1 < len(x) and sx[j + 1] == sx[i]:
            j += 1
        r[order[i:j + 1]] = (i + j) / 2 + 1
        i = j + 1
    return r


def corr(a: np.ndarray, b: np.ndarray):
    a, b = a - a.mean(), b - b.mean()
    den = float(np.sqrt((a * a).sum() * (b * b).sum()))
    return float((a * b).sum() / den) if den > 0 else None


def spearman(x, y):
    """Rank correlation; None when one side is all ties."""
    return corr(ranks(x), ranks(y))


def partial(x, y, z):
    """Rank correlation of x and y with z held fixed; None when it cannot be computed."""
    rx, ry, rz = ranks(x), ranks(y), ranks(z)
    xy, xz, yz = corr(rx, ry), corr(rx, rz), corr(ry, rz)
    if None in (xy, xz, yz):
        return None
    den = np.sqrt((1 - xz * xz) * (1 - yz * yz))
    return float((xy - xz * yz) / den) if den > 1e-9 else None


def block_interval(values, block: int, draws: int = DRAWS, seed: int = SEED):
    """90% interval of the mean from a moving-block bootstrap (runs of `block` consecutive values, so neighbours
    that share most of their week stay together). None with fewer than two blocks."""
    v = np.asarray(values, dtype=float)
    n = len(v)
    if n < 2 * block:
        return None
    rng = np.random.default_rng(seed)
    k = -(-n // block)
    starts = rng.integers(0, n - block + 1, size=(draws, k))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(draws, -1)[:, :n]
    lo, hi = np.percentile(v[idx].mean(axis=1), [5, 95])
    return [float(lo), float(hi)]


def day_stats(table: dict, closes: dict, first: int, last: int, kind: str, lag: int = 0) -> list:
    """One row per day with MIN_COINS coins: the rank correlation, across the coins, of the reading with the next
    week's return (ic), the same with the last week's return held fixed (partial), and with the last week (follows)."""
    out = []
    for d in range(first, last + 1):
        cs = cross_section(table, closes, d, kind, lag)
        if len(cs) < MIN_COINS:
            continue
        x, f, p = [c[1] for c in cs], [c[2] for c in cs], [c[3] for c in cs]
        ic, pic, fol = spearman(x, f), partial(x, f, p), spearman(x, p)
        if ic is None or pic is None:
            continue
        out.append({"day": d, "coins": len(cs), "ic": ic, "partial": pic, "follows": fol or 0.0})
    return out


def halves(values) -> list:
    h = len(values) // 2
    return [float(np.mean(values[:h])), float(np.mean(values[h:]))] if h else [0.0, 0.0]


def ic_row(stats: list) -> dict:
    """The deciding row of a reading: met when it has MIN_DAYS days, its mean daily rank correlation is IC_BAR or
    more with a 90% interval above 0, it is above 0 in each half, and with the last week's return held fixed its
    interval is still above 0."""
    if not stats:
        return {"days": 0, "met": False, "confirms": False}
    ic, pic = [s["ic"] for s in stats], [s["partial"] for s in stats]
    row = {"days": len(stats), "coins_median": float(np.median([s["coins"] for s in stats])),
           "mean": float(np.mean(ic)), "interval": block_interval(ic, BLOCK_DAYS), "halves": halves(ic),
           "partial_mean": float(np.mean(pic)), "partial_interval": block_interval(pic, BLOCK_DAYS),
           "follows_last_week": float(np.mean([s["follows"] for s in stats]))}
    row["met"] = bool(row["days"] >= MIN_DAYS and row["mean"] >= IC_BAR and row["interval"] and row["interval"][0] > 0
                      and min(row["halves"]) > 0 and row["partial_interval"] and row["partial_interval"][0] > 0)
    row["confirms"] = bool(row["mean"] > 0 and row["partial_mean"] > 0)        # the held-out check of a row met in sample
    return row


def trade_weeks(table: dict, closes: dict, first: int, last: int, kind: str) -> list:
    """Every HORIZON days from the first: long the third of the coins with the highest reading, short the third with
    the lowest (ties by name), equal weights, held HORIZON days. net = top minus bottom minus COST."""
    out = []
    for d in range(first, last + 1, HORIZON):
        cs = sorted(cross_section(table, closes, d, kind), key=lambda c: (-c[1], c[0]))
        if len(cs) < MIN_COINS:
            continue
        k = len(cs) // 3
        top, bottom = float(np.mean([c[2] for c in cs[:k]])), float(np.mean([c[2] for c in cs[-k:]]))
        out.append({"day": d, "coins": len(cs), "top": top, "bottom": bottom, "median": float(np.median([c[2] for c in cs])),
                    "net": top - bottom - COST})
    return out


def trade_row(weeks: list) -> dict:
    """Met with MIN_WEEKS weeks, a mean net return above 0 with a 90% interval above 0, and above 0 in each half."""
    if not weeks:
        return {"weeks": 0, "met": False, "confirms": False}
    net = [w["net"] for w in weeks]
    row = {"weeks": len(weeks), "gross": float(np.mean([w["top"] - w["bottom"] for w in weeks])), "net": float(np.mean(net)),
           "interval": block_interval(net, BLOCK_WEEKS), "halves": halves(net),
           "top_over_median": float(np.mean([w["top"] - w["median"] for w in weeks])),
           "bottom_over_median": float(np.mean([w["bottom"] - w["median"] for w in weeks]))}
    row["met"] = bool(row["weeks"] >= MIN_WEEKS and row["net"] > 0 and row["interval"] and row["interval"][0] > 0 and min(row["halves"]) > 0)
    row["confirms"] = bool(row["net"] > 0)
    return row


def quarter(d: int) -> str:
    s = iso(d)
    return f"{s[:4]} Q{(int(s[5:7]) - 1) // 3 + 1}"


def run_study(conn, first_s: str, last_s: str) -> dict:
    table, closes, _ = load(conn)
    first, last = day_of(first_s), day_of(last_s)
    out = {"period": [first_s, last_s], "rows": {}, "reported": {}}
    for kind in ("level", "change"):
        stats = day_stats(table, closes, first, last, kind)
        by_q = {}
        for s in stats:
            by_q.setdefault(quarter(s["day"]), []).append(s["ic"])
        later = day_stats(table, closes, first, last, kind, lag=1)
        out["rows"][kind] = {"ic": ic_row(stats), "trade": trade_row(trade_weeks(table, closes, first, last, kind)),
                             "by_quarter": {q: [round(float(np.mean(v)), 4), len(v)] for q, v in sorted(by_q.items())},
                             "one_day_later": round(float(np.mean([s["ic"] for s in later])), 4) if later else None}
    usd = ic_row(day_stats(table, closes, first, last, "usd"))
    out["reported"]["level_in_dollars"] = {k: usd.get(k) for k in ("days", "mean", "interval", "partial_mean")}
    return out


def shape(conn, first_s: str, last_s: str) -> dict:
    """Counts only: wallets, whales a day, coins with a reading, days and weeks that count, and how much each
    reading stays the same from one week to the next. No return is read."""
    table, closes, counts = load(conn)
    first, last = day_of(first_s), day_of(last_s)
    days = [d for d in range(first, last + 1)]
    tot = np.array([counts.get(d, [0, 0, 0, 0]) for d in days], dtype=float)
    out = {"period": [first_s, last_s], "read": status(conn),
           "whales_a_day": {"median": float(np.median(tot[:, 0])), "min": float(tot[:, 0].min()), "max": float(tot[:, 0].max())},
           "positions_read_share": float(tot[:, 1].sum() / max(1.0, tot[:, 0].sum())),
           "over_25_markets_share": float(tot[:, 2].sum() / max(1.0, tot[:, 1].sum())),
           "holding_share": float(tot[:, 3].sum() / max(1.0, tot[:, 1].sum())), "readings": {}, "months": {}}
    for kind in ("level", "change"):
        sizes, same = {}, []
        for d in days:
            cs = cross_section(table, closes, d, kind, returns=False)
            sizes[d] = len(cs)
            before = {c: reading(table, d - HORIZON, c, kind) for c, *_ in cs}
            pair = [(x, before[c]) for c, x, *_ in cs if before[c] is not None]
            if len(pair) >= MIN_COINS:
                r = spearman([p[0] for p in pair], [p[1] for p in pair])
                if r is not None:
                    same.append(r)
        counted = [d for d in days if sizes[d] >= MIN_COINS]
        out["readings"][kind] = {"days": len(counted), "weeks": sum(sizes[d] >= MIN_COINS for d in range(first, last + 1, HORIZON)),
                                 "coins_median": float(np.median([sizes[d] for d in counted])) if counted else 0.0,
                                 "same_a_week_later": float(np.mean(same)) if same else 0.0}
        for d in days:
            m = out["months"].setdefault(iso(d)[:7], {"whales": [], "level": [], "change": []})
            m[kind].append(sizes[d])
            if kind == "level":
                m["whales"].append(counts.get(d, [0])[0])
    out["months"] = {m: {"whales_median": float(np.median(v["whales"])), "coins_level_median": float(np.median(v["level"])),
                         "coins_change_median": float(np.median(v["change"])),
                         "days_level": int(sum(x >= MIN_COINS for x in v["level"])), "days_change": int(sum(x >= MIN_COINS for x in v["change"]))}
                     for m, v in out["months"].items()}
    return out


def level_model(level_same: float, change_same: float) -> tuple:
    """(share, week) of a made-up level that is a slow part plus daily noise: the slow part's share of the variance
    and its correlation a week apart, chosen so that the level and its 7-day change stay the same from one week to
    the next as much as the counted ones do. With L = share * week (the level a week apart), the change a week
    apart is (2L - 1 - share * week^2) / (2 (1 - L))."""
    lv = float(np.clip(level_same, 0.0, 0.995))
    if lv <= 0:
        return 0.0, 0.0
    two_weeks = float(np.clip(2 * lv - 1 - 2 * change_same * (1 - lv), 0.0, lv))      # the level two weeks apart
    week = float(np.clip(two_weeks / lv, 0.0, 0.995))
    return (float(np.clip(lv / week, 0.0, 1.0)) if week > 0 else 0.0), week


def power(shape_json: dict, reps: int = 400, truths=(0.0, 0.02, 0.03, 0.05), spread: float = 0.10) -> dict:
    """How often each bar is met on made-up returns, with this study's days, coins a day and how much each reading
    stays the same from week to week. Made-up level: per coin, a slow series plus daily noise (level_model); the
    made-up change is that level minus itself 7 days before. Made-up daily returns: noise plus a part that follows
    yesterday's reading, sized so that the mean daily rank correlation with the next week is the stated truth. For
    the trade, a week's returns spread by `spread` across the coins (a guess)."""
    rng = np.random.default_rng(SEED)
    share, week = level_model(shape_json["readings"]["level"]["same_a_week_later"], shape_json["readings"]["change"]["same_a_week_later"])
    phi = week ** (1 / HORIZON)
    out = {"spread": spread, "reps": reps, "level_model": {"slow_share": round(share, 3), "slow_a_week_apart": round(week, 3)}}

    def rank_rows(a):
        return np.argsort(np.argsort(a, axis=1), axis=1).astype(float)

    def row_corr(a, b):
        a, b = a - a.mean(1, keepdims=True), b - b.mean(1, keepdims=True)
        return (a * b).sum(1) / np.sqrt((a * a).sum(1) * (b * b).sum(1))

    def sim(days, n, kind, beta):
        burn, m = 60, days + 60 + 2 * HORIZON + 1
        e = rng.standard_normal((m, n)) * np.sqrt(1 - phi * phi)
        slow = np.empty((m, n))
        slow[0] = rng.standard_normal(n)
        for t in range(1, m):
            slow[t] = phi * slow[t - 1] + e[t]
        x = np.sqrt(share) * slow + np.sqrt(1 - share) * rng.standard_normal((m, n))
        if kind == "change":
            x[HORIZON:] = (x[HORIZON:] - x[:-HORIZON]) / np.sqrt(2 * (1 - share * week))
        r = rng.standard_normal((m, n))
        r[1:] += beta * x[:-1]
        c = np.vstack([np.zeros((1, n)), np.cumsum(r, axis=0)])
        t = np.arange(burn + HORIZON, burn + HORIZON + days)
        nxt, lst = c[t + 1 + HORIZON] - c[t + 1], c[t + 1] - c[t + 1 - HORIZON]
        rx, rf, rp = rank_rows(x[t]), rank_rows(nxt), rank_rows(lst)
        xy, xz, yz = row_corr(rx, rf), row_corr(rx, rp), row_corr(rf, rp)
        pic = (xy - xz * yz) / np.sqrt((1 - xz ** 2) * (1 - yz ** 2))
        k = n // 3
        order = np.argsort(-x[t][::HORIZON], axis=1)
        wk = nxt[::HORIZON] / nxt[::HORIZON].std(axis=1, keepdims=True) * spread
        top = np.take_along_axis(wk, order[:, :k], 1).mean(1)
        bottom = np.take_along_axis(wk, order[:, -k:], 1).mean(1)
        same = row_corr(rx[HORIZON:], rx[:-HORIZON]).mean()
        return xy, pic, top - bottom - COST, same

    def strength(n, kind, ref=0.08):
        """The rank correlation that a following part of size 1 gives. Measured on a strong relation over many days,
        where it is read precisely; while small, the two are proportional."""
        return float(sim(20000, n, kind, ref)[0].mean()) / ref

    for kind, r in shape_json["readings"].items():
        days, n = int(r["days"]), int(r["coins_median"])
        if days < 2 * BLOCK_DAYS or n < 6:
            out[kind] = None
            continue
        block = {"days": days, "coins": n, "same_a_week_later": round(float(sim(3000, n, kind, 0.0)[3]), 3), "ic_row": {}, "trade_row": {},
                 "mean_seen": {}}
        per_unit = strength(n, kind)
        for truth in truths:
            beta, met_ic, met_tr, seen = truth / per_unit, 0, 0, []
            for _ in range(reps):
                ic, pic, net, _ = sim(days, n, kind, beta)
                seen.append(float(ic.mean()))
                a, b = block_interval(ic, BLOCK_DAYS), block_interval(pic, BLOCK_DAYS)
                met_ic += days >= MIN_DAYS and ic.mean() >= IC_BAR and a[0] > 0 and min(halves(ic)) > 0 and b[0] > 0
                w = block_interval(net, BLOCK_WEEKS)
                met_tr += bool(len(net) >= MIN_WEEKS and net.mean() > 0 and w and w[0] > 0 and min(halves(net)) > 0)
            block["ic_row"][str(truth)] = round(met_ic / reps, 3)
            block["trade_row"][str(truth)] = round(met_tr / reps, 3)
            block["mean_seen"][str(truth)] = [round(float(np.mean(seen)), 4), round(float(np.percentile(seen, 5)), 4), round(float(np.percentile(seen, 95)), 4)]
        out[kind] = block
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("census", "funding", "candles", "status", "shape", "power", "run"):
        p = sub.add_parser(name)
        p.add_argument("--db", default=str(DEFAULT_DB))
        p.add_argument("--leaderboard", help="a saved leaderboard file (census); fetched when not given")
        p.add_argument("--minutes", type=float, default=110.0)
        p.add_argument("--holdout", action="store_true")
        p.add_argument("--shape", help="the shape step's JSON (power)")
        p.add_argument("--out")
    args = ap.parse_args()
    conn = db(args.db)
    R.BUCKET = R.Bucket(RATE)
    if args.cmd == "census":
        lb = json.load(open(args.leaderboard)) if args.leaderboard else json.loads(urllib.request.urlopen(URL_LEADERBOARD, timeout=180).read())
        census(conn, lb, args.minutes)
    elif args.cmd == "funding":
        funding(conn, args.minutes)
    elif args.cmd == "candles":
        candles(conn)
    if args.cmd in ("census", "funding", "candles", "status"):
        print(json.dumps({**status(conn), "rate_limited": R.STATS["429"], "errors": R.STATS["errors"]}))
        return
    first, last = HOLDOUT if args.holdout else IN_SAMPLE
    if args.cmd == "shape":
        out = shape(conn, first, last)
    elif args.cmd == "power":
        out = power(json.load(open(args.shape)))
    else:
        out = run_study(conn, first, last)
    text = json.dumps(out, indent=1)
    if args.out:
        Path(args.out).write_text(text)
    print(text)


if __name__ == "__main__":
    main()
