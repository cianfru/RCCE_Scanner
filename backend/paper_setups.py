"""Forward-only research ledger and conservative OHLCV paper simulation."""

from __future__ import annotations
import copy
import json
import math
import os
import sqlite3
from collections import Counter
from pathlib import Path
from statistics import mean
from trading_setups import TF_SECONDS, execution_quality, finite

ACTIVE = {"pending", "scheduled", "open"}


def initial_state(contract):
    state = dict(
        status=contract["status"],
        reason=contract["reason"],
        updated_at=contract["observed_at"],
        cursor=math.ceil(contract["observed_at"] / TF_SECONDS) * TF_SECONDS,
        entry=None,
        entry_at=None,
        exit=None,
        exit_at=None,
        bars_held=0,
        mfe=0.0,
        mae=0.0,
        ambiguous=False,
        funding_complete=False,
        net_return=None,
        net_r=None,
    )
    if contract.get("entry_mode") == "next_open" and contract["status"] == "pending":
        state.update(
            status="scheduled",
            trigger_at=contract["observed_at"],
            trigger_candle_close=contract["reference_close"],
            entry_due=math.ceil(contract["observed_at"] / TF_SECONDS) * TF_SECONDS,
            trigger_execution=copy.deepcopy(contract["execution"]),
            reason="Closed-candle setup confirmed; next opening precommitted",
        )
    return state


def finish(contract, state, price, exit_at, reason):
    p = contract["parameters"]
    entry = state["entry"]
    cost = state["slippage_bps"] / 10000
    exit_price = price * (1 - cost)
    qty = p["paper_notional_usd"] / entry
    fee = qty * (entry + exit_price) * p["fee_bps"] / 10000
    before_funding = (qty * (exit_price - entry) - fee) / p["paper_notional_usd"]
    state.update(
        status="closed",
        reason=reason,
        exit=exit_price,
        exit_at=exit_at,
        gross_return=(price - state["raw_entry"]) / state["raw_entry"],
        fees_usd=fee,
        before_funding_return=before_funding,
    )


def settle_funding(contract, state, events):
    if state["status"] != "closed" or state["funding_complete"]:
        return
    expected = range(
        (int(state["entry_at"]) // 3600 + 1) * 3600,
        (int(state["exit_at"]) // 3600) * 3600 + 1,
        3600,
    )
    rates = {
        int(e["time"]): e["rate"]
        for e in events
        if finite(e.get("time")) and finite(e.get("rate"))
    }
    missing = [t for t in expected if t not in rates]
    state["missing_funding_hours"] = len(missing)
    if missing:
        return
    funding = sum(rates[t] for t in expected)
    net = state["before_funding_return"] - funding
    risk_fraction = (state["entry"] - contract["stop"]) / state["entry"]
    state.update(
        funding_complete=True,
        funding_cost_fraction=funding,
        funding_usd=funding * contract["parameters"]["paper_notional_usd"],
        net_return=net,
        net_r=net / risk_fraction if risk_fraction > 0 else None,
        funding_model="Realized hourly rates on fixed entry notional; settlement mark not reconstructed",
    )


def advance(contract, previous, bars, book, funding, *, as_of):
    """Consume only completed, ordered bars; never backdate a observed trigger fill."""
    state = copy.deepcopy(previous)
    if state["status"] == "closed":
        settle_funding(contract, state, funding)
        state["updated_at"] = as_of
        return state
    if state["status"] not in ACTIVE:
        return state
    if bars is None:
        state["paused_reason"] = "Candle feed unavailable"
        return state
    state.pop("paused_reason", None)
    p = contract["parameters"]
    for bar in sorted(bars, key=lambda b: b["time"]):
        start = bar["time"]
        end = start + TF_SECONDS
        if end > as_of or start < state["cursor"]:
            continue
        if start != state["cursor"]:
            state.update(
                status="data_gap",
                reason="Missing intervening candle; outcome not scored",
            )
            break
        values = [bar.get(k) for k in ("open", "high", "low", "close")]
        if (
            not all(finite(v) and v > 0 for v in values)
            or bar["low"] > min(bar["open"], bar["close"])
            or bar["high"] < max(bar["open"], bar["close"])
        ):
            state.update(
                status="data_gap", reason="Invalid market candle; outcome not scored"
            )
            break
        state["cursor"] = end
        state["last_bar"] = dict(bar)
        if state["status"] == "pending":
            if end > contract["expires_at"]:
                state.update(
                    status="expired", reason="Trigger did not occur before expiry"
                )
                break
            if bar["low"] <= contract["stop"]:
                state.update(
                    status="invalidated", reason="Structure failed before trigger"
                )
                break
            if bar["close"] > contract["trigger"]:
                execution = execution_quality(book, as_of=as_of, params=p)
                if as_of > contract["expires_at"]:
                    state.update(
                        status="missed", reason="Trigger observed after expiry"
                    )
                    break
                if execution["status"] != "ready":
                    state.update(
                        status="missed",
                        reason="Trigger observed without acceptable fresh execution data",
                    )
                    break
                state.update(
                    status="scheduled",
                    reason="Trigger observed; next opening fill precommitted",
                    trigger_at=as_of,
                    trigger_candle_close=end,
                    entry_due=math.ceil(as_of / TF_SECONDS) * TF_SECONDS,
                    trigger_execution=execution,
                )
                if state["entry_due"] > contract["expires_at"]:
                    state.update(
                        status="expired",
                        reason="Next eligible entry opening falls after expiry",
                    )
                continue
        if state["status"] == "scheduled":
            if start < state["entry_due"]:
                continue
            raw = bar["open"]
            lower, upper = contract["entry_zone"]
            if not lower <= raw <= upper:
                state.update(
                    status="missed", reason="Opening gap outside frozen entry zone"
                )
                break
            slip = p["slippage_bps"] + state["trigger_execution"]["spread_bps"] / 2
            entry = raw * (1 + slip / 10000)
            risk = entry - contract["stop"]
            reward = contract["target"] * (1 - slip / 10000) - entry
            fee = (entry + contract["target"]) * p["fee_bps"] / 10000
            if risk <= 0 or (reward - fee) / risk < p["min_reward_r"]:
                state.update(
                    status="missed",
                    reason="Opening fill fails reward/risk after assumed costs",
                )
                break
            state.update(
                status="open",
                reason="Simulated precommitted opening fill",
                entry=entry,
                raw_entry=raw,
                entry_at=start,
                slippage_bps=slip,
            )
        if state["status"] == "open":
            active_stop = state.get("active_stop", contract["stop"])
            stop = bar["low"] <= active_stop
            target = bar["high"] >= contract["target"]
            state["bars_held"] += 1
            state["ambiguous"] = state["ambiguous"] or (stop and target)
            if stop:
                raw_exit = min(bar["open"], active_stop)
                state["mae"] = min(state["mae"], raw_exit / state["entry"] - 1)
                finish(
                    contract,
                    state,
                    raw_exit,
                    end,
                    (
                        "Protected stop hit"
                        if active_stop > contract["stop"]
                        else "Stop hit; conservative ordering"
                        if target
                        else "Stop hit"
                    ),
                )
            else:
                state["mae"] = min(state["mae"], bar["low"] / state["entry"] - 1)
                favorable = (
                    min(bar["high"], contract["target"]) if target else bar["high"]
                )
                state["mfe"] = max(state["mfe"], favorable / state["entry"] - 1)
                if target:
                    finish(contract, state, contract["target"], end, "Target hit")
                elif state["bars_held"] >= p["max_hold_bars"]:
                    finish(contract, state, bar["close"], end, "Time exit")
            if state["status"] == "open":
                # Only completed closes can arm protection, and the new stop
                # takes effect next bar. Never use a bar's high to backdate BE.
                risk = state["entry"] - contract["stop"]
                mode = p.get("protection", "none")
                held = state["bars_held"] >= p.get("protection_min_bars", 0)
                arm = (
                    bar["close"] >= state["entry"] * 1.05
                    if mode in ("be_5pct", "legacy_be_5pct")
                    else bar["close"] >= state["entry"] + 2 * risk
                )
                if held and mode in ("be_5pct", "legacy_be_5pct", "be_2r") and arm:
                    # Cost-aware level compensates estimated entry/exit fees
                    # and exit slippage, but not unknown future funding/gaps.
                    fee = p["fee_bps"] / 10000
                    slip = state["slippage_bps"] / 10000
                    level = state["entry"] * (1 + fee) / ((1 - slip) * (1 - fee))
                    if mode == "legacy_be_5pct":
                        level = state["raw_entry"]
                    state["active_stop"] = max(active_stop, level)
                elif held and mode == "trail_2r" and arm:
                    state["active_stop"] = max(
                        active_stop, bar["close"] - 2 * contract["atr"]
                    )
            if state["status"] == "closed":
                settle_funding(contract, state, funding)
                break
    if state["status"] in ACTIVE and state["cursor"] + TF_SECONDS <= as_of:
        state["paused_reason"] = "Awaiting missing completed candles"
        state["updated_at"] = as_of
        return state
    if state["status"] == "pending" and as_of > contract["expires_at"]:
        state.update(status="expired", reason="Untriggered setup expired")
    state["updated_at"] = as_of
    return state


def summarize(records):
    counts = dict(Counter(r["state"]["status"] for r in records))
    closed = [r for r in records if r["state"]["status"] == "closed"]
    complete = [r for r in closed if r["state"]["funding_complete"]]

    def avg(key):
        return mean(r["state"][key] for r in complete) if complete else None

    # Fixed one-unit-risk sequence; diagnostic realized drawdown, not portfolio equity.
    equity = peak = drawdown = 0.0
    for r in sorted(
        complete, key=lambda r: (r["state"]["exit_at"], r["contract"]["id"])
    ):
        equity += r["state"]["net_r"]
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return dict(
        observations=len(records),
        states=counts,
        closed_trades=len(closed),
        fully_costed_trades=len(complete),
        funding_coverage=len(complete) / len(closed) if closed else None,
        expectancy=avg("net_return"),
        expectancy_r=avg("net_r"),
        losing_fraction=sum(r["state"]["net_return"] <= 0 for r in complete)
        / len(complete)
        if complete
        else None,
        mean_mfe=avg("mfe"),
        mean_mae=avg("mae"),
        realized_drawdown_r=drawdown if complete else None,
        ambiguous_trades=sum(r["state"]["ambiguous"] for r in closed),
        label="Forward paper observations; unvalidated; fully net metrics exclude unknown funding",
    )


class PaperLedger:
    def __init__(self, path=None):
        root = Path(
            os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
            or Path(__file__).parent / "data"
        )
        path = Path(
            path
            or os.environ.get("PAPER_SETUPS_DB_PATH", str(root / "paper_setups.db"))
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS setups(id TEXT PRIMARY KEY,symbol TEXT,strategy TEXT,observed_at REAL,contract TEXT NOT NULL,state TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS paper_events(id INTEGER PRIMARY KEY,setup_id TEXT,observed_at REAL,event TEXT,payload TEXT);
          CREATE INDEX IF NOT EXISTS paper_symbol_strategy ON setups(symbol,strategy,observed_at);
        """)

    def records(self, limit=None):
        sql = "SELECT contract,state FROM setups ORDER BY observed_at DESC,id"
        rows = self.db.execute(
            sql + (" LIMIT ?" if limit else ""), (limit,) if limit else ()
        )
        return [
            dict(contract=json.loads(r["contract"]), state=json.loads(r["state"]))
            for r in rows
        ]

    def observe(self, contract):
        existing = self.db.execute(
            "SELECT contract,state FROM setups WHERE id=?", (contract["id"],)
        ).fetchone()
        if existing:
            return dict(
                contract=json.loads(existing["contract"]),
                state=json.loads(existing["state"]),
            )
        state = initial_state(contract)
        active = self.db.execute(
            "SELECT state FROM setups WHERE symbol=? AND strategy=?",
            (contract["symbol"], contract["strategy"]),
        )
        if state["status"] in ("pending", "scheduled") and any(
            json.loads(r[0])["status"] in ACTIVE for r in active
        ):
            state.update(
                status="blocked",
                reason="An earlier episode for this symbol/strategy is still active",
            )
        encode = lambda x: json.dumps(x, sort_keys=True, allow_nan=False)
        with self.db:
            self.db.execute(
                "INSERT INTO setups VALUES (?,?,?,?,?,?)",
                (
                    contract["id"],
                    contract["symbol"],
                    contract["strategy"],
                    contract["observed_at"],
                    encode(contract),
                    encode(state),
                ),
            )
            self.db.execute(
                "INSERT INTO paper_events(setup_id,observed_at,event,payload) VALUES (?,?,?,?)",
                (contract["id"], contract["observed_at"], "observed", encode(state)),
            )
        return dict(contract=contract, state=state)

    def save_state(self, contract, previous, state, as_of):
        if previous == state:
            return
        significant = any(
            previous.get(k) != state.get(k)
            for k in (
                "status",
                "funding_complete",
                "entry_at",
                "exit_at",
                "paused_reason",
                "active_stop",
            )
        )
        payload = json.dumps(state, sort_keys=True, allow_nan=False)
        with self.db:
            self.db.execute(
                "UPDATE setups SET state=? WHERE id=?", (payload, contract["id"])
            )
            if previous.get("entry_at") is None and state.get("entry_at") is not None:
                self.db.execute(
                    "INSERT INTO paper_events(setup_id,observed_at,event,payload) VALUES (?,?,?,?)",
                    (contract["id"], as_of, "entry", payload),
                )
            if significant:
                self.db.execute(
                    "INSERT INTO paper_events(setup_id,observed_at,event,payload) VALUES (?,?,?,?)",
                    (
                        contract["id"],
                        as_of,
                        "funding_complete"
                        if previous["status"] == "closed" and state["funding_complete"]
                        else "stop_updated"
                        if state.get("active_stop") != previous.get("active_stop")
                        and state["status"] == "open"
                        else state["status"],
                        payload,
                    ),
                )

    def advance_all(self, market, *, as_of):
        for record in self.records():
            c, s = record["contract"], record["state"]
            feed = market.get(c["symbol"], {})
            if s["status"] not in ACTIVE and not (
                s["status"] == "closed" and not s["funding_complete"]
            ):
                continue
            updated = advance(
                c,
                s,
                feed.get("bars"),
                feed.get("book"),
                feed.get("funding", []),
                as_of=as_of,
            )
            self.save_state(c, s, updated, as_of)

    def cancel_pending(self, symbol, reason, *, as_of):
        for r in self.records():
            if r["contract"]["symbol"] == symbol and r["state"]["status"] in (
                "pending",
                "scheduled",
            ):
                updated = dict(
                    r["state"], status="cancelled", reason=reason, updated_at=as_of
                )
                self.save_state(r["contract"], r["state"], updated, as_of)

    def report(self):
        records = self.records()
        grouped = {}
        for r in records:
            key = r["contract"]["version"] + ":" + r["contract"]["strategy"]
            grouped.setdefault(key, []).append(r)
        return dict(
            mode="paper",
            validation_status="unvalidated",
            strategies={
                key: dict(
                    summary=summarize(rows),
                    assets={
                        s: summarize([r for r in rows if r["contract"]["symbol"] == s])
                        for s in sorted({r["contract"]["symbol"] for r in rows})
                    },
                    regimes={
                        g: summarize([r for r in rows if r["contract"]["regime"] == g])
                        for g in sorted(
                            {r["contract"]["regime"] for r in rows}, key=str
                        )
                    },
                )
                for key, rows in grouped.items()
            },
            records=records[:30],
            active_records=[r for r in records if r["state"]["status"] in ACTIVE],
            assumptions="Long-only fixed-notional independent research episodes; no combined portfolio return. Same-bar stop/target uses stop first. Funding uses entry notional. Future execution uses modeled costs.",
        )

    def events(self, setup_id):
        return [
            dict(r)
            for r in self.db.execute(
                "SELECT * FROM paper_events WHERE setup_id=? ORDER BY id", (setup_id,)
            )
        ]

    def close(self):
        self.db.close()
