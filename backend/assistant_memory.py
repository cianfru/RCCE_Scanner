"""
assistant_memory.py
~~~~~~~~~~~~~~~~~~~
Persistent conversation memory + user profile + proactive market monitor.

Three layers:
1. **Conversation Memory**: SQLite + FTS5 for past conversation recall.
2. **User Profile**: Auto-extracted trading preferences injected into system prompt.
3. **Market Monitor**: Periodic scanner check that pushes insights via WebSocket.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

import aiosqlite

logger = logging.getLogger("assistant_memory")

_PERSIST_DIR = Path(os.environ.get("RCCE_DATA_DIR", Path(__file__).parent / "data"))
_DB_PATH = _PERSIST_DIR / "assistant_memory.db"


# ══════════════════════════════════════════════════════════════════════════════
# 1. Conversation Memory
# ══════════════════════════════════════════════════════════════════════════════

class ConversationMemory:
    """SQLite-backed conversation memory with FTS5 full-text search."""

    _instance: Optional["ConversationMemory"] = None

    def __init__(self) -> None:
        self._db: Optional[aiosqlite.Connection] = None

    @classmethod
    def get(cls) -> "ConversationMemory":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def init(self) -> None:
        _PERSIST_DIR.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(_DB_PATH))
        self._db.row_factory = aiosqlite.Row

        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                wallet TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                symbol TEXT,
                timestamp INTEGER NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_conv_session
                ON conversations(session_id);
            CREATE INDEX IF NOT EXISTS idx_conv_wallet
                ON conversations(wallet);
            CREATE INDEX IF NOT EXISTS idx_conv_symbol
                ON conversations(symbol);
            CREATE INDEX IF NOT EXISTS idx_conv_ts
                ON conversations(timestamp);

            CREATE TABLE IF NOT EXISTS user_profile (
                wallet TEXT NOT NULL DEFAULT '',
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (wallet, key)
            );

            CREATE TABLE IF NOT EXISTS market_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_type TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp INTEGER NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_snap_ts
                ON market_snapshots(timestamp);
        """)

        # FTS5 virtual table for conversation search
        try:
            await self._db.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS conversations_fts
                USING fts5(content, symbol, content=conversations, content_rowid=id);
            """)
        except Exception:
            pass  # FTS5 may already exist

        await self._db.commit()
        logger.info("Assistant memory initialized at %s", _DB_PATH)

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    # ── Store ─────────────────────────────────────────────────────────────

    async def store_message(
        self,
        session_id: str,
        role: str,
        content: str,
        symbol: Optional[str] = None,
        wallet: str = "",
    ) -> None:
        """Persist a single message, scoped to wallet."""
        if not self._db:
            return
        ts = int(time.time())
        cursor = await self._db.execute(
            "INSERT INTO conversations (session_id, wallet, role, content, symbol, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, wallet, role, content, symbol, ts),
        )
        # Update FTS index
        try:
            await self._db.execute(
                "INSERT INTO conversations_fts (rowid, content, symbol) VALUES (?, ?, ?)",
                (cursor.lastrowid, content, symbol or ""),
            )
        except Exception:
            pass
        await self._db.commit()

    async def store_exchange(
        self,
        session_id: str,
        user_msg: str,
        assistant_reply: str,
        symbol: Optional[str] = None,
        wallet: str = "",
    ) -> None:
        """Store a full user→assistant exchange, scoped to wallet."""
        await self.store_message(session_id, "user", user_msg, symbol, wallet)
        await self.store_message(session_id, "assistant", assistant_reply, symbol, wallet)

    # ── Recall ────────────────────────────────────────────────────────────

    async def recall_by_symbol(self, symbol: str, wallet: str = "", limit: int = 10) -> List[Dict]:
        """Get recent conversations about a specific symbol for this wallet."""
        if not self._db:
            return []
        rows = await self._db.execute_fetchall(
            "SELECT role, content, timestamp FROM conversations "
            "WHERE symbol = ? AND wallet = ? ORDER BY timestamp DESC LIMIT ?",
            (symbol, wallet, limit),
        )
        return [dict(r) for r in rows]

    async def recall_by_query(self, query: str, wallet: str = "", limit: int = 8) -> List[Dict]:
        """FTS5 search across conversations for this wallet."""
        if not self._db:
            return []
        try:
            safe_query = " ".join(
                w for w in query.split()
                if w.isalnum() or w in ("AND", "OR", "NOT")
            )
            if not safe_query:
                return []
            rows = await self._db.execute_fetchall(
                "SELECT c.role, c.content, c.symbol, c.timestamp "
                "FROM conversations_fts f "
                "JOIN conversations c ON c.id = f.rowid "
                "WHERE conversations_fts MATCH ? AND c.wallet = ? "
                "ORDER BY rank LIMIT ?",
                (safe_query, wallet, limit),
            )
            return [dict(r) for r in rows]
        except Exception:
            return []

    async def recall_recent(self, wallet: str = "", limit: int = 20) -> List[Dict]:
        """Get most recent conversations for this wallet."""
        if not self._db:
            return []
        rows = await self._db.execute_fetchall(
            "SELECT role, content, symbol, timestamp FROM conversations "
            "WHERE wallet = ? ORDER BY timestamp DESC LIMIT ?",
            (wallet, limit),
        )
        return [dict(r) for r in rows]

    # ── Build memory context for LLM ─────────────────────────────────────

    async def build_memory_context(
        self,
        current_symbol: Optional[str] = None,
        user_message: str = "",
        wallet: str = "",
    ) -> str:
        """Build a memory block to inject into the system prompt.

        Combines:
        - Recent conversations about the same symbol (for this wallet)
        - FTS search hits from the current question (for this wallet)
        - User profile preferences (for this wallet)
        """
        parts: List[str] = []

        # Symbol-specific recall
        if current_symbol:
            symbol_history = await self.recall_by_symbol(current_symbol, wallet=wallet, limit=6)
            if symbol_history:
                lines = []
                for msg in reversed(symbol_history):  # chronological
                    role = "You" if msg["role"] == "assistant" else "User"
                    # Truncate long messages
                    content = msg["content"][:300]
                    if len(msg["content"]) > 300:
                        content += "..."
                    lines.append(f"  [{role}]: {content}")
                parts.append(
                    f"## Past Conversations About {current_symbol}\n" + "\n".join(lines)
                )

        # FTS recall from current question
        if user_message and len(user_message) > 10:
            search_hits = await self.recall_by_query(user_message, wallet=wallet, limit=4)
            # Filter out hits already shown in symbol recall
            if search_hits:
                lines = []
                for msg in search_hits:
                    sym_tag = f" [{msg['symbol']}]" if msg.get("symbol") else ""
                    content = msg["content"][:200]
                    if len(msg["content"]) > 200:
                        content += "..."
                    role = "You" if msg["role"] == "assistant" else "User"
                    lines.append(f"  [{role}]{sym_tag}: {content}")
                if lines:
                    parts.append(
                        "## Related Past Conversations\n" + "\n".join(lines)
                    )

        # User profile
        profile = await self.get_profile(wallet=wallet)
        if profile:
            profile_lines = []
            for k, v in profile.items():
                profile_lines.append(f"  - {k}: {v}")
            parts.append("## User Trading Profile\n" + "\n".join(profile_lines))

        if not parts:
            return ""
        return "## Assistant Memory\n\n" + "\n\n".join(parts)

    # ══════════════════════════════════════════════════════════════════════
    # 2. User Profile
    # ══════════════════════════════════════════════════════════════════════

    async def get_profile(self, wallet: str = "") -> Dict[str, str]:
        """Get all profile entries for this wallet."""
        if not self._db:
            return {}
        rows = await self._db.execute_fetchall(
            "SELECT key, value FROM user_profile WHERE wallet = ? ORDER BY key",
            (wallet,),
        )
        return {r["key"]: r["value"] for r in rows}

    async def update_profile(self, key: str, value: str, wallet: str = "") -> None:
        """Upsert a profile entry for this wallet."""
        if not self._db:
            return
        await self._db.execute(
            "INSERT INTO user_profile (wallet, key, value, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(wallet, key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            (wallet, key, value, int(time.time())),
        )
        await self._db.commit()

    async def extract_profile_from_conversation(
        self, user_message: str, assistant_reply: str,
        symbol: Optional[str] = None, wallet: str = "",
    ) -> None:
        """Extract trading preferences from a conversation exchange.

        Lightweight extraction — no LLM call, just pattern matching.
        Scoped to wallet.
        """
        msg_lower = user_message.lower()

        # Track asked-about symbols (frequency = interest)
        if symbol:
            counts = {}
            profile = await self.get_profile(wallet=wallet)
            if "symbol_interest" in profile:
                try:
                    counts = json.loads(profile["symbol_interest"])
                except Exception:
                    pass
            base = symbol.replace("/USDT", "").replace("/USD", "")
            counts[base] = counts.get(base, 0) + 1
            top = dict(sorted(counts.items(), key=lambda x: -x[1])[:20])
            await self.update_profile("symbol_interest", json.dumps(top), wallet=wallet)

        # Detect risk preferences from language
        if any(w in msg_lower for w in ("conservative", "safe", "careful", "low risk")):
            await self.update_profile("risk_preference", "conservative", wallet=wallet)
        elif any(w in msg_lower for w in ("aggressive", "degen", "yolo", "high risk", "leverage")):
            await self.update_profile("risk_preference", "aggressive", wallet=wallet)

        # Detect position sizing mentions
        if any(w in msg_lower for w in ("trim", "partial", "scale out", "take profit")):
            await self.update_profile("exit_style", "gradual (trims/scales)", wallet=wallet)
        elif any(w in msg_lower for w in ("all in", "full exit", "close everything")):
            await self.update_profile("exit_style", "binary (all-or-nothing)", wallet=wallet)

        # Track last interaction
        await self.update_profile("last_active", str(int(time.time())), wallet=wallet)


# ══════════════════════════════════════════════════════════════════════════════
# 3. Proactive Market Monitor
# ══════════════════════════════════════════════════════════════════════════════

# Snapshot of last monitor state to detect changes
_last_monitor_state: Dict = {}


async def _build_monitor_snapshot() -> Dict:
    """Build a compact snapshot of current market state for change detection."""
    from scanner import cache

    snapshot = {
        "consensus_4h": (cache.consensus.get("4h") or {}).get("consensus", "N/A"),
        "consensus_1d": (cache.consensus.get("1d") or {}).get("consensus", "N/A"),
        "strength_4h": (cache.consensus.get("4h") or {}).get("strength", 0),
        "strength_1d": (cache.consensus.get("1d") or {}).get("strength", 0),
    }

    # Count signals by type
    signal_counts = {}
    for r in cache.results.get("4h", []):
        sig = r.get("unified_signal") or r.get("signal", "WAIT")
        signal_counts[sig] = signal_counts.get(sig, 0) + 1
    snapshot["signal_counts"] = signal_counts

    # Active anomalies
    snapshot["anomaly_count"] = len(cache.anomalies)
    snapshot["anomaly_symbols"] = [a.get("symbol", "") for a in cache.anomalies[:5]]

    # Symbols with strong signals
    snapshot["strong_longs"] = [
        r["symbol"] for r in cache.results.get("4h", [])
        if (r.get("unified_signal") or r.get("signal")) == "STRONG_LONG"
    ]
    snapshot["risk_offs"] = [
        r["symbol"] for r in cache.results.get("4h", [])
        if (r.get("unified_signal") or r.get("signal")) in ("RISK_OFF", "TRIM_HARD")
    ]

    return snapshot


def _detect_changes(prev: Dict, curr: Dict) -> List[Dict]:
    """Compare two snapshots and return notable changes."""
    changes = []

    # Consensus shift
    for tf in ("4h", "1d"):
        pk = f"consensus_{tf}"
        sk = f"strength_{tf}"
        if prev.get(pk) and curr.get(pk) and prev[pk] != curr[pk]:
            changes.append({
                "type": "consensus_shift",
                "detail": f"{tf.upper()} consensus shifted from {prev[pk]} to {curr[pk]}",
                "severity": "high",
                "timeframe": tf,
            })
        # Strength momentum (big swing)
        prev_str = prev.get(sk, 0)
        curr_str = curr.get(sk, 0)
        if abs(curr_str - prev_str) >= 15:
            direction = "strengthening" if curr_str > prev_str else "weakening"
            changes.append({
                "type": "strength_shift",
                "detail": f"{tf.upper()} consensus {direction}: {prev_str:.0f}% → {curr_str:.0f}%",
                "severity": "medium",
                "timeframe": tf,
            })

    # New strong signals appearing
    prev_longs = set(prev.get("strong_longs", []))
    curr_longs = set(curr.get("strong_longs", []))
    new_longs = curr_longs - prev_longs
    if new_longs:
        syms = ", ".join(s.replace("/USDT", "") for s in list(new_longs)[:5])
        changes.append({
            "type": "new_strong_long",
            "detail": f"New STRONG_LONG signals: {syms}",
            "severity": "high",
            "symbols": list(new_longs),
        })

    # New risk-off signals
    prev_risks = set(prev.get("risk_offs", []))
    curr_risks = set(curr.get("risk_offs", []))
    new_risks = curr_risks - prev_risks
    if new_risks:
        syms = ", ".join(s.replace("/USDT", "") for s in list(new_risks)[:5])
        changes.append({
            "type": "new_risk_off",
            "detail": f"New RISK_OFF/TRIM_HARD signals: {syms}",
            "severity": "high",
            "symbols": list(new_risks),
        })

    # Signal distribution shift (e.g. many more longs appearing)
    prev_counts = prev.get("signal_counts", {})
    curr_counts = curr.get("signal_counts", {})
    entry_sigs = {"STRONG_LONG", "LIGHT_LONG", "ACCUMULATE"}
    exit_sigs = {"TRIM", "TRIM_HARD", "RISK_OFF", "NO_LONG"}

    prev_entries = sum(prev_counts.get(s, 0) for s in entry_sigs)
    curr_entries = sum(curr_counts.get(s, 0) for s in entry_sigs)
    prev_exits = sum(prev_counts.get(s, 0) for s in exit_sigs)
    curr_exits = sum(curr_counts.get(s, 0) for s in exit_sigs)

    if curr_entries >= prev_entries + 5:
        changes.append({
            "type": "entry_wave",
            "detail": f"Entry signals rising: {prev_entries} → {curr_entries} symbols showing long setups",
            "severity": "medium",
        })
    if curr_exits >= prev_exits + 5:
        changes.append({
            "type": "exit_wave",
            "detail": f"Exit signals rising: {prev_exits} → {curr_exits} symbols showing caution",
            "severity": "medium",
        })

    return changes


async def _generate_insight(changes: List[Dict]) -> Optional[str]:
    """Use LLM to generate a natural-language insight from detected changes.

    Falls back to a simple template if LLM is unavailable.
    """
    if not changes:
        return None

    # Simple template-based insight (no LLM call — fast and free)
    lines = []
    for c in changes:
        lines.append(f"- {c['detail']}")

    # Check user's interested symbols
    mem = ConversationMemory.get()
    profile = await mem.get_profile()
    interest_raw = profile.get("symbol_interest", "{}")
    try:
        interests = json.loads(interest_raw)
    except Exception:
        interests = {}

    # Cross-reference changes with user interests
    interested_mentions = []
    for c in changes:
        for sym in c.get("symbols", []):
            base = sym.replace("/USDT", "").replace("/USD", "")
            if base in interests:
                interested_mentions.append(f"{base} ({c['type']})")

    if interested_mentions:
        lines.append(f"- Symbols you follow: {', '.join(interested_mentions)}")

    return "\n".join(lines)


async def run_market_monitor(interval: float = 300.0) -> None:
    """Periodic market monitor — runs every 5 minutes.

    Compares current scanner state against previous snapshot,
    detects notable changes, and pushes insights via WebSocket.

    Runtime-toggleable via /api/admin/features (flag: market_monitor).
    When disabled the loop sleeps; toggling back on takes effect within
    ~30s without restart.
    """
    global _last_monitor_state
    from feature_flags import get_flag

    # Wait for scanner to have initial data
    await asyncio.sleep(120)

    logger.info("Market monitor started (interval=%.0fs)", interval)

    while True:
        if not get_flag("market_monitor"):
            await asyncio.sleep(30)
            continue
        try:
            curr = await _build_monitor_snapshot()

            if _last_monitor_state:
                changes = _detect_changes(_last_monitor_state, curr)

                if changes:
                    insight = await _generate_insight(changes)
                    if insight:
                        # Push via WebSocket
                        try:
                            from ws_hub import WebSocketHub
                            hub = WebSocketHub.get()
                            if hub.client_count > 0:
                                await hub.broadcast({
                                    "type": "assistant-insight",
                                    "data": {
                                        "message": insight,
                                        "changes": changes,
                                        "timestamp": time.time(),
                                    },
                                    "ts": time.time(),
                                })
                        except Exception:
                            pass

                        # Store snapshot for memory
                        mem = ConversationMemory.get()
                        if mem._db:
                            await mem._db.execute(
                                "INSERT INTO market_snapshots (snapshot_type, content, timestamp) "
                                "VALUES (?, ?, ?)",
                                ("insight", insight, int(time.time())),
                            )
                            await mem._db.commit()

                        logger.info("Market monitor: %d changes detected", len(changes))

            _last_monitor_state = curr

        except Exception as exc:
            logger.debug("Market monitor error: %s", exc)

        await asyncio.sleep(interval)
