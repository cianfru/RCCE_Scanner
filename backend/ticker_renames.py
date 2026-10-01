"""
Tickers Hyperliquid renamed: the old perp was delisted and the coin trades under the new name
(FTM -> S, MATIC -> POL, RNDR -> RENDER). Both coins were swapped 1:1, so the old name's
history is the new name's history.

The app keys these markets by their current names. Records written under the old names are
renamed once, at startup (migrate_stores), and the stores read at import (the OHLCV cache,
favourites, the Radar watch list) rename on load. Every step is idempotent: a record already
under the current name is left alone, and when both names are present the current one wins.

Left as written, on purpose:
- the executor's state and trade history (its behaviour changes only with the owner's approval;
  executor_exposure reports what it holds under an old name, read-only);
- raw Hyperliquid records (wallet fills, snapshots, trade events): the old perps really traded
  under those names;
- research data and studies (seeds/, docs/reviews/): exchange pair names as they were.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

RENAMED: Dict[str, str] = {"FTM": "S", "MATIC": "POL", "RNDR": "RENDER"}
VERSION = 1


def current_coin(coin: str) -> str:
    """The current ticker for a bare coin ("MATIC" -> "POL"); anything else unchanged."""
    return RENAMED.get(coin, coin) if isinstance(coin, str) else coin


def current_symbol(symbol: str) -> str:
    """The current name for a symbol in any of the app's forms: "MATIC/USDT" -> "POL/USDT",
    "MATIC/USDT:USDT" -> "POL/USDT:USDT", "coin:MATIC" -> "coin:POL", "MATIC" -> "POL"."""
    if not isinstance(symbol, str) or not symbol:
        return symbol
    if symbol.startswith("coin:"):
        return "coin:" + current_coin(symbol[5:])
    base, sep, rest = symbol.partition("/")
    new = RENAMED.get(base)
    return f"{new}{sep}{rest}" if new else symbol


def renamed(symbol: str) -> bool:
    return current_symbol(symbol) != symbol


# ------------------------------------------------------------------ in-memory structures
def rename_keys(d: dict) -> Tuple[dict, int]:
    """A copy of ``d`` with old-name keys renamed; a key already present under the current
    name keeps its value. Returns (dict, keys renamed or dropped)."""
    out, n = {}, 0
    for k, v in d.items():
        if not renamed(k):
            out[k] = v
    for k, v in d.items():
        if renamed(k):
            n += 1
            out.setdefault(current_symbol(k), v)
    return out, n


def rename_list(items: Iterable[str]) -> Tuple[List[str], int]:
    """Old names renamed, order kept, duplicates dropped. Returns (list, entries changed)."""
    out, seen, n = [], set(), 0
    for s in items:
        c = current_symbol(s)
        if c != s:
            n += 1
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out, n


# ------------------------------------------------------------------ SQLite
def _has_table(c: sqlite3.Connection, table: str) -> bool:
    return c.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone() is not None


def rename_column(c: sqlite3.Connection, table: str, column: str, pairs: Dict[str, str]) -> Tuple[int, int]:
    """Rename ``column`` values per ``pairs`` (old -> new). A row whose renamed key already
    exists (a unique key) stays out: the current-name row is kept and the old one deleted.
    Returns (rows renamed, duplicate rows dropped)."""
    if not _has_table(c, table):
        return 0, 0
    moved = dropped = 0
    for old, new in pairs.items():
        moved += c.execute(f'UPDATE OR IGNORE "{table}" SET "{column}" = ? WHERE "{column}" = ?', (new, old)).rowcount
        dropped += c.execute(f'DELETE FROM "{table}" WHERE "{column}" = ?', (old,)).rowcount
    return moved, dropped


def _symbol_pairs(quotes: Iterable[str] = ("USDT",)) -> Dict[str, str]:
    return {f"{o}/{q}": f"{n}/{q}" for o, n in RENAMED.items() for q in quotes}


def _coin_pairs(prefix: str = "") -> Dict[str, str]:
    return {f"{prefix}{o}": f"{prefix}{n}" for o, n in RENAMED.items()}


def _open(path: Path) -> Optional[sqlite3.Connection]:
    """A connection to an existing database (never creates one)."""
    if not path or not Path(path).is_file():
        return None
    c = sqlite3.connect(str(path), timeout=30)
    c.execute("PRAGMA busy_timeout=30000")
    return c


def _migrate_db(path: Path, plan: List[Tuple[str, str, Dict[str, str]]], extra=None) -> dict:
    c = _open(path)
    if c is None:
        return {"skipped": "no file"}
    out = {}
    try:
        with c:
            for table, column, pairs in plan:
                moved, dropped = rename_column(c, table, column, pairs)
                if moved or dropped:
                    out[f"{table}.{column}"] = {"renamed": moved, "duplicates_dropped": dropped}
            if extra:
                out.update(extra(c))
    finally:
        c.close()
    return out


def _wallet_states(c: sqlite3.Connection) -> dict:
    """cohorts.db wallet_state_latest: positions JSON [[coin, usd, long, first_seen, size], ...]."""
    if not _has_table(c, "wallet_state_latest"):
        return {}
    like = " OR ".join("positions LIKE ?" for _ in RENAMED)
    rows = c.execute(f"SELECT address, positions FROM wallet_state_latest WHERE {like}",
                     [f'%"{o}"%' for o in RENAMED]).fetchall()
    n = 0
    for address, raw in rows:
        try:
            ps = json.loads(raw)
        except ValueError:
            continue
        changed = False
        for p in ps:
            if isinstance(p, list) and p and p[0] in RENAMED:
                p[0] = RENAMED[p[0]]
                changed = True
        if changed:
            c.execute("UPDATE wallet_state_latest SET positions = ? WHERE address = ?",
                      (json.dumps(ps, separators=(",", ":")), address))
            n += 1
    return {"wallet_state_latest.positions": {"renamed": n}} if n else {}


# ------------------------------------------------------------------ the stores
def _persist_dir() -> Path:
    env = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    if env and Path(env).is_dir():
        return Path(env)
    return Path(__file__).resolve().parent / "data"


def _paths() -> Dict[str, Optional[Path]]:
    """Where each store lives, read from the modules that own them."""
    out: Dict[str, Optional[Path]] = {}
    try:
        import signal_log
        out["signal_events"] = Path(signal_log._DB_PATH)
    except Exception:
        out["signal_events"] = None
    try:
        import signal_outcomes
        out["signal_outcomes"] = Path(signal_outcomes._DB_PATH)
    except Exception:
        out["signal_outcomes"] = None
    try:
        import hl_persistence
        out["hyperlens"] = Path(hl_persistence._DB_PATH)
    except Exception:
        out["hyperlens"] = None
    try:
        from cohorts.store import default_path
        out["cohorts"] = Path(default_path())
    except Exception:
        out["cohorts"] = None
    try:
        import accounts
        out["accounts"] = Path(accounts.PATH)
    except Exception:
        out["accounts"] = None
    root = Path(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or Path(__file__).resolve().parent / "data")
    out["opportunities"] = Path(os.environ.get("OPPORTUNITY_DB_PATH", str(root / "opportunities.db")))
    return out


def plans() -> Dict[str, Tuple[List[Tuple[str, str, Dict[str, str]]], object]]:
    """Store -> ([(table, column, old -> new)], extra step). Scanner symbols are "BASE/USDT";
    HyperLens and the Radar key coins bare (trader_lean groups as "coin:BASE")."""
    sym = _symbol_pairs()
    return {
        # Signal and regime transitions, and their resolved outcomes.
        "signal_events": ([("signal_events", "symbol", sym), ("regime_events", "symbol", sym)], None),
        "signal_outcomes": ([("signal_outcomes", "symbol", sym)], None),
        # The Radar's forward record and the per-coin trader lean behind the setup-map trails.
        "hyperlens": ([("radar_readings", "coin", _coin_pairs()), ("trader_lean", "grp", _coin_pairs("coin:"))], None),
        # Cohort time series and each wallet's last reading (so positions keep their first-seen time).
        "cohorts": ([("cohort_snapshots", "symbol", _coin_pairs())], _wallet_states),
        # Per-account Radar watch lists.
        "accounts": ([("watch", "coin", _coin_pairs())], None),
        # Opportunity journal: per-candle snapshots, latest states, transitions.
        "opportunities": ([("snapshots", "symbol", sym), ("states", "symbol", sym), ("transitions", "symbol", sym)], None),
    }


def marker_path() -> Path:
    return _persist_dir() / "ticker_renames.json"


def _read_marker(path: Path) -> dict:
    try:
        m = json.loads(path.read_text())
        return m if isinstance(m, dict) and m.get("version") == VERSION else {"version": VERSION, "done": {}}
    except (OSError, ValueError):
        return {"version": VERSION, "done": {}}


def migrate_stores(paths: Optional[Dict[str, Optional[Path]]] = None, marker: Optional[Path] = None,
                   executor_state: Optional[Path] = None) -> dict:
    """Rename old-name records in every SQLite store, once (the marker records each store done).
    A store that fails, or has no file yet, is tried again at the next start."""
    paths = _paths() if paths is None else paths
    marker = marker_path() if marker is None else marker
    state = _read_marker(marker)
    done = state.setdefault("done", {})
    for name, (plan, extra) in plans().items():
        if name in done:
            continue
        path = paths.get(name)
        if path is None:
            continue
        try:
            result = _migrate_db(path, plan, extra)
        except Exception as exc:
            logger.warning("Ticker renames: %s not migrated (retried next start): %s", name, exc)
            continue
        if result.get("skipped"):
            continue                    # no file yet: checked again at the next start (one stat)
        done[name] = {"at": time.time(), **result}
        if result:
            logger.info("Ticker renames: %s %s", name, result)
    state["executor"] = executor_exposure(executor_state)
    if state["executor"].get("old_names"):
        logger.warning("Ticker renames: the executor holds old names, left as they are for the owner: %s",
                       state["executor"])
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        tmp = marker.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=1))
        tmp.replace(marker)
    except OSError as exc:
        logger.warning("Ticker renames: marker not saved: %s", exc)
    return state


# ------------------------------------------------------------------ the executor (read only)
def executor_exposure(path: Optional[Path] = None) -> dict:
    """What the executor's saved state holds under an old name. Read only: nothing is changed.
    Open positions or whitelist entries under an old name never meet a scan row (rows are keyed
    by the current names), so they are reported for the owner to decide."""
    if path is None:
        try:
            import executor
            path = executor._STATE_FILE
        except Exception:
            return {"checked": False}
    try:
        state = json.loads(Path(path).read_text())
    except FileNotFoundError:
        return {"checked": True, "old_names": False}
    except (OSError, ValueError) as exc:
        return {"checked": False, "error": str(exc)[:200]}
    positions = sorted(s for s in (state.get("positions") or {}) if renamed(s))
    whitelist = sorted(s for s in (state.get("whitelist") or []) if renamed(s))
    pair_map = sorted(s for s in (state.get("pair_map") or {}) if renamed(s))
    trades = sorted({t.get("symbol") for t in (state.get("trade_log") or []) if renamed(t.get("symbol"))})
    return {"checked": True, "old_names": bool(positions or whitelist),
            "open_positions": positions, "whitelist": whitelist, "pair_map": pair_map,
            "closed_trade_symbols": trades}
