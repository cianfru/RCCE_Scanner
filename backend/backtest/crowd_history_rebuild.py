"""
Profitable traders, re-picked each day, over the past year (docs/reviews/wallet-history.md). Context, not a signal.

HyperLens re-picks its profitable traders every day from Hyperliquid's leaderboard: the wallets up 30% or more and
$10K or more over the last 30 days, in profit before them, with $10K+ of account value and $5K+ in perps, market
makers out, the best 600 by that return (hl_intelligence, roster version 2). Hyperliquid keeps no past
leaderboards, and its account histories thin out to points days or weeks apart beyond the last month, too coarse
for a 30-day return. So this applies the same rule, day by day, to the wallets whose every trade is already
rebuilt: the weighted sample of `backtest.wallet_history_rebuild` (wallets that were in smart money or whales on
some day of the year). For each wallet and day:

- its profit over the last 30 days, marked at the daily closes from its own fills (positions at both closes valued
  at the coin's close, less what it paid and received in between; before fees and funding);
- its return: that profit over its perp equity 30 days earlier plus what it added since (equity change less
  profit, when positive), its equity from Hyperliquid's own portfolio history;
- in the list that day when it passes the rule; with more than 600 (weighted), the best 600 by return.

The day's reading is the list's open positions at the 00:00 UTC close, each wallet-coin position once, long or
short, weighted by one over each wallet's chance of being sampled: the measure HyperLens records (trader_lean)
and Outrider counts. The list here draws only on wallets that were in smart money or whales at some point, so its
level can sit apart from HyperLens's, whose list also takes smaller accounts; the page sets it to the recorded
level where the two overlap.

Run from backend/ after the wallet rebuild (no Hyperliquid calls):

  python -m backtest.crowd_history_rebuild --db data/wallet_history_cache/rebuild.db [--out seeds/crowd_share_seed.json]
"""
from __future__ import annotations

import argparse
import bisect
import collections
import datetime
import json
from pathlib import Path

from backtest.wallet_history_rebuild import (COINS, DAY, DEFAULT_DB, MAX_POSITIONS, chance, day_ends, db, in_sample,
                                             interp, positions_at, price)

SEED = Path(__file__).resolve().parent.parent / "seeds" / "crowd_share_seed.json"
WINDOW = 30                      # days of return, as the leaderboard's month
MIN_ROI, MIN_PNL = 0.30, 10_000
MIN_EQUITY, MIN_PERP = 10_000, 5_000
MIN_BASE = 1_000                 # a month that began nearly empty reads as a huge return (_meaningful_roi)
TARGET = 600


def cash_flows(rows: list) -> tuple:
    """(times, running sum of signed size x price): what the wallet paid (+) and received (-) up to each fill."""
    times, run, s = [], [], 0.0
    for r in rows:
        s += r[3] * r[4]
        times.append(r[0])
        run.append(s)
    return times, run


def paid_by(flows: tuple, t: int) -> float:
    times, run = flows
    i = bisect.bisect_right(times, t)
    return run[i - 1] if i else 0.0


def profit(book0: dict, book1: dict, flows: dict, t0: int, t1: int, px0, px1) -> float | None:
    """Marked profit between two closes over every coin held or traded: the value of the positions at the second
    close less at the first, less what was paid in between. None when a coin has no price."""
    total = 0.0
    for c in set(book0) | set(book1) | {c for c, f in flows.items() if paid_by(f, t1) != paid_by(f, t0)}:
        s0, s1 = book0.get(c, 0.0), book1.get(c, 0.0)
        p0, p1 = (px0(c) if s0 else 0.0), (px1(c) if s1 else 0.0)
        if p0 is None or p1 is None:
            return None
        f = flows.get(c)
        spent = paid_by(f, t1) - paid_by(f, t0) if f else 0.0
        total += s1 * p1 - s0 * p0 - spent
    return total


def roster_rows(conn, share: float, whale_share: float, end_ms=None) -> dict:
    """Per day: the list's weighted long and short positions, overall and per main coin, with how many sampled
    wallets made the list."""
    ends = day_ends(end_ms)
    meta = {a: (k, av, vlm) for a, k, av, vlm in conn.execute("SELECT addr, skey, lb_av, lb_vlm FROM wallets")}
    census = {a: json.loads(c) for a, c in conn.execute("SELECT addr, census FROM wallets WHERE census IS NOT NULL")
              if in_sample(meta[a][0], meta[a][1], meta[a][2], share, whale_share)}
    closes = {c: {int(d): float(v) for d, v in json.loads(data)} for c, data in conn.execute("SELECT coin, data FROM candles")}
    by_day = collections.defaultdict(list)          # day -> [(roi, weight, book)]
    covered = collections.defaultdict(float)        # day -> weight of wallets whose 30 days are covered
    for addr, cur, data, cov in conn.execute("SELECT addr, current, data, coverage_start FROM fills"):
        rec = census.get(addr)
        if rec is None:
            continue
        cur, data = json.loads(cur), json.loads(data)
        weight = 1.0 / chance(meta[addr][1], meta[addr][2], share, whale_share)
        books = positions_at(cur, data, [(d, t) for d, t in ends if t >= cov], end_ms)
        flows = {c: cash_flows(rows) for c, rows in data.items()}
        for d, t1 in ends:
            t0 = t1 - WINDOW * DAY
            if t0 < cov or (d - WINDOW) not in books:
                continue
            covered[d] += weight
            b0, b1 = books[d - WINDOW], books[d]
            if len(b1) > MAX_POSITIONS:
                continue
            pnl = profit(b0, b1, flows, t0, t1, lambda c: price(closes, data, c, d - WINDOW, t0),
                         lambda c: price(closes, data, c, d, t1))
            if pnl is None or pnl < MIN_PNL:
                continue
            eq0, eq1 = interp(rec["eq"], t0) or 0.0, interp(rec["eq"], t1) or 0.0
            before = interp(rec["pnl"], t0)
            base = eq0 + max(0.0, eq1 - eq0 - pnl)
            if base < MIN_BASE or eq1 < max(MIN_EQUITY, MIN_PERP) or before is None or before < 0:
                continue
            roi = pnl / base
            if roi >= MIN_ROI:
                by_day[d].append((roi, weight, b1))
    out = {}
    for d, _ in ends:
        if not covered.get(d):
            continue
        members = sorted(by_day.get(d, []), key=lambda m: -m[0])
        acc = collections.defaultdict(float)
        n = 0
        for roi, w, book in members:
            if acc["members"] >= TARGET:                   # the best 600 (weighted) by return
                break
            acc["members"] += w
            n += 1
            for c, sz in book.items():
                acc["long" if sz > 0 else "short"] += w
                if c in COINS:
                    acc[f"{c}_long" if sz > 0 else f"{c}_short"] += w
        out[d] = {"long": round(acc["long"]), "short": round(acc["short"]), "members": round(acc["members"]), "sampled": n,
                  "coins": {c: [round(acc[f"{c}_long"]), round(acc[f"{c}_short"])] for c in COINS}}
    return out


def seed(rows: dict, recorded_from: int | None = None) -> dict:
    """The page's seed: [day, long, short] per day with positions (the share long is long / (long + short))."""
    days = sorted(d for d, r in rows.items() if r["long"] + r["short"] and (recorded_from is None or d < recorded_from))
    epoch = datetime.date(1970, 1, 1)
    return {
        "version": 2,
        "source": "backend/backtest/crowd_history_rebuild.py on the wallet rebuild's sample (wallets in smart money "
                  "or whales on some day): HyperLens's daily rule applied each day",
        "rule": "30-day return 30%+ and profit $10K+, in profit before, $10K+ equity, best 600; open positions at "
                "the 00:00 UTC close, each wallet-coin once",
        "built": datetime.date.today().isoformat(),
        "columns": ["day", "long", "short"],
        "rows": [[d, rows[d]["long"], rows[d]["short"]] for d in days],
        "coin_columns": ["day", "long", "short"],
        "coins": {c: [[d, *rows[d]["coins"][c]] for d in days if sum(rows[d]["coins"][c])] for c in COINS},
        "members": [[d, rows[d]["members"], rows[d]["sampled"]] for d in days],
        "first": (epoch + datetime.timedelta(days=days[0])).isoformat() if days else None,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--share", type=float, default=0.10)
    ap.add_argument("--whale-share", type=float, default=0.35)
    ap.add_argument("--out", default=str(SEED))
    a = ap.parse_args()
    rows = roster_rows(db(a.db), a.share, a.whale_share)
    doc = seed(rows)
    Path(a.out).write_text(json.dumps(doc, separators=(",", ":")) + "\n")
    print(f"wrote {a.out}: {len(doc['rows'])} days from {doc['first']}")
