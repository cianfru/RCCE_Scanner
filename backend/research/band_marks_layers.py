"""Band model marks with Reflex's layers: at the mark, does a layer split its marks into a group that goes the right
way clearly more often? (docs/reviews/band-marks-layers-study.md, declared before running.)

The marks, their counting, the 90-day outcome and the chance are those of research/band_marks.py (the marks study).
Fixed here before any outcome is split by a layer: the layers, how each is read at a mark, how marks are split, which
layers are judged and the bar.

Run from backend/:
    python -m research.band_marks_layers check     # data check: each layer's coverage of the counted marks (no outcomes)
    python -m research.band_marks_layers run       # the study
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import sys
import urllib.error
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from research import band_marks as M
from research.stretch_tops import band_mid

SEEDS = Path(__file__).resolve().parent.parent / "seeds"
DAY_MS = 86_400_000
MIN_SEED_COINS = 20                # market layers: days the seed read on 20 coins or more
FUNDING_DAYS = 7                   # funding: the mean rate over the 7 days to the mark's close, per 8 hours
FUNDING_MIN_HOURS = 120            # ...from payments covering at least 120 of those 168 hours
OI_DAYS = 30                       # open interest: the log change over the 30 days to the mark's close
COVERAGE = 0.90                    # a layer is judged on a mark when it has a value on 90% of its counted marks
BAR_GROUP = 30                     # bars: a group of at least 30 marks...
BAR_GAIN = 0.10                    # ...whose margin over chance is 10 points above the mark's own...
BAR_PART = 5                       # ...and above the other group's in each part (each group 5 marks or more there)
FIRST_MONTH = (2019, 9)            # Binance USDT-M funding archives start September 2019
LAST_MONTH = (2026, 10)

# (key, name, how it splits, judged). "median": high and low halves at the median of the layer over the mark's own
# counted marks with a value (ties go high); "binary": the layer is a yes or no.
LAYERS = [
    ("breadth", "Uptrend share (Reflex: coins in Uptrend or Overheated)", "median", True),
    ("market_stretch", "Coins stretched (Reflex: band z 1.6 or more)", "median", True),
    ("market_z", "Market's median z (Reflex engine)", "median", True),
    ("fear_greed", "Fear and Greed index", "median", True),
    ("btc_band", "BTC above its weekly band", "binary", True),
    ("coin_z", "The coin's z (Reflex engine)", "median", True),
    ("funding", "The coin's funding, 7 days", "median", True),
    ("oi_change", "The coin's open interest, 30-day change", "median", True),
    ("top_traders", "Top traders' long/short ratio (Binance)", "median", True),
    ("accounts", "All accounts' long/short ratio (Binance)", "median", True),
    ("traders_long", "Profitable traders long (Reflex, the 600)", "median", False),
    ("smart_long", "Smart money long (Reflex)", "median", False),
    ("whales_long", "Whales long (Reflex)", "median", False),
]


# ---------------------------------------------------------------------------------------------------------- sources
def _cache() -> Path:
    from backtest import binance_history as bh
    bh.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return bh.CACHE_DIR


def _get(url: str) -> Optional[bytes]:
    from backtest import binance_history as bh
    try:
        return bh._get(url)
    except urllib.error.HTTPError:
        return None


def seed_layers() -> Dict[str, Dict[int, float]]:
    """Reflex's market layers by day, from the repository's seeds (days read on MIN_SEED_COINS coins or more), and
    its positioning layers (report only)."""
    mh = json.loads((SEEDS / "market_history_seed.json").read_text())
    bs = json.loads((SEEDS / "band_stretch_seed.json").read_text())
    cs = json.loads((SEEDS / "crowd_share_seed.json").read_text())
    wh = json.loads((SEEDS / "wallet_history_seed.json").read_text())
    out: Dict[str, Dict[int, float]] = {"breadth": {}, "market_z": {}, "market_stretch": {}, "traders_long": {},
                                        "smart_long": {}, "whales_long": {}}
    for d in mh["days"]:                       # day, n, uptrend, overheated, downtrend, basing, median_z, btc
        if d[1] >= MIN_SEED_COINS:
            out["breadth"][int(d[0])] = d[2] + d[3]
            if d[6] is not None:
                out["market_z"][int(d[0])] = d[6]
    for d in bs["rows"]:                       # day, coins, above, median
        if d[1] >= MIN_SEED_COINS:
            out["market_stretch"][int(d[0])] = d[2] / d[1]
    for d in cs["rows"]:                       # day, long, short
        if d[1] + d[2] > 0:
            out["traders_long"][int(d[0])] = d[1] / (d[1] + d[2])
    for grp, key in (("smart", "smart_long"), ("whales", "whales_long")):
        for d in wh["groups"][grp]:            # day, wallets, positioned, long, short, ...
            if d[3] + d[4] > 0:
                out[key][int(d[0])] = d[3] / (d[3] + d[4])
    return out


def fear_greed() -> Dict[int, float]:
    """The Fear and Greed index (alternative.me) by day, as published at 00:00 UTC that day."""
    path = _cache() / "fear_greed_all.json"
    if not path.exists():
        blob = _get("https://api.alternative.me/fng/?limit=0&format=json")
        path.write_bytes(blob)
    data = json.loads(path.read_text())["data"]
    return {int(r["timestamp"]) // 86_400: float(r["value"]) for r in data}


def _months():
    y, m = FIRST_MONTH
    while (y, m) <= LAST_MONTH:
        yield f"{y:04d}-{m:02d}"
        m += 1
        if m == 13:
            y, m = y + 1, 1


def parse_funding(text: str) -> List[Tuple[int, float, float]]:
    """(time ms, rate per 8 hours, hours the payment covers) from a fundingRate archive (calc_time,
    funding_interval_hours, last_funding_rate; older archives without the hours column are 8-hourly)."""
    out = []
    for r in csv.reader(io.StringIO(text)):
        if not r or not r[0].isdigit():
            continue
        hours = float(r[1]) if len(r) > 2 and r[1] else 8.0
        out.append((int(r[0]), float(r[-1]) * 8.0 / hours, hours))
    return out


def funding(pair: str) -> np.ndarray:
    """Every funding payment of PAIR's USDT-M perpetual (Binance archives), as [time ms, rate per 8 hours, hours]."""
    path = _cache() / f"funding_{pair}_{FIRST_MONTH[0]}-{FIRST_MONTH[1]:02d}_{LAST_MONTH[0]}-{LAST_MONTH[1]:02d}.csv"
    if not path.exists():
        def one(ym):
            blob = _get(f"https://data.binance.vision/data/futures/um/monthly/fundingRate/{pair}/{pair}-fundingRate-{ym}.zip")
            if not blob:
                return []
            with zipfile.ZipFile(io.BytesIO(blob)) as zf:
                return [x for n in zf.namelist() for x in parse_funding(zf.read(n).decode())]
        with ThreadPoolExecutor(8) as ex:
            rows = sorted({t: (r, h) for part in ex.map(one, list(_months())) for t, r, h in part}.items())
        path.write_text("".join(f"{t},{r!r},{h!r}\n" for t, (r, h) in rows))
    rows = [ln.split(",") for ln in path.read_text().splitlines() if ln]
    return np.array([[float(x) for x in r] for r in rows]) if rows else np.zeros((0, 3))


def funding_at(fund: np.ndarray, day: int) -> Optional[float]:
    """The time-weighted mean rate (per 8 hours) of the payments in the FUNDING_DAYS to the close of `day`, when
    they cover at least FUNDING_MIN_HOURS."""
    if not len(fund):
        return None
    end = (day + 1) * DAY_MS
    w = fund[(fund[:, 0] > end - FUNDING_DAYS * DAY_MS) & (fund[:, 0] <= end)]
    if w[:, 2].sum() < FUNDING_MIN_HOURS:
        return None
    return float((w[:, 1] * w[:, 2]).sum() / w[:, 2].sum())


def parse_metrics(text: str) -> List[Optional[float]]:
    """The day's last open interest (contracts), top traders' long/short ratio (positions) and all accounts'
    long/short ratio, each its last non-empty value."""
    rows = list(csv.reader(io.StringIO(text)))
    head = rows[0] if rows else []
    cols = {"sum_open_interest": None, "sum_toptrader_long_short_ratio": None, "count_long_short_ratio": None}
    idx = {c: head.index(c) for c in cols if c in head}
    for r in rows[1:]:
        for c, i in idx.items():
            if i < len(r) and r[i] not in ("", None):
                try:
                    cols[c] = float(r[i])
                except ValueError:
                    pass
    return [cols["sum_open_interest"], cols["sum_toptrader_long_short_ratio"], cols["count_long_short_ratio"]]


def metrics_points(wanted: List[Tuple[str, str]]) -> Dict[str, Optional[list]]:
    """Binance futures daily metrics for (pair, YYYY-MM-DD), cached; None where the day has no file."""
    path = _cache() / "metrics_points.json"
    have = json.loads(path.read_text()) if path.exists() else {}
    todo = sorted({f"{p}|{d}" for p, d in wanted} - set(have))

    def one(key):
        p, d = key.split("|")
        blob = _get(f"https://data.binance.vision/data/futures/um/daily/metrics/{p}/{p}-metrics-{d}.zip")
        if not blob:
            return key, None
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            return key, parse_metrics(zf.read(zf.namelist()[0]).decode())
    with ThreadPoolExecutor(8) as ex:
        for k, v in ex.map(one, todo):
            have[k] = v
    if todo:
        path.write_text(json.dumps(have))
    return have


# ---------------------------------------------------------------------------------------------------------- layers
def _ds(day: int) -> str:
    return (datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(days=int(day))).strftime("%Y-%m-%d")


def coin_z(close: np.ndarray) -> np.ndarray:
    from engines.rcce_engine import _calc_zscore_hybrid, LEN_LONG, LEN_REGRESSION
    z = _calc_zscore_hybrid(np.asarray(close, dtype=float), LEN_LONG, LEN_REGRESSION)
    z[: 2 * LEN_LONG - 1] = np.nan                                 # the engine's warm-up
    return z


def btc_above(series: Dict[str, dict]) -> Dict[int, bool]:
    s = series["BTC"]
    mid = band_mid(s["days"], s["close"])
    return {int(d): bool(c > m) for d, c, m in zip(s["days"], s["close"], mid) if np.isfinite(m)}


def layer_values(series: Dict[str, dict], marks: Dict[str, List[dict]], fetch: bool = True) -> Dict[str, dict]:
    """Every layer's value at every counted mark: {kind: [ {layer: value or None} per mark ]} plus data digests."""
    seeds = seed_layers()
    fg = fear_greed()
    btc = btc_above(series)
    z = {c: coin_z(series[c]["close"]) for c in {r["coin"] for rows in marks.values() for r in rows}}
    pairs = sorted({r["coin"] for rows in marks.values() for r in rows})
    fund = {c: funding(f"{c}USDT") for c in pairs} if fetch else {}
    want = []
    for rows in marks.values():
        for r in rows:
            d = int(series[r["coin"]]["days"][r["t"]])
            want += [(f"{r['coin']}USDT", _ds(d)), (f"{r['coin']}USDT", _ds(d - OI_DAYS))]
    mp = metrics_points(want) if fetch else {}
    out = {}
    for kind, rows in marks.items():
        vals = []
        for r in rows:
            c, t = r["coin"], r["t"]
            d = int(series[c]["days"][t])
            now = mp.get(f"{c}USDT|{_ds(d)}")
            then = mp.get(f"{c}USDT|{_ds(d - OI_DAYS)}")
            oi = math.log(now[0] / then[0]) if now and then and now[0] and then[0] else None
            zz = z[c][t]
            v = {"breadth": seeds["breadth"].get(d), "market_stretch": seeds["market_stretch"].get(d),
                 "market_z": seeds["market_z"].get(d), "fear_greed": fg.get(d),
                 "btc_band": (1.0 if btc[d] else 0.0) if d in btc else None,
                 "coin_z": float(zz) if np.isfinite(zz) else None,
                 "funding": funding_at(fund.get(c, np.zeros((0, 3))), d),
                 "oi_change": oi, "top_traders": now[1] if now else None, "accounts": now[2] if now else None,
                 "traders_long": seeds["traders_long"].get(d), "smart_long": seeds["smart_long"].get(d),
                 "whales_long": seeds["whales_long"].get(d)}
            vals.append(v)
        out[kind] = vals
    h = hashlib.sha256()
    h.update(json.dumps(sorted(fg.items())).encode())
    for c in sorted(fund):
        h.update(c.encode()); h.update(np.round(fund[c], 12).tobytes())
    h.update(json.dumps({k: mp[k] for k in sorted(mp)}).encode())
    return {"values": out, "sha256_layers": h.hexdigest()}


# ---------------------------------------------------------------------------------------------------------- the test
def split(rows: List[dict], vals: List[dict], layer: str, how: str):
    """The marks with a value, cut into (high, low, cut): binary on 1/0; otherwise at the median of those values."""
    have = [(r, v[layer]) for r, v in zip(rows, vals) if v.get(layer) is not None]
    if not have:
        return [], [], None
    cut = 0.5 if how == "binary" else float(np.median([x for _, x in have]))
    return [r for r, x in have if x >= cut], [r for r, x in have if x < cut], cut


def _parts(rows: List[dict], pt: Dict[str, List[str]]) -> Dict[str, List[dict]]:
    return {"calibration": [r for r in rows if r["coin"] in pt["calibration"]],
            "test": [r for r in rows if r["coin"] in pt["test"]],
            "to 2021": [r for r in rows if r["era"] == "to 2021"],
            "from 2022": [r for r in rows if r["era"] == "from 2022"]}


def judge(rows: List[dict], vals: List[dict], layer: str, how: str, judged: bool, days_by_coin, side: int,
          pt: Dict[str, List[str]]) -> dict:
    """One mark and one layer: the two groups against chance, and the bar for each group."""
    hi, lo, cut = split(rows, vals, layer, how)
    with_value = hi + lo
    coverage = len(with_value) / len(rows) if rows else 0.0
    base = M.summarize(with_value, days_by_coin, side)
    res = {"cut": cut, "coverage": coverage, "with_value": base, "judged": bool(judged and coverage >= COVERAGE)}
    groups = {"high": hi, "low": lo}
    for g, mine in groups.items():
        other = groups["low" if g == "high" else "high"]
        s = M.summarize(mine, days_by_coin, side)
        p_mine, p_other = _parts(mine, pt), _parts(other, pt)
        each = {}
        for k in p_mine:
            a = M.summarize(p_mine[k], days_by_coin, side)
            b = M.summarize(p_other[k], days_by_coin, side)
            each[k] = bool(a["marks"] >= BAR_PART and b["marks"] >= BAR_PART and a["margin"] is not None
                           and b["margin"] is not None and a["margin"] > b["margin"])
        enough = s["marks"] >= BAR_GROUP
        gain = s["margin"] is not None and base["margin"] is not None and s["margin"] >= base["margin"] + BAR_GAIN - 1e-12
        res[g] = {**s, "bar": {"enough": enough, "gain": gain, "parts": each,
                               "met": bool(res["judged"] and enough and gain and all(each.values()))}}
    return res


# ---------------------------------------------------------------------------------------------------------- runs
def _setup():
    series = M.load_all()
    pt = M.parts()
    unseen = [c for c in pt["calibration"] + pt["test"] if c in series]
    m = {c: M.model(s["days"], s["high"], s["low"], s["close"]) for c, s in series.items() if c in unseen}
    marks, days_by_coin = M.collect(series, unseen, m)
    marks = {k: v for k, v in marks.items() if k in M.KINDS}
    return series, pt, marks, days_by_coin


def check() -> dict:
    """Coverage of each layer on each kind's counted marks, the medians the marks would be cut at, and the layers'
    data digest. No outcome is read."""
    series, pt, marks, _ = _setup()
    lv = layer_values(series, marks)
    cov = {}
    for kind, rows in marks.items():
        vals = lv["values"][kind]
        cov[kind] = {"marks": len(rows)}
        for key, _, how, judged in LAYERS:
            x = [v[key] for v in vals if v[key] is not None]
            cov[kind][key] = {"with_value": len(x), "share": round(len(x) / len(rows), 3) if rows else None,
                              "cut": (0.5 if how == "binary" else round(float(np.median(x)), 6)) if x else None,
                              "judged": bool(judged and rows and len(x) / len(rows) >= COVERAGE)}
    return {"sha256_prices": M.digest(series), "sha256_layers": lv["sha256_layers"], "coverage": cov}


def run() -> dict:
    series, pt, marks, days_by_coin = _setup()
    lv = layer_values(series, marks)
    out = {"sha256_prices": M.digest(series), "sha256_layers": lv["sha256_layers"], "kinds": {}}
    for kind, rows in marks.items():
        name, side = M.KINDS[kind]
        vals = lv["values"][kind]
        entry = {"name": name, "side": side, "all": M.summarize(rows, days_by_coin, side), "layers": {}}
        for key, lname, how, judged in LAYERS:
            entry["layers"][key] = {"name": lname, **judge(rows, vals, key, how, judged, days_by_coin, side, pt)}
        out["kinds"][kind] = entry
    out["passed"] = [(k, l, g) for k, e in out["kinds"].items() for l, r in e["layers"].items()
                     for g in ("high", "low") if r[g]["bar"]["met"]]
    return out


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("check", "run"))
    args = ap.parse_args(argv)
    out = check() if args.cmd == "check" else run()
    json.dump(out, sys.stdout, indent=1, default=lambda v: None if isinstance(v, float) and math.isnan(v) else v)
    print()


if __name__ == "__main__":
    main()
