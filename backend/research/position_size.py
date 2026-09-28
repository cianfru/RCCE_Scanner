"""
Do profitable traders' positions get bigger into tops and greed? (docs/reviews/position-size-at-tops-study.md)

    python research/position_size.py <data dir> <fear-greed json> [--out result.json]    (run from backend/)

<data dir> is the turn study's (fills/ and candles/, see research/traders_turn.py); positions are
rebuilt with that study's functions. <fear-greed json> holds alternative.me's daily index as
[[utc_day, value], ...], either as the whole file or under "fear_greed" (market_history's view()).

Every size figure is summed over a FIXED panel of wallets (covered from PANEL_START), so wallets
entering coverage cannot look like growth. A measure at a 4-hour close T uses fills strictly before
T; hindsight tops, "after" windows and forward returns read later data, and are labelled so.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import warnings
from datetime import datetime, timezone

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from research.traders_turn import BAR, DAY, GROUPS, H, Study, iso, load, rounded  # noqa: E402


def utc_ms(y, m, d):
    return int(datetime(y, m, d, tzinfo=timezone.utc).timestamp() * 1000)


PANEL_START = utc_ms(2026, 3, 25)       # panel: wallets covered from here
ANALYSIS_START = utc_ms(2026, 4, 1)     # events and daily series from here
HOLD = 30 * DAY                         # headline: correlations/outcome windows end by data end - 30d
W72, W7D = 18, 42                       # 72 hours and 7 days in 4-hour bars
FWD = {"7d": 42, "14d": 84}
MATCH, MATCH_EXCL = 90, 18              # matched baseline: bars within 15 days, not within 72 hours
COOL = 72 * H
MIN_HOLDERS = 5                         # panel wallets holding the coin 72h before an event
MIN_MEDIAN_WALLETS = 5                  # median per-wallet long notional needs this many long wallets
Z_TOP = 2.0
GREED = 70
POOL_MIN_FRAC = 0.25                    # alt pool: >= 5 panel holders on >= 25% of analysis bars
MM_MAX_POSITIONS = 25
BLOCK = 14                              # days, circular moving-block bootstrap for correlations
N_BOOT = 2000
SEED = 20260928
MIN_EVENTS, MIN_DAYS, MIN_RHO = 30, 120, 0.2

MEASURES = ("long_coins", "long_usd", "share", "median_wallet_usd")
WINDOWS = {"before_72h": (-W72, 0), "before_7d": (-W7D, 0), "after_72h": (0, W72), "after_7d": (0, W7D)}
EVENT_KINDS = ("top_z2", "top_any_z", "stretch_start", "greed_start")


# ---------------------------------------------------------------- statistics

def ranks(x):
    """Ranks 1..n with ties averaged."""
    x = np.asarray(x, float)
    order = np.argsort(x, kind="mergesort")
    r = np.empty(len(x))
    r[order] = np.arange(1, len(x) + 1)
    _, inv, cnt = np.unique(x, return_inverse=True, return_counts=True)
    if (cnt > 1).any():
        sums = np.bincount(inv, weights=r)
        r = sums[inv] / cnt[inv]
    return r


def spearman(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 3:
        return float("nan")
    rx, ry = ranks(x), ranks(y)
    if rx.std() == 0 or ry.std() == 0:
        return float("nan")
    return float(np.corrcoef(rx, ry)[0, 1])


def block_boot_rho(x, y, day, block=BLOCK, n_boot=N_BOOT, seed=SEED):
    """Spearman rho and a 90% interval from a circular moving-block bootstrap over whole days: blocks of
    `block` consecutive observed days are drawn with replacement, every observation of a drawn day kept."""
    x, y, day = np.asarray(x, float), np.asarray(y, float), np.asarray(day)
    m = np.isfinite(x) & np.isfinite(y)
    x, y, day = x[m], y[m], day[m]
    udays, inv = np.unique(day, return_inverse=True)
    nd = len(udays)
    out = {"n": int(len(x)), "days": int(nd), "rho": spearman(x, y)}
    if nd < 3:
        return out
    by_day = [np.where(inv == k)[0] for k in range(nd)]
    rng = np.random.default_rng(seed)
    nb = -(-nd // block)
    rhos = np.empty(n_boot)
    for i in range(n_boot):
        starts = rng.integers(0, nd, nb)
        pos = ((starts[:, None] + np.arange(block)[None, :]) % nd).ravel()[:nd]
        idx = np.concatenate([by_day[p] for p in pos])
        rhos[i] = spearman(x[idx], y[idx])
    rhos = rhos[np.isfinite(rhos)]
    out["ci90"] = [float(np.percentile(rhos, 5)), float(np.percentile(rhos, 95))] if len(rhos) else None
    return out


def day_boot_median(v, days, n_boot=N_BOOT, seed=SEED):
    """90% interval of the median, whole UTC days of events drawn with replacement."""
    rng = np.random.default_rng(seed)
    uniq, inv = np.unique(days, return_inverse=True)
    groups = [v[inv == k] for k in range(len(uniq))]
    meds = np.empty(n_boot)
    for i in range(n_boot):
        meds[i] = np.median(np.concatenate([groups[j] for j in rng.integers(0, len(uniq), len(uniq))]))
    return [float(np.percentile(meds, 5)), float(np.percentile(meds, 95))]


def summarize(vals, days):
    v, d = np.asarray(vals, float), np.asarray(days)
    m = np.isfinite(v)
    v, d = v[m], d[m]
    if not len(v):
        return {"n": 0}
    return {"n": int(len(v)), "days": int(len(np.unique(d))), "median": float(np.median(v)),
            "mean": float(v.mean()), "pos_pct": 100 * float((v > 0).mean()), "neg_pct": 100 * float((v < 0).mean()),
            "ci90_median": day_boot_median(v, d),
            # review fix: 7-day windows of events a few days apart overlap, so also draw whole
            # calendar weeks (day // 7) instead of whole days (exploratory, no verdict uses it)
            "ci90_median_week_blocks": day_boot_median(v, d // 7)}


# ---------------------------------------------------------------- size on the panel

def change_series(arr, lo, hi, kind):
    """Change of `arr` from bar x+lo to x+hi, for every x (NaN out of range): % for sizes, points for
    the share (which is a fraction in `arr`). Undefined when the start value is 0 or missing."""
    n = len(arr)
    out = np.full(n, np.nan)
    x = np.arange(n)
    ok = (x + lo >= 0) & (x + hi < n)
    a, b = arr[x[ok] + lo], arr[x[ok] + hi]
    with np.errstate(invalid="ignore", divide="ignore"):
        if kind == "share":
            out[ok] = 100 * (b - a)
        else:
            out[ok] = np.where((a > 0) & np.isfinite(a) & np.isfinite(b), 100 * (b / np.where(a > 0, a, 1) - 1), np.nan)
    return out


class Size:
    def __init__(self, s: Study, fng: dict, panel_start=PANEL_START, analysis_start=ANALYSIS_START):
        self.s = s
        self.grid, NB = s.grid, len(s.grid)
        self.p0 = int(np.searchsorted(self.grid, panel_start))
        self.a0 = int(np.searchsorted(self.grid, analysis_start))
        self.panel_start = panel_start
        self.hc = int(np.searchsorted(self.grid, s.end - HOLD, side="right")) - 1   # last headline bar
        self.ec = int(np.searchsorted(self.grid, s.end - HOLD - 7 * DAY, side="right")) - 1
        # forward-filled closes for exposure (0 before a coin lists; it cannot be held then)
        cf = s.close.copy()
        for row in cf:
            have = np.isfinite(row)
            if have.any():
                idx = np.where(have, np.arange(NB), 0)
                np.maximum.accumulate(idx, out=idx)
                row[:] = np.where(np.arange(NB) >= np.argmax(have), row[idx], 0.0)
            else:
                row[:] = 0.0
        self.closeff = cf
        nW = len(s.addrs)
        self.G = np.zeros((nW, NB))                 # gross perp notional per wallet
        self.N = np.zeros((nW, NB), dtype=np.int32)  # open positions per wallet
        for c in s.coins:
            rows = s.rows[c]
            if len(rows):
                P = s.P[c]
                self.G[rows] += np.abs(P) * cf[s.ci[c]][None, :]
                self.N[rows] += (P != 0)
        self.fg = np.array([fng.get(int(t // DAY) - 1, np.nan) for t in self.grid], dtype=float)
        self.daily = np.array([b for b in range(self.a0, NB) if self.grid[b] % DAY == 0], dtype=int)
        # equal-weight basket excess returns at the forward horizons
        self.fwd, self.fwd_ex = {}, {}
        for h, k in FWD.items():
            r = np.full(s.close.shape, np.nan)
            r[:, :NB - k] = s.close[:, k:] / s.close[:, :NB - k] - 1
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                bask = np.nanmean(r, axis=0)
            self.fwd[h], self.fwd_ex[h] = r, r - bask[None, :]

    # -- wallet sets

    def panel(self, g):
        return self.s.member[g] & (self.s.cover <= self.panel_start)

    def mm_filtered(self, mask):
        return mask & (self.N[:, self.a0:].max(1) <= MM_MAX_POSITIONS)

    def measures(self, c, wmask):
        """Per-bar size measures of coin c over the wallets in wmask (bool over all wallets)."""
        s, ci = self.s, self.s.ci[c]
        rows = s.rows[c]
        keep = wmask[rows] if len(rows) else np.zeros(0, bool)
        P = s.P[c][keep]
        cl = s.close[ci]
        lng = np.maximum(P, 0)
        coins = lng.sum(0)
        usd = coins * cl
        gross = self.G[wmask].sum(0)
        nlong = (P > 0).sum(0)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            share = np.where(gross > 0, usd / np.where(gross > 0, gross, 1), np.nan)
            med = np.nanmedian(np.where(P > 0, P * cl[None, :], np.nan), axis=0) if len(P) else np.full(len(cl), np.nan)
        med = np.where(nlong >= MIN_MEDIAN_WALLETS, med, np.nan)
        return {"long_coins": coins, "long_usd": usd, "share": share, "median_wallet_usd": med,
                "short_usd": np.maximum(-P, 0).sum(0) * cl, "wallets_long": nlong,
                "holders": (P != 0).sum(0), "gross_usd": gross}

    def largest(self, c, wmask):
        """The wallet in wmask with the largest average long notional on c over the headline analysis
        bars; returns (mask without it, its short tag, top-1 and top-3 shares of long notional in %)."""
        s = self.s
        rows = s.rows[c]
        keep = wmask[rows] if len(rows) else np.zeros(0, bool)
        ids = rows[keep]
        if not len(ids):
            return wmask, None, None, None
        sl = slice(self.a0, self.hc + 1)
        v = (np.maximum(s.P[c][keep][:, sl], 0) * np.nan_to_num(s.close[s.ci[c], sl])[None, :]).mean(1)
        k = int(np.argmax(v))
        out = wmask.copy()
        out[ids[k]] = False
        tot = v.sum()
        top = np.sort(v)[::-1]
        return (out, s.addrs[ids[k]][:6] + "..." + s.addrs[ids[k]][-4:],
                100 * top[0] / tot if tot else None, 100 * top[:3].sum() / tot if tot else None)

    def without_top(self, c, wmask, k=3):
        """Review fix (exploratory): wmask without the k wallets with the largest average long notional on
        c over the headline analysis bars. On BTC the top 3 trade in lockstep (one entity, it seems)."""
        s = self.s
        rows = s.rows[c]
        keep = wmask[rows] if len(rows) else np.zeros(0, bool)
        ids = rows[keep]
        out = wmask.copy()
        if len(ids):
            sl = slice(self.a0, self.hc + 1)
            v = (np.maximum(s.P[c][keep][:, sl], 0) * np.nan_to_num(s.close[s.ci[c], sl])[None, :]).mean(1)
            out[ids[np.argsort(-v)[:k]]] = False
        return out

    # -- events (bars on coin c; eligibility from the panel measures m)

    def events(self, c, m, kind, last_bar):
        s, ci = self.s, self.s.ci[c]
        cl, z, NB = s.close[ci], s.z[ci], len(self.grid)
        out, last = [], None
        for b in range(max(self.a0, W7D), min(last_bar, NB - 1) + 1):
            if m["holders"][b - W72] < MIN_HOLDERS or not np.isfinite(cl[b]):
                continue
            if kind in ("top_z2", "top_any_z"):
                if b + W72 >= NB:
                    continue
                win = cl[b - W72:b + W72 + 1]
                if not np.isfinite(win).all() or cl[b] < win.max():
                    continue
                if kind == "top_z2" and not (np.isfinite(z[b]) and z[b] >= Z_TOP):
                    continue
            elif kind == "stretch_start":
                if not (np.isfinite(z[b]) and z[b] >= Z_TOP and np.isfinite(z[b - 1]) and z[b - 1] < Z_TOP):
                    continue
            elif kind == "greed_start":
                if not (self.grid[b] % DAY == 0 and self.fg[b] >= GREED and self.fg[b - 6] < GREED):
                    continue
            if last is None or self.grid[b] - self.grid[last] >= COOL:
                out.append(b)
                last = b
        return out

    def event_rows(self, c, m, bars, limit):
        """Per event: the change in each measure over each window, the matched baseline (median change at
        the same coin's bars within 15 days, not within 72 hours, windows inside [panel start, limit]) and
        the excess. Also the coin's price change over the window."""
        ci = self.s.ci[c]
        price = self.s.close[ci]
        chg = {(k, w): change_series(m[k], lo, hi, k) for k in MEASURES for w, (lo, hi) in WINDOWS.items()}
        pchg = {w: change_series(price, lo, hi, "pct") for w, (lo, hi) in WINDOWS.items()}
        x = np.arange(len(self.grid))
        rows = []
        for b in bars:
            r = {"coin": c, "t": int(self.grid[b]), "time": iso(self.grid[b]), "b": int(b),
                 "z": float(self.s.z[ci, b]) if np.isfinite(self.s.z[ci, b]) else None,
                 "fear_greed": float(self.fg[b]) if np.isfinite(self.fg[b]) else None,
                 "level": {k: float(m[k][b]) for k in ("long_coins", "long_usd", "share", "wallets_long")}}
            for w, (lo, hi) in WINDOWS.items():
                near = (np.abs(x - b) <= MATCH) & (np.abs(x - b) > MATCH_EXCL) & (x + lo >= self.p0) & (x + hi <= limit)
                r[f"price_{w}"] = float(pchg[w][b])
                for k in MEASURES:
                    ev = float(chg[(k, w)][b]) if b + hi <= limit else float("nan")
                    base = chg[(k, w)][near]
                    base = base[np.isfinite(base)]
                    bm = float(np.median(base)) if len(base) else float("nan")
                    r[f"{k}_{w}"] = ev
                    r[f"{k}_{w}_matched"] = bm
                    r[f"{k}_{w}_excess"] = ev - bm
            rows.append(r)
        return rows

    def all_bars_baseline(self, c, m, limit):
        """Median change per measure and window over all analysis bars of c with the window inside
        [panel start, limit]."""
        out = {}
        for w, (lo, hi) in WINDOWS.items():
            x = np.arange(self.a0, len(self.grid))
            x = x[(x + lo >= self.p0) & (x + hi <= limit)]
            for k in MEASURES:
                v = change_series(m[k], lo, hi, k)[x]
                v = v[np.isfinite(v)]
                out[f"{k}_{w}"] = float(np.median(v)) if len(v) else None
        return out


def event_stats(rows):
    days = [r["t"] // DAY for r in rows]
    out = {"events": len(rows), "distinct_days": len(set(days))}
    for w in WINDOWS:
        d = {"price_pct": summarize([r[f"price_{w}"] for r in rows], days)}
        for k in MEASURES:
            d[k] = {"raw": summarize([r[f"{k}_{w}"] for r in rows], days),
                    "excess": summarize([r[f"{k}_{w}_excess"] for r in rows], days)}
        out[w] = d
    return out


def verdict_a(st, st_wo):
    """Declared test A: size (long coins) rises into tops, and its mirror for cuts after tops."""
    def up(x, w):
        e = x[w]["long_coins"]["excess"]
        return bool(e.get("n") and e["median"] > 0 and e["ci90_median"][0] > 0)

    def down(x, w):
        e = x[w]["long_coins"]["excess"]
        return bool(e.get("n") and e["median"] < 0 and e["ci90_median"][1] < 0)

    enough = st["distinct_days"] >= MIN_EVENTS
    rise = {"1_at_least_30_independent_events": enough,
            "2_before_72h_excess_long_coins_above_0": up(st, "before_72h"),
            "3_before_7d_excess_long_coins_above_0": up(st, "before_7d"),
            "4_holds_without_largest_wallet": up(st_wo, "before_72h") and up(st_wo, "before_7d")}
    cut = {"1_at_least_30_independent_events": enough,
           "2_after_72h_excess_long_coins_below_0": down(st, "after_72h"),
           "3_after_7d_excess_long_coins_below_0": down(st, "after_7d"),
           "4_holds_without_largest_wallet": down(st_wo, "after_72h") and down(st_wo, "after_7d")}
    lab = lambda t: "passes" if all(t.values()) else ("not informative" if not enough else "not shown")
    return {"size_rises_into_event": {"tests": rise, "verdict": lab(rise)},
            "size_cut_after_event": {"tests": cut, "verdict": lab(cut)}}


def verdict_b(g2, g2_wo):
    tests = {"1_at_least_120_days": g2.get("days", 0) >= MIN_DAYS,
             "2_rho_ge_0.2": bool(np.isfinite(g2.get("rho", np.nan)) and g2["rho"] >= MIN_RHO),
             "3_ci90_above_0": bool(g2.get("ci90") and g2["ci90"][0] > 0),
             "4_ci90_above_0_without_largest_wallet": bool(g2_wo.get("ci90") and g2_wo["ci90"][0] > 0)}
    if not tests["1_at_least_120_days"]:
        v = "not informative"
    elif all(tests.values()):
        v = "relationship"
    else:
        v = "no clear relationship"
    return {"tests": tests, "verdict": v}


def verdict_c(f, f_wo):
    def ok(x):
        a, b = x.get("7d", {}), x.get("14d", {})
        if not (a.get("ci90") and b.get("ci90")):
            return False
        same = np.sign(a["rho"]) == np.sign(b["rho"]) != 0
        excl = lambda y: y["ci90"][0] > 0 or y["ci90"][1] < 0
        return bool(same and abs(a["rho"]) >= MIN_RHO and abs(b["rho"]) >= MIN_RHO and excl(a) and excl(b))
    tests = {"1_at_least_120_days_each_horizon": all(f.get(h, {}).get("days", 0) >= MIN_DAYS for h in FWD),
             "2_abs_rho_ge_0.2_same_sign_ci_excludes_0_at_7d_and_14d": ok(f),
             "3_same_without_largest_wallet": ok(f_wo)}
    return {"tests": tests, "verdict": ("signal bar met" if all(tests.values()) else
                                         "not informative" if not tests["1_at_least_120_days_each_horizon"]
                                         else "no predictive relationship shown")}


# ---------------------------------------------------------------- correlations

def daily_obs(z, c, m, last):
    """Daily (00:00 UTC) observations on coin c up to bar index `last` (forward windows must end by it):
    predictors and outcomes as arrays keyed by name, plus the day."""
    s = z.s
    b = z.daily
    ci = s.ci[c]
    k7 = W7D
    ch = lambda arr, kind: change_series(arr, -k7, 0, kind)[b]
    o = {"day": z.grid[b] // DAY, "bar": b,
         "fg": z.fg[b], "d_fg_7d": z.fg[b] - np.where(b - k7 >= 0, z.fg[np.maximum(b - k7, 0)], np.nan),
         "long_coins": m["long_coins"][b], "long_usd": m["long_usd"][b], "share": m["share"][b],
         "price": s.close[ci, b],
         "d_long_coins_7d": ch(m["long_coins"], "pct"), "d_long_usd_7d": ch(m["long_usd"], "pct"),
         "d_share_7d": ch(m["share"], "share")}
    for h, k in FWD.items():
        ok = b + k <= last
        o[f"fwd_{h}"] = np.where(ok, z.fwd[h][ci, b], np.nan)
        o[f"fwd_ex_{h}"] = np.where(ok, z.fwd_ex[h][ci, b], np.nan)
    o["in_headline"] = b <= last
    return o


def correlations(obs_list, alt=False):
    """G1-G3 and F1-F2 on a list of daily observation dicts (one per coin), pooled."""
    cat = lambda k: np.concatenate([o[k] for o in obs_list]) if obs_list else np.zeros(0)
    day, inh = cat("day"), cat("in_headline").astype(bool)
    ret = "fwd_ex_" if alt else "fwd_"
    sel = lambda x: np.where(inh, x, np.nan)
    out = {"G1_level": {k: block_boot_rho(sel(cat("fg")), sel(cat(k)), day) for k in ("long_coins", "long_usd", "share")},
           "G2_d_fg_vs_d_long_coins_7d": block_boot_rho(sel(cat("d_fg_7d")), sel(cat("d_long_coins_7d")), day),
           "G3": {k: block_boot_rho(sel(cat("d_fg_7d")), sel(cat(k)), day) for k in ("d_long_usd_7d", "d_share_7d")},
           "F1_d_long_coins_7d_vs_forward": {h: block_boot_rho(cat("d_long_coins_7d"), cat(ret + h), day) for h in FWD},
           "F2": {p: {h: block_boot_rho(cat(p), cat(ret + h), day) for h in FWD}
                  for p in ("share", "d_long_usd_7d", "fg")}}
    if not alt:
        out["price_level_vs"] = {k: block_boot_rho(sel(cat("price")), sel(cat(k)), day) for k in ("long_coins", "long_usd")}
    return out


def greed_levels(z, obs):
    """Median BTC levels on headline days with known F&G >= 70 vs below (description)."""
    inh = obs["in_headline"].astype(bool)
    hi = inh & (obs["fg"] >= GREED)
    lo = inh & (obs["fg"] < GREED)
    f = lambda mask, k: float(np.nanmedian(obs[k][mask])) if mask.any() else None
    return {"days_greed": int(hi.sum()), "days_other": int(lo.sum()),
            **{k: {"greed": f(hi, k), "other": f(lo, k)} for k in ("long_coins", "long_usd", "share", "price")}}


def monthly_levels(z, m, c):
    """Median level per calendar month over analysis bars (description)."""
    month = np.array([iso(t)[:7] for t in z.grid])
    out = {}
    for mo in sorted(set(month[z.a0:])):
        sl = (month == mo) & (np.arange(len(z.grid)) >= z.a0)
        out[mo] = {k: float(np.nanmedian(m[k][sl])) for k in ("long_coins", "long_usd", "share", "wallets_long")}
        out[mo]["price"] = float(np.nanmedian(z.s.close[z.s.ci[c], sl]))
    return out


def timeline(z, m, m3, c):
    """Review addition (exploratory): BTC every 7 days from the analysis start, panel and panel without
    its top 3 wallets, with price and the known Fear & Greed value."""
    ci = z.s.ci[c]
    out = []
    for b in range(z.a0, len(z.grid), W7D):
        out.append({"time": iso(z.grid[b]), "price": float(z.s.close[ci, b]), "fear_greed": float(z.fg[b]),
                    "long_coins": float(m["long_coins"][b]), "long_coins_without_top3": float(m3["long_coins"][b]),
                    "wallets_long": int(m["wallets_long"][b]), "wallets_long_without_top3": int(m3["wallets_long"][b]),
                    "share_without_top3": float(m3["share"][b])})
    return out


# ---------------------------------------------------------------- the study

def alt_pool(z):
    m_all = z.panel("money_printer")
    out = []
    for c in z.s.coins:
        if c == "BTC":
            continue
        h = z.measures(c, m_all)["holders"][z.a0:z.hc + 1]
        if len(h) and (h >= MIN_HOLDERS).mean() >= POOL_MIN_FRAC:
            out.append(c)
    return out


def run_group(z, g, pool, wmask=None, light=False):
    """Everything for group g. wmask overrides the panel (sensitivities). light: key numbers only."""
    base = z.panel(g) if wmask is None else wmask
    res = {"panel_wallets": int(base.sum()),
           "panel_wallets_with_perp_positions": int((base & (z.N[:, z.p0:].max(1) > 0)).sum())}
    ends = {"headline": (z.ec, z.hc), "all_biased": (len(z.grid) - 1 - W7D, len(z.grid) - 1)}
    for scope, coins in (("BTC", ["BTC"]), ("alt_pool", pool)):
        per = {}
        for c in coins:
            m = z.measures(c, base)
            wo_mask, top_tag, top1, top3 = z.largest(c, base)
            m_wo = z.measures(c, wo_mask)
            per[c] = (m, m_wo, top_tag, top1, top3, z.measures(c, z.without_top(c, base)))
        sc = {}
        for period, (ev_last, limit) in ends.items():
            sp = {}
            for kind in EVENT_KINDS:
                rows, rows_wo, rows_wo3 = [], [], []
                for c, (m, m_wo, _t, _1, _3, m_wo3) in per.items():
                    bars = z.events(c, m, kind, ev_last)
                    rows += z.event_rows(c, m, bars, limit)
                    rows_wo += z.event_rows(c, m_wo, bars, limit)
                    rows_wo3 += z.event_rows(c, m_wo3, bars, limit)
                st, st_wo = event_stats(rows), event_stats(rows_wo)
                sp[kind] = {"stats": st, "verdict": verdict_a(st, st_wo)}
                st3 = event_stats(rows_wo3)
                sp[kind]["exploratory_without_top3_wallets"] = {
                    w: {k: st3[w][k] for k in ("long_coins", "long_usd")} for w in WINDOWS}
                sp[kind]["exploratory_verdict_rules_without_top3"] = verdict_a(st3, st3)
                if not light:
                    sp[kind]["without_largest_wallet"] = st_wo
                    sp[kind]["events"] = [{k: v for k, v in r.items() if k in (
                        "coin", "time", "z", "fear_greed", "level") or k.startswith("price_")
                        or (k.split("_")[0] in ("long", "share") and not k.endswith("_matched"))} for r in rows] \
                        if scope == "BTC" else len(rows)
            sc[period] = sp
        # correlations on the headline sample
        obs = [daily_obs(z, c, per[c][0], z.hc) for c in coins]
        obs_wo = [daily_obs(z, c, per[c][1], z.hc) for c in coins]
        cor, cor_wo = correlations(obs, alt=scope != "BTC"), correlations(obs_wo, alt=scope != "BTC")
        obs_wo3 = [daily_obs(z, c, per[c][5], z.hc) for c in coins]
        cor3 = correlations(obs_wo3, alt=scope != "BTC")
        sc["exploratory_correlations_headline_without_top3_wallets"] = {
            k: cor3[k] for k in ("G1_level", "G2_d_fg_vs_d_long_coins_7d", "G3", "F1_d_long_coins_7d_vs_forward")}
        # all days (biased: every Fear & Greed reading of 70 or more falls after 21 August)
        obs_all = [daily_obs(z, c, per[c][0], len(z.grid) - 1) for c in coins]
        obs_all3 = [daily_obs(z, c, per[c][5], len(z.grid) - 1) for c in coins]
        sc["exploratory_correlations_all_days_biased"] = {
            "G2": correlations(obs_all, alt=scope != "BTC")["G2_d_fg_vs_d_long_coins_7d"],
            "G2_without_top3": correlations(obs_all3, alt=scope != "BTC")["G2_d_fg_vs_d_long_coins_7d"]}
        sc["correlations_headline"] = cor
        sc["correlations_headline_without_largest_wallet"] = (
            {"G2_d_fg_vs_d_long_coins_7d": cor_wo["G2_d_fg_vs_d_long_coins_7d"],
             "F1_d_long_coins_7d_vs_forward": cor_wo["F1_d_long_coins_7d_vs_forward"]} if light else cor_wo)
        sc["verdict_B_greed"] = verdict_b(cor["G2_d_fg_vs_d_long_coins_7d"], cor_wo["G2_d_fg_vs_d_long_coins_7d"])
        sc["verdict_C_predicts"] = verdict_c(cor["F1_d_long_coins_7d_vs_forward"], cor_wo["F1_d_long_coins_7d_vs_forward"])
        if not light:
            sc["largest_wallet"] = {c: {"wallet": v[2], "top1_share_of_long_usd_pct": v[3],
                                        "top3_share_of_long_usd_pct": v[4]} for c, v in per.items()}
            if scope == "BTC":
                o = obs[0]
                sc["greed_days_vs_other_days"] = greed_levels(z, o)
                sc["exploratory_greed_days_vs_other_days_all_days_biased"] = {
                    "panel": greed_levels(z, obs_all[0]), "without_top3": greed_levels(z, obs_all3[0])}
                sc["exploratory_timeline"] = timeline(z, per["BTC"][0], per["BTC"][5], "BTC")
                sc["monthly_levels"] = monthly_levels(z, per["BTC"][0], "BTC")
                sc["levels_now"] = {k: float(per["BTC"][0][k][-1]) for k in ("long_coins", "long_usd", "share", "wallets_long")}
            else:
                # pool-level daily series: median across pool coins of each coin's 7-day change
                D = np.vstack([o["d_long_coins_7d"] for o in obs]) if obs else np.zeros((0, 0))
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", RuntimeWarning)
                    med = np.nanmedian(D, axis=0) if len(D) else D
                o0 = obs[0] if obs else None
                if o0 is not None:
                    inh = o0["in_headline"].astype(bool)
                    sc["pool_median_series_G2"] = block_boot_rho(np.where(inh, o0["d_fg_7d"], np.nan),
                                                                 np.where(inh, med, np.nan), o0["day"])
        res[scope] = sc
    return res


def per_event_panel(z, g, pool):
    """Sensitivity: each event measured over the group's wallets covered from its 7-day pre-window
    (admits active traders the fixed panel leaves out). Raw changes only, next to the fixed panel's."""
    out = {}
    fixed = z.panel(g)
    for scope, coins in (("BTC", ["BTC"]), ("alt_pool", pool)):
        sp = {}
        for kind in ("top_z2", "top_any_z", "stretch_start"):
            rows_f, rows_e = [], []
            for c in coins:
                m = z.measures(c, fixed)
                for b in z.events(c, m, kind, z.ec):
                    wm = z.s.member[g] & (z.s.cover <= z.grid[b - W7D])
                    me = z.measures(c, wm)
                    rows_f += z.event_rows(c, m, [b], z.hc)
                    rows_e += z.event_rows(c, me, [b], z.hc)
            f, e = event_stats(rows_f), event_stats(rows_e)
            sp[kind] = {"events": f["events"], **{
                w: {"long_coins_fixed": f[w]["long_coins"]["raw"].get("median"),
                    "long_coins_per_event_panel": e[w]["long_coins"]["raw"].get("median"),
                    "long_usd_fixed": f[w]["long_usd"]["raw"].get("median"),
                    "long_usd_per_event_panel": e[w]["long_usd"]["raw"].get("median")} for w in WINDOWS}}
        out[scope] = sp
    return out


def compact(r):
    out = {}
    for scope in ("BTC", "alt_pool"):
        x = r[scope]
        out[scope] = {
            "top_any_z_before_7d_long_coins_excess": x["headline"]["top_any_z"]["stats"]["before_7d"]["long_coins"]["excess"],
            "top_any_z_after_7d_long_coins_excess": x["headline"]["top_any_z"]["stats"]["after_7d"]["long_coins"]["excess"],
            "top_z2_events": x["headline"]["top_z2"]["stats"]["events"],
            "top_z2_verdict": {k: v["verdict"] for k, v in x["headline"]["top_z2"]["verdict"].items()},
            "G2": x["correlations_headline"]["G2_d_fg_vs_d_long_coins_7d"],
            "F1": x["correlations_headline"]["F1_d_long_coins_7d_vs_forward"],
            "verdict_B": x["verdict_B_greed"]["verdict"], "verdict_C": x["verdict_C_predicts"]["verdict"]}
    return out


def load_fng(path):
    with open(path) as fh:
        d = json.load(fh)
    if isinstance(d, dict):
        d = d.get("fear_greed", d)
    if isinstance(d, dict):
        return {int(k): int(v) for k, v in d.items()}
    return {int(k): int(v) for k, v in d}


def run(data_dir, fng_path):
    np.seterr(invalid="ignore", divide="ignore")
    warnings.filterwarnings("ignore", message="Mean of empty slice")
    warnings.filterwarnings("ignore", message="All-NaN slice")
    t0 = time.time()
    wallets, candles, end = load(data_dir)
    s = Study(wallets, candles, end)
    z = Size(s, load_fng(fng_path))
    pool = alt_pool(z)
    out = {"meta": {
        "data_end": iso(end), "panel_start": iso(PANEL_START), "analysis_start": iso(z.grid[z.a0]),
        "headline_last_bar": iso(z.grid[z.hc]), "headline_last_event_bar": iso(z.grid[z.ec]),
        "bars_4h_analysis": int(len(z.grid) - z.a0), "daily_obs": int(len(z.daily)),
        "alt_pool": pool,
        "fear_greed_days_ge_70_in_analysis": int(np.sum(z.fg[z.daily] >= GREED)),
        "notes": [
            "Changes are in % for long_coins, long_usd and median_wallet_usd, in points for share; returns are fractions.",
            "share = the coin's long notional / the panel's gross notional across all perpetual coins.",
            "excess = event change minus the median change at the same coin's bars within 15 days, not within 72 hours.",
            "F&G stamped day D is used from the 00:00 UTC close of day D+1.",
            "Correlations are Spearman with a 14-day circular moving-block bootstrap over days (90% interval).",
        ]}}
    for g in GROUPS:
        out[g] = run_group(z, g, pool)
        out[g]["sensitivity_market_maker_filter"] = compact(run_group(z, g, pool, wmask=z.mm_filtered(z.panel(g)), light=True))
        out[g]["sensitivity_market_maker_filter"]["panel_wallets"] = int(z.mm_filtered(z.panel(g)).sum())
        out[g]["sensitivity_per_event_panel"] = per_event_panel(z, g, pool)
    out["meta"]["runtime_s"] = time.time() - t0
    return rounded(out, 4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data")
    ap.add_argument("fng")
    ap.add_argument("--out")
    args = ap.parse_args()
    txt = json.dumps(run(args.data, args.fng), indent=1)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w") as fh:
            fh.write(txt)
    else:
        print(txt)


if __name__ == "__main__":
    main()
