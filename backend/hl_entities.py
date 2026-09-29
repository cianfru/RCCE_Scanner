"""
Wallets that trade as one entity ("lockstep" wallets). Pure functions, no I/O.

Some traders split one book across several wallets: the same coins, the same side, sized in
proportion, traded at the same time (docs/reviews/position-size-at-tops-study.md: three
wallets held 84% of the profitable traders' BTC longs). Counted separately they look like
three traders agreeing. Counts of traders (consensus, the Radar, the 4-hour trader record,
convergences) count such a group once; dollars are still summed.

Data: the position change log (hl_persistence.position_changes). Every time a tracked wallet's
reading differs from its previous one beyond dust (hl_cadence.changed), the coins that moved
are logged with their size before and after and the time window the change happened in
(previous reading -> this reading). Fills are not stored, so "at the same time" is judged at
the resolution of the readings (10-15 min after a trade, up to about an hour for a quiet
wallet).

Rule (recomputed daily with the roster, over the last WINDOW_DAYS):

1. Moves. A wallet's changes to one coin in one direction (adding to a long or a short, or
   cutting it) that follow each other within MOVE_GAP_S are one move.
2. Traded together. A move of wallet A matches a move of wallet B when it is the same coin and
   direction and they happened within MATCH_S of each other (each move matches at most one).
   Both wallets need at least MIN_MATCHED matched moves, and at least MIN_SHARE of each one's
   moves must be matched (most of what one does, the other does too).
3. Held together. Each wallet's position in every coin either of them held, in dollars at one
   price per coin, sampled every GRID_S over the window: the two series must correlate at
   MIN_CORRELATION or more (same coins, same side, sizes rising and falling in proportion).
4. Entities. Linked wallets are joined (A-B and B-C make one entity of three). The entity id
   is "grp-" plus the start of its smallest address.

Calibrated on the September 2026 roster's fills (docs/hyperlens-wallet-tracking.md): the three
BTC wallets of the size study traded the same moves hours to a day and a half apart, so
MATCH_S is 48 hours; the correlation and share tests keep traders who merely buy the same
dip apart.
"""
from __future__ import annotations

import math
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

WINDOW_DAYS = 30
MOVE_GAP_S = 2 * 3600
MATCH_S = 48 * 3600
MIN_MATCHED = 2
MIN_SHARE = 0.7
MIN_CORRELATION = 0.8
GRID_S = 4 * 3600

# One logged change of one coin: (t0 = previous reading, t1 = this reading, coin, size before,
# size after, price). Sizes are signed (+ long, - short).
Change = Tuple[float, float, str, float, float, float]
# Current positions: coin -> (signed size, usd)
Book = Dict[str, Tuple[float, float]]


def _direction(before: float, after: float) -> str:
    """'add_long', 'cut_long', 'add_short', 'cut_short' (a flip is a cut and an add; its add names it)."""
    if after > 0 and (before <= 0 or after > before):
        return "add_long"
    if after < 0 and (before >= 0 or after < before):
        return "add_short"
    return "cut_long" if before > 0 else "cut_short"


def moves(changes: Iterable[Change]) -> List[dict]:
    """One wallet's changes -> moves (see the module doc), oldest first."""
    out: List[dict] = []
    open_by_key: Dict[Tuple[str, str], dict] = {}
    for t0, t1, coin, before, after, px in sorted(changes, key=lambda c: (c[1], c[2])):
        if before == after:
            continue
        key = (coin, _direction(before, after))
        usd = abs(after - before) * abs(px or 0.0)
        m = open_by_key.get(key)
        if m is not None and t0 - m["t1"] <= MOVE_GAP_S:
            m["t1"], m["usd"] = max(m["t1"], t1), m["usd"] + usd
            continue
        m = {"coin": coin, "dir": key[1], "t0": t0, "t1": t1, "usd": usd}
        open_by_key[key] = m
        out.append(m)
    return out


def match(ma: Sequence[dict], mb: Sequence[dict]) -> List[Tuple[dict, dict]]:
    """Greedy one-to-one matching of two wallets' moves: same coin and direction, within MATCH_S."""
    used: Set[int] = set()
    pairs = []
    for a in ma:
        best, best_gap = None, None
        for j, b in enumerate(mb):
            if j in used or b["coin"] != a["coin"] or b["dir"] != a["dir"]:
                continue
            gap = abs(a["t1"] - b["t1"])
            if gap <= MATCH_S and (best is None or gap < best_gap):
                best, best_gap = j, gap
        if best is not None:
            used.add(best)
            pairs.append((a, mb[best]))
    return pairs


def pearson(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def size_at(changes: Sequence[Change], now_size: float, t: float) -> float:
    """A coin's signed size at time t from its changes (time-sorted) and the size now."""
    size = changes[0][3] if changes else now_size
    for c in changes:
        if c[1] > t:
            break
        size = c[4]
    return size


def exposure(changes: Sequence[Change], book: Book, coins: Sequence[str], grid: Sequence[float],
             prices: Dict[str, float]) -> List[float]:
    """Signed dollars per (coin, grid time), coins in the given order, at one price per coin."""
    by_coin: Dict[str, List[Change]] = {}
    for c in sorted(changes, key=lambda c: c[1]):
        by_coin.setdefault(c[2], []).append(c)
    out = []
    for coin in coins:
        cs = by_coin.get(coin, [])
        now_size = (book.get(coin) or (0.0, 0.0))[0]
        px = prices.get(coin, 1.0)
        out.extend(size_at(cs, now_size, t) * px for t in grid)
    return out


def linked(ca: Sequence[Change], cb: Sequence[Change], book_a: Book, book_b: Book, grid: Sequence[float],
           prices: Dict[str, float], ma: Optional[List[dict]] = None, mb: Optional[List[dict]] = None
           ) -> Tuple[bool, dict]:
    """Do two wallets trade as one? Returns (linked, the figures behind the answer)."""
    ma = moves(ca) if ma is None else ma
    mb = moves(cb) if mb is None else mb
    info = {"moves_a": len(ma), "moves_b": len(mb), "matched": 0, "share_a": 0.0, "share_b": 0.0,
            "correlation": None}
    if len(ma) < MIN_MATCHED or len(mb) < MIN_MATCHED:
        return False, info
    if min(len(ma), len(mb)) < MIN_SHARE * max(len(ma), len(mb)):
        return False, info                  # cannot pass the share test: skip the matching
    n = len(match(ma, mb))
    info.update(matched=n, share_a=round(n / len(ma), 3), share_b=round(n / len(mb), 3))
    if n < MIN_MATCHED or n / len(ma) < MIN_SHARE or n / len(mb) < MIN_SHARE:
        return False, info
    coins = sorted({c[2] for c in ca} | {c[2] for c in cb} | set(book_a) | set(book_b))
    r = pearson(exposure(ca, book_a, coins, grid, prices), exposure(cb, book_b, coins, grid, prices))
    info["correlation"] = None if r is None else round(r, 3)
    return (r is not None and r >= MIN_CORRELATION), info


def candidate_pairs(by_wallet: Dict[str, List[dict]]) -> Set[Tuple[str, str]]:
    """Pairs of wallets with at least one move of the same coin and direction within MATCH_S."""
    buckets: Dict[Tuple[str, str], List[Tuple[float, str]]] = {}
    for w, ms in by_wallet.items():
        if len(ms) < MIN_MATCHED:
            continue
        for m in ms:
            buckets.setdefault((m["coin"], m["dir"]), []).append((m["t1"], w))
    out: Set[Tuple[str, str]] = set()
    for items in buckets.values():
        items.sort()
        for i, (t, w) in enumerate(items):
            for u, v in items[i + 1:]:
                if u - t > MATCH_S:
                    break
                if v != w:
                    out.add((w, v) if w < v else (v, w))
    return out


def entity_id(members: Iterable[str]) -> str:
    return "grp-" + min(members)[2:10]


def find_entities(changes_by_wallet: Dict[str, List[Change]], books: Optional[Dict[str, Book]] = None,
                  now: Optional[float] = None) -> Tuple[Dict[str, str], List[dict]]:
    """Group lockstep wallets. ``books``: address -> current positions {coin: (signed size, usd)}.
    Returns (address -> entity id for grouped wallets only, the links with their figures)."""
    import time as _time
    books = books or {}
    now = _time.time() if now is None else now
    grid = [now - WINDOW_DAYS * 86400 + k * GRID_S for k in range(int(WINDOW_DAYS * 86400 // GRID_S) + 1)]
    prices: Dict[str, float] = {}
    for cs in changes_by_wallet.values():
        for c in sorted(cs, key=lambda c: c[1]):
            if c[5]:
                prices[c[2]] = abs(c[5])
    for b in books.values():
        for coin, (size, usd) in b.items():
            if size and usd and coin not in prices:
                prices[coin] = abs(usd / size)
    by_wallet = {w: moves(cs) for w, cs in changes_by_wallet.items()}
    parent: Dict[str, str] = {}

    def find(x: str) -> str:
        while parent.get(x, x) != x:
            x = parent[x]
        return x

    links = []
    for a, b in sorted(candidate_pairs(by_wallet)):
        ok, info = linked(changes_by_wallet[a], changes_by_wallet[b], books.get(a, {}), books.get(b, {}),
                          grid, prices, by_wallet[a], by_wallet[b])
        if ok:
            links.append({"a": a, "b": b, **info})
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[max(ra, rb)] = min(ra, rb)
    groups: Dict[str, List[str]] = {}
    for w in {x for link in links for x in (link["a"], link["b"])}:
        groups.setdefault(find(w), []).append(w)
    out: Dict[str, str] = {}
    for members in groups.values():
        gid = entity_id(members)
        for w in members:
            out[w] = gid
    return out, links


SEED_BURST_S = 10 * 60        # fills of one coin this close together are one change when seeding


def changes_from_fills(fills: Iterable[dict], since: float, until: float,
                       dust_usd: float = 500.0) -> List[Change]:
    """Change-log rows rebuilt from a wallet's fills (Hyperliquid userFills: coin, time in ms, px, sz,
    side B/A, startPosition), for seeding the log once after it starts empty. Fills of one coin less
    than SEED_BURST_S apart are one change; changes worth under ``dust_usd`` are dropped; spot and
    builder-dex fills are skipped. Only changes that ended in [since, until) are returned."""
    by_coin: Dict[str, List[tuple]] = {}
    for f in fills:
        coin = str(f.get("coin") or "")
        if not coin or coin.startswith("@") or "/" in coin or ":" in coin or f.get("startPosition") is None:
            continue
        try:
            t = float(f["time"]) / 1000
            sp, sz, px = float(f["startPosition"]), float(f["sz"]), float(f["px"])
        except (KeyError, TypeError, ValueError):
            continue
        by_coin.setdefault(coin, []).append((t, sp, sz if f.get("side") == "B" else -sz, px))
    out: List[Change] = []
    for coin, xs in by_coin.items():
        xs.sort()
        burst = None
        for t, sp, d, px in xs + [(math.inf, 0.0, 0.0, 0.0)]:
            if burst is not None and t - burst[1] > SEED_BURST_S:
                t0, t1, before, after, bpx = burst
                if abs(after - before) * bpx >= dust_usd and since <= t1 < until:
                    out.append((t0, t1, coin, before, after, bpx))
                burst = None
            if t == math.inf:
                break
            if burst is None:
                burst = [t, t, sp, sp + d, px]
            else:
                burst[1], burst[3], burst[4] = t, sp + d, px
    out.sort(key=lambda c: c[1])
    return out


def note(size: int) -> str:
    return f"Part of a group of {size} wallets that trade together"
