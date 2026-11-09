"""
Record every decision input of one replay of the live logic (step 1 of the rule lab, docs/reviews/rule-lab-study.md).

    python backtest/rule_capture.py --symbols primary|secondary --tf 4h|1d --out <prefix>

The replay is backtest/live_logic_replay.py in the live configuration (funding and stablecoin context, the
top-divergence exit on a 90-day window, Strong long capped). The engines are the slow part and do not depend on
the synthesizer's rules, so each call of the decision pipeline is written to disk as it is made: the engine row
as passed, the context and the metadata. backtest/rule_lab.py then re-runs only the pipeline on those inputs,
once per rule variant, in seconds instead of hours.

Two files: <prefix>.cap holds windows 1-9, <prefix>.holdout.cap the holdout window. The lab opens the second
only for the one declared holdout read.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import pickle
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRE_KEYS = ("divergence", "top_div_window")      # what the replay sets on a daily row before each re-evaluation


def _ms(day: str) -> int:
    return int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbols", choices=("primary", "secondary"), default="primary")
    ap.add_argument("--tf", choices=("4h", "1d"), default="4h")
    ap.add_argument("--out", required=True)
    ap.add_argument("--end", help="last day of data, exclusive (default: the study's freeze date)")
    ap.add_argument("--until", help="test only: cut every series at this day")
    args = ap.parse_args(argv)
    sys.path.insert(0, str(HERE.parent))
    from backtest import live_logic_replay as L
    from backtest.larsson_study import FREEZE_END, HOLDOUT, windows
    end = args.end or FREEZE_END
    split_ms = [w for w in windows() if w["index"] == HOLDOUT][0]["start_ms"]
    L.DATA_END = end                                    # the divergence marks read the same end date
    bh = L._bh()
    data = {tf: {} for tf in ("4h", "1d", "1w")}
    start = {"4h": L.DATA_START, "1d": L.DATA_START, "1w": "2019-01-07"}
    if args.tf == "1d":
        start["1d"] = L.DATA_START_1D_PRIMARY
    symbols = L.SYMBOLS
    if args.symbols == "secondary":
        from backtest.larsson_scenarios import SECONDARY_FILE
        symbols = json.loads(SECONDARY_FILE.read_text())["symbols"]
    cut = _ms(args.until) if args.until else None
    for s in symbols:
        for tf in data:
            if args.tf == "1d" and tf == "4h":
                continue
            d = bh.load(f"{s}USDT", tf, start[tf], end)
            if d is not None and cut is not None:
                keep = d["timestamp"] < cut
                d = {k: v[keep] for k, v in d.items()}
            if d is not None:
                data[tf][f"{s}/USDT"] = d
    fng = L._fear_greed()
    import engines.rcce_engine as rcce
    import signal_synthesizer
    import backtest.replay_engine as re_mod
    from backtest.live_context import make_hook
    L._zbase(rcce, "current")
    L._div_exit(symbols, 90)
    signal_synthesizer.STRONG_LONG_CAP = True
    re_mod.CONTEXT_HOOK = make_hook(symbols)

    real_eval, real_cons = re_mod.evaluate_decision, re_mod.compute_consensus
    files = {False: open(f"{args.out}.cap", "wb"), True: open(f"{args.out}.holdout.cap", "wb")}
    st = {"n": 0, "daily": set(), "seen": {}, "calls": 0, "eval_s": 0.0}

    def consensus(results):
        st["n"] += 1
        if st["n"] % 2 == 0:                            # the second call of each bar is over the daily rows
            st["daily"] = {id(r) for r in results}
        return real_cons(results)

    def evaluate(row, ctx, state, *, as_of, metadata=None, synthesizer=None):
        ms = int(round(as_of * 1000))
        sym = row["symbol"]
        if id(row) in st["daily"]:
            if st["seen"].get(sym) is row:              # same day, later bar: only what the replay set since
                rec = ("D", sym, ms, None, {k: row[k] for k in PRE_KEYS if k in row}, ctx, metadata)
            else:
                st["seen"][sym] = row
                rec = ("D", sym, ms, row, None, ctx, metadata)
        else:
            rec = ("T", sym, ms, row, None, ctx, metadata)
        pickle.dump(rec, files[ms >= split_ms], protocol=5)
        t = time.perf_counter()
        try:
            return real_eval(row, ctx, state, as_of=as_of, metadata=metadata, synthesizer=synthesizer)
        finally:
            st["calls"] += 1
            st["eval_s"] += time.perf_counter() - t

    re_mod.evaluate_decision, re_mod.compute_consensus = evaluate, consensus
    primary = data[args.tf]
    t0 = time.time()
    res = asyncio.run(re_mod.run_replay(list(primary), primary, data["1d"], data["1w"], fng, warmup_bars=500,
                                        timeframe=args.tf))
    for f in files.values():
        f.close()
    rows = [{k: getattr(r, k, None) for k in L.FIELDS} for r in res]
    Path(f"{args.out}.rows.pkl").write_bytes(pickle.dumps([r for r in rows if r["timestamp"] < split_ms]))
    print(f"{len(rows)} bar results, {st['calls']} decisions ({1e6 * st['eval_s'] / max(st['calls'], 1):.0f} us each) "
          f"in {time.time() - t0:.0f}s -> {args.out}.cap")


if __name__ == "__main__":
    main()
