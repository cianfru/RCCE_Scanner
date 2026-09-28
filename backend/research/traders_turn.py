"""
Do profitable traders turn when coins top out? (docs/reviews/traders-turn-at-tops-study.md)

    python research/traders_turn.py <data dir> [--out result.json]      (run from backend/)

<data dir> holds fills/<address>.json ({"cohorts": [...], "fills": [[coin, time_ms, px, sz, side,
dir, startPosition, twap], ...]}, each list newest first) and candles/<coin>.json ([[t_ms, close],
...], 1h), pulled from Hyperliquid's public API for today's roster. Nothing here reads the product.

Every measure at a 4-hour close T uses fills strictly before T and closes up to T; only the
outcomes (forward returns) and the hindsight table D3 read later closes.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import warnings
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engines.rcce_engine import (LEN_LONG, LEN_REGRESSION, Z_SCALE, Z_SMOOTH,  # noqa: E402
                                 _calc_zscore_hybrid)

H = 3600 * 1000
BAR = 4 * H
DAY = 24 * H
LAG = 6                      # 24 hours in 4-hour bars
COOL = 72 * H                # between events on one coin (and between market turns)
HOLD = 30 * DAY              # headline: events at or before data end minus this
CAP = 2000                   # per-list cap of the fills endpoints
MIN_HOLDERS = 5
SHARE_DROP = 0.20
SHORTS_RISE = 2
MKT_DROP = 0.10
Z_STRETCH = 2.0
TOP_WIN = 18                 # 72 hours either side, for D3
HORIZONS = (1, 3, 7)
N_BOOT = 2000
SEED = 20260926
EPS = 1e-9                   # float slack on the 20- and 10-point thresholds
# Positions smaller than this are rounding leftovers of a close, set to flat. The API's merged sizes
# and startPositions carry float noise ('727061.7999999999'), so a full close can leave 1e-10. In
# this data every leftover is below 1e-8 and the smallest real position is 1e-5 (BTC's size step).
DUST = 1e-6
GROUPS = ("money_printer", "smart_money")
BANDS = (("below 0", -np.inf, 0.0), ("0 to 1", 0.0, 1.0), ("1 to 2", 1.0, 2.0), ("2 or more", 2.0, np.inf))

# The protocol fixes the engine's z as 200-bar average, 300-bar regression, no smoothing, scale 1.
assert (LEN_LONG, LEN_REGRESSION, Z_SMOOTH, Z_SCALE) == (200, 300, 1, 1.0), "engine z settings moved"


def iso(t):
    return datetime.fromtimestamp(t / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def is_perp(coin):
    """Perpetual main-dex markets only: no builder-dex (':'), spot ('@', '/') or outcome ('#') markets."""
    return not any(ch in coin for ch in ":@/#")


# ---------------------------------------------------------------- fills and positions

def coverage_start(fills):
    """Later of the two cut-offs: the oldest fill of each list that hit the 2,000 cap (0 if neither did)."""
    reg = [f[1] for f in fills if not f[7]]
    twap = [f[1] for f in fills if f[7]]
    return max(min(reg) if len(reg) >= CAP else 0, min(twap) if len(twap) >= CAP else 0)


def positions(fills):
    """Per perpetual coin: (fill times, position after each, position before each), oldest first.

    Position after a fill = startPosition + sz for a buy, - sz for a sell. Fills at the same
    millisecond on one coin are merged into one step, because no sampling time can fall between
    them: the step starts at the fill whose startPosition is not another's end (the list order,
    reversed, when that is ambiguous) and ends after all of their sizes.

    Positions below DUST in size (float leftovers of a close) are set to flat, before and after.
    """
    by = defaultdict(lambda: defaultdict(list))
    n = len(fills)
    for k, (coin, t, _px, sz, side, _d, start, _tw) in enumerate(fills):
        if not is_perp(coin):
            continue
        before = float(start or 0)
        delta = float(sz) * (1 if side == "B" else -1)
        by[coin][t].append((n - k, before, before + delta, delta))   # n - k: list order reversed
    out = {}
    for coin, groups in by.items():
        ts, before, after = [], [], []
        for t in sorted(groups):
            g = sorted(groups[t])
            first = g[0]
            if len(g) > 1:
                ends = [x[2] for x in g]
                heads = [x for x in g if not any(abs(x[1] - e) <= 1e-9 * max(1.0, abs(e)) for e in ends)]
                if len(heads) == 1:
                    first = heads[0]
            b0 = first[1]
            ts.append(t)
            before.append(b0)
            after.append(b0 + sum(x[3] for x in g))
        after, before = np.array(after), np.array(before)
        after[np.abs(after) < DUST] = 0.0
        before[np.abs(before) < DUST] = 0.0
        out[coin] = (np.array(ts, dtype=np.int64), after, before)
    return out


def position_at(series, t, cover=None):
    """Position at time(s) t: after the last fill strictly before t; if none, the position recorded
    before the next fill; flat if the wallet never traded the coin (series None).

    With `cover` (the wallet's coverage start): at t >= cover, a last fill older than cover may be
    followed by fills the capped list no longer holds, so the next fill's recorded startPosition is
    used instead when there is one. None applies the rule literally."""
    t = np.asarray(t, dtype=np.int64)
    if series is None:
        return np.zeros(t.shape)
    times, after, before = series
    i = np.searchsorted(times, t, side="left") - 1
    pos = np.where(i >= 0, after[np.maximum(i, 0)], before[0])
    if cover is not None:
        stale = (i >= 0) & (times[np.maximum(i, 0)] < cover) & (t >= cover) & (i + 1 < len(times))
        pos = np.where(stale, before[np.minimum(i + 1, len(times) - 1)], pos)
    return pos


def chain_check(wallets):
    """Consecutive steps should chain (after one = before the next). Breaks show missing fills."""
    out = {"covered_pairs": 0, "covered_breaks": 0, "across_cutoff_pairs": 0, "across_cutoff_breaks": 0}
    for w in wallets.values():
        for times, after, before in w["pos"].values():
            ok = np.abs(after[:-1] - before[1:]) <= 1e-6 * np.maximum(1.0, np.abs(after[:-1]))
            cov = times[:-1] >= w["cover"]
            cross = (times[:-1] < w["cover"]) & (times[1:] >= w["cover"])
            out["covered_pairs"] += int(cov.sum())
            out["covered_breaks"] += int((cov & ~ok).sum())
            out["across_cutoff_pairs"] += int(cross.sum())
            out["across_cutoff_breaks"] += int((cross & ~ok).sum())
    return out


# ---------------------------------------------------------------- prices and stretch

def load(data_dir):
    wallets = {}
    fdir = os.path.join(data_dir, "fills")
    for fn in sorted(os.listdir(fdir)):
        with open(os.path.join(fdir, fn)) as fh:
            d = json.load(fh)
        wallets[fn[:-5]] = {"cohorts": set(d["cohorts"]), "cover": coverage_start(d["fills"]),
                            "pos": positions(d["fills"])}
    candles = {}
    cdir = os.path.join(data_dir, "candles")
    for fn in sorted(os.listdir(cdir)):
        coin = fn[:-5]
        if not is_perp(coin):
            continue
        with open(os.path.join(cdir, fn)) as fh:
            c = json.load(fh)
        if c:
            candles[coin] = c
    # The newest hourly candle was still open when pulled: drop it. Its open time is the data end
    # (the close of the hour before it).
    end = max(c[-1][0] for c in candles.values())
    candles = {k: [x for x in c if x[0] < end] for k, c in candles.items()}
    return wallets, {k: c for k, c in candles.items() if c}, end


def four_hour_closes(hourly, grid):
    """Close at each 4-hour close T: the hourly candle opening at T - 1h; if missing, the latest
    hourly close inside the 4 hours (candles opening T - 2h, T - 3h, T - 4h); else NaN."""
    m = {int(t): float(c) for t, c in hourly}
    out = np.full(len(grid), np.nan)
    for k, T in enumerate(grid):
        for back in (1, 2, 3, 4):
            v = m.get(int(T) - back * H)
            if v is not None:
                out[k] = v
                break
    return out


def stretch(closes):
    """The engine's z at every bar from that bar's history only: _calc_zscore_hybrid times the
    warm-up factor min(1, (n - 200) / 200) with n the bars up to that bar. NaN below 200 bars,
    where the engine returns no result."""
    closes = np.asarray(closes, dtype=float)
    z = _calc_zscore_hybrid(closes, len_ma=LEN_LONG, len_reg=LEN_REGRESSION, z_smooth=Z_SMOOTH, z_scale=Z_SCALE)
    n = np.arange(1, len(closes) + 1)
    z = z * np.clip((n - LEN_LONG) / LEN_LONG, 0.0, 1.0)
    z[n < LEN_LONG] = np.nan
    return z


def stretch_on_grid(close):
    """z per grid bar, computed on the coin's own 4-hour closes (bars it has) in time order."""
    z = np.full(len(close), np.nan)
    have = np.isfinite(close)
    if have.sum():
        z[have] = stretch(close[have])
    return z


# ---------------------------------------------------------------- comparisons and events

def compare(P, C, close, bt, bn):
    """Over the wallets covered at bar bt (rows of P, C), positions at bt and at bn.

    P: sizes (wallets x bars); C: covered (wallets x bars); bt, bn: arrays of bar indices.
    Returns counts long/short and position values (size x the 4-hour close) at both ends."""
    W = C[:, bt]
    Pt, Pn = P[:, bt], P[:, bn]
    r = {"Lt": ((Pt > 0) & W).sum(0), "St": ((Pt < 0) & W).sum(0),
         "Ln": ((Pn > 0) & W).sum(0), "Sn": ((Pn < 0) & W).sum(0)}
    r["VLt"] = np.where(W, np.maximum(Pt, 0), 0).sum(0) * close[bt]
    r["VSt"] = np.where(W, np.maximum(-Pt, 0), 0).sum(0) * close[bt]
    r["VLn"] = np.where(W, np.maximum(Pn, 0), 0).sum(0) * close[bn]
    r["VSn"] = np.where(W, np.maximum(-Pn, 0), 0).sum(0) * close[bn]
    return r


def share(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    tot = a + b
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(tot > 0, a / np.where(tot > 0, tot, 1), np.nan)


def turn_test(r, has_both):
    """TURN test per bar from a 24h comparison: coin eligible (>= 5 counted wallets hold it 24h
    before, closes at both ends) and the long share by wallets falls >= 20 points (not met if
    nobody holds at T) or wallets short rise by >= 2. Returns (eligible, test, by_share, by_shorts)."""
    elig = has_both & ((r["Lt"] + r["St"]) >= MIN_HOLDERS)
    drop = share(r["Lt"], r["St"]) - share(r["Ln"], r["Sn"])
    with np.errstate(invalid="ignore"):
        by_share = elig & (drop >= SHARE_DROP - EPS)          # NaN (nobody holds at T): not met
    by_shorts = elig & ((r["Sn"] - r["St"]) >= SHORTS_RISE)
    return elig, by_share | by_shorts, by_share, by_shorts


def run_starts(test, times, cool=COOL):
    """First bar of each run (holds now, not at the bar before), at least `cool` after the last event."""
    out, last = [], None
    for b in range(len(test)):
        if test[b] and not (b > 0 and test[b - 1]):
            if last is None or times[b] - times[last] >= cool:
                out.append(b)
                last = b
    return out


def recent_any(test, k):
    """True at b when test held at any of bars b-k .. b."""
    c = np.concatenate(([0], np.cumsum(test.astype(int))))
    idx = np.arange(len(test))
    return (c[idx + 1] - c[np.maximum(idx - k, 0)]) > 0


# ---------------------------------------------------------------- statistics

def boot_median_ci(v, days):
    rng = np.random.default_rng(SEED)
    uniq, inv = np.unique(days, return_inverse=True)
    groups = [v[inv == k] for k in range(len(uniq))]
    meds = np.empty(N_BOOT)
    for i in range(N_BOOT):
        pick = rng.integers(0, len(uniq), len(uniq))
        meds[i] = np.median(np.concatenate([groups[j] for j in pick]))
    return float(np.percentile(meds, 5)), float(np.percentile(meds, 95))


def summarize(vals, days, boot=True):
    """n, mean, median, share negative and the day-cluster 90% interval of the median (in %)."""
    v = np.asarray(vals, dtype=float)
    d = np.asarray(days)
    m = np.isfinite(v)
    v, d = v[m], d[m]
    if not len(v):
        return {"n": 0}
    out = {"n": int(len(v)), "days": int(len(np.unique(d))), "mean": 100 * float(v.mean()),
           "median": 100 * float(np.median(v)), "neg_pct": 100 * float((v < 0).mean())}
    if boot:
        lo, hi = boot_median_ci(v, d)
        out["ci90_median"] = [100 * lo, 100 * hi]
    return out


def rounded(x, nd=2):
    if isinstance(x, dict):
        return {k: rounded(v, nd) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [rounded(v, nd) for v in x]
    if isinstance(x, (float, np.floating)):
        return None if not np.isfinite(x) else round(float(x), nd)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


# ---------------------------------------------------------------- the study

class Study:
    def __init__(self, wallets, candles, end, literal=False, drop_stale=False):
        """literal: apply the position rule literally at the coverage start (sensitivity).
        drop_stale: a wallet whose last visible fill on a coin is older than its coverage start is
        treated as not holding that coin from the coverage start on, because fills in between may
        be missing and may have closed it (sensitivity; the declared rule carries the old position)."""
        self.wallets, self.end = wallets, end
        self.headline = end - HOLD
        first_open = min(c[0][0] for c in candles.values())
        start = -(-(first_open + H) // BAR) * BAR
        self.grid = np.arange(start, end + 1, BAR, dtype=np.int64)
        self.days = self.grid // DAY
        self.coins = sorted(candles)
        self.ci = {c: i for i, c in enumerate(self.coins)}
        NB = len(self.grid)
        self.close = np.vstack([four_hour_closes(candles[c], self.grid) for c in self.coins])
        self.z = np.vstack([stretch_on_grid(row) for row in self.close])
        # forward returns and the equal-weight basket of all coins with closes at both ends
        self.ret, self.bask, self.ex = {}, {}, {}
        for d in HORIZONS:
            k = 6 * d
            r = np.full(self.close.shape, np.nan)
            r[:, :NB - k] = self.close[:, k:] / self.close[:, :NB - k] - 1
            with np.errstate(invalid="ignore"):
                b = np.nanmean(np.where(np.isfinite(r), r, np.nan), axis=0) if r.size else r
            self.ret[d], self.bask[d], self.ex[d] = r, b, r - b[None, :]
        # per coin: wallet rows (both groups), sizes and coverage on the grid
        addrs = sorted(wallets)
        self.cover = np.array([wallets[a]["cover"] for a in addrs], dtype=np.int64)
        self.member = {g: np.array([g in wallets[a]["cohorts"] for a in addrs]) for g in GROUPS}
        holders = defaultdict(list)
        for i, a in enumerate(addrs):
            for coin in wallets[a]["pos"]:
                if coin in self.ci:
                    holders[coin].append(i)
        self.rows, self.P = {}, {}
        for c in self.coins:
            rows = np.array(holders.get(c, []), dtype=int)
            self.rows[c] = rows
            self.P[c] = (np.vstack([position_at(wallets[addrs[i]]["pos"][c], self.grid,
                                              None if literal else wallets[addrs[i]]["cover"]) for i in rows])
                         if len(rows) else np.zeros((0, NB)))
            if drop_stale:
                for k, i in enumerate(rows):
                    cov = wallets[addrs[i]]["cover"]
                    if cov > 0 and wallets[addrs[i]]["pos"][c][0][-1] < cov:
                        self.P[c][k, self.grid >= cov] = 0.0
        self.addrs = addrs

    def group_rows(self, c, g, ids=False):
        rows = self.rows[c]
        keep = self.member[g][rows] if len(rows) else np.zeros(0, bool)
        P = self.P[c][keep]
        C = self.cover[rows[keep]][:, None] <= self.grid[None, :]
        return (P, C, rows[keep]) if ids else (P, C)

    def tag(self, i):
        """Short wallet label for concentration notes (public address, first 10 characters)."""
        return self.addrs[i][:10]

    def comparisons(self, g):
        """24h comparisons at every coin-bar for group g, aligned to the later bar."""
        NB, nc = len(self.grid), len(self.coins)
        keys = ("Lt", "St", "Ln", "Sn", "VLt", "VSt", "VLn", "VSn")
        A = {k: np.full((nc, NB), np.nan) for k in keys}
        elig = np.zeros((nc, NB), bool)
        test = np.zeros((nc, NB), bool)
        by_share = np.zeros((nc, NB), bool)
        by_shorts = np.zeros((nc, NB), bool)
        bt = np.arange(0, NB - LAG)
        bn = bt + LAG
        for ci, c in enumerate(self.coins):
            P, C = self.group_rows(c, g)
            r = compare(P, C, self.close[ci], bt, bn)
            for k in keys:
                A[k][ci, bn] = r[k]
            has_both = np.isfinite(self.close[ci, bt]) & np.isfinite(self.close[ci, bn])
            e, t, s1, s2 = turn_test(r, has_both)
            elig[ci, bn], test[ci, bn], by_share[ci, bn], by_shorts[ci, bn] = e, t, s1, s2
        A.update(elig=elig, test=test, by_share=by_share, by_shorts=by_shorts)
        return A

    # -- per-event details

    def movers(self, c, g, b):
        """Side changes over the 24h before b. Also returns (bearish movers, new shorts) as wallet
        indexes, for the concentration notes."""
        P, C, ids = self.group_rows(c, g, ids=True)
        W = C[:, b - LAG]
        st, sn = np.sign(P[W, b - LAG]), np.sign(P[W, b])
        bear = ((st == 1) & (sn <= 0)) | ((st == 0) & (sn == -1))
        return ({"changed": int((st != sn).sum()),
                 "bearish": int(bear.sum()),
                 "long_to_short": int(((st == 1) & (sn == -1)).sum()),
                 "long_to_flat": int(((st == 1) & (sn == 0)).sum()),
                 "flat_to_short": int(((st == 0) & (sn == -1)).sum()),
                 "bullish": int((((st == -1) & (sn >= 0)) | ((st == 0) & (sn == 1))).sum())},
                (ids[W][bear].tolist(), ids[W][(sn == -1) & (st != -1)].tolist()))

    def around(self, c, g, b):
        """Wallets covered from 24h before b: long/short counts and shares at b-24h, b, b+24h, b+72h."""
        ci = self.ci[c]
        P, C = self.group_rows(c, g)
        W = C[:, b - LAG]
        out = {}
        for tag, k in (("pre", -LAG), ("at", 0), ("p24", LAG), ("p72", 3 * LAG)):
            bk = b + k
            if bk >= len(self.grid) or not np.isfinite(self.close[ci, bk]):
                out[tag] = None
                continue
            p = P[W, bk]
            L, S = int((p > 0).sum()), int((p < 0).sum())
            vl, vs = float(np.maximum(p, 0).sum()), float(np.maximum(-p, 0).sum())
            out[tag] = {"long": L, "short": S, "share_w": float(share(L, S)), "share_n": float(share(vl, vs))}
        return out

    # -- event sets

    def turn_events(self, A):
        ev = []
        for ci, c in enumerate(self.coins):
            for b in run_starts(A["test"][ci], self.grid):
                ev.append((ci, b))
        return ev

    def controls(self, A):
        qual = A["elig"] & (np.nan_to_num(self.z, nan=-np.inf) >= Z_STRETCH)
        for ci in range(len(self.coins)):
            qual[ci] &= ~recent_any(A["test"][ci], LAG)
        return qual

    def match(self, qual, ci, b):
        """Control coins for an event: same bar; else same UTC day at each coin's first qualifying bar."""
        others = np.arange(len(self.coins)) != ci
        same = np.where(qual[:, b] & others)[0]
        if len(same):
            return "bar", [(c2, b) for c2 in same]
        day = np.where(self.days == self.days[b])[0]
        out = []
        for c2 in np.where(others)[0]:
            hit = day[qual[c2, day]]
            if len(hit):
                out.append((c2, int(hit[0])))
        return ("day", out) if out else ("none", [])

    def run_group(self, g):
        A = self.comparisons(g)
        ev = self.turn_events(A)
        qual = self.controls(A)
        records = []
        for ci, b in ev:
            c = self.coins[ci]
            z = self.z[ci, b]
            mv, (bear_ids, new_short_ids) = self.movers(c, g, b)
            rec = {"coin": c, "t": int(self.grid[b]), "time": iso(self.grid[b]), "b": b, "ci": ci,
                   "z": float(z) if np.isfinite(z) else None,
                   "primary": bool(np.isfinite(z) and z >= Z_STRETCH),
                   "headline": bool(self.grid[b] <= self.headline),
                   "holders_24h_before": int(A["Lt"][ci, b] + A["St"][ci, b]),
                   "long_short_24h_before": [int(A["Lt"][ci, b]), int(A["St"][ci, b])],
                   "long_short_at": [int(A["Ln"][ci, b]), int(A["Sn"][ci, b])],
                   "trigger": ("both" if A["by_share"][ci, b] and A["by_shorts"][ci, b]
                               else "share" if A["by_share"][ci, b] else "shorts"),
                   "movers": mv, "_bearish": [self.tag(i) for i in bear_ids],
                   "_new_short": [self.tag(i) for i in new_short_ids]}
            for d in HORIZONS:
                rec[f"ret_{d}d"] = float(self.ret[d][ci, b])
                rec[f"ex_{d}d"] = float(self.ex[d][ci, b])
            if rec["primary"]:
                how, m = self.match(qual, ci, b)
                rec["control_match"] = how
                rec["control_n"] = len(m)
                for d in HORIZONS:
                    v = np.array([self.ex[d][c2, b2] for c2, b2 in m])
                    v = v[np.isfinite(v)]
                    rec[f"control_ex_{d}d"] = float(np.median(v)) if len(v) else float("nan")
            records.append(rec)
        return A, records

    def market(self, A):
        """Market-wide long share by notional per bar, over coins eligible 24h before, same wallets and
        coins at both ends. Returns (share_then, share_now, defined)."""
        e = A["elig"]
        s = {k: np.where(e, np.nan_to_num(A[k]), 0).sum(0) for k in ("VLt", "VSt", "VLn", "VSn")}
        then, now = share(s["VLt"], s["VSt"]), share(s["VLn"], s["VSn"])
        defined = e.any(0) & np.isfinite(then) & np.isfinite(now)
        return then, now, defined

    def market_turns(self, A):
        then, now, defined = self.market(A)
        test = defined & np.nan_to_num(then - now >= MKT_DROP - EPS, nan=False)
        return run_starts(test, self.grid), then, now, defined

    def market_detail(self, g, A, b):
        """For a market turn at b: the same share counted by open positions (wallet-coin pairs) rather
        than value, and the drop left when the one wallet whose removal shrinks it most is left out
        (description only)."""
        per = defaultdict(lambda: np.zeros(4))          # wallet -> value long/short then, long/short now
        for ci in np.where(A["elig"][:, b])[0]:
            P, C, ids = self.group_rows(self.coins[ci], g, ids=True)
            W = C[:, b - LAG]
            pt, pn = P[W, b - LAG], P[W, b]
            ct, cn = self.close[ci, b - LAG], self.close[ci, b]
            for i, a, s_, c_, d_ in zip(ids[W], np.maximum(pt, 0) * ct, np.maximum(-pt, 0) * ct,
                                        np.maximum(pn, 0) * cn, np.maximum(-pn, 0) * cn):
                per[i] += (a, s_, c_, d_)
        V = np.array(list(per.values())) if per else np.zeros((0, 4))
        tot = V.sum(0)
        drop = float(share(tot[0], tot[1]) - share(tot[2], tot[3]))
        loo = [float(share(tot[0] - v[0], tot[1] - v[1]) - share(tot[2] - v[2], tot[3] - v[3])) for v in V]
        k = int(np.nanargmin(loo)) if loo else None
        e = A["elig"][:, b]
        sw = [float(share(A["Lt"][e, b].sum(), A["St"][e, b].sum())),
              float(share(A["Ln"][e, b].sum(), A["Sn"][e, b].sum()))]
        return {"wallets_with_positions": int(((V[:, :2].sum(1) > 0) | (V[:, 2:].sum(1) > 0)).sum()),
                "notional_then_usd": float(tot[:2].sum()), "notional_now_usd": float(tot[2:].sum()),
                "drop_pts": 100 * drop,
                "drop_without_top_wallet_pts": 100 * loo[k] if k is not None else None,
                "top_wallet": self.tag(list(per)[k]) if k is not None else None,
                "share_by_position_count_then_pct": 100 * sw[0], "share_by_position_count_now_pct": 100 * sw[1]}

    def holder_concentration(self, g, A, mask):
        """Who fills the coin-bars in `mask` (wallets counted at T, covered 24h before): distinct
        holders, the coins, and the top wallets' share of holder slots and of long value."""
        slots, long_slots, long_val = defaultdict(int), defaultdict(int), defaultdict(float)
        by_coin = {}
        for ci in np.where(mask.any(1))[0]:
            bs = np.where(mask[ci])[0]
            P, C, ids = self.group_rows(self.coins[ci], g, ids=True)
            W = C[:, bs - LAG]
            p = P[:, bs]
            hold = (W & (p != 0)).sum(1)
            lng = (W & (p > 0)).sum(1)
            val = (np.where(W, np.maximum(p, 0), 0) * self.close[ci, bs][None, :]).sum(1)
            for i, h, l_, v in zip(ids, hold, lng, val):
                if h:
                    slots[i] += int(h)
                    long_slots[i] += int(l_)
                    long_val[i] += float(v)
            by_coin[self.coins[ci]] = int(len(bs))
        tot, lv = sum(slots.values()), sum(long_val.values())
        top = sorted(slots.values(), reverse=True)
        topv = sorted(long_val.values(), reverse=True)
        return {"coin_bars": int(mask.sum()), "coins": len(by_coin),
                "top_coins_by_coin_bars": dict(sorted(by_coin.items(), key=lambda kv: -kv[1])[:5]),
                "distinct_holders": len(slots), "distinct_long_holders": sum(v > 0 for v in long_slots.values()),
                "top1_share_of_holder_slots_pct": 100 * top[0] / tot if tot else None,
                "top10_share_of_holder_slots_pct": 100 * sum(top[:10]) / tot if tot else None,
                "top3_share_of_long_value_pct": 100 * sum(topv[:3]) / lv if lv else None}

    # -- descriptive tables

    def d1_by_month(self, A, cutoff):
        """D1 split by calendar month (exploratory: levels mix months with different coverage)."""
        month = np.array([iso(t)[:7] for t in self.grid])
        out = {}
        for m in sorted(set(month[self.grid <= cutoff])):
            t = self.d1(A, cutoff, extra=(month == m)[None, :])
            out[m] = {band: {k: v[k] for k in ("coin_bars", "wallets_long", "long_share_wallets_pct",
                                                "chg_24h_wallets_long") if k in v} for band, v in t.items()}
        return out

    def d1(self, A, cutoff, extra=True):
        z = self.z
        base = A["elig"] & np.isfinite(z) & (self.grid[None, :] <= cutoff) & extra
        swn, swt = share(A["Ln"], A["Sn"]), share(A["Lt"], A["St"])
        snn, snt = share(A["VLn"], A["VSn"]), share(A["VLt"], A["VSt"])
        out = {}
        for name, lo, hi in BANDS:
            m = base & (np.nan_to_num(z, nan=-np.inf) >= lo) & (np.nan_to_num(z, nan=np.inf) < hi)
            if not m.any():
                out[name] = {"coin_bars": 0}
                continue
            out[name] = {"coin_bars": int(m.sum()),
                         "wallets_long": float(A["Ln"][m].mean()), "wallets_short": float(A["Sn"][m].mean()),
                         "long_share_wallets_pct": 100 * float(np.nanmean(swn[m])),
                         "long_share_notional_pct": 100 * float(np.nanmean(snn[m])),
                         "chg_24h_wallets_long": float((A["Ln"] - A["Lt"])[m].mean()),
                         "chg_24h_wallets_short": float((A["Sn"] - A["St"])[m].mean()),
                         "chg_24h_long_share_wallets_pts": 100 * float(np.nanmean((swn - swt)[m])),
                         "chg_24h_long_share_notional_pts": 100 * float(np.nanmean((snn - snt)[m]))}
        return out

    def d2_events(self, A):
        out = []
        z = np.nan_to_num(self.z, nan=-np.inf)
        zprev = np.full(self.z.shape, np.nan)
        zprev[:, 1:] = self.z[:, :-1]
        cross = A["elig"] & (z >= Z_STRETCH) & np.nan_to_num(zprev < Z_STRETCH, nan=False)
        for ci in range(len(self.coins)):
            last = None
            for b in np.where(cross[ci])[0]:
                if last is None or self.grid[b] - self.grid[last] >= COOL:
                    out.append((ci, int(b)))
                    last = b
        return out

    def d3_events(self, A):
        out, NB = [], len(self.grid)
        z = np.nan_to_num(self.z, nan=-np.inf)
        for ci in range(len(self.coins)):
            cl, last = self.close[ci], None
            for b in np.where(A["elig"][ci] & (z[ci] >= Z_STRETCH))[0]:
                if b - TOP_WIN < 0 or b + TOP_WIN >= NB:
                    continue
                win = cl[b - TOP_WIN:b + TOP_WIN + 1]
                if not np.isfinite(win).all() or cl[b] < win.max():
                    continue
                if last is None or self.grid[b] - self.grid[last] >= COOL:
                    out.append((ci, int(b)))
                    last = b
        return out

    def around_table(self, g, events, cutoff):
        rows = [self.around(self.coins[ci], g, b) for ci, b in events if self.grid[b] <= cutoff]
        out = {"events": len(rows)}
        for span, a, bb in (("24h_before_to_bar", "pre", "at"), ("bar_to_24h_after", "at", "p24"),
                            ("bar_to_72h_after", "at", "p72")):
            d = {}
            for key, label in (("long", "wallets_long"), ("short", "wallets_short"),
                               ("share_w", "long_share_wallets_pts"), ("share_n", "long_share_notional_pts")):
                v = np.array([r[bb][key] - r[a][key] for r in rows if r[a] and r[bb]], dtype=float)
                v = v[np.isfinite(v)]
                k = 100 if key.startswith("share") else 1
                d[label] = {"n": int(len(v)), "mean": k * float(v.mean()) if len(v) else None,
                            "median": k * float(np.median(v)) if len(v) else None,
                            "fall": int((v < 0).sum()), "level": int((v == 0).sum()), "rise": int((v > 0).sum())}
            out[span] = d
        lv = [r["pre"] for r in rows if r["pre"]]
        out["levels_24h_before"] = {"wallets_long": float(np.mean([x["long"] for x in lv])) if lv else None,
                                    "wallets_short": float(np.mean([x["short"] for x in lv])) if lv else None}
        return out


def mover_concentration(records):
    """How much of an event set one wallet drives: the wallet that moved toward short in the most
    events, the wallet that was a new short in the most events, and the top 5 wallets' share of all
    toward-short moves."""
    out = {}
    for key, label in (("_bearish", "toward_short"), ("_new_short", "new_short")):
        cnt, slots = defaultdict(int), 0
        for r in records:
            for a in set(r.get(key, [])):
                cnt[a] += 1
            slots += len(r.get(key, []))
        top = sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))       # ties: by address
        out[label] = {"distinct_wallets": len(cnt),
                      "top_wallet": top[0][0] if top else None,
                      "top_wallet_events": top[0][1] if top else 0,
                      "top_wallet_events_pct": 100 * top[0][1] / len(records) if top else None,
                      "top5_share_of_moves_pct": 100 * sum(v for _, v in top[:5]) / slots if slots else None}
    return out


def event_stats(records, horizons=HORIZONS):
    days = [r["t"] // DAY for r in records]
    out = {"events": len(records),
           "single_wallet_events": sum(r["movers"]["bearish"] == 1 for r in records),
           "only_one_wallet_changed_side": sum(r["movers"]["changed"] == 1 for r in records),
           "with_a_long_to_short_flip": sum(r["movers"]["long_to_short"] >= 1 for r in records),
           "trigger": {k: sum(r["trigger"] == k for r in records) for k in ("share", "shorts", "both")},
           "holders_24h_before_median": (float(np.median([r["holders_24h_before"] for r in records]))
                                         if records else None),
           # the shorts test held while wallets long did not fall: shorts added, not longs turning
           "shorts_test_with_wallets_long_not_falling": sum(
               r["trigger"] != "share" and r["long_short_at"][0] >= r["long_short_24h_before"][0] for r in records),
           "concentration": mover_concentration(records)}
    for d in horizons:
        out[f"{d}d"] = {"raw": summarize([r[f"ret_{d}d"] for r in records], days),
                        "excess": summarize([r[f"ex_{d}d"] for r in records], days)}
    return out


def control_stats(records):
    out = {"matched_same_bar": sum(r.get("control_match") == "bar" for r in records),
           "matched_same_day": sum(r.get("control_match") == "day" for r in records),
           "unmatched": sum(r.get("control_match") == "none" for r in records)}
    for d in HORIZONS:
        pairs = [(r[f"ex_{d}d"], r[f"control_ex_{d}d"]) for r in records
                 if np.isfinite(r[f"ex_{d}d"]) and np.isfinite(r.get(f"control_ex_{d}d", np.nan))]
        if pairs:
            e, c = np.array(pairs).T
            out[f"{d}d"] = {"n": len(pairs), "event_median_excess": 100 * float(np.median(e)),
                            "control_median_excess": 100 * float(np.median(c)),
                            "gap_pts": 100 * float(np.median(e) - np.median(c))}
        else:
            out[f"{d}d"] = {"n": 0}
    return out


def primary_verdict(st, ctrl):
    s3, s7 = st["3d"]["excess"], st["7d"]["excess"]
    c7 = ctrl["7d"]
    tests = {
        "1_at_least_30_events": st["events"] >= 30,
        "2_median_excess_le_-1.5_at_3d_and_7d": bool(s3.get("n") and s7.get("n") and s3["median"] <= -1.5 and s7["median"] <= -1.5),
        "3_neg_share_ge_60_at_3d_and_7d": bool(s3.get("n") and s7.get("n") and s3["neg_pct"] >= 60 and s7["neg_pct"] >= 60),
        "4_ci90_7d_median_below_0": bool(s7.get("n") and s7["ci90_median"][1] < 0),
        "5_control_gap_7d_ge_1.5_with_30_matched": bool(c7.get("n", 0) >= 30 and c7["gap_pts"] <= -1.5),
    }
    return {"tests": tests, "informative": all(tests.values())}


def market_verdict(st, base):
    s3, s7 = st["btc"]["3d"], st["btc"]["7d"]
    b7 = base["btc"]["7d"]
    tests = {
        "1_at_least_30_turns": st["turns"] >= 30,
        "2_btc_median_le_-1.5_at_3d_and_7d": bool(s3.get("n") and s7.get("n") and s3["median"] <= -1.5 and s7["median"] <= -1.5),
        "3_neg_share_ge_60_at_3d_and_7d": bool(s3.get("n") and s7.get("n") and s3["neg_pct"] >= 60 and s7["neg_pct"] >= 60),
        "4_ci90_7d_median_below_0": bool(s7.get("n") and s7["ci90_median"][1] < 0),
        "5_7d_median_ge_1.5_below_all_bars": bool(s7.get("n") and b7.get("n") and s7["median"] <= b7["median"] - 1.5),
    }
    return {"tests": tests, "informative": all(tests.values())}


def analyse(s):
    """Every declared table for both groups, on the headline set and on all events."""
    end, btc = s.end, s.ci.get("BTC")
    out, events_out = {}, {}
    for g in GROUPS:
        A, recs = s.run_group(g)
        turns, mthen, mnow, mdef = s.market_turns(A)
        d2, d3 = s.d2_events(A), s.d3_events(A)
        mdetail = {b: s.market_detail(g, A, b) for b in turns}
        res = {}
        for period, cutoff in (("headline", s.headline), ("all_biased", end)):
            sel = [r for r in recs if r["t"] <= cutoff]
            prim = [r for r in sel if r["primary"]]
            pst = event_stats(prim)
            ctrl = control_stats(prim)
            mt = [b for b in turns if s.grid[b] <= cutoff]
            mdays = [int(s.days[b]) for b in mt]
            mst = {"turns": len(mt),
                   "while_btc_z_ge_2": int(sum(np.nan_to_num(s.z[btc, b], nan=-9) >= Z_STRETCH for b in mt)),
                   "drop_pts_median": 100 * float(np.median([mthen[b] - mnow[b] for b in mt])) if mt else None,
                   "btc": {f"{d}d": summarize([s.ret[d][btc, b] for b in mt], mdays) for d in HORIZONS},
                   "basket": {f"{d}d": summarize([s.bask[d][b] for b in mt], mdays) for d in HORIZONS}}
            allb = np.where(mdef & (s.grid <= cutoff))[0]
            base = {"bars": int(len(allb)),
                    "btc": {f"{d}d": summarize(s.ret[d][btc, allb], s.days[allb], boot=False) for d in HORIZONS},
                    "basket": {f"{d}d": summarize(s.bask[d][allb], s.days[allb], boot=False) for d in HORIZONS}}
            in_period = s.grid[None, :] <= cutoff
            res[period] = {
                "turn_tests_fired_coin_bars": int((A["test"] & in_period).sum()),
                "eligible_coin_bars": int((A["elig"] & in_period).sum()),
                "eligible_coin_bars_with_z_ge_2": int((A["elig"] & (np.nan_to_num(s.z, nan=-9) >= Z_STRETCH)
                                                      & in_period).sum()),
                "primary_turn_at_top": {**pst, "control": ctrl, "verdict": primary_verdict(pst, ctrl)},
                "secondary_turn_any_z": {**event_stats(sel),
                                         "with_z_available": sum(r["z"] is not None for r in sel)},
                "market_turn": {**mst, "all_bars_baseline": base, "verdict": market_verdict(mst, base)},
                "D1_by_stretch": s.d1(A, cutoff),
                "D2_as_stretch_starts": s.around_table(g, d2, cutoff),
                "D3_tops_in_hindsight": s.around_table(g, d3, cutoff),
                "who_holds": {"eligible_coin_bars": s.holder_concentration(g, A, A["elig"] & in_period),
                              "eligible_coin_bars_z_ge_2": s.holder_concentration(
                                  g, A, A["elig"] & (np.nan_to_num(s.z, nan=-9) >= Z_STRETCH) & in_period)},
            }
            res[period]["market_turn"]["turns_below_10_pts_without_top_wallet"] = sum(
                mdetail[b]["drop_without_top_wallet_pts"] is not None
                and mdetail[b]["drop_without_top_wallet_pts"] < 100 * MKT_DROP for b in mt)
        # Exploratory: events whose outcome windows end by the headline cut-off, so no outcome
        # falls inside the month the wallets were picked on (7 days for returns, 72h for D2/D3).
        c7, c3 = s.headline - 7 * DAY, s.headline - 3 * DAY
        prim7 = [r for r in recs if r["primary"] and r["t"] <= c7]
        res["exploratory_outcomes_end_by_cutoff"] = {
            "event_cutoff_returns": iso(c7), "event_cutoff_D2_D3": iso(c3),
            "headline_primary_with_7d_window_past_cutoff": sum(c7 < r["t"] <= s.headline for r in recs if r["primary"]),
            "headline_secondary_with_7d_window_past_cutoff": sum(c7 < r["t"] <= s.headline for r in recs),
            "primary_turn_at_top": {**event_stats(prim7), "control": control_stats(prim7)},
            "secondary_turn_any_z": event_stats([r for r in recs if r["t"] <= c7]),
            "D2_as_stretch_starts": s.around_table(g, d2, c3),
            "D3_tops_in_hindsight": s.around_table(g, d3, c3)}
        res["exploratory_D1_by_month_headline"] = s.d1_by_month(A, s.headline)
        res["market_share_now_pct"] = 100 * float(mnow[-1]) if mdef[-1] else None
        out[g] = res
        keep = ("coin", "time", "z", "headline", "holders_24h_before", "long_short_24h_before", "long_short_at",
                "trigger", "movers", "control_match", "control_n") + tuple(
            f"{p}_{d}d" for d in HORIZONS for p in ("ret", "ex", "control_ex"))
        pct = lambda k, v: 100 * v if k.startswith(("ret_", "ex_", "control_ex_")) else v    # returns in %
        events_out[g] = {"primary": [{**{k: pct(k, r[k]) for k in keep if k in r},
                                      "toward_short_wallets": r["_bearish"], "new_short_wallets": r["_new_short"]}
                                     for r in recs if r["primary"]],
                         "secondary": [{k: r[k] for k in ("coin", "time", "z", "trigger", "holders_24h_before")}
                                       for r in recs],
                         "market_turns": [{"time": iso(s.grid[b]), "share_then_pct": 100 * float(mthen[b]),
                                           "share_now_pct": 100 * float(mnow[b]),
                                           "btc_z": float(s.z[btc, b]) if np.isfinite(s.z[btc, b]) else None,
                                           **{f"btc_{d}d_pct": 100 * float(s.ret[d][btc, b]) for d in HORIZONS},
                                           **mdetail[b]}
                                          for b in turns]}
    out["events"] = events_out
    return out


def compact(res):
    """Key numbers only, for the sensitivity run."""
    out = {}
    for g in GROUPS:
        for period in ("headline", "all_biased"):
            x = res[g][period]
            pr, se, mk = x["primary_turn_at_top"], x["secondary_turn_any_z"], x["market_turn"]
            out[f"{g}/{period}"] = {
                "primary_events": pr["events"], "primary_7d_excess": pr["7d"]["excess"],
                "primary_informative": pr["verdict"]["informative"],
                "secondary_events": se["events"], "secondary_7d_excess": se["7d"]["excess"],
                "market_turns": mk["turns"], "market_informative": mk["verdict"]["informative"],
                "eligible_coin_bars": x["eligible_coin_bars"],
                "D1_2_or_more": x["D1_by_stretch"]["2 or more"],
                "D2_events": x["D2_as_stretch_starts"]["events"], "D3_events": x["D3_tops_in_hindsight"]["events"],
                "D2_bar_to_24h_wallets_long": x["D2_as_stretch_starts"]["bar_to_24h_after"]["wallets_long"],
                "D3_bar_to_72h_wallets_long": x["D3_tops_in_hindsight"]["bar_to_72h_after"]["wallets_long"]}
    return out


def run(data_dir):
    np.seterr(invalid="ignore", divide="ignore")
    warnings.filterwarnings("ignore", message="Mean of empty slice")
    t0 = time.time()
    wallets, candles, end = load(data_dir)
    s = Study(wallets, candles, end)
    t_load = time.time() - t0
    lit = Study(wallets, candles, end, literal=True)
    differ = sum(int(((s.P[c] != lit.P[c]) & (s.cover[s.rows[c]][:, None] <= s.grid[None, :])).sum())
                 for c in s.coins if len(s.rows[c]))
    perp = np.array([any(c in s.ci for c in wallets[a]["pos"]) for a in s.addrs])
    stale = sum(1 for w in wallets.values() for c, t in w["pos"].items()
                if c in s.ci and w["cover"] > 0 and t[0][-1] < w["cover"] and t[1][-1] != 0)
    out = {"meta": {
        "data_end": iso(end), "headline_cutoff": iso(s.headline),
        "bars_4h": len(s.grid), "first_bar": iso(s.grid[0]),
        "coins": len(s.coins), "coins_trading_at_end": int(np.isfinite(s.close[:, -1]).sum()),
        "coins_with_z_ge_2_ever": int((np.nan_to_num(s.z, nan=-9) >= Z_STRETCH).any(1).sum()),
        "wallets": {g: int(s.member[g].sum()) for g in GROUPS},
        "covered_from_180d": {g: int((s.member[g] & (s.cover <= end - 180 * DAY)).sum()) for g in GROUPS},
        "covered_from_30d": {g: int((s.member[g] & (s.cover <= end - 30 * DAY)).sum()) for g in GROUPS},
        # wallets with no perpetual fills on a candle coin can never hold one: the effective group
        "covered_with_perp_fills_from_180d": {g: int((s.member[g] & perp & (s.cover <= end - 180 * DAY)).sum())
                                              for g in GROUPS},
        "covered_with_perp_fills_from_30d": {g: int((s.member[g] & perp & (s.cover <= end - 30 * DAY)).sum())
                                             for g in GROUPS},
        "wallets_without_perp_fills": {g: int((s.member[g] & ~perp).sum()) for g in GROUPS},
        "newest_perp_fill": iso(max(int(t[0][-1]) for w in wallets.values() for t in w["pos"].values())),
        "open_positions_last_filled_before_coverage": stale,   # carried forward; may have closed unseen
        "fill_chain": chain_check(wallets),
        "covered_wallet_coin_bars_where_literal_rule_differs": differ,
        "notes": [
            "Returns and shares are in % (share changes in points); event rows list returns in %.",
            "z is not available below 200 4-hour bars (the engine returns no result there).",
            "Fills at the same millisecond on one coin are merged into one step (no sampling time falls between them).",
            "Position lookups at or after a wallet's coverage start ignore an older last fill when a later fill "
            "exists and use that fill's recorded startPosition; sensitivity_literal_position_rule applies the rule literally.",
            "single_wallet_events: exactly one counted wallet moved toward short (long to flat/short, or flat to short).",
            f"Positions smaller than {DUST:g} in size are float leftovers of a close and count as flat.",
            "Fills were pulled on 26 Sep between about 16:27 and 18:52 UTC, so positions at the last bar "
            "(20:00) are as of each wallet's pull, up to about 3.5 hours stale; the 16:00 bar is complete.",
            "sensitivity_drop_stale_positions: a wallet whose last visible fill on a coin is older than its "
            "coverage start counts as not holding that coin from the coverage start on.",
            "who_holds, concentration, market-turn detail and everything prefixed exploratory_ are description only.",
            "A coin-bar exists where the coin has 4-hour closes at both ends of the 24-hour comparison.",
        ],
    }}
    out.update(analyse(s))
    out["sensitivity_literal_position_rule"] = compact(analyse(lit))
    out["sensitivity_drop_stale_positions"] = compact(analyse(Study(wallets, candles, end, drop_stale=True)))
    out["meta"]["runtime_s"] = {"load_and_build": t_load, "total": time.time() - t0}
    return rounded(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data")
    ap.add_argument("--out", help="write the JSON result here as well as to stdout")
    args = ap.parse_args()
    res = run(args.data)
    txt = json.dumps(res, indent=1)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w") as fh:
            fh.write(txt)
    else:
        print(txt)


if __name__ == "__main__":
    main()
