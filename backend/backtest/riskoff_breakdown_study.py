"""
R2-RO: R2's support-breakdown exit, acting only while the market is risk-off
(declared in docs/reviews/larsson-study.md before it was run). Windows 1-9 only;
the holdout stays locked and is never loaded.

    python -m backtest.riskoff_breakdown_study --out r2ro_breakdown_w1-9      (from backend/)

Runs the four declared variants, their parents and the ungated R2 context rows on
the primary and secondary universes, the Reality Check against B1, the
best-coin-removed check and the no-reset diagnostic, and writes ``summary.json``
and ``tables.md`` under ``data/larsson_runs/<out>``.

Trigger, fills, entries, sizing, BMSB entry gate and costs are R2's
(``backtest.breakdown_exit_study``). The only change is a gate read on the
breakdown close:

  RO-BMSB  BTC's last completed weekly close is below its weekly BMSB mid (B1's
           filter with one week instead of two, B1's completed-week keys)
  RO-CONS  the replay's own market consensus for that day is RISK-OFF (the value
           it passed to the synthesizer, read from its stored per-coin results)
"""
from __future__ import annotations

import argparse
import json
import logging
import re
from collections import defaultdict
from typing import Callable, Dict, List, Optional

import numpy as np

from backtest.breakdown_exit_study import (
    H60, H60_NAME, attach_levels, beats, best_coin, breakdown_exit_class, forward_returns, run_all, summarise,
)
from backtest.larsson_scenarios import prepare, reality_check, scenario_pm_class
from backtest.larsson_study import (
    HOLDOUT, RUNS_DIR, _compute_bmsb_filter, _costed_pm_class, _days, _is_bmsb_blocked, windows,
)

logger = logging.getLogger("riskoff_breakdown_study")

RO_BMSB, RO_CONS = "RO-BMSB", "RO-CONS"
DEFINITIONS = (RO_BMSB, RO_CONS)
VARIANTS = ("RO1-B1", "RO2-B1", "RO1-H60", "RO2-H60")
CONTEXT = ("R2-B1", "R2-H60")                       # ungated R2 rule, not tested
GATE_OF = {"RO1-B1": RO_BMSB, "RO2-B1": RO_CONS, "RO1-H60": RO_BMSB, "RO2-H60": RO_CONS}
PARENTS = {"RO1-B1": "B1", "RO2-B1": "B1", "RO1-H60": H60_NAME, "RO2-H60": H60_NAME,
           "R2-B1": "B1", "R2-H60": H60_NAME}
ROWS = ("B1", H60_NAME) + VARIANTS + CONTEXT
EXPECTED = {   # earlier runs: compounded %, worst window DD % (scen_* for parents, r2_breakdown_w1-9 for R2)
    "primary": {"B1": (53.9, -24.4), H60_NAME: (83.4, -19.8), "R2-B1": (50.1, -23.9), "R2-H60": (74.7, -18.6)},
    "secondary": {"B1": (12.5, -26.3), H60_NAME: (22.4, -27.3), "R2-B1": (11.9, -25.9), "R2-H60": (20.7, -26.4)},
}
_LABEL = re.compile(r"consensus[= ](RISK-ON|EUPHORIA|RISK-OFF|ACCUMULATION|MIXED)\b")


# ------------------------------------------------------------------------------ risk-off definitions

def ro_bmsb_gate(weekly_btc: Optional[dict]) -> Callable[[float], bool]:
    """True when BTC's last completed weekly close is below its BMSB mid.

    ``weekly_btc`` is keyed to each week's final-day open (as the replay cache stores
    it), so at a daily bar's timestamp only weeks finished by that bar's close count.
    """
    m = _compute_bmsb_filter(weekly_btc, consecutive_weeks=1) if weekly_btc is not None else {}
    keys = sorted(m)
    return lambda ts: bool(_is_bmsb_blocked(m, keys, ts))


def replay_consensus(replay_bars: dict) -> Dict[float, str]:
    """The replay's own consensus per day, from its stored results keyed (sym, ts).

    Each result's signal reason records the consensus it was synthesized with. A day
    with no record is recounted with the live scanner's function from that day's
    stored regimes. Only results stamped with that day are read.
    """
    from scanner import compute_consensus
    by_ts = defaultdict(list)
    for (_, ts), r in replay_bars.items():
        by_ts[ts].append(r)
    out = {}
    for ts, rs in by_ts.items():
        labels = {m.group(1) for r in rs for m in _LABEL.finditer(r.signal_reason or "")}
        if len(labels) > 1:
            raise ValueError(f"conflicting consensus records on {ts}: {sorted(labels)}")
        out[ts] = labels.pop() if labels else compute_consensus([{"regime": r.regime} for r in rs])["consensus"]
    return out


def ro_cons_gate(replay_bars: dict) -> Callable[[float], bool]:
    cons = replay_consensus(replay_bars)
    return lambda ts: cons.get(ts) == "RISK-OFF"     # a day with no replay results is not risk-off


def gates(replay: dict) -> Dict[str, Callable[[float], bool]]:
    return {RO_BMSB: ro_bmsb_gate(replay.get("weekly_btc")), RO_CONS: ro_cons_gate(replay["bars"])}


# ------------------------------------------------------------------------------ strategies

def pm_classes(replay: dict) -> Dict[str, Optional[type]]:
    """Fresh classes (each gated class keeps its own skip log). None is B1's own manager."""
    g = gates(replay)
    b1, h60 = _costed_pm_class(), scenario_pm_class(H60)
    base = {"B1": b1, H60_NAME: h60}
    out: Dict[str, Optional[type]] = {"B1": None, H60_NAME: h60}
    for v in VARIANTS:
        out[v] = breakdown_exit_class(base[PARENTS[v]], gate=g[GATE_OF[v]])
    out["R2-B1"] = breakdown_exit_class(b1)
    out["R2-H60"] = breakdown_exit_class(h60)
    return out


def run(data, replay, bmsb, wins, names=None) -> dict:
    return run_all(data, replay, bmsb, wins, names=names, classes=pm_classes(replay))


# ------------------------------------------------------------------------------ reporting

def skipped_stats(skipped: List[dict], data) -> dict:
    """Skipped breakdowns: per close, per position, and R2's 20-bar measure at each
    position's first skipped close (open of bar i + 1 to the close of bar i + 20)."""
    first = {}
    for s in sorted(skipped, key=lambda s: s["bd_bar"]):
        first.setdefault((s["symbol"], s["entry"]), s)
    pseudo = [{"symbol": s["symbol"], "exit": "BREAKDOWN", "bd_bar": s["bd_bar"], "fill_bar": s["bd_bar"] + 1}
              for s in first.values()]
    return {"closes": len(skipped), "positions": len(first), "fwd20": forward_returns(pseudo, data)}


def risk_off_share(g: Dict[str, Callable[[float], bool]], data, wins) -> dict:
    out = {}
    for name in DEFINITIONS:
        per, all_days = {}, []
        for w in wins:
            on = [g[name](ts) for ts in _days(w, data)]
            per[w["index"]] = float(np.mean(on) * 100) if on else 0.0
            all_days.extend(on)
        out[name] = {"per_window_pct": per, "w1_9_pct": float(np.mean(all_days) * 100) if all_days else 0.0}
    return out


def table(results: dict, data) -> dict:
    t = summarise(results, data, parents=PARENTS)
    for name, res in results.items():
        t[name]["skipped"] = skipped_stats(res.get("skipped", []), data) if name in VARIANTS else None
    return t


def statistics_vs(results: dict) -> dict:
    rc = reality_check(results, list(VARIANTS), benchmark="B1")
    rc["naive_p_vs_parent"] = {v: reality_check(results, [v], benchmark=PARENTS[v])["naive_p"][v] for v in VARIANTS}
    return rc


def _check(universe: str, t: dict) -> dict:
    out = {}
    for name, (comp, dd) in EXPECTED[universe].items():
        got = (round(t[name]["compounded_pct"], 1), round(t[name]["worst_dd_pct"], 1))
        out[name] = {"expected": [comp, dd], "got": list(got), "match": got == (comp, dd)}
    return out


def verdict(payload: dict) -> dict:
    out = {}
    for v in VARIANTS:
        p = PARENTS[v]
        c1 = bool(payload["primary"]["reality_check"]["adjusted_p"][v] < 0.10)
        both = {u: beats(payload[u]["table"][v], payload[u]["table"][p]) for u in ("primary", "secondary")}
        c3 = payload["best_coin_removed"][v]["holds"]
        out[v] = {"c1_reality_check": c1, "c2_beats_parent_both": all(both.values()), "c2_by_universe": both,
                  "c3_best_coin_removed": c3, "candidate": bool(c1 and all(both.values()) and c3)}
    return out


def study_windows() -> List[dict]:
    """Windows 1-9; the holdout window is never part of this study."""
    return [w for w in windows() if w["index"] < HOLDOUT and not w["holdout"]]


def study() -> dict:
    wins = study_windows()
    payload = {"windows": [w["index"] for w in wins], "variants": list(VARIANTS), "context": list(CONTEXT),
               "parents": PARENTS, "gates": GATE_OF}
    for universe in ("primary", "secondary"):
        data, replay, bmsb = prepare(universe)
        attach_levels(data)
        results = run(data, replay, bmsb, wins)
        t = table(results, data)
        payload[universe] = {"symbols": list(data), "reality_check": statistics_vs(results), "table": t,
                             "risk_off_share": risk_off_share(gates(replay), data, wins),
                             "check": _check(universe, t)}
        if universe == "primary":
            removed = {}
            for v in VARIANTS:
                coin = best_coin(results[v]["trades"], results[PARENTS[v]]["trades"])
                sub = {s: sd for s, sd in data.items() if s != coin}
                st = table(run(sub, replay, bmsb, wins, names={v, PARENTS[v]}), sub)
                removed[v] = {"coin": coin, "variant": {k: st[v][k] for k in ("compounded_pct", "worst_dd_pct")},
                              "parent": {k: st[PARENTS[v]][k] for k in ("compounded_pct", "worst_dd_pct")},
                              "holds": beats(st[v], st[PARENTS[v]])}
            payload["best_coin_removed"] = removed
            first, last = wins[0], wins[-1]
            span = {"index": 0, "start_ms": first["start_ms"], "end_ms": last["end_ms"],
                    "start": first["start"], "end": last["end"]}
            payload["continuous"] = {"span": [span["start"], span["end"]],
                                     "table": table(run(data, replay, bmsb, [span]), data)}
    payload["verdict"] = verdict(payload)
    return payload


def _pct(x, nd=1):
    return "-" if x is None else f"{x:+.{nd}f}%"


def _p(x):
    return "-" if x is None else f"{x:.2f}"


def _fwd(f):
    if not f or not f["n"]:
        return "-"
    extra = f"; {f['excluded']} past W9" if f["excluded"] else ""
    return f"{_pct(f['mean_pct'])} / {_pct(f['median_pct'])} / {f['share_negative_pct']:.0f}% ({f['n']}{extra})"


def markdown(payload: dict) -> str:
    lines = []
    for u in ("primary", "secondary"):
        t, rc = payload[u]["table"], payload[u]["reality_check"]
        lines += [f"### {u}", "",
                  "| Strategy | Compounded W1-9 | Worst window DD | Median Sharpe | Windows beating parent | Trades | Win rate "
                  "| Avg hold | Breakdown exits | Skipped (closes / positions) | Held 20 bars after exits: mean / median / "
                  "share < 0 (n) | Held 20 bars after skipped | RC p | Naive p vs B1 | Naive p vs parent |",
                  "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---:|---:|---:|"]
        for name in ROWS:
            r = t[name]
            sk = r.get("skipped")
            wbp = "-" if r["windows_beating_parent"] is None else f"{r['windows_beating_parent']}/9"
            lines.append(
                f"| {name} | {_pct(r['compounded_pct'])} | {r['worst_dd_pct']:.1f}% | {r['median_sharpe']:.2f} | {wbp} | "
                f"{r['trades']} | {r['win_rate_pct']:.0f}% | {r['avg_hold']:.0f} | "
                f"{r['breakdown_exits'] if name in VARIANTS + CONTEXT else '-'} | "
                f"{'-' if sk is None else str(sk['closes']) + ' / ' + str(sk['positions'])} | "
                f"{_fwd(r['fwd20']) if name in VARIANTS + CONTEXT else '-'} | {_fwd(sk['fwd20']) if sk else '-'} | "
                f"{_p(rc['adjusted_p'].get(name))} | {_p(rc['naive_p'].get(name))} | {_p(rc['naive_p_vs_parent'].get(name))} |")
        lines += ["", f"Reality Check (four variants vs B1): family p = {rc['family_p']:.2f}, best {rc['best']}", "",
                  "Parent and context check: " + ", ".join(
                      f"{k} {'ok' if c['match'] else 'MISMATCH ' + str(c['got'])}" for k, c in payload[u]["check"].items()), ""]
        sh = payload[u]["risk_off_share"]
        lines += [f"Risk-off share of days ({u})", "", "| Definition | " + " | ".join(f"W{w}" for w in payload["windows"]) + " | W1-9 |",
                  "|---|" + "---:|" * (len(payload["windows"]) + 1)]
        for d in DEFINITIONS:
            lines.append(f"| {d} | " + " | ".join(f"{sh[d]['per_window_pct'][w]:.0f}%" for w in payload["windows"])
                         + f" | {sh[d]['w1_9_pct']:.0f}% |")
        lines += [""]
    c = payload["continuous"]["table"]
    lines += ["### continuous (primary, no resets)", "",
              "| Strategy | Total return | Max DD | Trades | Win rate | Avg hold | Breakdown exits | Skipped (closes / positions) |",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for name in ROWS:
        r = c[name]
        sk = r.get("skipped")
        lines.append(f"| {name} | {_pct(r['compounded_pct'])} | {r['worst_dd_pct']:.1f}% | {r['trades']} | {r['win_rate_pct']:.0f}% | "
                     f"{r['avg_hold']:.0f} | {r['breakdown_exits'] if name in VARIANTS + CONTEXT else '-'} | "
                     f"{'-' if sk is None else str(sk['closes']) + ' / ' + str(sk['positions'])} |")
    lines += ["", "### best coin removed (primary)", "",
              "| Variant | Coin removed | Variant: compounded / worst DD | Parent: compounded / worst DD | Holds |", "|---|---|---|---|---|"]
    for v, r in payload["best_coin_removed"].items():
        lines.append(f"| {v} | {r['coin']} | {_pct(r['variant']['compounded_pct'])} / {r['variant']['worst_dd_pct']:.1f}% | "
                     f"{_pct(r['parent']['compounded_pct'])} / {r['parent']['worst_dd_pct']:.1f}% | {'yes' if r['holds'] else 'no'} |")
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
