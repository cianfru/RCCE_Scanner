"""
Re-run the decision pipeline on recorded engine inputs, once per rule variant (step 2 of the rule lab,
docs/reviews/rule-lab-study.md).

backtest/rule_capture.py records what the replay passes to the decision pipeline on every bar. This module feeds
those inputs back through decision_pipeline.evaluate_decision with a variant's switches set on signal_synthesizer,
and returns the same rows a full replay of that variant returns. Several variants run in one pass over the file;
each keeps its own decision state and its own daily rows, so nothing leaks between them.

    from backtest import rule_lab
    rows = rule_lab.run(["primary_4h.cap"], {"live": {}, "light50": {"LIGHT_LONG_MIN": 0.50}})

    python -m backtest.rule_lab --cap <prefix> --tf 4h|1d --out <result.json> [--jobs 3]        (from backend/)

scores every declared variant on windows 1-9 with the costed position manager of backtest/live_logic_check.py.
`--holdout NAME=switches.json` is the one declared read of window 10 for the live rules, the rules before the
capped Strong long and the top-divergence exit, and one chosen set; it writes a marker first and refuses to run
twice for the same data set.
"""
from __future__ import annotations

import pickle
from typing import Dict, Iterable, Iterator, List

FIELDS = ("price", "signal", "raw_signal", "regime", "conditions_met", "conditions_total", "signal_status",
          "zscore", "heat", "deviation_pct")
EXTRA = ("signal_reason", "confidence", "heat_phase", "heat_direction", "floor_confirmed", "is_absorption",
         "vol_state", "divergence", "bmsb_valid", "exhaustion_state")


def stream(path) -> Iterator[tuple]:
    with open(path, "rb") as f:
        while True:
            try:
                yield pickle.load(f)
            except EOFError:
                return


def _context_fields(ctx: dict) -> dict:
    return {"consensus": (ctx.get("consensus") or {}).get("consensus"),
            "fng": (ctx.get("sentiment") or {}).get("fear_greed_value"),
            "funding_regime": (ctx.get("positioning") or {}).get("funding_regime"),
            "stable_trend": (ctx.get("stablecoin") or {}).get("trend")}


SLIM = ("price", "signal", "regime")              # with timestamp, symbol and confluence_label: all the manager reads

# The declared variants (docs/reviews/rule-lab-study.md). Each differs from the live rules in one switch.
VARIANTS: Dict[str, dict] = {
    "live": {},
    "A50": {"LIGHT_LONG_MIN": 0.50}, "A60": {"LIGHT_LONG_MIN": 0.60}, "A70": {"LIGHT_LONG_MIN": 0.70},
    "B15": {"MARKUP_ENTRY_Z_MAX": 1.5}, "B10": {"MARKUP_ENTRY_Z_MAX": 1.0},
    "C": {"MODERATE_MIXED_OK": False},
    "D_greed60": {"FNG_GREED": 60}, "D_greed80": {"FNG_GREED": 80},
    "D_fear30": {"FNG_FEAR": 30}, "D_fear50": {"FNG_FEAR": 50},
    "E": {"MARKUP_FADE_BLOCK": True},
    "G": {"STRONG_LONG_CAP": False, "MARKUP_STRONG_OK": False},
    "H": {"CROWDED_BLOWOFF_OK": False},
    "J": {"ACCUM_STRONG_OK": False},                # round 2, declared after the round 1 results
}
BEFORE = {"STRONG_LONG_CAP": False, "DIV_EXIT": False}       # the rules before the two changes of 8 Nov 2026
DECAY_DAYS = (3.3, 7, 10, 20, 40, None)                      # family F: days of Wait before a position is closed
BARS_PER_DAY = {"4h": 6, "1d": 1}
DECAY_TODAY = 20                                             # bars, on either timeframe


def decay_bars(days, tf: str) -> int:
    return 10 ** 9 if days is None else max(1, round(days * BARS_PER_DAY[tf]))


def run(paths: Iterable[str], variants: Dict[str, dict], extra: bool = True, state=None,
        fields=FIELDS) -> Dict[str, List[dict]]:
    """Rows per variant. A variant is {switch name on signal_synthesizer: value}; {} is the code as it stands.
    `state` (from an earlier call, see run_state) continues a run into another file."""
    import signal_synthesizer as S
    from confluence import compute_confluence
    from decision_pipeline import evaluate_decision, new_state
    names = list(variants)
    base = {k: getattr(S, k) for v in variants.values() for k in v}
    st = state if state is not None else {n: {"decision": new_state(), "daily": {}} for n in names}
    out = {n: [] for n in names}
    for path in paths:
        for kind, sym, ms, row, pre, ctx, meta in stream(path):
            for n in names:
                v, s = variants[n], st[n]
                for k, val in v.items():
                    setattr(S, k, val)
                try:
                    if kind == "D":
                        if row is not None:
                            s["daily"][sym] = r = dict(row)
                        else:
                            r = s["daily"][sym]
                            r.update(pre)
                        try:
                            evaluate_decision(r, ctx, s["decision"], as_of=ms / 1000, metadata=meta,
                                              synthesizer=S.synthesize_signal)
                        except Exception:
                            r["signal"] = "WAIT"
                        continue
                    r = dict(row)
                    try:
                        evaluate_decision(r, ctx, s["decision"], as_of=ms / 1000, metadata=meta,
                                          synthesizer=S.synthesize_signal)
                        c = compute_confluence(r, s["daily"].get(sym))
                    except Exception:
                        continue
                    o = {"timestamp": float(ms), "symbol": sym, "confluence_label": c.label}
                    for k in fields:
                        o[k] = r.get(k)
                    if extra:
                        for k in EXTRA:
                            o[k] = r.get(k)
                        o.update(_context_fields(ctx))
                    out[n].append(o)
                finally:
                    for k, val in base.items():
                        setattr(S, k, val)
    run.state = st
    return out


def same(a: List[dict], b: List[dict], keys=("timestamp", "symbol", "confluence_label") + FIELDS) -> List[str]:
    """Differences between two row lists on `keys` (empty when they match)."""
    if len(a) != len(b):
        return [f"lengths differ: {len(a)} vs {len(b)}"]
    bad = []
    for i, (x, y) in enumerate(zip(a, b)):
        for k in keys:
            if x.get(k) != y.get(k) and not (x.get(k) is None and y.get(k) is None):
                bad.append(f"row {i} {x.get('symbol')} {k}: {x.get(k)!r} vs {y.get(k)!r}")
                break
        if len(bad) >= 10:
            break
    return bad


def bmsb_filter(end: str):
    from backtest.larsson_study import _compute_bmsb_filter, _weekly_completed
    m = _compute_bmsb_filter(_weekly_completed("BTC", end))
    return m, sorted(m)


def score(rows: List[dict], bmsb, wins: List[dict], decay: int = DECAY_TODAY) -> List[dict]:
    """Per-window metrics, as backtest/live_logic_check.score, for the given windows and decay threshold (bars)."""
    import collections
    from types import SimpleNamespace
    import backtest.position_manager as PM
    from backtest.larsson_study import INITIAL_CAPITAL, _costed_pm_class, _is_bmsb_blocked, metrics
    from backtest.live_logic_check import _daily
    by_ts = collections.defaultdict(list)
    for r in rows:
        by_ts[r["timestamp"]].append(SimpleNamespace(**r))
    stamps = sorted(by_ts)
    syms = sorted({r["symbol"] for r in rows})
    out, before = [], PM._SIGNAL_DECAY_THRESHOLD
    PM._SIGNAL_DECAY_THRESHOLD = decay
    try:
        for w in wins:
            pm = _costed_pm_class()(INITIAL_CAPITAL, syms)
            span = [t for t in stamps if w["start_ms"] <= t < w["end_ms"]]
            exposure = []
            for ts in span:
                pm.macro_blocked = _is_bmsb_blocked(bmsb[0], bmsb[1], ts)
                for bar in by_ts[ts]:
                    pm.process_bar(bar)
                pm.mark_to_market(ts, {b.symbol: b.price for b in by_ts[ts]})
                eq = pm.equity_curve[-1][1]
                value = sum(pm.per_symbol_alloc * p.size_pct * pm._latest_prices.get(s, p.entry_price) / p.entry_price
                            for s, p in pm.positions.items() if p.entry_price > 0)
                exposure.append(value / eq if eq > 0 else 0.0)
            pm.close_all_at_end(span[-1])
            pm.equity_curve[-1] = (span[-1], pm.get_equity())
            trades = [dict(pnl=t.pnl_usd, r=None, bars=t.bars_held, exit=t.exit_signal) for t in pm.trades]
            m = metrics(_daily(pm.equity_curve), exposure, trades, (w["end_ms"] - w["start_ms"]) / 86_400_000)
            exits = collections.Counter(t["exit"] for t in trades)
            out.append(dict(window=w["index"], exits=dict(exits), **m))
    finally:
        PM._SIGNAL_DECAY_THRESHOLD = before
    return out


def _job(args):
    """One process: a share of the variants over the capture, scored."""
    paths, tf, variants, wins, end, all_decays = args
    import collections
    rows = run(paths, variants, extra=False, fields=SLIM)
    bmsb = bmsb_filter(end)
    out = {}
    for name, rs in rows.items():
        first = wins[0]["start_ms"]
        res = {"signals": dict(collections.Counter(r["signal"] for r in rs if r["timestamp"] >= first)),
               "windows": score(rs, bmsb, wins)}
        if all_decays and name == "live":
            res["decay"] = {("off" if d is None else str(d)): score(rs, bmsb, wins, decay_bars(d, tf))
                            for d in DECAY_DAYS}
        out[name] = res
    return out


def main(argv=None):
    import argparse
    import json
    import sys
    from concurrent.futures import ProcessPoolExecutor
    from datetime import datetime, timezone
    from pathlib import Path
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cap", required=True, help="capture prefix from backtest/rule_capture.py")
    ap.add_argument("--tf", choices=("4h", "1d"), required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--holdout", metavar="NAME=switches.json", help="the one read of window 10")
    args = ap.parse_args(argv)
    from backtest.larsson_study import FREEZE_END, HOLDOUT, RUNS_DIR, windows
    paths = [f"{args.cap}.cap"]
    if args.holdout:
        name, _, spec = args.holdout.partition("=")
        chosen = json.loads(Path(spec).read_text())
        variants = {"before": BEFORE, "live": {}, name: chosen}
        wins = [w for w in windows() if w["index"] == HOLDOUT]
        end = FREEZE_END
        marker = RUNS_DIR / ".rule-lab-holdout-used"
        used = marker.read_text() if marker.exists() else ""
        key = Path(args.cap).name
        if f" {key} " in used:
            sys.exit(f"Window 10 was already read for {key}. A second read is not an untouched test.")
        with marker.open("a") as f:
            f.write(f"{datetime.now(timezone.utc).isoformat()} {key} {json.dumps(variants, sort_keys=True)}\n")
        paths.append(f"{args.cap}.holdout.cap")
    else:
        variants = VARIANTS
        wins = [w for w in windows() if w["index"] < HOLDOUT]
        end = windows()[HOLDOUT - 2]["end"]
    names = list(variants)
    n = max(1, min(args.jobs, len(names)))
    shares = [{k: variants[k] for k in names[i::n]} for i in range(n)]
    with ProcessPoolExecutor(n) as ex:
        parts = list(ex.map(_job, [(paths, args.tf, s, wins, end, not args.holdout) for s in shares]))
    res = {k: v for part in parts for k, v in part.items()}
    Path(args.out).write_text(json.dumps({"cap": args.cap, "tf": args.tf, "variants": variants, "results": res},
                                         indent=1, default=float))
    for k in names:
        tot = 1.0
        for w in res[k]["windows"]:
            tot *= 1 + w["total_return_pct"] / 100
        print(f"{k:<10} {100 * (tot - 1):+7.1f}%  worst {min(w['total_return_pct'] for w in res[k]['windows']):+6.1f}%")


if __name__ == "__main__":
    main()
