"""Summarise a larsson_study run: per-window table, median-based selection, acceptance checks.

    python -m backtest.larsson_summary RUN_NAME            (from backend/)

Selection follows the spec: each variant's parameters are chosen on the
median across windows (Sharpe), never on the best window. Acceptance
criteria 1, 2 and 4 are evaluated on windows 1-9 only; criterion 3 needs the
holdout and is reported as pending.
"""
from __future__ import annotations

import csv
import json
import statistics
import sys
from pathlib import Path

from backtest.larsson_study import DECLARED, L_VARIANTS, RUNS_DIR, STRATEGIES, _pkey

W4 = 4


def _load(run: Path):
    rows = list(csv.DictReader((run / "results.csv").open()))
    for r in rows:
        r["window"] = int(r["window"])
        for k, v in list(r.items()):
            if k not in ("strategy", "params", "window"):
                r[k] = float(v) if v not in ("", "None") else None
    return rows


def select(rows):
    """Per strategy: parameters with the best median-window Sharpe."""
    chosen = {}
    for s in STRATEGIES:
        by_p = {}
        for r in rows:
            if r["strategy"] == s:
                by_p.setdefault(r["params"], []).append(r["sharpe"])
        chosen[s] = max(by_p, key=lambda p: (statistics.median(by_p[p]), p))
    return chosen


def table(rows, params, metric):
    wins = sorted({r["window"] for r in rows})
    get = {(r["window"], r["strategy"], r["params"]): r[metric] for r in rows}
    return wins, {s: [get.get((w, s, params[s])) for w in wins] for s in STRATEGIES}


def acceptance(rows, params, best):
    wins, sharpe = table(rows, params, "sharpe")
    _, dd = table(rows, params, "max_dd_pct")
    _, ret = table(rows, params, "total_return_pct")
    med_best, med_b1 = statistics.median(sharpe[best]), statistics.median(sharpe["B1"])
    dd_better = sum(1 for a, b in zip(dd[best], dd["B1"]) if a > b)
    i4 = wins.index(W4) if W4 in wins else None
    return {
        "L_best": best, "params": params[best],
        "c1_median_sharpe": {"L_best": med_best, "B1": med_b1, "pass": med_best > med_b1},
        "c1_dd_better_windows": {"count": dd_better, "of": len(wins), "need": "6 of 10 incl. holdout"},
        "c2_w4": None if i4 is None else {"L_best_sharpe": sharpe[best][i4], "B1_sharpe": sharpe["B1"][i4],
                                          "L_best_return": ret[best][i4], "B1_return": ret["B1"][i4],
                                          "pass": sharpe[best][i4] >= sharpe["B1"][i4] and ret[best][i4] >= ret["B1"][i4]},
        "c3_holdout": "pending (not run)",
        "c4_single_asset": "run the study without the best asset; see summary",
    }


def fmt(x, nd=2):
    return "  —  " if x is None else f"{x:.{nd}f}"


def markdown(rows, params, label):
    out = []
    for metric, nd, title in (("sharpe", 2, "Sharpe (annualised, daily)"), ("total_return_pct", 1, "Return %"),
                              ("max_dd_pct", 1, "Max drawdown %")):
        wins, t = table(rows, params, metric)
        out.append(f"\n**{title} — {label}**\n")
        out.append("| Window | " + " | ".join(STRATEGIES) + " |")
        out.append("|---" * (len(STRATEGIES) + 1) + "|")
        for i, w in enumerate(wins):
            name = f"**W{w}**" if w == W4 else f"W{w}"
            cells = [fmt(t[s][i], nd) for s in STRATEGIES]
            if w == W4:
                cells = [f"**{c}**" for c in cells]
            out.append(f"| {name} | " + " | ".join(cells) + " |")
        med = [fmt(statistics.median([v for v in t[s] if v is not None]), nd) for s in STRATEGIES]
        out.append("| median | " + " | ".join(med) + " |")
    return "\n".join(out)


def contribution(rows, params):
    wins, sh = table(rows, params, "sharpe")
    _, ret = table(rows, params, "total_return_pct")
    steps = [("L1", "L2"), ("L2", "L3"), ("L3", "L4")]
    return {f"{a}->{b}": {"sharpe": [None if x is None or y is None else y - x for x, y in zip(sh[a], sh[b])],
                          "return": [None if x is None or y is None else y - x for x, y in zip(ret[a], ret[b])]}
            for a, b in steps} | {"windows": wins}


def summarize(run_name: str) -> dict:
    run = RUNS_DIR / run_name
    rows = _load(run)
    declared = {s: _pkey(DECLARED) if s in L_VARIANTS + ("B2",) else "-" for s in STRATEGIES}
    have_grid = len({r["params"] for r in rows}) > 2
    chosen = select(rows) if have_grid else declared
    best = max(L_VARIANTS, key=lambda s: statistics.median(table(rows, chosen, "sharpe")[1][s]))
    summary = {
        "run": run_name, "selected_params": chosen, "L_best": best,
        "acceptance": acceptance(rows, chosen, best),
        "contribution_declared": contribution(rows, declared),
    }
    md = ["# Larsson study — windows 1-9 (holdout not run)", markdown(rows, declared, "declared parameters")]
    if have_grid:
        md.append(markdown(rows, chosen, "parameters selected on median-window Sharpe"))
    (run / "summary.json").write_text(json.dumps(summary, indent=1, default=float))
    (run / "summary.md").write_text("\n".join(md) + "\n")
    return summary


if __name__ == "__main__":
    print(json.dumps(summarize(sys.argv[1]), indent=1, default=float))
