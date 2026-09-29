"""
How often a tracked Hyperliquid wallet is read (adaptive cadence). Pure functions, no I/O.

After each reading a wallet's next reading is scheduled from what the reading showed:

    followed wallet (the Follow list, Telegram alerts)      every FOLLOWED_S (5 min)
    positions changed since the previous reading            BACKOFF_S[0] (10 min)
    unchanged since then, positioned                        BACKOFF_S[1..]: 15, 30, 45, then 60 min
    unchanged and flat (no positions)                       FLAT_S (2 h)
    elite wallet (in both cohorts)                          never slower than ELITE_MAX_S (15 min)

"Changed": a coin opened, closed or flipped side, or a coin's size moved by more than
DUST_FRAC of the position and more than DUST_USD in value. Positions under DUST_USD are
ignored. A wallet that just closed everything counts as changed (10 min), then flat (2 h).

The sweep checks for due wallets every TICK_S, so a reading can come up to one tick after it
is due (10 min means 10-15 min). Intervals of 30 min and more get +-JITTER so wallets polled
together drift apart instead of bunching into bursts.

Readings up to MAX_READING_AGE_S old still count as current (consensus, the 4-hour trader
record, the 30-minute cohort snapshots, convergence timing): the slowest tier plus a tick and
the 20-minute quiet window after each 4-hour close. An unchanged wallet's old reading is, by
construction, its current position (valued at the price when it was read).
"""
from __future__ import annotations

import random
from typing import Callable, Dict, Optional, Tuple

FOLLOWED_S = 5 * 60
BACKOFF_S = (10 * 60, 15 * 60, 30 * 60, 45 * 60, 60 * 60)
FLAT_S = 2 * 3600
ELITE_MAX_S = 15 * 60
TICK_S = 5 * 60
JITTER = 0.10
JITTER_MIN_S = 30 * 60
MAX_READING_AGE_S = FLAT_S + 30 * 60
SETTLED_STREAK = len(BACKOFF_S) - 1          # streak of a wallet on the slowest positioned tier

DUST_USD = 500.0
DUST_FRAC = 0.01

# Stored records written with roster version 2 (600/60 cohorts, adaptive cadence) carry this.
ROSTER_VERSION = 2

# coin -> (signed size: + long / - short, position value in USD)
Book = Dict[str, Tuple[float, float]]


def live(book: Optional[Book]) -> Book:
    """Positions worth DUST_USD or more."""
    return {c: v for c, v in (book or {}).items() if v[0] and abs(v[1]) >= DUST_USD}


def changed(prev: Optional[Book], cur: Book) -> bool:
    """Did the positions change between two readings, beyond dust? ``prev`` None: no previous
    reading, counted as a change."""
    if prev is None:
        return True
    a, b = live(prev), live(cur)
    if set(a) != set(b):
        return True                                     # opened or closed a coin
    for coin, (s0, usd0) in a.items():
        s1, usd1 = b[coin]
        if (s0 > 0) != (s1 > 0):
            return True                                 # flipped side
        d = abs(s1 - s0)
        if d > DUST_FRAC * abs(s0):
            px = abs(usd1 / s1) if s1 else (abs(usd0 / s0) if s0 else 0.0)
            if d * px > DUST_USD:
                return True
    return False


def changed_sides(prev_sides: Optional[set], cur: Book) -> bool:
    """For readings stored before sizes were kept: only the set of (coin, long) can be compared."""
    if prev_sides is None:
        return True
    return set(prev_sides) != {(c, s > 0) for c, (s, _) in live(cur).items()}


def next_streak(streak: int, did_change: bool) -> int:
    """Readings in a row without a change (0 right after a change)."""
    return 0 if did_change else min(streak + 1, SETTLED_STREAK + 1)


def interval(streak: int, flat: bool, followed: bool = False, elite: bool = False) -> float:
    """Seconds until the next reading, before jitter."""
    if followed:
        return float(FOLLOWED_S)
    if flat and streak > 0:
        base = FLAT_S
    else:
        base = BACKOFF_S[min(max(streak, 0), len(BACKOFF_S) - 1)]
    if elite:
        base = min(base, ELITE_MAX_S)
    return float(base)


def next_at(now: float, streak: int, flat: bool, followed: bool = False, elite: bool = False,
            rng: Optional[Callable[[], float]] = None) -> float:
    """When the next reading is due."""
    s = interval(streak, flat, followed, elite)
    if s >= JITTER_MIN_S:
        s *= 1 + JITTER * (2 * (rng or random.random)() - 1)
    return now + s


def book_from_state(data: dict) -> Book:
    """Book from a raw clearinghouseState response."""
    out: Book = {}
    for ap in (data or {}).get("assetPositions", []) or []:
        p = ap.get("position", {}) or {}
        try:
            szi = float(p.get("szi", 0) or 0)
        except (TypeError, ValueError):
            continue
        if not szi:
            continue
        usd = abs(float(p.get("positionValue", 0) or 0)) or abs(szi) * float(p.get("entryPx", 0) or 0)
        coin = p.get("coin", "")
        s0, u0 = out.get(coin, (0.0, 0.0))
        out[coin] = (s0 + szi, u0 + usd)
    return out
