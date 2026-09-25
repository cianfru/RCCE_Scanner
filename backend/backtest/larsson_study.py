"""
Larsson-process walk-forward study (shadow research). Run from ``backend/``:

    python -m backtest.larsson_study --out run1                  # windows 1-9 + full grid
    python -m backtest.larsson_study --out hold --holdout --frozen frozen.json   # once, ever

Compares benchmarks B0-B3 with variants L1-L5 over frozen 180-day windows on
Binance spot daily data, fresh capital per window, with the same costs.

  B0  equal-weight buy & hold of the symbols tradable at the window start
  B1  current RCCE baseline: replay_engine + PositionManager at 1D, unmodified
      rules, with the study's costs and completed-week BMSB/weekly inputs
  B2  cto_engine ("CTO Line Advanced") up state through L1 mechanics
  B3  B1 with RCCE longs vetoed while the Larsson ribbon is blue
  L1-L5  see backtest/larsson_manager.py

Windows are frozen: ten 180-day windows ending at the last complete daily bar
of the freeze date. Window 10 is the holdout. A normal run loads data only up
to the end of window 9, so nothing from the holdout period can leak into the
results or the parameter choice. ``--holdout`` refuses to run twice (a marker
is written on first use) and refuses to overwrite an output directory.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import itertools
import json
import logging
import math
import pickle
import statistics
import sys
import time
import urllib.request
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from backtest import binance_history as bh
from backtest.larsson_manager import DayBar, LarssonManager, ManagerConfig
from engines.larsson_engine import LARSSON_VERSION, READY_BARS, compute_larsson_series
from engines.levels_engine import LEVELS_VERSION, LevelConfig, compute_levels

logger = logging.getLogger("larsson_study")

STUDY_VERSION = "larsson-study-1"
DAY_MS = 86_400_000
DATA_START = "2019-01-01"
FREEZE_END = "2026-09-25"          # exclusive: the last complete daily bar at freeze opens 2026-09-24
N_WINDOWS, WINDOW_DAYS, HOLDOUT = 10, 180, 10
INITIAL_CAPITAL = 10_000.0
FEE_BPS, SLIP_BPS = 5.0, 5.0
PRIMARY = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "DOGE", "DOT", "LINK"]   # DEFAULT_BACKTEST_SYMBOLS
GRID = {"risk_pct": (0.005, 0.01, 0.02), "tol": (0.01, 0.015), "max_last": (30, 60), "b": (0.01, 0.015)}
DECLARED = {"risk_pct": 0.01, "tol": 0.015, "max_last": 30, "b": 0.01}
L_VARIANTS = ("L1", "L2", "L3", "L4", "L5")
STRATEGIES = ("B0", "B1", "B2", "B3") + L_VARIANTS
RUNS_DIR = Path(__file__).resolve().parent.parent / "data" / "larsson_runs"
HOLDOUT_MARKER = RUNS_DIR / f".{STUDY_VERSION}-holdout-used"


def _ms(date: str) -> int:
    return int(datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)


def _date(ms: float) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def windows() -> List[dict]:
    end = _ms(FREEZE_END)
    out = []
    for k in range(1, N_WINDOWS + 1):
        start = end - (N_WINDOWS - k + 1) * WINDOW_DAYS * DAY_MS
        out.append({"index": k, "start_ms": start, "end_ms": start + WINDOW_DAYS * DAY_MS,
                    "start": _date(start), "end": _date(start + WINDOW_DAYS * DAY_MS), "holdout": k == HOLDOUT})
    return out


# ---------------------------------------------------------------------------------------------- data

@dataclass
class SymbolData:
    sym: str
    usd: Dict[str, np.ndarray]
    pair: Optional[Dict[str, np.ndarray]]
    pair_synthetic: bool
    ll: dict
    cto_up: np.ndarray
    is_alt: np.ndarray
    index: Dict[float, int]


def _cto_up(d) -> np.ndarray:
    from engines.cto_engine import compute_cto_series, COLOR_STRONG_UP, COLOR_WEAK_UP
    s = compute_cto_series(d["high"], d["low"], d["close"], d["timestamp"])
    up = {p["time"] * 1000.0 for p in s["cto_fast"] if p["color"] in (COLOR_STRONG_UP, COLOR_WEAK_UP)}
    return np.array([t in up for t in d["timestamp"]])


def _alt_flags(d, btc) -> np.ndarray:
    """90-day correlation of daily returns with BTC above 0.6, from bars <= i."""
    idx = {t: i for i, t in enumerate(btc["timestamp"])}
    r = np.diff(np.log(d["close"]), prepend=np.nan)
    rb_full = np.diff(np.log(btc["close"]), prepend=np.nan)
    rb = np.array([rb_full[idx[t]] if t in idx else np.nan for t in d["timestamp"]])
    out = np.zeros(len(r), dtype=bool)
    for i in range(91, len(r)):
        a, b = r[i - 89:i + 1], rb[i - 89:i + 1]
        ok = np.isfinite(a) & np.isfinite(b)
        if ok.sum() >= 60 and np.std(a[ok]) > 0 and np.std(b[ok]) > 0:
            out[i] = np.corrcoef(a[ok], b[ok])[0, 1] > 0.6
    return out


def _synth_pair(d, btc) -> Dict[str, np.ndarray]:
    idx = {t: i for i, t in enumerate(btc["timestamp"])}
    keep = np.array([t in idx for t in d["timestamp"]])
    j = np.array([idx[t] for t in d["timestamp"][keep]])
    o, c = d["open"][keep] / btc["open"][j], d["close"][keep] / btc["close"][j]
    return {"timestamp": d["timestamp"][keep], "open": o, "close": c,
            "high": np.maximum(o, c), "low": np.minimum(o, c), "volume": d["volume"][keep]}


def load_universe(symbols: List[str], data_end: str) -> Dict[str, SymbolData]:
    btc = bh.load("BTCUSDT", "1d", DATA_START, data_end)
    out = {}
    for sym in symbols:
        d = btc if sym == "BTC" else bh.load(f"{sym}USDT", "1d", DATA_START, data_end)
        if d is None or len(d["close"]) < READY_BARS:
            logger.warning("Skipping %s: insufficient history", sym)
            continue
        pair, synthetic = None, False
        if sym != "BTC":
            try:
                pair = bh.load(f"{sym}BTC", "1d", DATA_START, data_end)
            except Exception:
                pair = None
            if pair is None or len(pair["close"]) < 100:
                pair, synthetic = _synth_pair(d, btc), True
        out[sym] = SymbolData(sym=sym, usd=d, pair=pair, pair_synthetic=synthetic,
                              ll=compute_larsson_series(d["close"], d["timestamp"]), cto_up=_cto_up(d),
                              is_alt=np.zeros(len(d["close"]), bool) if sym == "BTC" else _alt_flags(d, btc),
                              index={t: i for i, t in enumerate(d["timestamp"])})
    return out


_LEVEL_CACHE: Dict[tuple, list] = {}


def levels_for(sd: SymbolData, tol: float, max_last: int, b: float, chart: str = "usd"):
    key = (sd.sym, chart, tol, max_last, b)
    if key not in _LEVEL_CACHE:
        data = sd.usd if chart == "usd" else sd.pair
        states = sd.ll["state"] if chart == "usd" else None
        _LEVEL_CACHE[key] = compute_levels(data, LevelConfig(tol=tol, max_last=max_last, b=b), states)
    return _LEVEL_CACHE[key]


# ---------------------------------------------------------------------------------------------- RCCE baseline

def _fear_greed() -> Dict[str, int]:
    try:
        raw = json.loads(urllib.request.urlopen("https://api.alternative.me/fng/?limit=0&format=json", timeout=30).read())
        return {_date(int(x["timestamp"]) * 1000): int(x["value"]) for x in raw["data"]}
    except Exception as exc:                                    # neutral 50 is the replay's own default
        logger.warning("Fear & Greed history unavailable (%s); replay uses 50", exc)
        return {}


def _weekly_completed(sym: str, data_end: str) -> Optional[dict]:
    """Weekly bars keyed by their final day's open, so a week is visible only once complete."""
    w = bh.load(f"{sym}USDT", "1w", "2017-08-14", data_end)
    if w is None:
        return None
    w = dict(w)
    w["timestamp"] = w["timestamp"] + 6 * DAY_MS
    return w


def rcce_replay(data: Dict[str, SymbolData], data_end: str, cache_dir: Path) -> dict:
    """Replay the RCCE pipeline once over the whole period (cached). Keys: (sym, ts)."""
    tag = hashlib.sha1(json.dumps([sorted(data), data_end, DATA_START]).encode()).hexdigest()[:12]
    path = cache_dir / f"rcce_replay_{tag}.pkl"
    if path.exists():
        with path.open("rb") as fh:
            return pickle.load(fh)
    from backtest.replay_engine import run_replay
    start = _ms("2020-05-01")               # 500-bar rolling engine window is full by the first window
    daily = {f"{s}/USDT": {k: v[sd.usd["timestamp"] >= start] for k, v in sd.usd.items()} for s, sd in data.items()}
    weekly = {f"{s}/USDT": w for s in data if (w := _weekly_completed(s, data_end)) is not None}
    t0 = time.time()
    res = asyncio.run(run_replay(list(daily), daily, {}, weekly, _fear_greed(), warmup_bars=150))
    logger.info("RCCE replay: %d bar results in %.0fs", len(res), time.time() - t0)
    out = {"bars": {(r.symbol.split("/")[0], r.timestamp): r for r in res}, "weekly_btc": weekly.get("BTC/USDT")}
    cache_dir.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        pickle.dump(out, fh)
    return out


# backtest.runner's BMSB helpers, reproduced verbatim in behaviour: on main, importing
# backtest.runner fails (data_loader imports data_fetcher._create_exchange, which is not
# defined there). Fed completed-week timestamps, the lookup sees only finished weeks.
def _compute_bmsb_filter(weekly: dict, consecutive_weeks: int = 2) -> Dict[float, bool]:
    close = np.asarray(weekly["close"], dtype=np.float64)
    ts = [float(t) for t in weekly["timestamp"]]
    n = len(close)
    if n < 21:
        return {}
    sma20 = np.full(n, np.nan)
    for i in range(19, n):
        sma20[i] = close[i - 19:i + 1].mean()
    ema21 = np.full(n, np.nan)
    ema21[20] = close[:21].mean()
    for i in range(21, n):
        ema21[i] = 2 / 22 * close[i] + (1 - 2 / 22) * ema21[i - 1]
    mid = (sma20 + ema21) / 2
    out, below = {}, 0
    for i in range(n):
        if np.isnan(mid[i]):
            out[ts[i]] = False
            continue
        below = below + 1 if close[i] < mid[i] else 0
        out[ts[i]] = below >= consecutive_weeks
    return out


def _is_bmsb_blocked(bmsb_map: Dict[float, bool], weekly_ts: List[float], ts: float) -> bool:
    import bisect
    idx = bisect.bisect_right(weekly_ts, ts) - 1
    return bmsb_map.get(weekly_ts[idx], False) if idx >= 0 else False


def _bmsb(replay) -> tuple:
    w = replay.get("weekly_btc")
    m = _compute_bmsb_filter(w) if w is not None else {}
    return m, sorted(m)


# ---------------------------------------------------------------------------------------------- strategies

def _days(win, data) -> List[float]:
    btc = data["BTC"].usd["timestamp"]
    return [float(t) for t in btc if win["start_ms"] <= t < win["end_ms"]]


def run_larsson(variant: str, params: dict, win: dict, data: Dict[str, SymbolData], replay=None, bmsb=None):
    cfg = ManagerConfig(variant=variant, risk_pct=params["risk_pct"], fee_bps=FEE_BPS, slip_bps=SLIP_BPS)
    syms = [s for s in data]
    mgr = LarssonManager(INITIAL_CAPITAL, syms, cfg)
    lv = {s: levels_for(data[s], params["tol"], params["max_last"], params["b"]) for s in syms}
    seen = set()
    days = _days(win, data)
    for ts in days:
        bars = {}
        for s in syms:
            sd = data[s]
            i = sd.index.get(ts)
            if i is None or i < READY_BARS:
                continue
            u, ll = sd.usd, sd.ll
            if variant == "B2":
                up = bool(sd.cto_up[i])
                trend, lat = ("gold" if up else "blue"), ("gold" if up else "blue")
                flip = trend if i > 0 and bool(sd.cto_up[i - 1]) != up else None
                gag = False
            else:
                trend, lat, flip, gag = ll["state"][i], ll["last_actionable"][i], ll["flip"][i], ll["grey_after_gold"][i]
            gate = True
            if variant == "L5" and replay is not None:
                r = replay["bars"].get((s, ts))
                gate = not _is_bmsb_blocked(bmsb[0], bmsb[1], ts) and not (r is not None and r.signal == "RISK_OFF")
            bl = lv[s][i]
            bars[s] = DayBar(symbol=s, timestamp=ts, open=u["open"][i], high=u["high"][i], low=u["low"][i],
                             close=u["close"][i], trend=trend, last_actionable=lat, flip=flip, grey_after_gold=gag,
                             events=bl.events, sr_levels=bl.sr_levels, range_state=bl.range_state,
                             prev_range_state=lv[s][i - 1].range_state, gate_ok=gate, is_alt=bool(sd.is_alt[i]),
                             first_bar=s not in seen)
            seen.add(s)
        if bars:
            mgr.process_day(ts, bars)
    if days:
        mgr.close_all_at_end(days[-1])
        mgr.equity_curve[-1] = (days[-1], mgr.get_equity())
    trades = [dict(symbol=t.symbol, pnl=t.pnl_usd, r=t.r_multiple, bars=t.bars_held, exit=t.exit_reason) for t in mgr.trades]
    return mgr.equity_curve, [x for _, x in mgr.exposure_curve], trades


def run_b0(win, data):
    days = _days(win, data)
    rate = (FEE_BPS + SLIP_BPS) / 10_000.0
    first = days[0]
    held = [s for s, sd in data.items() if first in sd.index]
    qty = {s: INITIAL_CAPITAL / len(held) * (1 - rate) / data[s].usd["open"][data[s].index[first]] for s in held}
    curve, last = [], {}
    for ts in days:
        for s in held:
            i = data[s].index.get(ts)
            if i is not None:
                last[s] = data[s].usd["close"][i]
        curve.append((ts, sum(qty[s] * last[s] for s in held)))
    curve[-1] = (days[-1], curve[-1][1] * (1 - rate))
    trades = [dict(symbol=s, pnl=qty[s] * last[s] * (1 - rate) - INITIAL_CAPITAL / len(held), r=None, bars=len(days), exit="end")
              for s in held]
    return curve, [1.0] * len(days), trades


def run_b1(win, data, replay, bmsb, veto_blue=False):
    from backtest.position_manager import PositionManager
    rate = (FEE_BPS + SLIP_BPS) / 10_000.0

    class CostedPM(PositionManager):
        def _open_position(self, sym, bar, confluence):
            before = self.cash
            out = super()._open_position(sym, bar, confluence)
            self.cash -= (before - self.cash) * rate
            return out

        def _add_to_position(self, sym, bar, confluence):
            before = self.cash
            out = super()._add_to_position(sym, bar, confluence)
            self.cash -= (before - self.cash) * rate
            return out

        def _close_position(self, sym, timestamp, price, exit_signal, close_pct=1.0):
            before = self.cash
            t = super()._close_position(sym, timestamp, price, exit_signal, close_pct)
            fee = (self.cash - before) * rate
            self.cash -= fee
            if t is not None:
                t.pnl_usd -= fee
            return t

    syms = [f"{s}/USDT" for s in data]
    pm = CostedPM(INITIAL_CAPITAL, syms)
    days = _days(win, data)
    exposure = []
    for ts in days:
        bars = [replay["bars"][(s, ts)] for s in data if (s, ts) in replay["bars"]]
        blocked = _is_bmsb_blocked(bmsb[0], bmsb[1], ts)
        for bar in bars:
            s = bar.symbol.split("/")[0]
            veto = False
            if veto_blue:
                i = data[s].index.get(ts)
                veto = i is not None and data[s].ll["state"][i] == "blue"
            pm.macro_blocked = blocked or veto
            pm.process_bar(bar)
        pm.mark_to_market(ts, {b.symbol: b.price for b in bars})
        value = sum(pm.per_symbol_alloc * p.size_pct * pm._latest_prices.get(sym, p.entry_price) / p.entry_price
                    for sym, p in pm.positions.items() if p.entry_price > 0)
        exposure.append(value / pm.equity_curve[-1][1] if pm.equity_curve[-1][1] > 0 else 0.0)
    pm.close_all_at_end(days[-1])
    pm.equity_curve[-1] = (days[-1], pm.get_equity())
    trades = [dict(symbol=t.symbol.split("/")[0], pnl=t.pnl_usd, r=None, bars=t.bars_held, exit=t.exit_signal) for t in pm.trades]
    return pm.equity_curve, exposure, trades


# ---------------------------------------------------------------------------------------------- metrics

def metrics(curve, exposure, trades, days: int) -> dict:
    eq = np.array([INITIAL_CAPITAL] + [e for _, e in curve], dtype=float)
    r = eq[1:] / eq[:-1] - 1
    total = eq[-1] / eq[0] - 1
    sd = r.std()
    down = math.sqrt(np.mean(np.minimum(r, 0) ** 2)) if len(r) else 0.0
    peak = np.maximum.accumulate(eq)
    months: Dict[str, List[float]] = {}
    for (ts, e) in curve:
        months.setdefault(_date(ts)[:7], []).append(e)
    month_ret, prev = [], INITIAL_CAPITAL
    for k in sorted(months):
        month_ret.append(months[k][-1] / prev - 1)
        prev = months[k][-1]
    wins = [t["pnl"] for t in trades if t["pnl"] > 0]
    losses = [t["pnl"] for t in trades if t["pnl"] <= 0]
    rs = [t["r"] for t in trades if t.get("r") is not None]
    avg_exp = float(np.mean(exposure)) if len(exposure) else 0.0
    return {
        "total_return_pct": total * 100,
        "cagr_pct": ((1 + total) ** (365 / days) - 1) * 100 if total > -1 else -100.0,
        "sharpe": float(r.mean() / sd * math.sqrt(365)) if sd > 0 else 0.0,
        "sortino": float(r.mean() / down * math.sqrt(365)) if down > 0 else 0.0,
        "max_dd_pct": float(((eq - peak) / peak).min() * 100),
        "time_in_market_pct": float(np.mean([x > 0 for x in exposure]) * 100) if len(exposure) else 0.0,
        "trades": len(trades),
        "trades_per_year": len(trades) / (days / 365),
        "avg_hold_bars": float(np.mean([t["bars"] for t in trades])) if trades else 0.0,
        "win_rate_pct": len(wins) / len(trades) * 100 if trades else 0.0,
        "payoff": (np.mean(wins) / abs(np.mean(losses))) if wins and losses and np.mean(losses) != 0 else None,
        "expectancy_r": float(np.mean(rs)) if rs else None,
        "worst_month_pct": min(month_ret) * 100 if month_ret else 0.0,
        "avg_exposure_pct": avg_exp * 100,
        "exposure_adj_return_pct": total / avg_exp * 100 if avg_exp > 0 else None,
    }


# ---------------------------------------------------------------------------------------------- study

def _grid():
    keys = list(GRID)
    return [dict(zip(keys, v)) for v in itertools.product(*(GRID[k] for k in keys))]


def _pkey(p):
    return f"risk{p['risk_pct']}_tol{p['tol']}_last{p['max_last']}_b{p['b']}"


def study(window_ids, symbols, out_dir: Path, *, grid: bool = True, frozen: Optional[dict] = None) -> dict:
    wins = [w for w in windows() if w["index"] in window_ids]
    # Outside the holdout, never load data past window 9's end (shared replay cache too).
    data_end = FREEZE_END if HOLDOUT in window_ids else windows()[HOLDOUT - 2]["end"]
    data = load_universe(symbols, data_end)
    # A subset of the primary universe (e.g. the single-asset check) reuses the primary
    # replay: RCCE consensus is computed across the scanned set, as in production.
    replay_data = load_universe(PRIMARY, data_end) if set(data) < set(PRIMARY) else data
    replay = rcce_replay(replay_data, data_end, RUNS_DIR / "cache")
    bmsb = _bmsb(replay)
    configs = [frozen] if frozen else (_grid() if grid else [DECLARED])
    rows, trades_out = [], {}
    for w in wins:
        days = len(_days(w, data))
        base = {"B0": run_b0(w, data), "B1": run_b1(w, data, replay, bmsb), "B3": run_b1(w, data, replay, bmsb, veto_blue=True)}
        for name, (curve, exp, tr) in base.items():
            rows.append(dict(window=w["index"], strategy=name, params="-", **metrics(curve, exp, tr, days)))
            trades_out[(w["index"], name, "-")] = tr
        for p in configs:
            for name in ("B2",) + L_VARIANTS:
                curve, exp, tr = run_larsson(name, p, w, data, replay, bmsb)
                rows.append(dict(window=w["index"], strategy=name, params=_pkey(p), **metrics(curve, exp, tr, days)))
                trades_out[(w["index"], name, _pkey(p))] = tr
        logger.info("window %d done", w["index"])
    report = {
        "version": STUDY_VERSION, "engines": {"larsson": LARSSON_VERSION, "levels": LEVELS_VERSION},
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "windows": wins, "symbols": list(data), "data_end": data_end, "declared": DECLARED, "grid": GRID,
        "costs_bps_per_side": FEE_BPS + SLIP_BPS, "rows": rows,
        "pair_charts": {s: ("synthetic ALT/USDT / BTC/USDT" if sd.pair_synthetic else "Binance ALTBTC") for s, sd in data.items() if s != "BTC"},
    }
    out_dir.mkdir(parents=True, exist_ok=False)
    (out_dir / "report.json").write_text(json.dumps(report, indent=1, default=float))
    with (out_dir / "results.csv").open("w", newline="") as fh:
        w_ = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w_.writeheader()
        w_.writerows(rows)
    with (out_dir / "trades.json").open("w") as fh:
        json.dump({"|".join(map(str, k)): v for k, v in trades_out.items()}, fh, default=float)
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="run name; written under backend/data/larsson_runs/")
    ap.add_argument("--windows", default="1-9", help="walk-forward windows to run (holdout excluded)")
    ap.add_argument("--no-grid", action="store_true", help="declared parameters only")
    ap.add_argument("--params", type=json.loads, help="one fixed parameter set (JSON), e.g. for the single-asset check")
    ap.add_argument("--symbols", default=",".join(PRIMARY))
    ap.add_argument("--holdout", action="store_true", help="run the frozen holdout window once")
    ap.add_argument("--frozen", type=Path, help="parameters selected before the holdout (JSON)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    out = RUNS_DIR / args.out
    if out.exists():
        ap.error(f"{out} exists; results are never overwritten")
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if args.holdout:
        if HOLDOUT_MARKER.exists():
            ap.error(f"The holdout was already used ({HOLDOUT_MARKER.read_text().strip()}). A rerun is not an untouched test.")
        if not args.frozen:
            ap.error("--holdout needs --frozen parameters chosen from windows 1-9")
        frozen = json.loads(args.frozen.read_text())
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        HOLDOUT_MARKER.write_text(f"{datetime.now(timezone.utc).isoformat()} params={json.dumps(frozen)}\n")
        study([HOLDOUT], symbols, out, frozen=frozen)
        return
    lo, hi = (int(x) for x in args.windows.split("-")) if "-" in args.windows else (int(args.windows),) * 2
    ids = list(range(lo, hi + 1))
    if HOLDOUT in ids:
        ap.error("Window 10 is the holdout; use --holdout with --frozen parameters")
    study(ids, symbols, out, grid=not args.no_grid, frozen=args.params)


if __name__ == "__main__":
    main()
