"""
Scenario search: RCCE entries x exit rules (declared in docs/reviews/larsson-study.md
before it was run). Windows 1-9 only; the holdout stays locked.

    python -m backtest.larsson_scenarios select-secondary          # pick the 30-coin set (pre-W1 volume)
    python -m backtest.larsson_scenarios replay --universe secondary
    python -m backtest.larsson_scenarios search --universe primary --out scen_primary
    python -m backtest.larsson_scenarios confirm --from scen_primary --universe secondary --out scen_secondary
    python -m backtest.larsson_scenarios continuous --from scen_primary --out scen_continuous

Entries, sizing, BMSB gate, costs and fills are B1's (replay_engine + PositionManager).
Each scenario changes only the entry veto and the exit rules.
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import logging
import math
import statistics
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from backtest import binance_history as bh
from backtest.larsson_study import (
    DAY_MS, HOLDOUT, INITIAL_CAPITAL, PRIMARY, RUNS_DIR, _bmsb, _costed_pm_class, _days, _ms,
    load_universe, metrics, rcce_replay, run_b1, windows,
)
from engines.levels_engine import wilder_atr

logger = logging.getLogger("larsson_scenarios")

SECONDARY_FILE = RUNS_DIR / "secondary_universe.json"
EXCLUDE = {"USDC", "TUSD", "PAX", "USDP", "BUSD", "DAI", "FDUSD", "USDS", "USDSB", "UST", "SUSD", "EUR", "GBP", "AUD",
           "TRY", "BRL", "RUB", "NGN", "UAH", "ZAR", "IDRT", "BIDR", "BVND", "WBTC", "WBETH", "BETH", "PAXG", "AEUR",
           "EURI", "XUSD", "USD1", "BFUSD", "BKRW", "USDE", "RLUSD"}


@dataclass(frozen=True)
class Scenario:
    veto: bool            # F1: skip entries while the ribbon is blue
    exit: str             # flip | grey | blue | e32 | atr3 | t30 | t60
    stop: Optional[float] # None | 0.12 | 0.08
    signals: bool         # RCCE exit signals on

    @property
    def name(self) -> str:
        return f"{'F1' if self.veto else 'F0'}-{self.exit}-{'nostop' if self.stop is None else f's{int(self.stop*100)}'}-{'sig' if self.signals else 'nosig'}"


H1 = Scenario(veto=False, exit="flip", stop=0.12, signals=False)


def family() -> List[Scenario]:
    out = []
    for veto in (False, True):
        exits = ("flip", "grey", "e32", "atr3", "t30", "t60") + (("blue",) if veto else ())
        for ex, stop, sig in itertools.product(exits, (None, 0.12, 0.08), (False, True)):
            out.append(Scenario(veto, ex, stop, sig))
    return out


# ------------------------------------------------------------------------------ manager

def scenario_pm_class(sc: Scenario):
    from backtest.position_manager import _ENTRY_SIGNALS, _EXIT_100_SIGNALS, _EXIT_ALL_SIGNAL
    base = _costed_pm_class()

    class ScenarioPM(base):
        ctx = None

        def set_context(self, sym, i, sd):
            self.ctx = (sym, i, sd)

        def process_bar(self, bar):
            sym, price, signal = bar.symbol, bar.price, bar.signal
            self._latest_prices[sym] = price
            if not hasattr(self, "_st"):
                self._st = {}
            _, i, sd = self.ctx
            state = sd.ll["state"][i] if i is not None else None
            if sym in self.positions:
                pos = self.positions[sym]
                pos.bars_held += 1
                st = self._st.setdefault(sym, {"gold": False, "above": False, "peak": price})
                st["peak"] = max(st["peak"], price)
                if state == "gold":
                    st["gold"] = True
                e32 = sd.ll["e32"][i] if i is not None else np.nan
                reason = None
                if sc.exit == "flip" and st["gold"] and state == "blue":
                    reason = "LL_FLIP"
                elif sc.exit == "grey" and st["gold"] and state in ("grey", "blue"):
                    reason = "LL_GREY"
                elif sc.exit == "blue" and state == "blue":
                    reason = "LL_BLUE"
                elif sc.exit == "e32" and np.isfinite(e32):
                    if price > e32:
                        st["above"] = True
                    elif st["above"]:
                        reason = "E32"
                elif sc.exit == "atr3" and i is not None:
                    atr = sd.atr[i]
                    if np.isfinite(atr) and price < st["peak"] - 3 * atr:
                        reason = "ATR3"
                elif sc.exit in ("t30", "t60") and pos.bars_held >= int(sc.exit[1:]):
                    reason = sc.exit.upper()
                if reason is None and sc.stop is not None and price <= pos.entry_price * (1 - sc.stop):
                    reason = f"STOP_{int(sc.stop * 100)}"
                if reason is None and sc.signals and signal in _EXIT_100_SIGNALS:
                    reason = signal
                if reason is not None:
                    self._st.pop(sym, None)
                    return self._close_position(sym, bar.timestamp, price, reason, close_pct=1.0)
            if sc.signals and signal == _EXIT_ALL_SIGNAL:
                for s in list(self.positions):
                    self._st.pop(s, None)
                trades = self._close_all(bar.timestamp, price_override=None, exit_signal=signal)
                return trades[-1] if trades else None
            # Entries: identical to PositionManager.process_bar
            if signal in _ENTRY_SIGNALS and not self.macro_blocked:
                if signal == "ACCUMULATE" and sym in self.positions:
                    return self._add_to_position(sym, bar, bar.confluence_label)
                if sym not in self.positions:
                    self._st[sym] = {"gold": state == "gold", "above": False, "peak": price}
                    return self._open_position(sym, bar, bar.confluence_label)
            return None

    return ScenarioPM


# ------------------------------------------------------------------------------ universe

def select_secondary(n: int = 30) -> List[str]:
    info = json.loads(bh._get("https://data-api.binance.vision/api/v3/exchangeInfo?permissions=SPOT"))
    w1 = _ms(windows()[0]["start"])
    cutoff = _ms("2020-02-01")
    cands = []
    for s in info["symbols"]:
        base = s["baseAsset"]
        if s["quoteAsset"] != "USDT" or base in EXCLUDE or base in PRIMARY:
            continue
        if base.endswith(("UP", "DOWN", "BULL", "BEAR")) and len(base) > 4:
            continue
        cands.append(s["symbol"])
    scored = []
    for sym in cands:
        try:
            first = json.loads(bh._get(f"{bh.API}?symbol={sym}&interval=1d&startTime=0&limit=1"))
            if not first or int(first[0][0]) > cutoff:
                continue
            rows = json.loads(bh._get(f"{bh.API}?symbol={sym}&interval=1d&startTime={w1 - 90 * DAY_MS}&endTime={w1 - 1}&limit=100"))
        except Exception:
            continue
        if len(rows) >= 80:
            scored.append((sum(float(r[7]) for r in rows), sym[:-4]))
    scored.sort(reverse=True)
    chosen = [b for _, b in scored[:n]]
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    SECONDARY_FILE.write_text(json.dumps({"rule": "top quote volume, 90 days before W1; listed before 2020-02",
                                          "candidates_scored": len(scored), "symbols": chosen,
                                          "volumes_usd": {b: v for v, b in scored[:n]}}, indent=1))
    return chosen


def universe(name: str) -> List[str]:
    if name == "primary":
        return list(PRIMARY)
    return json.loads(SECONDARY_FILE.read_text())["symbols"]


def _data_end() -> str:
    return windows()[HOLDOUT - 2]["end"]


def prepare(name: str):
    """Trading universe plus the RCCE replay. BTC and ETH always join the replay as
    references (timeline, beta, divergence, BMSB), but only the named universe trades."""
    data = load_universe(universe(name), _data_end())
    for sd in data.values():
        sd.atr = wilder_atr(sd.usd["high"], sd.usd["low"], sd.usd["close"])
    refs = [s for s in ("BTC", "ETH") if s not in data]
    replay_data = {**data, **load_universe(refs, _data_end())} if refs else data
    replay = rcce_replay(replay_data, _data_end(), RUNS_DIR / "cache")
    return data, replay, _bmsb(replay)


# ------------------------------------------------------------------------------ runs and statistics

def run_scenarios(scenarios, data, replay, bmsb, wins):
    """Returns {name: {"rows": [...], "daily": np.array, "trades": [...]}} incl. B1 and B3."""
    out = {}
    specs = [("B1", None, False), ("B3", None, True)] + [(sc.name, sc, sc.veto) for sc in scenarios]
    for name, sc, veto in specs:
        rows, daily, trades = [], [], []
        for w in wins:
            cls = scenario_pm_class(sc) if sc else None
            curve, exp, tr = run_b1(w, data, replay, bmsb, veto_blue=veto, pm_class=cls)
            days = len(_days(w, data))
            rows.append(dict(window=w["index"], strategy=name, **metrics(curve, exp, tr, days)))
            eq = np.array([INITIAL_CAPITAL] + [e for _, e in curve])
            daily.extend(eq[1:] / eq[:-1] - 1)
            trades.extend(tr)
        out[name] = {"rows": rows, "daily": np.array(daily), "trades": trades}
    return out


def _stationary_bootstrap_idx(n, mean_block, rng):
    idx = np.empty(n, dtype=int)
    idx[0] = rng.integers(n)
    p = 1.0 / mean_block
    for t in range(1, n):
        idx[t] = rng.integers(n) if rng.random() < p else (idx[t - 1] + 1) % n
    return idx


def reality_check(results, names, benchmark="B1", reps=2000, mean_block=10, seed=7):
    """White's Reality Check on mean daily excess return vs the benchmark.

    Returns the family p-value for the best scenario and naive per-scenario p-values.
    """
    rng = np.random.default_rng(seed)
    d = np.vstack([results[n]["daily"] - results[benchmark]["daily"] for n in names])
    n = d.shape[1]
    means = d.mean(axis=1)
    stat = math.sqrt(n) * means.max()
    boot_max, boot_each = np.empty(reps), np.zeros(len(names))
    for r in range(reps):
        idx = _stationary_bootstrap_idx(n, mean_block, rng)
        centred = d[:, idx].mean(axis=1) - means
        boot_max[r] = math.sqrt(n) * centred.max()
        boot_each += (centred >= means)            # naive one-sided p for each scenario
    return {"best": names[int(means.argmax())], "family_p": float((boot_max >= stat).mean()),
            "naive_p": {nm: float(c / reps) for nm, c in zip(names, boot_each)},
            "mean_excess_bps_per_day": {nm: float(m * 1e4) for nm, m in zip(names, means)}}


def summarise(results, rc=None):
    b1 = {r["window"]: r for r in results["B1"]["rows"]}
    table = {}
    for name, res in results.items():
        rows = res["rows"]
        tr = res["trades"]
        table[name] = {
            "compounded_pct": (math.prod(1 + r["total_return_pct"] / 100 for r in rows) - 1) * 100,
            "worst_dd_pct": min(r["max_dd_pct"] for r in rows),
            "median_sharpe": statistics.median(r["sharpe"] for r in rows),
            "windows_beating_b1": sum(r["total_return_pct"] > b1[r["window"]]["total_return_pct"] for r in rows),
            "trades": len(tr),
            "win_rate_pct": sum(t["pnl"] > 0 for t in tr) / len(tr) * 100 if tr else 0.0,
            "avg_hold": statistics.mean(t["bars"] for t in tr) if tr else 0.0,
            "exits": dict(Counter(t["exit"] for t in tr)),
            "naive_p": None if rc is None else rc["naive_p"].get(name),
            "per_window": {r["window"]: [round(r["total_return_pct"], 2), round(r["sharpe"], 2), round(r["max_dd_pct"], 2)] for r in rows},
        }
    return table


def candidates(table) -> List[str]:
    scen = {k: v for k, v in table.items() if k not in ("B1", "B3")}
    top = sorted(scen, key=lambda k: -scen[k]["compounded_pct"])[:3]
    best_sharpe = max(scen, key=lambda k: scen[k]["median_sharpe"])
    out = top + ([best_sharpe] if best_sharpe not in top else [])
    return out + ([H1.name] if H1.name not in out else [])


def _write(out: Path, payload: dict):
    out.mkdir(parents=True)
    (out / "summary.json").write_text(json.dumps(payload, indent=1, default=float))


def cmd_search(args):
    data, replay, bmsb = prepare(args.universe)
    wins = [w for w in windows() if w["index"] < HOLDOUT]
    fam = family()
    results = run_scenarios(fam, data, replay, bmsb, wins)
    rc = reality_check(results, [s.name for s in fam])
    table = summarise(results, rc)
    _write(RUNS_DIR / args.out, {"universe": args.universe, "symbols": list(data), "reality_check": rc,
                                 "candidates": candidates(table), "table": table})


def _scenario(name: str) -> Scenario:
    return next(s for s in family() if s.name == name)


def cmd_confirm(args):
    prior = json.loads((RUNS_DIR / args.source / "summary.json").read_text())
    scen = [_scenario(n) for n in prior["candidates"]]
    data, replay, bmsb = prepare(args.universe)
    wins = [w for w in windows() if w["index"] < HOLDOUT]
    results = run_scenarios(scen, data, replay, bmsb, wins)
    rc = reality_check(results, [s.name for s in scen])
    _write(RUNS_DIR / args.out, {"universe": args.universe, "symbols": list(data), "from": args.source,
                                 "reality_check": rc, "table": summarise(results, rc)})


def cmd_continuous(args):
    prior = json.loads((RUNS_DIR / args.source / "summary.json").read_text())
    scen = [_scenario(n) for n in prior["candidates"]]
    data, replay, bmsb = prepare("primary")
    first, last = windows()[0], windows()[HOLDOUT - 2]
    span = {"index": 0, "start_ms": first["start_ms"], "end_ms": last["end_ms"], "start": first["start"], "end": last["end"]}
    results = run_scenarios(scen, data, replay, bmsb, [span])
    table = summarise(results)
    _write(RUNS_DIR / args.out, {"span": [span["start"], span["end"]], "table": table})


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("select-secondary")
    p = sub.add_parser("replay"); p.add_argument("--universe", default="secondary")
    p = sub.add_parser("search"); p.add_argument("--universe", default="primary"); p.add_argument("--out", required=True)
    p = sub.add_parser("confirm"); p.add_argument("--from", dest="source", required=True)
    p.add_argument("--universe", default="secondary"); p.add_argument("--out", required=True)
    p = sub.add_parser("continuous"); p.add_argument("--from", dest="source", required=True); p.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    if getattr(args, "out", None) and (RUNS_DIR / args.out).exists():
        ap.error("results are never overwritten")
    if args.cmd == "select-secondary":
        print(json.dumps(select_secondary(), indent=1))
    elif args.cmd == "replay":
        prepare(args.universe)
    elif args.cmd == "search":
        cmd_search(args)
    elif args.cmd == "confirm":
        cmd_confirm(args)
    elif args.cmd == "continuous":
        cmd_continuous(args)


if __name__ == "__main__":
    main()
