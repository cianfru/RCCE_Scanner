"""
Wallet positioning history for the market history page: how many Hyperliquid smart-money wallets and whales
were net long and net short at each daily close (docs/reviews/wallet-history.md). Context, not a signal.

One row per day and group, [day, wallets, positioned, long, short, long_usd, short_usd, sampled]:

- smart: the cohort sweep's Smart Money and Money Printer PnL cohorts ($100K+ all-time PnL, $10K+ perp equity);
- whales: its Tidal Whale and Leviathan equity cohorts ($1M+ perp equity).

A wallet is long or short by the sign of its net dollar position over all markets, as in cohorts.assign.aggregate.
For the main coins (COINS) one more row per day and group, [day, long, short]: wallets long and short that coin (the
sweep's symbol rows); the group's wallets that day are the total, as for all markets.

Two sources:
- the seed (seeds/wallet_history_seed.json): days rebuilt from Hyperliquid's public data by
  `python -m backtest.wallet_history_rebuild` (a weighted sample of wallets; `sampled` is how many were read);
- live days from the cohort sweep's all-market snapshot nearest each 00:00 UTC close (cohort_snapshots keeps 180
  days), stored in a file next to hyperlens.db so they outlive that retention. The page shows recorded days where
  the sweep has them and rebuilt days before (and in any gap), the rebuilt ones moved to the recorded level on the
  days both cover (``overlap``), so the seam does not read as wallets changing side.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DAY_S = 86_400
SEED_PATH = Path(__file__).resolve().parent / "seeds" / "wallet_history_seed.json"
COLUMNS = ["day", "wallets", "positioned", "long", "short", "long_usd", "short_usd", "sampled"]
COINS = ("BTC", "ETH", "SOL", "HYPE")
COIN_COLUMNS = ["day", "long", "short"]
GROUPS: Dict[str, Tuple[str, Tuple[str, ...]]] = {
    "smart": ("pnl", ("Smart Money", "Money Printer")),
    "whales": ("equity", ("Tidal Whale", "Leviathan")),
}
SNAP_WINDOW_S = 3600            # a close's row comes from the snapshot nearest it within an hour either side
UPDATE_AFTER_S = 50 * 60        # the sweep is quiet 20 min after each 4h close; its next snapshot follows
MIN_OVERLAP_DAYS = 7

_seed: Optional[dict] = None
_live: Dict[str, Dict[int, list]] = {}  # "smart", "whales", and per coin "smart:BTC" ... -> day -> row
_checked: Optional[int] = None    # the last day whose close has been looked up (with or without snapshots)
_view: Optional[dict] = None


def _live_path() -> str:
    hl = os.environ.get("HYPERLENS_DB_PATH")
    base = os.path.dirname(hl) if hl else str(Path(__file__).resolve().parent)
    return os.path.join(base, "wallet_history_live.json")


def _load() -> dict:
    """The seed ({} when this deploy has none) and, once, the live file."""
    global _seed, _live, _checked
    if _seed is None:
        try:
            _seed = json.loads(SEED_PATH.read_text())
        except FileNotFoundError:
            _seed = {}
        try:
            saved = json.loads(Path(_live_path()).read_text())
            _live = {g: {int(r[0]): r for r in rows} for g, rows in saved.get("days", {}).items()}
            _checked = saved.get("checked_through")
        except FileNotFoundError:
            _live, _checked = {}, None
        except Exception as exc:
            logger.warning("Wallet history: live file unreadable (%s); starting empty", exc)
            _live, _checked = {}, None
    return _seed


def _save() -> None:
    path = Path(_live_path())
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"columns": COLUMNS, "coin_columns": COIN_COLUMNS, "checked_through": _checked,
                               "days": {g: [rows[d] for d in sorted(rows)] for g, rows in _live.items()}},
                              separators=(",", ":")))
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Live rows from the cohort sweep
# ---------------------------------------------------------------------------

Fetch = Callable[..., List[Tuple[int, str, dict]]]


def _fetch_snapshots(dimension: str, cohorts: Tuple[str, ...], lo: int, hi: int, symbol: str = "") -> List[Tuple[int, str, dict]]:
    """(ts, cohort, data) of the sweep's rows for these cohorts with lo <= ts <= hi: all markets (symbol ''), or
    one coin (written once per 4h candle)."""
    from cohorts.sweeper import store
    marks = ",".join("?" * len(cohorts))
    return [(ts, c, json.loads(data)) for ts, c, data in store().db.execute(
        f"SELECT ts, cohort, data FROM cohort_snapshots WHERE dimension = ? AND symbol = ? AND cohort IN ({marks}) "
        "AND ts BETWEEN ? AND ? ORDER BY ts", (dimension, symbol, *cohorts, lo, hi))]


def day_row(day: int, snaps: List[Tuple[int, str, dict]]) -> Optional[list]:
    """The group's row at day's close (00:00 UTC of the next day): the snapshot nearest the close, its cohorts summed
    (a cohort with no wallets writes no row and counts as zero)."""
    if not snaps:
        return None
    close = (day + 1) * DAY_S
    ts = min({s[0] for s in snaps}, key=lambda t: (abs(t - close), t))
    rows = [d for t, _, d in snaps if t == ts]
    total = lambda k: sum(int(r.get(k) or 0) for r in rows)
    usd = lambda k: round(sum(float(r.get(k) or 0) for r in rows))
    wallets = total("wallets")
    return [day, wallets, total("positioned"), total("long_wallets"), total("short_wallets"),
            usd("long_usd"), usd("short_usd"), wallets]


def live_rows(days: List[int], fetch: Fetch = _fetch_snapshots) -> Dict[str, Dict[int, list]]:
    """Rows per key: each group's all-market row, and "group:COIN" rows [day, long, short] for the main coins."""
    out: Dict[str, Dict[int, list]] = {}
    for d in days:
        lo, hi = (d + 1) * DAY_S - SNAP_WINDOW_S, (d + 1) * DAY_S + SNAP_WINDOW_S
        for g, (dim, cohorts) in GROUPS.items():
            row = day_row(d, fetch(dim, cohorts, lo, hi))
            if row is not None:
                out.setdefault(g, {})[d] = row
            for coin in COINS:
                row = day_row(d, fetch(dim, cohorts, lo, hi, symbol=coin))
                if row is not None:
                    out.setdefault(f"{g}:{coin}", {})[d] = [d, row[3], row[4]]
    return out


def first_snapshot_day(fetch_first: Optional[Callable[[], Optional[int]]] = None) -> Optional[int]:
    """The first day whose close window can hold a snapshot (collection started then), or None before any."""
    if fetch_first is None:
        from cohorts.sweeper import store
        dim, cohorts = GROUPS["smart"]          # indexed (dimension, cohort, symbol, ts): no scan of the table
        fetch_first = lambda: store().db.execute(
            "SELECT MIN(ts) FROM cohort_snapshots WHERE dimension = ? AND cohort = ? AND symbol = ''",
            (dim, cohorts[0])).fetchone()[0]
    ts = fetch_first()
    return None if not ts else int(ts - SNAP_WINDOW_S) // DAY_S - 1


async def update(now: Optional[float] = None, fetch: Fetch = _fetch_snapshots,
                 fetch_first: Optional[Callable[[], Optional[int]]] = None) -> int:
    """Look up every day not yet looked up whose close window has passed (from the sweep's first snapshot on) and
    keep the rows found. Returns rows added."""
    global _view, _checked
    _load()
    now = time.time() if now is None else now
    first = first_snapshot_day(fetch_first)
    if first is None:
        return 0
    last = int(now - SNAP_WINDOW_S) // DAY_S - 1             # the latest day whose close window has passed
    todo = list(range(max(first, (_checked + 1) if _checked is not None else first), last + 1))
    if not todo:
        return 0
    rows = live_rows(todo, fetch)
    added = 0
    for g, by_day in rows.items():
        for d, r in by_day.items():
            added += d not in _live.setdefault(g, {})
            _live[g][d] = r
    _checked = last
    _save()
    if added:
        _view = None
    logger.info("Wallet history: %d live row(s) added, %d days checked", added, len(todo))
    return added


async def run_forever() -> None:
    await asyncio.sleep(180)
    while True:
        try:
            await update()
        except Exception as exc:
            logger.warning("Wallet history update failed: %s", exc)
        now = time.time()
        next_close = (int(now) // DAY_S + 1) * DAY_S
        await asyncio.sleep(max(60, next_close + UPDATE_AFTER_S - now))


# ---------------------------------------------------------------------------
# View for /api/market-history/wallets
# ---------------------------------------------------------------------------

def _share(r: list, k: int) -> Optional[float]:
    return r[k] / r[1] if r[1] else None


def overlap(seed_rows: List[list], live: Dict[int, list]) -> Optional[dict]:
    """Rebuilt against recorded on the days both cover: the mean difference of the positioned, long and short shares
    (recorded minus rebuilt, the offsets applied to the rebuilt days) and the mean absolute difference of the long
    and short shares, in percentage points. None under MIN_OVERLAP_DAYS."""
    both = [(r, live[r[0]]) for r in seed_rows if r[0] in live and r[1] and live[r[0]][1]]
    if len(both) < MIN_OVERLAP_DAYS:
        return None
    mean = lambda k: sum(_share(b, k) - _share(a, k) for a, b in both) / len(both)
    gap = lambda k: round(100 * sum(abs(_share(a, k) - _share(b, k)) for a, b in both) / len(both), 1)
    return {"days": len(both), "from": both[0][0][0], "to": both[-1][0][0], "long_pts": gap(3), "short_pts": gap(4),
            "offset": {"positioned": mean(2), "long": mean(3), "short": mean(4)}}


def aligned(row: list, offset: dict) -> list:
    """A rebuilt row moved to the recorded level: its positioned, long and short shares shifted by the overlap's
    mean differences, the counts rebuilt from the shares (dollars unchanged)."""
    n = row[1]
    if not n:
        return list(row)
    clamp = lambda v: min(1.0, max(0.0, v))
    long = round(clamp(row[3] / n + offset["long"]) * n)
    short = min(n - long, round(clamp(row[4] / n + offset["short"]) * n))
    positioned = min(n, max(long + short, round(clamp(row[2] / n + offset["positioned"]) * n)))
    return [row[0], n, positioned, long, short, row[5], row[6], row[7]]


def coin_rows(rebuilt: Dict[int, list], live: Dict[int, list], rebuilt_wallets: Dict[int, int],
              live_wallets: Dict[int, int]) -> List[list]:
    """One coin and group, [day, long, short, rebuilt]: recorded days where present, rebuilt days otherwise, moved to
    the recorded level as the group's rows are (long and short shares of the group's wallets, shifted by their mean
    differences over a week or more of overlap)."""
    both = [d for d in rebuilt if d in live and rebuilt_wallets.get(d) and live_wallets.get(d)]
    shift = None
    if len(both) >= MIN_OVERLAP_DAYS:
        shift = [sum(live[d][k] / live_wallets[d] - rebuilt[d][k] / rebuilt_wallets[d] for d in both) / len(both)
                 for k in (1, 2)]
    clamp = lambda v: min(1.0, max(0.0, v))
    out = []
    for d in sorted(set(rebuilt) | set(live)):
        if d in live:
            out.append(list(live[d][:3]) + [0])
            continue
        r, n = rebuilt[d], rebuilt_wallets.get(d)
        if shift and n:
            long = round(clamp(r[1] / n + shift[0]) * n)
            r = [d, long, min(n - long, round(clamp(r[2] / n + shift[1]) * n))]
        out.append(list(r[:3]) + [1])
    return out


def view() -> dict:
    """Per group, one row a day: recorded where the sweep has the day, rebuilt otherwise. Where the two overlap by a
    week or more, the rebuilt days are moved to the recorded level (the overlap's mean difference per share), so the
    seam between them does not read as positions changing; ``overlap`` says by how much. The main coins' rows follow
    the same rule."""
    global _view
    if _view is not None:
        return _view
    seed = _load()
    end = seed.get("end_day")
    groups, checks, coins = {}, {}, {c: {} for c in COINS}
    for g in GROUPS:
        rebuilt = {r[0]: list(r) for r in (seed.get("groups") or {}).get(g, [])}
        live = _live.get(g, {})
        check = overlap([rebuilt[d] for d in sorted(rebuilt)], live)
        rebuilt_wallets = {d: r[1] for d, r in rebuilt.items()}
        if check:
            rebuilt = {d: aligned(r, check["offset"]) for d, r in rebuilt.items()}
            check["offset"] = {k: round(100 * v, 1) for k, v in check["offset"].items()}
        days = sorted(set(rebuilt) | set(live))
        groups[g] = [live[d] + [0] if d in live else rebuilt[d] + [1] for d in days]
        checks[g] = check
        live_wallets = {d: r[1] for d, r in live.items()}
        for c in COINS:
            seed_rows = ((seed.get("coins") or {}).get(c) or {}).get(g, [])
            coins[c][g] = coin_rows({r[0]: r for r in seed_rows}, _live.get(f"{g}:{c}", {}), rebuilt_wallets, live_wallets)
    live_days = sorted(set().union(*(set(v) for k, v in _live.items() if k in GROUPS))) if _live else []
    _view = {
        "columns": COLUMNS + ["rebuilt"],
        "groups": groups,
        "coin_columns": COIN_COLUMNS + ["rebuilt"],
        "coins": coins,
        "rebuilt": {"from": seed.get("start_day"), "to": end, "built": seed.get("built"), "sample": seed.get("sample")}
        if seed else None,
        "recorded_from": live_days[0] if live_days else None,
        "overlap": checks,
    }
    return _view
