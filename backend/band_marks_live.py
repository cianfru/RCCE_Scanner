"""The band model's marks, live: the top divergence for the engine's exit, the capitulation turn for the record.

The marks are the TradingView band model's (tradingview/reflex_band_model.pine), computed by the same code the studies
used (research/band_marks.model) on the same data: Binance USDT spot daily candles, completed days only.

- Once a day the market-history job (market_history.update) computes them for its coins from about 2,000 days of
  candles, enough for every input of a recent day to match a computation on the full history, and records each coin's
  marks of the last RECORD_DAYS days (hl_persistence.save_band_marks).
- The scanner asks in_window(symbol) for each row: whether the coin had a top divergence within the last
  DIV_WINDOW_DAYS completed days (docs/reviews/top-divergence-exit-study.md, the 90-day window that passed). The
  engine acts on it only when signal_synthesizer.DIV_EXIT is on.
- Capitulation turns are recorded for a later look at the layers study's candidate (docs/reviews/band-marks-layers-
  study.md: a capitulation turn while the market's median z is in its high half); nothing reads them yet.
"""
from __future__ import annotations

import logging
import time
from typing import Dict, Iterable, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

DAY_S = 86_400
DIV_WINDOW_DAYS = 90           # the window that passed (top-divergence exit study, D90)
RECORD_DAYS = 120              # the marks kept per run: the window and a margin
KINDS = ("top_div", "cap_turn")
REFRESH_S = 600                # the scanner's view of the record is reread at most every 10 minutes

_view: Dict[str, object] = {"at": 0.0, "events": {}, "covered": set()}


def pair_of(symbol: str) -> Optional[str]:
    """The Binance USDT spot pair for a scanner symbol: "BTC/USDT" -> "BTCUSDT"; Hyperliquid's per-1,000 markets take
    the token's pair ("KPEPE/USDT" -> "PEPEUSDT": the marks do not depend on the price's unit)."""
    from ticker_renames import K_BASES
    base = str(symbol or "").split("/")[0].upper()
    if not base or ":" in base:
        return None
    if base.startswith("K") and base[1:] in K_BASES:
        base = base[1:]
    return base + "USDT"


def grid(klines: Iterable, last_day: int):
    """Binance daily klines on every day from the first to last_day (completed days only; a missing day takes the
    close before it, as the studies did). None when unreadable or empty."""
    by_day = {}
    try:
        for r in klines or []:
            d = int(float(r[0]) // 1000 // DAY_S)
            if d <= last_day:
                by_day[d] = (float(r[2]), float(r[3]), float(r[4]))
    except (TypeError, ValueError, IndexError):
        return None
    if not by_day:
        return None
    days = np.arange(min(by_day), max(by_day) + 1, dtype=np.int64)
    hi, lo, cl, last = [], [], [], None
    for d in days:
        if int(d) in by_day:
            last = by_day[int(d)]
            hi.append(last[0]); lo.append(last[1]); cl.append(last[2])
        else:
            hi.append(last[2]); lo.append(last[2]); cl.append(last[2])
    return days, np.array(hi), np.array(lo), np.array(cl)


def marks(klines: Iterable, last_day: int) -> Optional[Dict[str, List[int]]]:
    """The days of each recorded kind of mark among the last RECORD_DAYS completed days up to last_day."""
    from research.band_marks import model
    g = grid(klines, last_day)
    if g is None:
        return None
    days, high, low, close = g
    if not (close > 0).all():
        return None
    out = model(days, high, low, close)
    keep = days >= last_day - RECORD_DAYS + 1
    return {k: [int(d) for d in days[keep & out[k]]] for k in KINDS}


def _refresh(now: float) -> None:
    if now - float(_view["at"]) < REFRESH_S:
        return
    _view["at"] = now
    try:
        from hl_persistence import load_band_marks
        events, coverage = load_band_marks(int(now // DAY_S) - RECORD_DAYS - 1)
    except Exception as exc:                          # the record never blocks a scan
        logger.warning("Band marks: record unavailable (%s)", exc)
        return
    latest = max(coverage.values(), default=None)
    by_pair: Dict[str, List[int]] = {}
    for pair, day, kind in events:
        if kind == "top_div":
            by_pair.setdefault(pair, []).append(int(day))
    _view["events"] = by_pair
    _view["covered"] = {p for p, d in coverage.items() if d == latest}


def in_window(symbol: str, now: Optional[float] = None) -> Optional[bool]:
    """True when the coin had a top divergence within the last DIV_WINDOW_DAYS completed days; False when its marks
    were computed on the latest run and it had none; None when they were not."""
    now = time.time() if now is None else float(now)
    _refresh(now)
    pair = pair_of(symbol)
    if pair is None or pair not in _view["covered"]:
        return None
    last = int(now // DAY_S) - 1
    return any(last - DIV_WINDOW_DAYS + 1 <= d <= last for d in _view["events"].get(pair, ()))


def holding_out(now: Optional[float] = None) -> Dict[str, int]:
    """The covered pairs inside their window, with the day of their latest top divergence."""
    now = time.time() if now is None else float(now)
    _refresh(now)
    last = int(now // DAY_S) - 1
    out = {}
    for pair, days in _view["events"].items():
        inside = [d for d in days if last - DIV_WINDOW_DAYS + 1 <= d <= last]
        if inside and pair in _view["covered"]:
            out[pair] = max(inside)
    return out


def reset_view() -> None:
    """Forget the cached view (tests, and after a run writes new marks)."""
    _view.update(at=0.0, events={}, covered=set())
