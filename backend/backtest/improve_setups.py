"""Controlled development sweep. Selection is made before validation is run."""

import argparse, copy, json, math, statistics
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from candle_snapshot import closed_candles
from setup_v2 import features, candidate
from setup_research_service import apply_research_cycle
from backtest.setup_walkforward import ReplayLedger, scenario_book
from paper_setups import summarize
from trading_setups import UNIVERSE


def configs():
    return [
        dict(
            name=f"{family}-h{hold}-r{target}",
            family=family,
            hold=hold,
            target=target,
            protection="none",
        )
        for family in ("trend", "pullback", "recovery", "breakout")
        for hold in (12, 24, 42)
        for target in (2, 3)
    ]


def result(ledger):
    rows = list(ledger.all.values())
    m = summarize(rows)
    trades = [
        r
        for r in rows
        if r["state"]["status"] == "closed" and r["state"]["funding_complete"]
    ]
    values = [r["state"]["net_r"] for r in trades]
    # Selection heuristic only: no confidence claim for correlated trades.
    score = (
        (
            statistics.mean(values)
            - statistics.stdev(values) / math.sqrt(len(values))
            - 0.002 * m["realized_drawdown_r"]
        )
        if len(values) >= 30
        else -999
    )
    assets = {
        s: summarize([r for r in rows if r["contract"]["symbol"] == s])
        for s in UNIVERSE
    }
    windows = {}
    for r in rows:
        windows.setdefault(
            int(r["contract"]["observed_at"] // (90 * 86400)), []
        ).append(r)
    return dict(
        summary=m,
        assets=assets,
        windows={str(k): summarize(v) for k, v in windows.items()},
        selection_score=score,
        exit_reasons=dict(
            __import__("collections").Counter(r["state"]["reason"] for r in trades)
        ),
        trades=[r for r in rows if r["state"].get("entry_at") is not None],
    )


def run(data, funding, bars, profiles, spread=2):
    caches = {
        p["name"]: SimpleNamespace(paper_ledger=ReplayLedger(), results={})
        for p in profiles
    }
    for i, b in enumerate(bars):
        now = b["time"] + 60
        market = {}
        fs = {}
        daily = {r["symbol"]: r for r in b["daily"]}
        for row in b["rows"]:
            s = row["symbol"]
            c = closed_candles(data["4h"][s], "4h", b["time"] * 1000)
            c = {k: v[-120:] for k, v in c.items()}
            book = scenario_book(float(c["close"][-1]), now, spread)
            market[s] = dict(
                candles=c,
                book=book,
                bars=[
                    dict(
                        time=float(c["timestamp"][j]) / 1000,
                        **{k: float(c[k][j]) for k in ("open", "high", "low", "close")},
                    )
                    for j in range(max(0, len(c["close"]) - 3), len(c["close"]))
                ],
                funding=[
                    x
                    for x in funding.get(s, [])
                    if now - 12 * 86400 <= x["time"] <= now
                ],
            )
            fs[s] = features(row, daily.get(s), c, book, now)
        for p in profiles:
            cache = caches[p["name"]]
            cache.results = {
                "4h": copy.deepcopy(b["rows"]),
                "1d": copy.deepcopy(b["daily"]),
            }
            builder = lambda row, d, c, book, as_of: candidate(
                row, d, fs[row["symbol"]], p, as_of
            )
            apply_research_cycle(cache, market, as_of=now, builder=builder)
        if i % 100 == 0:
            print(f"{i}/{len(bars)}", flush=True)
    return {
        p["name"]: dict(config=p, **result(caches[p["name"]].paper_ledger))
        for p in profiles
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--decisions", default="setup-decisions.jsonl")
    p.add_argument("--data-root", type=Path, default=Path(".."))
    p.add_argument(
        "--stage", choices=["development", "validation", "late", "all"], required=True
    )
    p.add_argument("--profiles", type=Path)
    p.add_argument("--spread", type=float, default=2)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    root = args.data_root
    raw = json.loads((root / "setup-history.json").read_text())
    data = {
        tf: {s: {k: np.asarray(v) for k, v in b.items()} for s, b in syms.items()}
        for tf, syms in raw.items()
    }
    funding = json.loads((root / "setup-funding.json").read_text())
    bars = [json.loads(x) for x in (root / args.decisions).read_text().splitlines()]
    n = len(bars)
    a = int(0.6 * n)
    b = int(0.8 * n)
    ranges = {
        "development": (0, a),
        "validation": (a, b),
        "late": (b, n),
        "all": (0, n),
    }
    start, end = ranges[args.stage]
    profiles = json.loads(args.profiles.read_text()) if args.profiles else configs()
    results = run(data, funding, bars[start:end], profiles, args.spread)
    report = dict(
        stage=args.stage,
        span=[bars[start]["time"], bars[end - 1]["time"]],
        spread_bps=args.spread,
        results=results,
        limits="Historical external context and books missing. Separate chronological evaluation, but history previously exposed. No live validation claim.",
    )
    args.output.write_text(json.dumps(report, indent=2))
    print(
        [
            (
                k,
                round(v["selection_score"], 3),
                v["summary"]["fully_costed_trades"],
                v["summary"]["expectancy_r"],
            )
            for k, v in sorted(results.items(), key=lambda x: -x[1]["selection_score"])
        ][:10],
        flush=True,
    )


if __name__ == "__main__":
    main()
