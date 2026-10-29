"""
Which readings come before the market turns? A fixed menu of daily readings (market structure, sentiment, options fear,
leverage, liquidity) against what the typical coin did next, each checked in the first and the second half of its
history and against the last month's move (docs/reviews/turn-signs-study.md, declared 29 October 2026, before
running). Context, not a signal unless a reading clears the declared bar.

Run from backend/ (no network):

  node research/export_page_rows.mjs MH.json WALLETS.json ROWS.json
  python -m research.fetch_turn_data --out EXTRA.json
  python -m research.turn_signs --rows ROWS.json --live LIVE.json --extra EXTRA.json --wallets WALLETS.json \
      [--shape] [--out JSON]
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

import numpy as np

from research import late_uptrends as L
from research.late_uptrends import iso

H = 30                    # outcome horizon (days)
PAST = 30                 # the momentum control: the typical coin's change over the last 30 days
WIN = 90                  # divergence: position in the last 90 days' range
MIN_RHO = 0.15
TAIL = 0.10               # extremes: the first half's top and bottom 10%
TAIL_EDGE = 5.0           # points against the half's median, same direction in both halves
BLOCK = 30
BOOT = 2_000
SEED = 20261029

FEATURES = [
    # key, label, group
    ("breadth", "Share of coins in uptrend", "structure"),
    ("breadth_chg14", "Share of coins in uptrend, 14-day change", "structure"),
    ("mz", "Median z", "structure"),
    ("mz_chg14", "Median z, 14-day change", "structure"),
    ("down_share", "Share of coins in downtrend", "structure"),
    ("alt_past30", "Typical coin, last 30 days", "structure"),
    ("btc_past30", "BTC, last 30 days", "structure"),
    ("btc_band", "BTC over its weekly band's lower edge", "structure"),
    ("divergence", "BTC's place in its 90-day range minus the share's", "structure"),
    ("fg", "Fear & Greed", "sentiment"),
    ("fg_chg14", "Fear & Greed, 14-day change", "sentiment"),
    ("heat", "Market heat", "sentiment"),
    ("dvol", "BTC options implied volatility (DVOL)", "options"),
    ("dvol_chg14", "DVOL, 14-day change", "options"),
    ("funding", "BTC and ETH funding, 7-day mean", "leverage"),
    ("stables_chg30", "Stablecoin supply, 30-day change", "liquidity"),
]


# ---------------------------------------------------------------- statistics

def ranks(a: np.ndarray) -> np.ndarray:
    """Average ranks (ties share their mean rank)."""
    order = np.argsort(a, kind="mergesort")
    r = np.empty(len(a))
    sa = a[order]
    i = 0
    while i < len(a):
        j = i
        while j + 1 < len(a) and sa[j + 1] == sa[i]:
            j += 1
        r[order[i:j + 1]] = (i + j) / 2.0
        i = j + 1
    return r


def _corr(x: np.ndarray, y: np.ndarray) -> float:
    x, y = x - x.mean(), y - y.mean()
    d = np.sqrt((x * x).sum() * (y * y).sum())
    return float((x * y).sum() / d) if d > 0 else float("nan")


def spearman(x, y, z=None) -> float:
    """Spearman's rho of x and y; with z, the partial rho (ranks of x and y each cleared of the rank of z)."""
    rx, ry = ranks(np.asarray(x, float)), ranks(np.asarray(y, float))
    if z is None:
        return _corr(rx, ry)
    rz = ranks(np.asarray(z, float))
    A = np.vstack([rz, np.ones(len(rz))]).T
    ex = rx - A @ np.linalg.lstsq(A, rx, rcond=None)[0]
    ey = ry - A @ np.linalg.lstsq(A, ry, rcond=None)[0]
    return _corr(ex, ey)


def block_interval(x, y, z=None, block=BLOCK, boot=BOOT, seed=SEED) -> list:
    """90% moving-block bootstrap interval of the (partial) rho, blocks of 30 consecutive days."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    z = None if z is None else np.asarray(z, float)
    n = len(x)
    if n < 2 * block:
        return [float("nan"), float("nan")]
    rng = np.random.default_rng(seed)
    starts = np.arange(n - block + 1)
    vals = []
    for _ in range(boot):
        idx = np.concatenate([np.arange(s, s + block) for s in rng.choice(starts, size=n // block + 1)])[:n]
        vals.append(spearman(x[idx], y[idx], None if z is None else z[idx]))
    return [round(float(np.nanpercentile(vals, 5)), 3), round(float(np.nanpercentile(vals, 95)), 3)]


# ---------------------------------------------------------------- the daily table

def table(rows: list, out: L.Outcomes, extra: dict) -> dict:
    """{day: {feature: value, 'alt30': forward typical coin, 'btc30', 'breadth30'}} for every page day."""
    by = {r["day"]: r for r in rows}
    days = [r["day"] for r in rows]
    heat = dict(L.heat_series(rows))
    fund = {}
    fb = {int(k): v for k, v in extra.get("funding_btc", {}).items()}
    fe = {int(k): v for k, v in extra.get("funding_eth", {}).items()}
    for d in set(fb) & set(fe):
        fund[d] = (fb[d] + fe[d]) / 2
    dvol = {int(k): v for k, v in extra.get("dvol", {}).items()}
    stab = {int(k): v for k, v in extra.get("stables", {}).items()}

    def val(r, k):
        return None if r is None else r.get(k)

    def chg(series, d, n):
        a, b = series.get(d - n), series.get(d)
        return None if a is None or b is None else b - a

    share = {d: by[d]["uptrend"] for d in days}
    mz = {d: by[d]["median_z"] for d in days}
    fg = {d: by[d]["fg"] for d in days}
    btc = {d: by[d]["btc"] for d in days}
    out_t = {}
    for d in days:
        r = by[d]
        f = {}
        f["breadth"] = None if r["uptrend"] is None else 100 * r["uptrend"]
        c = chg(share, d, 14)
        f["breadth_chg14"] = None if c is None else 100 * c
        f["mz"] = r["median_z"]
        f["mz_chg14"] = chg(mz, d, 14)
        f["down_share"] = None if r["downtrend"] is None else 100 * r["downtrend"]
        f["alt_past30"] = out.alt(d - PAST, d) if d - PAST in by else None
        f["btc_past30"] = None if not btc.get(d - PAST) or not btc.get(d) else 100 * (btc[d] / btc[d - PAST] - 1)
        f["btc_band"] = None if not r["band_lo"] or not r["btc"] else 100 * (r["btc"] / r["band_lo"] - 1)
        wb = [btc.get(d - k) for k in range(WIN) if btc.get(d - k)]
        ws = [share.get(d - k) for k in range(WIN) if share.get(d - k) is not None]
        if len(wb) >= WIN * 0.9 and len(ws) >= WIN * 0.9 and max(wb) > min(wb) and max(ws) > min(ws) and r["uptrend"] is not None:
            f["divergence"] = (btc[d] - min(wb)) / (max(wb) - min(wb)) - (r["uptrend"] - min(ws)) / (max(ws) - min(ws))
        else:
            f["divergence"] = None
        f["fg"] = r["fg"]
        f["fg_chg14"] = chg(fg, d, 14)
        f["heat"] = heat.get(d)
        f["dvol"] = dvol.get(d)
        f["dvol_chg14"] = chg(dvol, d, 14)
        fw = [fund.get(d - k) for k in range(7) if fund.get(d - k) is not None]
        f["funding"] = 100 * sum(fw) / len(fw) if len(fw) >= 5 else None
        f["stables_chg30"] = None if not stab.get(d - 30) or not stab.get(d) else 100 * (stab[d] / stab[d - 30] - 1)
        o = out.all(d)
        f["alt30"], f["btc30"], f["breadth30"] = o["alt30"], o["btc30"], o["breadth30"]
        out_t[d] = f
    return out_t


def series(t: dict, key: str, outcome: str = "alt30", control: str | None = "alt_past30") -> list:
    """[(day, x, y, z)] where every needed value exists, oldest first."""
    out = []
    for d in sorted(t):
        f = t[d]
        x, y = f.get(key), f.get(outcome)
        z = f.get(control) if control else 0.0
        if x is None or y is None or (control and z is None):
            continue
        out.append((d, float(x), float(y), float(z)))
    return out


# ---------------------------------------------------------------- the checks

def check_feature(t: dict, key: str, outcome: str = "alt30") -> dict:
    s = series(t, key, outcome)
    if len(s) < 4 * BLOCK:
        return {"key": key, "n": len(s), "note": "too short"}
    k = len(s) // 2
    halves = [s[:k], s[k:]]
    res = {"key": key, "n": len(s), "from": iso(s[0][0]), "split": iso(s[k][0]), "to": iso(s[-1][0]), "halves": []}
    p10 = float(np.percentile([v[1] for v in halves[0]], 100 * TAIL))
    p90 = float(np.percentile([v[1] for v in halves[0]], 100 * (1 - TAIL)))
    res["tail_cuts"] = [round(p10, 3), round(p90, 3)]
    for h in halves:
        x, y, z = (np.array([v[i] for v in h]) for i in (1, 2, 3))
        row = {"n": len(h), "rho": round(spearman(x, y), 3), "rho_interval": block_interval(x, y)}
        if key != "alt_past30":
            row["partial"] = round(spearman(x, y, z), 3)
            row["partial_interval"] = block_interval(x, y, z)
        med = statistics.median(y.tolist())
        hi = [v[2] for v in h if v[1] >= p90]
        lo = [v[2] for v in h if v[1] <= p10]
        row["top"] = None if not hi else {"days": len(hi), "blocks": len({v[0] // BLOCK for v in h if v[1] >= p90}),
                                          "median": round(statistics.median(hi), 1), "vs_half": round(statistics.median(hi) - med, 1)}
        row["bottom"] = None if not lo else {"days": len(lo), "blocks": len({v[0] // BLOCK for v in h if v[1] <= p10}),
                                             "median": round(statistics.median(lo), 1), "vs_half": round(statistics.median(lo) - med, 1)}
        row["half_median"] = round(med, 1)
        res["halves"].append(row)

    def passes(rk, ik):
        a, b = res["halves"]
        if rk not in a:
            return False
        same = np.sign(a[rk]) == np.sign(b[rk]) != 0
        big = abs(a[rk]) >= MIN_RHO and abs(b[rk]) >= MIN_RHO
        excl = all((h[ik][0] > 0 or h[ik][1] < 0) for h in (a, b))
        return bool(same and big and excl)

    def tail_passes(side):
        a, b = (h[side] for h in res["halves"])
        if not a or not b:
            return False
        return bool(np.sign(a["vs_half"]) == np.sign(b["vs_half"]) != 0
                    and abs(a["vs_half"]) >= TAIL_EDGE and abs(b["vs_half"]) >= TAIL_EDGE)

    res["survives"] = passes("rho", "rho_interval")
    res["adds_beyond_momentum"] = passes("partial", "partial_interval")
    res["top_tail"] = tail_passes("top")
    res["bottom_tail"] = tail_passes("bottom")
    return res


def intercorrelation(t: dict) -> dict:
    keys = [k for k, _, _ in FEATURES]
    m = {}
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            pts = [(t[d][a], t[d][b]) for d in t if t[d].get(a) is not None and t[d].get(b) is not None]
            if len(pts) > 60:
                m[f"{a}|{b}"] = round(spearman([p[0] for p in pts], [p[1] for p in pts]), 2)
    return m


def turn_profiles(t: dict, events: dict) -> dict:
    """Description: each reading's percentile (against its whole history) on the turn days and 14 days before."""
    out = {}
    for name, days in events.items():
        prof = {}
        for k, _, _ in FEATURES:
            hist = sorted(v[k] for v in t.values() if v.get(k) is not None)
            if not hist:
                continue

            def pct(d):
                v = t.get(d, {}).get(k)
                return None if v is None else round(100 * np.searchsorted(hist, v, side="right") / len(hist))
            on = [p for p in (pct(d) for d in days) if p is not None]
            before = [p for p in (pct(d - 14) for d in days) if p is not None]
            prof[k] = {"on_day": None if not on else statistics.median(on), "14_days_before": None if not before else statistics.median(before),
                       "events": len(on)}
        out[name] = {"days": [iso(d) for d in days], "percentiles": prof}
    return out


def wallets_year(t: dict, wallets: dict) -> dict:
    """One year of wallet groups (description only, no halves): rho with the next and the last 30 days."""
    cols = wallets["columns"]
    ix = {c: i for i, c in enumerate(cols)}
    reads = {}
    for g in ("smart", "whales"):
        reads[f"{g}_net"] = {r[ix["day"]]: (r[ix["long"]] - r[ix["short"]]) / r[ix["wallets"]] for r in wallets["groups"][g] if r[ix["wallets"]]}
        rows = (wallets.get("coins") or {}).get("BTC", {}).get(g) or []
        cc = {c: i for i, c in enumerate(wallets.get("coin_columns") or [])}
        reads[f"{g}_btc_net"] = {r[cc["day"]]: (r[cc["long"]] - r[cc["short"]]) / (r[cc["long"]] + r[cc["short"]])
                                 for r in rows if (r[cc["long"]] or 0) + (r[cc["short"]] or 0)}
    cr = wallets.get("crowd") or {}
    ci = {c: i for i, c in enumerate(cr.get("columns") or [])}
    reads["traders_long"] = {r[ci["day"]]: r[ci["long_share"]] for r in cr.get("rows") or [] if r[ci["long_share"]] is not None}
    out = {}
    for k, rd in reads.items():
        res = {"days": len(rd)}
        for o in ("alt30", "btc30", "alt_past30", "btc_past30"):
            pts = [(rd[d], t[d][o]) for d in rd if d in t and t[d].get(o) is not None]
            res[o] = None if len(pts) < 60 else {"n": len(pts), "rho": round(spearman([p[0] for p in pts], [p[1] for p in pts]), 2)}
        out[k] = res
    return out


# ---------------------------------------------------------------- the study

def build(page, live, extra, seed=None):
    rows, out = L.build(page, live, seed)
    return rows, out, table(rows, out, extra)


def shape(page, live, extra, seed=None) -> dict:
    """Counts only: each reading's coverage and the days with an outcome (no outcome is read)."""
    rows, out, t = build(page, live, extra, seed)
    cov = {}
    for k, _, _ in FEATURES:
        ds = [d for d in sorted(t) if t[d].get(k) is not None]
        withy = [d for d in ds if t[d].get("alt30") is not None and t[d].get("alt_past30") is not None]
        cov[k] = {"from": iso(ds[0]) if ds else None, "to": iso(ds[-1]) if ds else None, "days": len(ds), "with_outcome": len(withy)}
    return {"coverage": cov}


def run_study(page, live, extra, wallets, seed=None) -> dict:
    rows, out, t = build(page, live, extra, seed)
    state, rs = L.runs(rows)
    share = {r["day"]: r["uptrend"] for r in rows}
    from research import turning_points as T
    dts = T.downturns(rows, rs, state)
    events = {"roll_overs": [d for d in (L.roll_over(r, share) for r in rs if not r["first"]) if d is not None],
              "turn_ups": [d for d in (T.first_move(dt["all_days"], share, L.ROLL, up=True) for dt in dts) if d is not None]}
    checks = [check_feature(t, k) for k, _, _ in FEATURES]
    reported = {o: [check_feature(t, k, o) for k, _, _ in FEATURES] for o in ("btc30", "breadth30")}
    return {
        "declared": "docs/reviews/turn-signs-study.md (29 October 2026)",
        "labels": {k: lab for k, lab, _ in FEATURES},
        "checks": checks,
        "summary": {
            "survive": [c["key"] for c in checks if c.get("survives")],
            "adds_beyond_momentum": [c["key"] for c in checks if c.get("adds_beyond_momentum")],
            "top_tail": [c["key"] for c in checks if c.get("top_tail")],
            "bottom_tail": [c["key"] for c in checks if c.get("bottom_tail")],
        },
        "reported_outcomes": reported,
        "intercorrelation": intercorrelation(t),
        "turn_profiles": turn_profiles(t, events),
        "wallets_one_year": wallets_year(t, wallets),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rows", required=True)
    ap.add_argument("--live", required=True)
    ap.add_argument("--extra", required=True)
    ap.add_argument("--wallets")
    ap.add_argument("--shape", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args()
    page, live, extra = (json.loads(Path(p).read_text()) for p in (a.rows, a.live, a.extra))
    res = shape(page, live, extra) if a.shape else run_study(page, live, extra, json.loads(Path(a.wallets).read_text()))
    text = json.dumps(res, indent=1)
    if a.out:
        Path(a.out).write_text(text)
    print(text)


if __name__ == "__main__":
    main()
