"""
Replay one version of the live signal logic on 4h Binance history (step 1 of 2).

    python backtest/live_logic_replay.py --backend <path to a backend/ checkout> --out <file.pkl> [--gate on|off] [--blowoff off|takeover|full]
        [--zbase current|G|F1|G1d|K1d] [--tf 4h|1d]

The 4h timeframe is what the executor trades (--tf 1d replays the daily chart as the traded
timeframe instead). The script imports the replay engine, engines and synthesizer from
``--backend``, so the same data can be run through an older commit (e.g. a git worktree)
and through today's code. Data comes from this
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
DATA_START_1D_PRIMARY = "2019-01-01"   # --tf 1d: 500 daily bars of warm-up end before W1
DATA_END = "2026-03-29"            # end of W9; the holdout starts here
FIELDS = ("timestamp", "symbol", "price", "signal", "raw_signal", "regime", "confluence_label",
          "conditions_met", "conditions_total", "signal_status", "zscore", "heat", "deviation_pct")


def _zbase(rcce, name):
    """Swap the engine's z function in-process (docs/reviews/z-baseline-study.md,
    docs/reviews/z-daily-study.md).
    current: today's re-centred z. G: today's z, set to 0 where its sign contradicts the raw
    deviation from the line. F1: no re-centring, z = dev / stdev(dev).
    G1d / K1d: daily charts only (4h z is today's). G1d is G. K1d clips the re-centring:
    z = (dev - clip(mean(dev), -stdev(dev), +stdev(dev))) / stdev(dev)."""
    import numpy as np
    original = rcce._calc_zscore_hybrid

    def dev_of(close, len_ma, len_reg):
        logp = np.log(np.maximum(close, rcce._EPS))
        reg = rcce._linreg(logp, len_reg)
        return logp - np.where(np.isnan(reg), rcce._sma(logp, len_ma), reg)

    def guarded(close, len_ma, len_reg, z_smooth=1, z_scale=1.0):
        z = original(close, len_ma, len_reg, z_smooth, z_scale)
        dev = dev_of(close, len_ma, len_reg)
        bad = np.isfinite(dev) & np.isfinite(z) & (np.sign(dev) * np.sign(z) < 0)
        return np.where(bad, 0.0, z)

    def no_recentre(close, len_ma, len_reg, z_smooth=1, z_scale=1.0):
        dev = dev_of(close, len_ma, len_reg)
        std = rcce._stdev_nan_safe(dev, len_ma)
        zero = (std < rcce._EPS) | np.isnan(std)
        z = np.where(zero, 0.0, dev / np.where(zero, 1.0, std)) * z_scale
        return rcce._sma_nan_safe(z, z_smooth) if z_smooth > 1 else z

    def capped(close, len_ma, len_reg, z_smooth=1, z_scale=1.0):
        dev = dev_of(close, len_ma, len_reg)
        mean = rcce._sma_nan_safe(dev, len_ma)
        std = rcce._stdev_nan_safe(dev, len_ma)
        zero = (std < rcce._EPS) | np.isnan(std)
        safe = np.where(zero, 1.0, std)
        z = np.where(zero, 0.0, (dev - np.clip(mean, -safe, safe)) / safe) * z_scale
        return rcce._sma_nan_safe(z, z_smooth) if z_smooth > 1 else z

    if name in ("G1d", "K1d"):
        import scanner
        variant, engine = (guarded if name == "G1d" else capped), scanner.compute_rcce

        def daily_only(ohlcv, *a, **k):
            ts = ohlcv["timestamp"]
            daily = len(ts) > 1 and float(ts[-1]) - float(ts[-2]) >= 43_200_000   # 4h series keep today's z
            rcce._calc_zscore_hybrid = variant if daily else original
            try:
                return engine(ohlcv, *a, **k)
            finally:
                rcce._calc_zscore_hybrid = original

        scanner.compute_rcce = daily_only
        return
    rcce._calc_zscore_hybrid = {"current": original, "G": guarded, "F1": no_recentre}[name]


def _off_high_90(rows, primary, tf_ms):
    """Close vs the highest close of the last 90 bars of the traded timeframe (this bar included), in %."""
    import numpy as np
    index = {}
    for sym, d in primary.items():
        c = np.asarray(d["close"], dtype=float)
        hi = np.array([c[max(0, i - 89):i + 1].max() for i in range(len(c))])
        index[sym] = {float(t): 100.0 * (c[i] / hi[i] - 1) for i, t in enumerate(d["timestamp"])}
    for r in rows:
        r["off_high_90"] = index.get(r["symbol"], {}).get(float(r["timestamp"]) - tf_ms)


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
    ap.add_argument("--cooloff", type=float, help="cool-off release z (after-the-spike study): 0 or 1; omit for off")
    ap.add_argument("--cooloff-source", choices=("own", "daily"), default="own")
    ap.add_argument("--symbols", choices=("primary", "secondary"), default="primary")
    ap.add_argument("--blowoff", choices=("off", "takeover", "full"),
                    help="Overheated fix (docs/reviews/overheated-regime.md): off, score only, or score + 2-bar entry")
    ap.add_argument("--zbase", choices=("current", "G", "F1", "G1d", "K1d"), default="current",
                    help="z baseline variant (docs/reviews/z-baseline-study.md, z-daily-study.md)")
    ap.add_argument("--tf", choices=("4h", "1d"), default="4h", help="traded (primary) timeframe")
    args = ap.parse_args(argv)
    bh = _bh()
    data = {tf: {} for tf in ("4h", "1d", "1w")}
    start = {"4h": DATA_START, "1d": DATA_START, "1w": "2019-01-07"}
    if args.tf == "1d":
        start["1d"] = DATA_START_1D_PRIMARY
    symbols = SYMBOLS
    if args.symbols == "secondary":
        from backtest.larsson_scenarios import SECONDARY_FILE
        symbols = json.loads(SECONDARY_FILE.read_text())["symbols"]
    for s in symbols:
        for tf in data:
            if args.tf == "1d" and tf == "4h":
                continue
            d = bh.load(f"{s}USDT", tf, start[tf], DATA_END)
            if d is not None:
                data[tf][f"{s}/USDT"] = d
    fng = _fear_greed()
    sys.path.insert(0, str(Path(args.backend).resolve()))
    if args.gate:
        import engines.rcce_engine as rcce
        rcce.MARKDOWN_TREND_GATE = args.gate == "on"
    if args.blowoff:
        import engines.rcce_engine as rcce
        rcce.BLOWOFF_TAKEOVER = args.blowoff != "off"
        rcce.BLOWOFF_ENTRY_BARS = 2 if args.blowoff == "full" else rcce.MIN_REGIME_BARS
    if args.cooloff is not None:
        import engines.rcce_engine as rcce
        rcce.COOL_OFF_RELEASE_Z = args.cooloff
        rcce.COOL_OFF_SOURCE = args.cooloff_source
    import engines.rcce_engine as rcce
    _zbase(rcce, args.zbase)
    from backtest.replay_engine import run_replay
    from candle_snapshot import TF_MS
    primary = data[args.tf]
    t0 = time.time()
    res = asyncio.run(run_replay(list(primary), primary, data["1d"], data["1w"], fng, warmup_bars=500,
                                 timeframe=args.tf))
    rows = [{k: getattr(r, k, None) for k in FIELDS} for r in res]
    _off_high_90(rows, primary, TF_MS[args.tf])
    Path(args.out).write_bytes(pickle.dumps(rows))
    print(f"{len(rows)} bar results in {time.time() - t0:.0f}s -> {args.out}")


if __name__ == "__main__":
    main()
