"""
Replay one version of the live signal logic on 4h Binance history (step 1 of 2).

    python backtest/live_logic_replay.py --backend <path to a backend/ checkout> --out <file.pkl> [--gate on|off]

The 4h timeframe is what the executor trades. The script imports the replay engine,
engines and synthesizer from ``--backend``, so the same data can be run through an
older commit (e.g. a git worktree) and through today's code. Data comes from this
checkout's binance_history (loaded by file path) so every version sees identical bars.
Windows 1-9 only (ends 2026-03-29); the holdout is never replayed. Output is a list of
plain dicts, consumed by backtest/live_logic_check.py.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import pickle
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "DOGE", "DOT", "LINK"]   # the study's primary set
DATA_START = "2020-10-01"          # 4h warm-up before W1 (2021-10-21)
DATA_END = "2026-03-29"            # end of W9; the holdout starts here
FIELDS = ("timestamp", "symbol", "price", "signal", "raw_signal", "regime", "confluence_label",
          "conditions_met", "conditions_total", "signal_status", "zscore", "heat")


def _bh():
    spec = importlib.util.spec_from_file_location("binance_history_file", HERE / "binance_history.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fear_greed():
    raw = json.loads(urllib.request.urlopen("https://api.alternative.me/fng/?limit=0&format=json", timeout=30).read())
    return {datetime.fromtimestamp(int(x["timestamp"]), tz=timezone.utc).strftime("%Y-%m-%d"): int(x["value"])
            for x in raw["data"]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--backend", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--gate", choices=("on", "off"))
    args = ap.parse_args(argv)
    bh = _bh()
    data = {tf: {} for tf in ("4h", "1d", "1w")}
    for s in SYMBOLS:
        for tf in data:
            d = bh.load(f"{s}USDT", tf, DATA_START if tf != "1w" else "2019-01-07", DATA_END)
            if d is not None:
                data[tf][f"{s}/USDT"] = d
    fng = _fear_greed()
    sys.path.insert(0, str(Path(args.backend).resolve()))
    if args.gate:
        import engines.rcce_engine as rcce
        rcce.MARKDOWN_TREND_GATE = args.gate == "on"
    from backtest.replay_engine import run_replay
    t0 = time.time()
    res = asyncio.run(run_replay(list(data["4h"]), data["4h"], data["1d"], data["1w"], fng, warmup_bars=500))
    rows = [{k: getattr(r, k, None) for k in FIELDS} for r in res]
    Path(args.out).write_bytes(pickle.dumps(rows))
    print(f"{len(rows)} bar results in {time.time() - t0:.0f}s -> {args.out}")


if __name__ == "__main__":
    main()
