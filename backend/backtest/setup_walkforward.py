"""Frozen-rule historical forward replay; never writes to the live paper ledger.

python -m backtest.setup_walkforward --candles history.json --funding funding.json --output report.json
Missing historical books stay unavailable in strict mode. Scenario books explicitly
assume a constant spread and sufficient depth; they are not historical observations.
"""

from __future__ import annotations
import argparse
import asyncio
import copy
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from candle_snapshot import closed_candles
from paper_setups import ACTIVE, PaperLedger, initial_state, summarize
from setup_research_service import apply_research_cycle
from trading_setups import PARAMETERS, UNIVERSE, VERSION
from backtest.replay_engine import run_replay


class ReplayLedger(PaperLedger):
    """Memory storage adapter; inherits production advance/cancellation semantics."""

    def __init__(self):
        self.all = {}
        self.processing = {}

    def records(self, limit=None):
        return list(self.processing.values())

    def observe(self, contract):
        if contract["id"] in self.all:
            return self.all[contract["id"]]
        state = initial_state(contract)
        if state["status"] in ("pending", "scheduled") and any(
            r["contract"]["symbol"] == contract["symbol"]
            and r["contract"]["strategy"] == contract["strategy"]
            and r["state"]["status"] in ACTIVE
            for r in self.processing.values()
        ):
            state.update(
                status="blocked",
                reason="An earlier episode for this symbol/strategy is still active",
            )
        r = dict(contract=copy.deepcopy(contract), state=state)
        self.all[contract["id"]] = r
        self._index(r)
        return r

    def _index(self, r):
        k = r["contract"]["id"]
        s = r["state"]
        if s["status"] in ACTIVE or (
            s["status"] == "closed" and not s["funding_complete"]
        ):
            self.processing[k] = r
        else:
            self.processing.pop(k, None)

    def save_state(self, contract, previous, state, as_of):
        r = self.all[contract["id"]]
        r["state"] = state
        self._index(r)


def scenario_book(price, as_of, spread_bps):
    if spread_bps is None:
        return None
    return dict(
        bid=price * (1 - spread_bps / 20000),
        ask=price * (1 + spread_bps / 20000),
        observed_at=as_of,
        bid_depth_usd=100000,
        ask_depth_usd=100000,
        historical_observation=False,
        assumption="Constant spread and adequate depth",
    )


def summarize_rows(rows):
    summary = summarize(rows)
    summary["reasons"] = dict(Counter(r["state"]["reason"] for r in rows))
    return summary


def report_scenario(ledger, start, end):
    rows = list(ledger.all.values())
    groups = {}
    for strategy in sorted({r["contract"]["strategy"] for r in rows}):
        selected = [r for r in rows if r["contract"]["strategy"] == strategy]
        groups[strategy] = dict(
            summary=summarize_rows(selected),
            assets={
                s: summarize_rows([r for r in selected if r["contract"]["symbol"] == s])
                for s in UNIVERSE
            },
            cto_cohorts={
                d: summarize_rows(
                    [
                        r
                        for r in selected
                        if (r["contract"].get("cto_reference") or {}).get(
                            "direction", "unavailable"
                        )
                        == d
                    ]
                )
                for d in ("up", "down", "neutral", "unavailable")
            },
        )
    windows = []
    window_start = start
    while window_start < end:
        stop = min(end, window_start + 90 * 86400)
        # Attribute by first observation; exclude outcomes reaching another window.
        window_rows = [
            r for r in rows if window_start <= r["contract"]["observed_at"] < stop
        ]
        crossing = [
            r
            for r in window_rows
            if r["state"].get("exit_at") is not None and r["state"]["exit_at"] >= stop
        ]
        scored = [r for r in window_rows if r not in crossing]
        windows.append(
            dict(
                start=window_start,
                end=stop,
                purged_crossing_outcomes=len(crossing),
                strategies={
                    s: summarize_rows(
                        [r for r in scored if r["contract"]["strategy"] == s]
                    )
                    for s in groups
                },
            )
        )
        window_start = stop
    return dict(
        strategies=groups,
        windows=windows,
        trades=[r for r in rows if r["state"].get("entry_at") is not None],
        observations=len(rows),
    )


async def run(
    data, funding, *, as_of_ms, latency_seconds=60, progress=None, decision_bars=None
):
    if not 0 < latency_seconds < 14400:
        raise ValueError("Positive sub-bar observation latency required")
    scenarios = {
        "strict_missing_books": None,
        "assumed_2bps_spread": 2.0,
        "assumed_10bps_spread": 9.999999,
    }
    caches = {
        name: SimpleNamespace(paper_ledger=ReplayLedger(), results={})
        for name in scenarios
    }
    times = []

    def observe(close_at, rows, daily):
        now = close_at + latency_seconds
        if now > as_of_ms / 1000:
            return
        for row in rows + daily:
            if row.get("signal_bar_close_time", close_at) > close_at:
                raise ValueError("Decision contains a candle that has not closed")
        times.append(now)
        base = {}
        for symbol in UNIVERSE:
            candles = closed_candles(data["4h"][symbol], "4h", close_at * 1000)
            candles = {k: v[-120:] for k, v in candles.items()}
            bars = [
                dict(
                    time=float(candles["timestamp"][i]) / 1000,
                    **{
                        k: float(candles[k][i])
                        for k in ("open", "high", "low", "close")
                    },
                )
                for i in range(len(candles["close"]))
            ]
            # Historical settlements become visible only after settlement time.
            rates = [
                f
                for f in funding.get(symbol, [])
                if now - 10 * 86400 <= f["time"] <= now
            ]
            base[symbol] = dict(candles=candles, bars=bars, funding=rates)
        for name, spread in scenarios.items():
            cache = caches[name]
            cache.results = {"4h": copy.deepcopy(rows), "1d": copy.deepcopy(daily)}
            market = {
                s: dict(
                    v, book=scenario_book(float(v["candles"]["close"][-1]), now, spread)
                )
                for s, v in base.items()
            }
            apply_research_cycle(cache, market, as_of=now)

    if decision_bars is None:
        results = await run_replay(
            list(UNIVERSE),
            data["4h"],
            data["1d"],
            data["1w"],
            {},
            warmup_bars=599,
            as_of_ms=as_of_ms,
            on_decision_bar=observe,
            on_progress=progress,
        )
        symbol_decisions = len(results)
    else:
        symbol_decisions = 0
        previous = -1
        for i, bar in enumerate(decision_bars):
            if bar["time"] <= previous:
                raise ValueError("Decision cache must be chronological and unique")
            previous = bar["time"]
            observe(bar["time"], bar["rows"], bar["daily"])
            symbol_decisions += len(bar["rows"])
            if progress and i % 100 == 0:
                progress(i / len(decision_bars) * 100, "Simulating frozen setup rules")
    if not times:
        raise ValueError("No replay decisions")
    return dict(
        study="setup-walkforward-1",
        strategy_version=VERSION,
        parameters=PARAMETERS,
        as_of_ms=as_of_ms,
        decision_bars=len(times),
        symbol_decisions=symbol_decisions,
        start=times[0],
        end=times[-1],
        latency_seconds=latency_seconds,
        validation_status="exploratory_historical_replay",
        promotion_approved=False,
        context_complete=False,
        limitations=[
            "Historical books unavailable; scenario spread/depth are assumptions.",
            "Historical external scanner context unavailable; technical-only shared decision pipeline.",
            "Consensus computed over fixed BTC/ETH/SOL universe, not the full historical live universe.",
            "No training or parameter selection: frozen rules tested in successive 90-day windows.",
            "Rules were designed with prior historical exposure; these are not untouched holdout results.",
            "First observed per completed bar at fixed latency; intrabar polling/context changes not reconstructed.",
            "OHLCV fills use production conservative rules; funding uses fixed entry notional and bar-close exit accounting.",
            "CTO cohorts are descriptive selection effects, not causal evidence for adding a filter.",
            "Ongoing end-of-history episodes remain censored; no artificial close.",
        ],
        scenarios={
            name: report_scenario(c.paper_ledger, times[0], times[-1] + 1)
            for name, c in caches.items()
        },
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--candles", type=Path, required=True)
    p.add_argument("--funding", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--as-of-ms", type=float, required=True)
    p.add_argument(
        "--decisions", type=Path, help="Optional cached causal decision bars as JSONL"
    )
    args = p.parse_args()
    raw = args.candles.read_bytes()
    fund = args.funding.read_bytes()
    data = {
        tf: {s: {k: np.asarray(v) for k, v in b.items()} for s, b in syms.items()}
        for tf, syms in json.loads(raw).items()
    }
    decisions = (
        [json.loads(line) for line in args.decisions.read_text().splitlines()]
        if args.decisions
        else None
    )
    report = asyncio.run(
        run(
            data,
            json.loads(fund),
            as_of_ms=args.as_of_ms,
            decision_bars=decisions,
            progress=lambda n, s: print(round(n, 1), s, flush=True),
        )
    )
    report["inputs"] = {
        "candles_sha256": hashlib.sha256(raw).hexdigest(),
        "funding_sha256": hashlib.sha256(fund).hexdigest(),
    }
    if args.decisions:
        report["inputs"]["decisions_sha256"] = hashlib.sha256(
            args.decisions.read_bytes()
        ).hexdigest()
    report["created_utc"] = datetime.now(timezone.utc).isoformat()
    report["data_coverage"] = {
        tf: {
            s: dict(
                bars=len(b["timestamp"]),
                first_open_ms=float(b["timestamp"][0]),
                last_open_ms=float(b["timestamp"][-1]),
                non_contiguous_steps=int(
                    np.sum(
                        np.diff(b["timestamp"])
                        != {"4h": 14400000, "1d": 86400000, "1w": 604800000}[tf]
                    )
                ),
            )
            for s, b in syms.items()
        }
        for tf, syms in data.items()
    }
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
