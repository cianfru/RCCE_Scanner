"""Cohort rules and per-snapshot aggregation. No I/O.

Equity cohorts use *perp* equity from clearinghouseState (the leaderboard's account
value includes spot, vaults and staking: for 37 of 40 sampled wallets it differed by
more than 10%). PnL cohorts use the leaderboard's all-time PnL.

Coverage: wallets come from the public leaderboard with an account value of $10K+,
so small accounts and small-PnL cohorts are only partly sampled; they are flagged.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

INF = math.inf
EQUITY_COHORTS = (
    ("Shrimp", 0, 250), ("Fish", 250, 10e3), ("Dolphin", 10e3, 50e3), ("Apex Predator", 50e3, 100e3),
    ("Small Whale", 100e3, 500e3), ("Whale", 500e3, 1e6), ("Tidal Whale", 1e6, 5e6), ("Leviathan", 5e6, INF),
)
PNL_COHORTS = (
    ("Giga-Rekt", -INF, -1e6), ("Full Rekt", -1e6, -100e3), ("Semi-Rekt", -100e3, -10e3), ("Exit Liquidity", -10e3, 0),
    ("Humble Earner", 0, 10e3), ("Grinder", 10e3, 100e3), ("Smart Money", 100e3, 1e6), ("Money Printer", 1e6, INF),
)
PARTIAL = {"Shrimp", "Fish", "Exit Liquidity", "Humble Earner"}   # under-sampled by the $10K discovery floor
YOUNG_S = 24 * 3600
MAX_POSITIONS = 25            # more concurrent positions than this: market maker / vault, excluded


def _pick(table, value: Optional[float]) -> Optional[str]:
    if value is None:
        return None
    for name, lo, hi in table:
        if lo <= value < hi:
            return name
    return table[0][0] if value < table[0][1] else None


def equity_cohort(perp_equity: Optional[float]) -> Optional[str]:
    return _pick(EQUITY_COHORTS, max(0.0, perp_equity) if perp_equity is not None else None)


def pnl_cohort(all_time_pnl: Optional[float]) -> Optional[str]:
    return _pick(PNL_COHORTS, all_time_pnl)


@dataclass
class Position:
    coin: str
    usd: float                 # mark value, always positive
    long: bool
    first_seen: float


@dataclass
class WalletState:
    address: str
    equity: float              # perp account value
    all_time_pnl: Optional[float]
    positions: List[Position] = field(default_factory=list)


def _bias(long_usd: float, short_usd: float) -> Optional[float]:
    total = long_usd + short_usd
    return round((long_usd - short_usd) / total, 4) if total > 0 else None


class _Acc:
    __slots__ = ("wallets", "positioned", "long_usd", "short_usd", "young_long", "young_short",
                 "equity_positioned", "levs", "long_wallets", "short_wallets")

    def __init__(self):
        self.wallets = self.positioned = self.long_wallets = self.short_wallets = 0
        self.long_usd = self.short_usd = self.young_long = self.young_short = self.equity_positioned = 0.0
        self.levs: List[float] = []

    def row(self) -> dict:
        notional = self.long_usd + self.short_usd
        return {
            "wallets": self.wallets, "positioned": self.positioned,
            "positioned_pct": round(100 * self.positioned / self.wallets, 1) if self.wallets else None,
            "long_wallets": self.long_wallets, "short_wallets": self.short_wallets,
            "long_usd": round(self.long_usd), "short_usd": round(self.short_usd),
            "net_usd": round(self.long_usd - self.short_usd),
            "lev_wavg": round(notional / self.equity_positioned, 2) if self.equity_positioned > 0 else None,
            "lev_median": round(statistics.median(self.levs), 2) if self.levs else None,
            "bias": _bias(self.long_usd, self.short_usd),
            "bias_24h": _bias(self.young_long, self.young_short),
        }


def aggregate(states: Iterable[WalletState], now: float, top_symbols: int = 40) -> List[dict]:
    """Rows for one snapshot: per dimension (equity, pnl) and cohort, all markets (symbol None)
    plus the top_symbols markets by total notional. Market makers are excluded."""
    acc: Dict[tuple, _Acc] = {}
    sym_notional: Dict[str, float] = {}

    def get(key):
        a = acc.get(key)
        if a is None:
            a = acc[key] = _Acc()
        return a

    for w in states:
        if len(w.positions) > MAX_POSITIONS:
            continue
        cohorts = [("equity", equity_cohort(w.equity)), ("pnl", pnl_cohort(w.all_time_pnl))]
        by_sym: Dict[str, List[Position]] = {}
        for p in w.positions:
            by_sym.setdefault(p.coin, []).append(p)
            sym_notional[p.coin] = sym_notional.get(p.coin, 0.0) + p.usd
        notional = sum(p.usd for p in w.positions)
        for dim, cohort in cohorts:
            if cohort is None:
                continue
            a = get((dim, cohort, None))
            a.wallets += 1
            if w.positions:
                a.positioned += 1
                if w.equity > 0:
                    a.equity_positioned += w.equity
                    a.levs.append(notional / w.equity)
                net = sum(p.usd if p.long else -p.usd for p in w.positions)
                a.long_wallets += net > 0
                a.short_wallets += net < 0
            for p in w.positions:
                young = now - p.first_seen < YOUNG_S
                if p.long:
                    a.long_usd += p.usd
                    a.young_long += p.usd if young else 0.0
                else:
                    a.short_usd += p.usd
                    a.young_short += p.usd if young else 0.0
            for coin, ps in by_sym.items():
                s = get((dim, cohort, coin))
                s.wallets += 1
                s.positioned += 1
                usd = sum(p.usd for p in ps)
                net = sum(p.usd if p.long else -p.usd for p in ps)
                s.long_wallets += net > 0
                s.short_wallets += net < 0
                if w.equity > 0:
                    s.equity_positioned += w.equity
                    s.levs.append(usd / w.equity)
                for p in ps:
                    young = now - p.first_seen < YOUNG_S
                    if p.long:
                        s.long_usd += p.usd
                        s.young_long += p.usd if young else 0.0
                    else:
                        s.short_usd += p.usd
                        s.young_short += p.usd if young else 0.0

    keep = {c for c, _ in sorted(sym_notional.items(), key=lambda kv: -kv[1])[:top_symbols]}
    rows = []
    for (dim, cohort, sym), a in acc.items():
        if sym is not None and sym not in keep:
            continue
        rows.append({"dimension": dim, "cohort": cohort, "symbol": sym, "partial": cohort in PARTIAL, **a.row()})
    return rows


def zscore(history: List[float], value: Optional[float], min_points: int = 30) -> Optional[float]:
    """value against a cohort's own rolling history; None until there is enough of it."""
    xs = [x for x in history if x is not None]
    if value is None or len(xs) < min_points:
        return None
    sd = statistics.pstdev(xs)
    return round((value - statistics.mean(xs)) / sd, 2) if sd > 0 else None


# Divergence: winning traders against losing traders (a contrarian read).
WINNERS = ("Smart Money", "Money Printer")
LOSERS = ("Giga-Rekt", "Full Rekt", "Semi-Rekt", "Exit Liquidity")


def divergence(rows: List[dict], symbol: Optional[str] = None) -> dict:
    def group(names):
        rs = [r for r in rows if r["dimension"] == "pnl" and r["cohort"] in names and r["symbol"] == symbol]
        lo, sh = sum(r["long_usd"] for r in rs), sum(r["short_usd"] for r in rs)
        return {"bias": _bias(lo, sh), "long_usd": lo, "short_usd": sh, "wallets": sum(r["positioned"] for r in rs)}
    win, lose = group(WINNERS), group(LOSERS)
    d = None if win["bias"] is None or lose["bias"] is None else round(win["bias"] - lose["bias"], 4)
    return {"symbol": symbol, "winners": win, "losers": lose, "divergence": d}
