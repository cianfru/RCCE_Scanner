"""
R2: exit RCCE trades on a support breakdown (declared in docs/reviews/larsson-study.md
before it was run). Windows 1-9 only; the holdout stays locked.

    python -m backtest.breakdown_exit_study --out r2_breakdown_w1-9      (from backend/)

Runs the four declared variants and their parents on the primary and secondary
universes, the Reality Check against B1, the best-coin-removed check and the
no-reset diagnostic, and writes ``summary.json`` under ``data/larsson_runs/<out>``.

Trigger: a Module B ``breakdown`` event (levels-1 declared defaults, n_low >= 2) on
the coin's USD daily chart, on a completed close after the entry bar, for a level at
or below the position's average entry price, evaluated after the parent's own rules
on that close. The exit fills at the open of the coin's next daily bar, before
anything else on that bar. Entries, sizing, BMSB gate, costs and the parents' own
fills are B1's.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import statistics
from collections import Counter, defaultdict
from typing import Dict, List, Optional

import numpy as np

from backtest.larsson_scenarios import Scenario, prepare, reality_check, scenario_pm_class
from backtest.larsson_study import (
    DECLARED, HOLDOUT, INITIAL_CAPITAL, RUNS_DIR, _costed_pm_class, _days, levels_for, metrics, run_b1, windows,
)

logger = logging.getLogger("breakdown_exit_study")

H60 = Scenario(veto=False, exit="t60", stop=0.12, signals=False)
H60_NAME = H60.name                                   # F0-t60-s12-nosig
VARIANTS = ("R2-B1", "R2-B1-50", "R2-H60", "R2-B1-ng")
PARENTS = {"R2-B1": "B1", "R2-B1-50": "B1", "R2-H60": H60_NAME, "R2-B1-ng": "B1"}
EXIT_FULL, EXIT_HALF = "BREAKDOWN", "BREAKDOWN_50"
BREAKDOWN_EXITS = (EXIT_FULL, EXIT_HALF)
FWD_BARS = 20
EXPECTED_PARENTS = {   # earlier runs (scen_primary / scen_secondary): compounded %, worst window DD %
    "primary": {"B1": (53.9, -24.4), H60_NAME: (83.4, -19.8)},
    "secondary": {"B1": (12.5, -26.3), H60_NAME: (22.4, -27.3)},
}


# ------------------------------------------------------------------------------ manager

def breakdown_exit_class(base, *, fraction: float = 1.0, once: bool = False, not_gold: bool = False):
    """``base`` (a PositionManager class) plus the declared breakdown exit.

    fraction  share of the position sold at the next open (1.0 full, 0.5 half)
    once      only the first breakdown of a trade counts
    not_gold  only breakdowns on bars where the ribbon is not gold count
    """
    label = EXIT_FULL if fraction >= 1.0 else EXIT_HALF

    class BreakdownExitPM(base):
        ctx = None

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._bd_pending: Dict[str, tuple] = {}   # sym -> (entry_time, breakdown bar index)
            self._bd_fired: set = set()               # (sym, entry_time) already triggered (once)

        def set_context(self, sym, i, sd):
            self.ctx = (sym, i, sd)

        def process_bar(self, bar):
            sym = bar.symbol
            _, i, sd = self.ctx
            fill, block_entry = None, False
            pending = self._bd_pending.pop(sym, None)
            if pending is not None and i is None:
                self._bd_pending[sym] = pending       # no daily bar to fill on yet
            elif pending is not None:
                pos = self.positions.get(sym)
                if pos is not None and pos.entry_time == pending[0]:
                    fill = self._close_position(sym, bar.timestamp, float(sd.usd["open"][i]), label, close_pct=fraction)
                    if fill is not None:
                        fill.tags = {"bd_bar": int(pending[1]), "fill_bar": int(i)}
                    if fraction >= 1.0:
                        block_entry = True            # no new entry on the exit bar
                        if hasattr(self, "_st"):
                            self._st.pop(sym, None)
            saved = self.macro_blocked
            if block_entry:
                self.macro_blocked = True
            try:
                out = super().process_bar(bar)
            finally:
                self.macro_blocked = saved
            # Trigger on this completed close, after the parent's own rules.
            pos = self.positions.get(sym)
            if pos is not None and i is not None and pos.entry_time < bar.timestamp:
                key = (sym, pos.entry_time)
                if (once and key in self._bd_fired) or (not_gold and sd.ll["state"][i] == "gold"):
                    return out if out is not None else fill
                if any(e["event"] == "breakdown" and e["level"] <= pos.entry_price for e in sd.levels[i].events):
                    self._bd_pending[sym] = (pos.entry_time, i)
                    if once:
                        self._bd_fired.add(key)
            return out if out is not None else fill

    return BreakdownExitPM


def pm_classes() -> Dict[str, Optional[type]]:
    """Parents and variants; None is B1's own PositionManager (run_b1's default)."""
    b1 = _costed_pm_class()
    h60 = scenario_pm_class(H60)
    return {
        "B1": None,
        H60_NAME: h60,
        "R2-B1": breakdown_exit_class(b1),
        "R2-B1-50": breakdown_exit_class(b1, fraction=0.5, once=True),
        "R2-H60": breakdown_exit_class(h60),
        "R2-B1-ng": breakdown_exit_class(b1, not_gold=True),
    }


# ------------------------------------------------------------------------------ runs

def attach_levels(data) -> None:
    for sd in data.values():
        sd.levels = levels_for(sd, DECLARED["tol"], DECLARED["max_last"], DECLARED["b"])


def run_all(data, replay, bmsb, wins, names=None) -> dict:
    out = {}
    for name, cls in pm_classes().items():
        if names is not None and name not in names:
            continue
        rows, daily, trades = [], [], []
        for w in wins:
            curve, exp, tr = run_b1(w, data, replay, bmsb, pm_class=cls)
            rows.append(dict(window=w["index"], **metrics(curve, exp, tr, len(_days(w, data)))))
            eq = np.array([INITIAL_CAPITAL] + [e for _, e in curve])
            daily.extend(eq[1:] / eq[:-1] - 1)
            trades.extend(tr)
        out[name] = {"rows": rows, "daily": np.array(daily), "trades": trades}
        logger.info("%s done", name)
    return out


def positions(trades: List[dict]) -> List[dict]:
    """One record per position: partial sells and the final close of the rest combined."""
    grouped = defaultdict(list)
    for t in trades:
        grouped[(t["symbol"], t["entry"])].append(t)
    return [{"symbol": k[0], "pnl": sum(t["pnl"] for t in g), "bars": max(t["bars"] for t in g), "exit": g[-1]["exit"]}
            for k, g in grouped.items()]


def forward_returns(trades: List[dict], data, bars: int = FWD_BARS) -> dict:
    """Return from each breakdown fill (open of bar i + 1) to the close of bar i + ``bars``."""
    vals, excluded = [], 0
    for t in trades:
        if t["exit"] not in BREAKDOWN_EXITS:
            continue
        sd = data[t["symbol"]]
        end = t["bd_bar"] + bars
        if end >= len(sd.usd["close"]):
            excluded += 1                    # runs past the end of W9: never read
            continue
        vals.append(sd.usd["close"][end] / sd.usd["open"][t["fill_bar"]] - 1)
    return {"n": len(vals), "excluded": excluded,
            "mean_pct": float(np.mean(vals) * 100) if vals else None,
            "median_pct": float(np.median(vals) * 100) if vals else None,
            "share_negative_pct": float(np.mean(np.array(vals) < 0) * 100) if vals else None}


def summarise(results: dict, data) -> dict:
    table = {}
    for name, res in results.items():
        rows, tr = res["rows"], res["trades"]
        pos = positions(tr)
        parent = PARENTS.get(name)
        prow = {r["window"]: r for r in results[parent]["rows"]} if parent in results else None
        table[name] = {
            "parent": parent,
            "compounded_pct": (math.prod(1 + r["total_return_pct"] / 100 for r in rows) - 1) * 100,
            "worst_dd_pct": min(r["max_dd_pct"] for r in rows),
            "median_sharpe": statistics.median(r["sharpe"] for r in rows),
            "windows_beating_parent": (sum(r["total_return_pct"] > prow[r["window"]]["total_return_pct"] for r in rows)
                                       if prow else None),
            "trades": len(pos),
            "win_rate_pct": sum(p["pnl"] > 0 for p in pos) / len(pos) * 100 if pos else 0.0,
            "avg_hold": statistics.mean(p["bars"] for p in pos) if pos else 0.0,
            "breakdown_exits": sum(t["exit"] in BREAKDOWN_EXITS for t in tr),
            "fwd20": forward_returns(tr, data),
            "exits": dict(Counter(t["exit"] for t in tr)),
            "per_window": {r["window"]: [round(r["total_return_pct"], 2), round(r["sharpe"], 2), round(r["max_dd_pct"], 2)]
                           for r in rows},
        }
    return table


def coin_pnl(trades: List[dict]) -> Dict[str, float]:
    out: Dict[str, float] = defaultdict(float)
    for t in trades:
        out[t["symbol"]] += t["pnl"]
    return dict(out)


def best_coin(variant_trades: List[dict], parent_trades: List[dict]) -> str:
    """Coin contributing most to the variant's gain over its parent (P&L difference)."""
    v, p = coin_pnl(variant_trades), coin_pnl(parent_trades)
    return max(set(v) | set(p), key=lambda s: (v.get(s, 0.0) - p.get(s, 0.0), s))


def beats(row: dict, parent_row: dict) -> bool:
    return row["compounded_pct"] > parent_row["compounded_pct"] and row["worst_dd_pct"] > parent_row["worst_dd_pct"]


def statistics_vs(results: dict) -> dict:
    rc = reality_check(results, list(VARIANTS), benchmark="B1")
    rc["naive_p_vs_parent"] = {v: reality_check(results, [v], benchmark=PARENTS[v])["naive_p"][v] for v in VARIANTS}
    return rc


# ------------------------------------------------------------------------------ main

def _parent_check(universe: str, table: dict) -> dict:
    out = {}
    for name, (comp, dd) in EXPECTED_PARENTS[universe].items():
        got = (round(table[name]["compounded_pct"], 1), round(table[name]["worst_dd_pct"], 1))
        out[name] = {"expected": [comp, dd], "got": list(got), "match": got == (comp, dd)}
    return out


def study() -> dict:
    wins = [w for w in windows() if w["index"] < HOLDOUT]
    payload = {"windows": [w["index"] for w in wins], "variants": list(VARIANTS), "parents": PARENTS}
    tables = {}
    for universe in ("primary", "secondary"):
        data, replay, bmsb = prepare(universe)
        attach_levels(data)
        results = run_all(data, replay, bmsb, wins)
        tables[universe] = summarise(results, data)
        payload[universe] = {"symbols": list(data), "reality_check": statistics_vs(results),
                             "table": tables[universe], "parent_check": _parent_check(universe, tables[universe])}
        if universe == "primary":
            removed = {}
            for v in VARIANTS:
                coin = best_coin(results[v]["trades"], results[PARENTS[v]]["trades"])
                sub = {s: sd for s, sd in data.items() if s != coin}
                res = run_all(sub, replay, bmsb, wins, names={v, PARENTS[v]})
                t = summarise(res, sub)
                removed[v] = {"coin": coin, "variant": {k: t[v][k] for k in ("compounded_pct", "worst_dd_pct")},
                              "parent": {k: t[PARENTS[v]][k] for k in ("compounded_pct", "worst_dd_pct")},
                              "holds": beats(t[v], t[PARENTS[v]])}
            payload["best_coin_removed"] = removed
            first, last = wins[0], wins[-1]
            span = {"index": 0, "start_ms": first["start_ms"], "end_ms": last["end_ms"],
                    "start": first["start"], "end": last["end"]}
            payload["continuous"] = {"span": [span["start"], span["end"]],
                                     "table": summarise(run_all(data, replay, bmsb, [span]), data)}
    verdict = {}
    for v in VARIANTS:
        p = PARENTS[v]
        c1 = payload["primary"]["reality_check"]["adjusted_p"][v] < 0.10
        c2 = all(beats(tables[u][v], tables[u][p]) for u in ("primary", "secondary"))
        c3 = payload["best_coin_removed"][v]["holds"]
        verdict[v] = {"c1_reality_check": c1, "c2_beats_parent_both": c2, "c3_best_coin_removed": c3,
                      "candidate": c1 and c2 and c3}
    payload["verdict"] = verdict
    return payload


def _fmt(x, nd=1, pct=False):
    if x is None:
        return "-"
    return f"{x:+.{nd}f}%" if pct else f"{x:.{nd}f}"


def markdown(payload: dict) -> str:
    lines = []
    for u in ("primary", "secondary"):
        t, rc = payload[u]["table"], payload[u]["reality_check"]
        lines += [f"### {u}", "", "| Strategy | Compounded W1-9 | Worst window DD | Median Sharpe | Windows beating parent | "
                  "Trades | Win rate | Avg hold | Breakdown exits | Held 20 bars: mean / median / share < 0 (n) | RC p | Naive p vs B1 | Naive p vs parent |",
                  "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|"]
        for name in ("B1", H60_NAME) + VARIANTS:
            r = t[name]
            f = r["fwd20"]
            fwd = "-" if not f["n"] else f"{_fmt(f['mean_pct'], pct=True)} / {_fmt(f['median_pct'], pct=True)} / {f['share_negative_pct']:.0f}% ({f['n']})"
            lines.append(f"| {name} | {_fmt(r['compounded_pct'], pct=True)} | {r['worst_dd_pct']:.1f}% | {r['median_sharpe']:.2f} | "
                         f"{'-' if r['windows_beating_parent'] is None else str(r['windows_beating_parent']) + '/9'} | {r['trades']} | "
                         f"{r['win_rate_pct']:.0f}% | {r['avg_hold']:.0f} | {r['breakdown_exits'] if name in VARIANTS else '-'} | {fwd} | "
                         f"{_fmt(rc['adjusted_p'].get(name), 2)} | {_fmt(rc['naive_p'].get(name), 2)} | {_fmt(rc['naive_p_vs_parent'].get(name), 2)} |")
        lines += ["", f"Reality Check (four variants vs B1): family p = {rc['family_p']:.2f}, best {rc['best']}", ""]
    c = payload["continuous"]["table"]
    lines += ["### continuous (primary, no resets)", "", "| Strategy | Total return | Max DD | Trades | Win rate | Avg hold | Breakdown exits |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for name in ("B1", H60_NAME) + VARIANTS:
        r = c[name]
        lines.append(f"| {name} | {_fmt(r['compounded_pct'], pct=True)} | {r['worst_dd_pct']:.1f}% | {r['trades']} | {r['win_rate_pct']:.0f}% | "
                     f"{r['avg_hold']:.0f} | {r['breakdown_exits'] if name in VARIANTS else '-'} |")
    lines += ["", "### best coin removed (primary)", "", "| Variant | Coin | Variant compounded / worst DD | Parent compounded / worst DD | Holds |",
              "|---|---|---|---|---|"]
    for v, r in payload["best_coin_removed"].items():
        lines.append(f"| {v} | {r['coin']} | {_fmt(r['variant']['compounded_pct'], pct=True)} / {r['variant']['worst_dd_pct']:.1f}% | "
                     f"{_fmt(r['parent']['compounded_pct'], pct=True)} / {r['parent']['worst_dd_pct']:.1f}% | {'yes' if r['holds'] else 'no'} |")
    lines += ["", "### verdict", ""] + [f"- {v}: {d}" for v, d in payload["verdict"].items()]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="run name; written under backend/data/larsson_runs/")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    out = RUNS_DIR / args.out
    if out.exists():
        ap.error("results are never overwritten")
    payload = study()
    out.mkdir(parents=True)
    (out / "summary.json").write_text(json.dumps(payload, indent=1, default=float))
    md = markdown(payload)
    (out / "tables.md").write_text(md)
    print(md)


if __name__ == "__main__":
    main()
