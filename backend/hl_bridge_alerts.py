"""
hl_bridge_alerts.py
~~~~~~~~~~~~~~~~~~~

Lightweight state machine for BTC × Hyperliquid-bridge divergence alerts.

The bridge divergence signal is a macro, single-asset (BTC) indicator, so it
doesn't fit the per-symbol loop in ``anomaly_detector.py``. This module tracks
the most recent divergence label and fires a Telegram alert on transitions
into a *confirmed* EXHAUSTION state, gated by a cooldown so we don't spam
the chat on jitter near the threshold.

Integrate by calling ``check_and_alert(divergence_payload)`` once per scan
cycle with the ``divergence`` dict returned by ``hl_bridge.get_bridge_flow()``.
Never raises — failures are logged and swallowed.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Don't re-fire within 6h of the last EXHAUSTION alert, even if we drop to
# DIVERGING and re-enter EXHAUSTION. This matches the signal's expected
# cadence — a genuine distribution event doesn't happen every hour.
_COOLDOWN_S = 6 * 3600

# Module-level state (singleton per process; fine for our single scanner worker)
_last_label: Optional[str] = None
_last_fire_ts: float = 0.0
_last_direction: Optional[str] = None  # "DISTRIBUTION" | "ACCUMULATION"


def _direction_for(score_6h: float) -> str:
    """Positive score = BTC leading flow up → distribution risk."""
    return "DISTRIBUTION" if score_6h > 0 else "ACCUMULATION"


def _format_alert(div: dict) -> str:
    """HTML text in the house style: no emojis, values escaped."""
    from tg_alerts import esc
    direction = _direction_for(float(div.get("score_6h") or 0.0)).lower()
    btc_z = float(div.get("btc_return_6h_z") or 0.0)
    flow_z = float(div.get("net_flow_6h_z") or 0.0)
    score_6h = float(div.get("score_6h") or 0.0)
    score_1h = float(div.get("score_1h") or 0.0)
    interp = div.get("interpretation") or ""
    lines = [f"<b>BTC</b> · bridge flow divergence, {direction}",
             f"6h: BTC {btc_z:+.1f}\u03c3, flow {flow_z:+.1f}\u03c3, score {score_6h:+.1f} · 1h score {score_1h:+.1f}"]
    if interp:
        lines.append(esc(interp))
    return "\n".join(lines)


async def _send_telegram(text: str, key: str = "exhaustion") -> int:
    """Through the alert gate (category "bridge", off by default). Returns 1 when sent."""
    try:
        import tg_alerts as ta
        return 1 if await ta.submit("bridge", key, text) == "sent" else 0
    except Exception as exc:
        logger.debug("hl_bridge_alerts: telegram not sent: %s", exc)
        return 0


async def check_and_alert(divergence: Optional[dict]) -> bool:
    """Fire Telegram alert on transition into a confirmed EXHAUSTION state.

    Returns True when an alert was sent. Safe to call every scan cycle —
    guarded by label transition + cooldown.
    """
    global _last_label, _last_fire_ts, _last_direction

    if not isinstance(divergence, dict):
        _last_label = None
        return False

    label = divergence.get("label")
    confirmed = bool(divergence.get("confirmed"))
    score_6h = float(divergence.get("score_6h") or 0.0)
    now = time.time()

    prev_label = _last_label
    _last_label = label

    # Only fire on confirmed EXHAUSTION, on a transition (not every snapshot),
    # and respect cooldown.
    if label != "EXHAUSTION" or not confirmed:
        return False

    direction = _direction_for(score_6h)
    direction_changed = direction != _last_direction
    is_transition = prev_label != "EXHAUSTION" or direction_changed
    if not is_transition:
        return False

    if now - _last_fire_ts < _COOLDOWN_S and not direction_changed:
        logger.info(
            "hl_bridge_alerts: EXHAUSTION fired, in cooldown (%.0f min remaining)",
            (_COOLDOWN_S - (now - _last_fire_ts)) / 60,
        )
        return False

    msg = _format_alert(divergence)
    sent = await _send_telegram(msg, f"exhaustion:{direction}")
    _last_fire_ts = now
    _last_direction = direction
    logger.info(
        "hl_bridge_alerts: EXHAUSTION %s fired, delivered to %d chats",
        direction, sent,
    )
    return sent > 0
