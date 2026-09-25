"""Chronological CTO comparison. Run: python -m backtest.cto_study --help.

Input JSON: {decisions: [scanner snapshots], candles: {symbol: [OHLCV dicts]},
funding: {symbol: [{time, rate}]}, funding_coverage: {symbol: [start,end]},
context_complete: bool}. All times are UTC seconds; candle time is OPEN time.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
from statistics import mean, stdev
from opportunities import assess_variant, ENTRIES
from candle_snapshot import TF_MS

POLICIES = [("baseline", 1), ("cto_ranking", 1)] + [(p, n) for p in ("cto_confirmation", "cto_veto") for n in (1, 2, 3)]
STUDY_VERSION = "cto-study-1"


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def outcome(row, candles, *, horizon=6, fee_bps=5, slippage_bps=5, funding=None, funding_coverage=None):
    """Next OPEN fill; fixed horizon or structural stop. Gaps fill at worse open.

    Excursions stop at exit; the stop bar's favorable extreme is excluded because
    OHLCV cannot establish its ordering relative to the stop.
    """
    close_time = row["signal_bar_close_time"]
    tf_seconds = TF_MS[row.get("timeframe", "4h")] / 1000
    observed = max(close_time, row.get("evaluated_at", close_time))
    executable = close_time + math.ceil((observed - close_time) / tf_seconds) * tf_seconds
    future = [b for b in candles if b["time"] >= executable][:horizon]
    if len(future) != horizon or future[0]["time"] != executable:
        return None
    if any(b["time"] != executable + i * tf_seconds for i, b in enumerate(future)):
        return None
    if any(not all(math.isfinite(b[k]) for k in ("open", "high", "low", "close")) or
           min(b[k] for k in ("open", "high", "low", "close")) <= 0 or
           b["low"] > min(b["open"], b["close"]) or b["high"] < max(b["open"], b["close"]) for b in future):
        return None
    sign = -1 if row.get("baseline_signal", row["signal"]) == "LIGHT_SHORT" else 1
    entry = future[0]["open"] * (1 + sign * slippage_bps / 10000)
    structural = row.get("structure") or {}
    stop = structural.get("swing_low" if sign > 0 else "swing_high")
    if stop is not None and (entry <= stop if sign > 0 else entry >= stop):
        return None  # Already invalidated before the executable entry.
    raw_exit = future[-1]["close"]
    exit_time = future[-1]["time"] + tf_seconds
    favorable = adverse = 0.0
    stopped = False
    for bar in future:
        hit = stop is not None and (bar["low"] <= stop if sign > 0 else bar["high"] >= stop)
        if hit:
            raw_exit = min(stop, bar["open"]) if sign > 0 else max(stop, bar["open"])
            exit_time = bar["time"] + tf_seconds  # Conservative funding and occupancy to bar close.
            adverse = min(0.0, sign * (raw_exit / entry - 1), adverse)
            stopped = True
            break
        adverse = min(adverse, sign * ((bar["low"] if sign > 0 else bar["high"]) / entry - 1))
        favorable = max(favorable, sign * ((bar["high"] if sign > 0 else bar["low"]) / entry - 1))
    exit_price = raw_exit * (1 - sign * slippage_bps / 10000)
    funding_known = funding_coverage is not None and funding_coverage[0] <= close_time and funding_coverage[1] >= exit_time
    funding_cost = sign * sum(x["rate"] for x in (funding or []) if executable < x["time"] <= exit_time)
    net = sign * (exit_price / entry - 1) - fee_bps / 10000 * (1 + exit_price / entry) - funding_cost
    return dict(symbol=row["symbol"], regime=row.get("regime", "UNKNOWN"),
                setup="reversal" if row.get("regime") in ("CAP", "ACCUM", "REACC") else "continuation",
                direction="short" if sign < 0 else "long", time=close_time, exit_time=exit_time,
                entry=entry, exit=exit_price, net_return=net, mfe=favorable, mae=adverse,
                stopped=stopped, funding_known=funding_known)


def metrics(trades):
    values = [t["net_return"] for t in trades]
    n = len(values)
    expectancy = mean(values) if n else None
    lower = expectancy - 1.96 * stdev(values) / math.sqrt(n) if n > 1 else None
    # An equal-weight basket per entry timestamp; no portfolio leverage assumptions.
    groups = {}
    for t in trades:
        groups.setdefault(t["time"], []).append(t["net_return"])
    equity = peak = 1.0
    drawdown = 0.0
    for ts in sorted(groups):
        equity *= max(0, 1 + mean(groups[ts]))
        peak = max(peak, equity)
        drawdown = max(drawdown, (peak - equity) / peak)
    return dict(n=n, net_expectancy=expectancy, lower_95_mean=lower,
                basket_max_drawdown=drawdown, false_signal_rate=sum(v <= 0 for v in values) / n if n else None,
                mean_mfe=mean(t["mfe"] for t in trades) if n else None,
                mean_mae=mean(t["mae"] for t in trades) if n else None,
                funding_coverage=sum(t["funding_known"] for t in trades) / n if n else 0)


def cohorts(trades):
    out = {}
    for field in ("symbol", "regime", "setup", "direction"):
        out[field] = {value: metrics([t for t in trades if t[field] == value]) for value in sorted({t[field] for t in trades})}
    return out


def evaluate(rows, dataset, policy, config, start, end):
    groups = {}
    for row in rows:
        if start <= row["signal_bar_close_time"] < end:
            groups.setdefault(row["signal_bar_close_time"], []).append(row)
    trades, missed, missing, busy = [], [], 0, {}
    for ts in sorted(groups):
        candidates = []
        for row in groups[ts]:
            if row.get("baseline_signal", row["signal"]) not in ENTRIES or row.get("signal_status") == "unavailable":
                continue
            a = assess_variant(row, *policy)
            result = outcome(row, dataset["candles"].get(row["symbol"], []),
                             horizon=config["horizon"], fee_bps=config["fee_bps"], slippage_bps=config["slippage_bps"],
                             funding=dataset.get("funding", {}).get(row["symbol"]),
                             funding_coverage=dataset.get("funding_coverage", {}).get(row["symbol"]))
            if result is None:
                missing += 1
                continue
            if result["exit_time"] >= end:
                continue  # Purge labels crossing a chronological partition boundary.
            if a["signal"] not in ENTRIES:
                missed.append(result)
                continue
            score = max(0, min(100, row.get("baseline_priority_score", row.get("priority_score", abs(row.get("signal_score", 0)))) + a["rank_adjustment"]))
            candidates.append((score, row["symbol"], result))
        available = [x for x in candidates if busy.get(x[1], 0) <= ts]
        for _, symbol, trade in sorted(available, key=lambda x: (-x[0], x[1]))[:config["top_k"]]:
            busy[symbol] = trade["exit_time"]
            trades.append(trade)
    return dict(metrics=metrics(trades), cohorts=cohorts(trades), missing_outcomes=missing,
                filtered_candidates=len(missed), filtered_winners=sum(t["net_return"] > 0 for t in missed),
                filtered_losers=sum(t["net_return"] <= 0 for t in missed),
                return_samples=[{"time": t["time"], "net_return": t["net_return"]} for t in trades])



def incremental_edge(chosen, baseline):
    """Paired weekly block bootstrap, retaining cross-asset/time clustering."""
    import random
    a, b = {}, {}
    for dest, result in ((a, chosen), (b, baseline)):
        for item in result.get("return_samples", []):
            dest.setdefault(int(item["time"] // (7 * 86400)), []).append(item["net_return"])
    blocks = sorted(a.keys() | b.keys())
    if len(blocks) < 2:
        return dict(blocks=len(blocks), lower_95=None)
    rng = random.Random(130)
    samples = []
    for _ in range(1000):
        indices = rng.choices(blocks, k=len(blocks))
        av = [v for i in indices for v in a.get(i, [])]
        bv = [v for i in indices for v in b.get(i, [])]
        if av and bv:
            samples.append(mean(av) - mean(bv))
    samples.sort()
    return dict(blocks=len(blocks), lower_95=samples[int(.025 * len(samples))] if samples else None)


def promotion_gate(report):
    """Conservative predeclared gate; never treats a technical-only replay as proof."""
    reasons = []
    if not report.get("holdout_fresh"):
        reasons.append("Final holdout is exploratory or already exposed")
    if not report.get("context_complete"):
        reasons.append("Historical external context is incomplete")
    if report["selected"][0] == "baseline":
        reasons.append("Training did not select an incremental CTO policy")
    if not report.get("recorded_parity_verified"):
        reasons.append("Recorded live/replay parity not verified")
    for split in ("validation", "holdout"):
        chosen, base = report[split]["selected"], report[split]["baseline"]
        edge = report[split].get("incremental_edge", {})
        if edge.get("blocks", 0) < 10 or (edge.get("lower_95") or -1) <= 0:
            reasons.append(f"{split}: incremental edge not established over ten weekly blocks")
        m, b = chosen["metrics"], base["metrics"]
        if m["n"] < 50 or b["n"] < 50:
            reasons.append(f"{split}: fewer than 50 entries after excluding within-asset overlap")
        if m["funding_coverage"] < 1 or b["funding_coverage"] < 1:
            reasons.append(f"{split}: missing funding history")
        if m["lower_95_mean"] is None or m["lower_95_mean"] <= 0:
            reasons.append(f"{split}: positive net expectancy not established")
        if m["net_expectancy"] is None or b["net_expectancy"] is None or m["net_expectancy"] <= b["net_expectancy"]:
            reasons.append(f"{split}: no incremental net expectancy")
        if m["basket_max_drawdown"] > b["basket_max_drawdown"]:
            reasons.append(f"{split}: drawdown worsens")
        if len(chosen["cohorts"]["symbol"]) < 3:
            reasons.append(f"{split}: fewer than three assets")
        for field in ("symbol", "regime", "setup"):
            for name, cohort in chosen["cohorts"][field].items():
                if cohort["n"] >= 10 and cohort["net_expectancy"] <= 0:
                    reasons.append(f"{split}: negative {field} cohort {name}")
    return dict(approved=not reasons, reasons=reasons)


def run_study(dataset, *, horizon=6, fee_bps=5, slippage_bps=5, top_k=3, holdout_fresh=False):
    if horizon < 1 or fee_bps <= 0 or slippage_bps <= 0 or top_k < 1:
        raise ValueError("Use positive horizon, fees, slippage and top_k")
    rows = sorted(dataset["decisions"], key=lambda r: (r["signal_bar_close_time"], r["symbol"]))
    if len({r.get("timeframe", "4h") for r in rows}) != 1:
        raise ValueError("Use one timeframe per study")
    keys = [(r["symbol"], r["signal_bar_close_time"]) for r in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate decisions: use first observed snapshot per candle")
    dates = sorted({r["signal_bar_close_time"] for r in rows})
    if len(dates) < 30:
        raise ValueError("At least 30 distinct completed decision bars are required")
    config = dict(horizon=horizon, fee_bps=fee_bps, slippage_bps=slippage_bps, top_k=top_k)
    first, val, hold, end = dates[0], dates[int(len(dates)*.6)], dates[int(len(dates)*.8)], dates[-1]+1
    train = {f"{p}:{n}": evaluate(rows, dataset, (p,n), config, first, val) for p,n in POLICIES}
    eligible = [(p,n) for p,n in POLICIES if train[f"{p}:{n}"]["metrics"]["n"] >= 20]
    selected = max(eligible, key=lambda x: train[f"{x[0]}:{x[1]}"]["metrics"]["net_expectancy"]) if eligible else ("baseline",1)
    # The choice is fixed using training only. Only baseline + chosen policy see holdout.
    validation = {f"{p}:{n}": evaluate(rows, dataset, (p,n), config, val, hold) for p,n in POLICIES}
    parity = False
    if rows and all("decision_state" in r for r in rows):
        from decision_pipeline import replay_recorded
        parity = all(replay_recorded(r)["baseline_signal"] == r.get("baseline_signal", r["signal"]) for r in rows)
    from decision_pipeline import VERSION
    report = dict(version=STUDY_VERSION, decision_version=VERSION, holdout_fresh=holdout_fresh, dataset_hash=fingerprint(dataset), config=config,
                  partitions=dict(train=[first,val], validation=[val,hold], holdout=[hold,end]),
                  context_complete=bool(dataset.get("context_complete")) and all("decision_state" in r for r in rows),
                  recorded_parity_verified=parity, selected=list(selected), train=train,
                  validation_variants=validation,
                  validation=dict(selected=validation[f"{selected[0]}:{selected[1]}"], baseline=validation["baseline:1"]),
                  holdout=dict(selected=evaluate(rows,dataset,selected,config,hold,end),
                               baseline=evaluate(rows,dataset,("baseline",1),config,hold,end)))
    report["scope"] = {"symbols": sorted({r["symbol"] for r in rows}), "timeframe": rows[0].get("timeframe", "4h")}
    for split in ("validation", "holdout"):
        report[split]["incremental_edge"] = incremental_edge(report[split]["selected"], report[split]["baseline"])
    report["promotion"] = promotion_gate(report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--horizon", type=int, default=6)
    parser.add_argument("--fee-bps", type=float, default=5)
    parser.add_argument("--slippage-bps", type=float, default=5)
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()
    dataset = json.loads(args.dataset.read_text())
    # Reserve this dataset before exposing holdout. A rerun is not an untouched test.
    lock = args.dataset.with_suffix(args.dataset.suffix + ".holdout-used")
    with lock.open("x") as stream:
        stream.write(fingerprint(dataset))
    report = run_study(dataset, horizon=args.horizon, fee_bps=args.fee_bps,
                       slippage_bps=args.slippage_bps, top_k=args.top_k, holdout_fresh=True)
    with args.output.open("x") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
    print(json.dumps(report["promotion"], indent=2))

if __name__ == "__main__":
    main()
