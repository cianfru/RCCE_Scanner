"""
exit_shadow.py
~~~~~~~~~~~~~~
Forward shadow log for RCCE exits (research only; never trades, never changes a
signal). It collects out-of-sample evidence for the question the Larsson study
left open (docs/reviews/larsson-study.md): do RCCE entries do better when held
about 60 days behind a 12% stop, ignoring TRIM / RISK_OFF, than under today's exits?

Once a day, just before the daily close (23:50-23:59 UTC), it reads the scanner's
1D results (signal and price per symbol) and advances two paper books that share
the same entries:

    current   the backtest PositionManager's exits: 8% stop, TRIM / TRIM_HARD /
              NO_LONG close the symbol, RISK_OFF on any symbol closes everything,
              20 consecutive WAIT snapshots close the symbol
    hold60    60 daily snapshots or a 12% stop; RCCE exit signals ignored

Entries (both books): STRONG_LONG, LIGHT_LONG, REVIVAL_SEED when the book has
no open position in the symbol. Returns are per trade, net of 10 bps per side.
One small JSON write per day; a missed day is skipped, never back-filled.
Disable with EXIT_SHADOW_ENABLED=0.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

logger = logging.getLogger("exit_shadow")

VERSION = "exit-shadow-1"
ENTRY_SIGNALS = {"STRONG_LONG", "LIGHT_LONG", "REVIVAL_SEED"}
EXIT_SIGNALS = {"TRIM", "TRIM_HARD", "NO_LONG"}
EXIT_ALL = "RISK_OFF"
COST = 0.001                      # 5 bps fee + 5 bps slippage per side
POLICIES = {
    "current": {"stop": 0.08, "signals": True, "decay": 20, "hold": None},
    "hold60": {"stop": 0.12, "signals": False, "decay": None, "hold": 60},
}
SNAPSHOT_FROM = (23, 50)          # UTC hour, minute
_DIR = Path(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or Path(__file__).parent / "data")
PATH = _DIR / "exit_shadow.json"


def _empty() -> dict:
    return {"version": VERSION, "started": None, "last_date": None, "skipped_days": 0,
            "books": {p: {"open": {}, "closed": []} for p in POLICIES}}


class ExitShadow:
    def __init__(self, path: Path = PATH):
        self.path = path
        try:
            self.state = json.loads(path.read_text())
        except (OSError, ValueError):
            self.state = _empty()

    # ------------------------------------------------------------------ core
    def process_day(self, date: str, rows: Iterable[dict]) -> bool:
        """Advance both books by one daily snapshot. Idempotent per date."""
        if self.state["last_date"] is not None and date <= self.state["last_date"]:
            return False
        rows = [r for r in rows if r.get("symbol") and r.get("price")]
        risk_off = any(r.get("signal") == EXIT_ALL for r in rows)
        for name, rule in POLICIES.items():
            book = self.state["books"][name]
            if rule["signals"] and risk_off:
                for sym in list(book["open"]):
                    price = next((r["price"] for r in rows if r["symbol"] == sym), None)
                    if price:
                        self._close(book, sym, date, price, EXIT_ALL)
            for r in rows:
                sym, sig, price = r["symbol"], r.get("signal", "WAIT"), float(r["price"])
                pos = book["open"].get(sym)
                if pos is not None:
                    pos["days"] += 1
                    pos["waits"] = pos["waits"] + 1 if sig == "WAIT" else 0
                    reason = None
                    if price <= pos["entry_price"] * (1 - rule["stop"]):
                        reason = f"STOP_{int(rule['stop'] * 100)}"
                    elif rule["signals"] and sig in EXIT_SIGNALS:
                        reason = sig
                    elif rule["decay"] and pos["waits"] >= rule["decay"]:
                        reason = "DECAY"
                    elif rule["hold"] and pos["days"] >= rule["hold"]:
                        reason = f"HOLD_{rule['hold']}"
                    if reason:
                        self._close(book, sym, date, price, reason)
                    continue
                if sig in ENTRY_SIGNALS:
                    book["open"][sym] = {"entry_date": date, "entry_price": price, "entry_signal": sig,
                                         "days": 0, "waits": 0}
        self.state["last_date"] = date
        self.state["started"] = self.state["started"] or date
        self._save()
        return True

    @staticmethod
    def _close(book: dict, sym: str, date: str, price: float, reason: str) -> None:
        pos = book["open"].pop(sym)
        ret = price * (1 - COST) / (pos["entry_price"] * (1 + COST)) - 1
        book["closed"].append({"symbol": sym, "entry_date": pos["entry_date"], "exit_date": date,
                               "entry_signal": pos["entry_signal"], "entry_price": pos["entry_price"],
                               "exit_price": price, "days": pos["days"], "reason": reason,
                               "return_pct": round(ret * 100, 3)})

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        with os.fdopen(fd, "w") as fh:
            json.dump(self.state, fh, separators=(",", ":"))
        os.replace(tmp, self.path)

    # ------------------------------------------------------------------ reporting
    def summary(self, recent: int = 20) -> dict:
        out = {"version": VERSION, "started": self.state["started"], "last_date": self.state["last_date"],
               "skipped_days": self.state["skipped_days"], "policies": {}}
        for name, book in self.state["books"].items():
            rets = [t["return_pct"] for t in book["closed"]]
            srt = sorted(rets)
            out["policies"][name] = {
                "rule": POLICIES[name], "closed": len(rets), "open": len(book["open"]),
                "mean_return_pct": round(sum(rets) / len(rets), 3) if rets else None,
                "median_return_pct": srt[len(srt) // 2] if rets else None,
                "win_rate_pct": round(sum(r > 0 for r in rets) / len(rets) * 100, 1) if rets else None,
                "worst_pct": srt[0] if rets else None,
                "recent": book["closed"][-recent:],
            }
        return out


def _today(now: datetime) -> str:
    return now.strftime("%Y-%m-%d")


async def run_exit_shadow(scan_cache, poll_seconds: int = 300) -> None:
    """Background loop: one snapshot per UTC day in the last minutes before the daily close."""
    if os.environ.get("EXIT_SHADOW_ENABLED", "1") == "0":
        logger.info("Exit shadow log disabled")
        return
    shadow = get()
    logger.info("Exit shadow log running (last day %s)", shadow.state["last_date"])
    while True:
        try:
            now = datetime.now(timezone.utc)
            date = _today(now)
            in_slot = (now.hour, now.minute) >= SNAPSHOT_FROM
            if in_slot and shadow.state["last_date"] != date:
                last = shadow.state["last_date"]
                if last is not None:
                    gap = (datetime.fromisoformat(date) - datetime.fromisoformat(last)).days - 1
                    shadow.state["skipped_days"] += max(gap, 0)
                rows = [{"symbol": r.get("symbol"), "signal": r.get("signal"), "price": r.get("price")}
                        for r in scan_cache.results.get("1d", [])]
                if rows and shadow.process_day(date, rows):
                    logger.info("Exit shadow: processed %s (%d symbols)", date, len(rows))
        except Exception:
            logger.exception("Exit shadow snapshot failed (non-fatal)")
        await asyncio.sleep(poll_seconds)


_instance: Optional[ExitShadow] = None


def get() -> ExitShadow:
    global _instance
    if _instance is None:
        _instance = ExitShadow()
    return _instance
