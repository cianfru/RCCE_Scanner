"""
Past paths for the market history drawer (declared in docs/reviews/market-paths-method.md): the seed's
aggregates and the walk-forward check, computed from the local rebuild cache.

    python -m backtest.market_paths calibrate        (from backend/: run the declared check, write it into the seed)

The seed gets derived aggregates only (backtest.breadth_history.export calls these):
  alt_paths   the typical alt's whole-% change from each day (1 May 2021 to END_DAY - 60) to 5, 10 ... 60 days on
  base_path   the ordinary path: medians over the study window, as the seed's `base`
  fan_check   the walk-forward check's counts
Per-coin closes stay in the gitignored cache. The fan itself (analogs, quantiles) is market_history.fan, shared
with the live view.
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Dict, List, Optional

import market_history as mh
from backtest.larsson_study import RUNS_DIR

END_DAY = 20541                    # 2026-03-29: the study's end day (backtest.breadth_history.END_DAY)
FIRST_DAY = 18748                  # 2021-05-01: first day with 40+ coins
MIN_COINS = 40
SEED = Path(__file__).resolve().parent.parent / "seeds" / "market_history_seed.json"


def _alt(closes: Dict[str, Dict[str, float]], t: int, e: int) -> Optional[float]:
    """Median simple return of coins other than BTC with closes on both days (20+), as a fraction."""
    rs = [c[str(e)] / c[str(t)] - 1 for p, c in closes.items()
          if p != "BTCUSDT" and str(t) in c and str(e) in c and c[str(t)] > 0]
    return statistics.median(rs) if len(rs) >= mh.MIN_ALTS else None


def alt_paths(closes: Dict[str, Dict[str, float]], first: int = FIRST_DAY, last: int = END_DAY - 60) -> dict:
    """Row i: the typical alt's change (whole %) from day first + i to each of ALT_PATHS_K days on; None if fewer
    than 20 alts have both closes."""
    rows = []
    for t in range(first, last + 1):
        row = []
        for k in mh.ALT_PATHS_K:
            a = _alt(closes, t, t + k)
            row.append(None if a is None else int(round(100 * a)))
        rows.append(row)
    return {"from": first, "k": list(mh.ALT_PATHS_K), "rows": rows}


def base_path(data: dict) -> dict:
    """The ordinary path at every knot: medians over the study's days (40+ coins, up to END_DAY) whose window closes
    by END_DAY and has BTC and 20+ alts, exactly as backtest.breadth_history.study's `base` (1 dp)."""
    closes = data["closes"]
    btc = closes["BTCUSDT"]
    studied = [d["day"] for d in data["days"] if d["n"] >= MIN_COINS and d["day"] <= END_DAY]
    out = {"k": list(mh.FAN_K), "btc": [], "alt": []}
    for k in mh.FAN_K:
        b, a = [], []
        for t in studied:
            e = t + k
            if e > END_DAY or str(t) not in btc or str(e) not in btc:
                continue
            x = _alt(closes, t, e)
            if x is None:
                continue
            b.append(btc[str(e)] / btc[str(t)] - 1)
            a.append(x)
        out["btc"].append(round(100 * statistics.median(b), 1) + 0.0)
        out["alt"].append(round(100 * statistics.median(a), 1) + 0.0)
    return out


def recent_closes(closes: Dict[str, Dict[str, float]], after: int) -> Dict[int, Dict[str, float]]:
    """Per-day closes for days after `after`, in the live file's shape ({day: {pair: close}})."""
    out: Dict[int, Dict[str, float]] = {}
    for p, c in closes.items():
        for d, v in c.items():
            if int(d) > after:
                out.setdefault(int(d), {})[p] = v
    return out


def history(src: str = "breadth_history"):
    """(days rows in the seed's shape, cache closes) from the local rebuild."""
    data = json.loads((RUNS_DIR / f"{src}.json").read_text())
    btc = data["closes"]["BTCUSDT"]
    rows = [[d["day"], d["n"], d["uptrend"], d["overheated"], d["downtrend"], d["basing"], d["median_z"],
             btc.get(str(d["day"]))] for d in data["days"]]
    return data, rows


def calibrate(data: dict, rows: List[list], paths: dict, bands_def, detail: bool = False) -> dict:
    """The declared walk-forward check over the whole cache, with the live alt_ret: the seed's alt_paths for
    origins up to END_DAY - 60, per-coin closes after (as production's _closes)."""
    band = mh.btc_band(rows)                                       # every day, as view() computes it
    days = [r for r in rows if r[1] >= MIN_COINS]
    alt_ret = mh.make_alt_ret(paths, recent_closes(data["closes"], paths["from"] + len(paths["rows"]) - 1))
    return mh.fan_check(days, band, alt_ret, days[-1][0], bands_def, detail=detail)


def table(check: dict) -> str:
    lines = [f"fan_check through {check['through']}: {check['tested']} of {check['of']} episodes with a fan "
             f"({check['runs']} runs), {check['scored']} scored with quantiles ({check['scored_runs']} runs), "
             f"untested={check['untested']}, median_vs_all={check['median_vs_all']}",
             "series   h   middle half (hits/n, Wilson 90%)     10-90 (hits/n, Wilson 90%)      MAE fan / all   pass"]
    from backtest.risk_on_cycles import wilson
    for s, v in check["series"].items():
        for h in ("30", "60"):
            m, o, n = v[h]
            ml, mhi = wilson(m, n)
            ol, ohi = wilson(o, n)
            fe, ae = check["mae"][s][h]
            lines.append(f"{s:8} {h:>3}  {m:>3}/{n:<3} {m / n:5.0%}  [{ml:.2f}, {mhi:.2f}]"
                         f"       {o:>3}/{n:<3} {o / n:5.0%}  [{ol:.2f}, {ohi:.2f}]"
                         f"      {fe:.4g} / {ae:.4g}   {v['pass']}" if n else f"{s:8} {h:>3}  no tests")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("calibrate", help="run the declared walk-forward check and write fan_check into the seed")
    c.add_argument("--src", default="breadth_history")
    c.add_argument("--dry", action="store_true", help="print only; leave the seed as it is")
    args = ap.parse_args(argv)
    seed = json.loads(SEED.read_text())
    data, rows = history(args.src)
    paths = seed.get("alt_paths") or alt_paths(data["closes"])
    check = calibrate(data, rows, paths, seed["bands_def"])
    print(table(check))
    print(json.dumps(check, separators=(",", ":")))
    if not args.dry:
        seed["fan_check"] = check
        SEED.write_text(json.dumps(seed, separators=(",", ":")))
        print(f"-> {SEED} ({SEED.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
