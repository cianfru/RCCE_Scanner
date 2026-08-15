"""
activity.py
~~~~~~~~~~~
Global active / idle state manager — the master throttle.

The app is **active** when someone is actually using it:

  * a dashboard WebSocket is connected, OR
  * "Keep Awake" is pinned on (feature flag ``keep_active``), OR
  * there was recent API traffic (within ``IDLE_AFTER_SECONDS``).

Otherwise, after ``IDLE_AFTER_SECONDS`` of no activity, the app is
**idle** and background loops drop to a slow heartbeat to minimize CPU
(and therefore Railway usage cost).

Design contract
---------------
* Nothing is *disabled* in idle mode — only the *cadence* changes. No
  feature is removed, no state is lost. 4H / 1D candles close far slower
  than even the idle scan interval, so no signal is ever missed.
* Loops read :func:`is_active` once per cycle and pick a fast vs slow
  interval. When idle they sleep via :func:`idle_sleep`, which returns
  early the instant activity resumes — so opening the dashboard restores
  full-speed scanning within a few seconds, without a redeploy.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

logger = logging.getLogger("activity")

# How long with no activity before dropping to idle. Env-tunable.
IDLE_AFTER_SECONDS = int(os.environ.get("IDLE_AFTER_SECONDS", "900"))  # 15 min

# Start "active" so the process warms up fully on boot / redeploy.
_last_activity: float = time.time()
_mode_logged: str = "active"


# ---------------------------------------------------------------------------
# Activity signals
# ---------------------------------------------------------------------------

def mark_active(source: str = "") -> None:
    """Record that activity happened *now*.

    Called on WebSocket connect and on inbound API traffic (via HTTP
    middleware). Cheap — just stamps a timestamp.
    """
    global _last_activity
    _last_activity = time.time()


def _ws_client_count() -> int:
    try:
        from ws_hub import WebSocketHub
        return WebSocketHub.get().client_count
    except Exception:
        return 0


def _keep_awake_pinned() -> bool:
    try:
        from feature_flags import get_flag
        return get_flag("keep_active")
    except Exception:
        return False


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

def is_active() -> bool:
    """Return True if background loops should run at full cadence."""
    global _mode_logged
    active = (
        _keep_awake_pinned()
        or _ws_client_count() > 0
        or (time.time() - _last_activity) < IDLE_AFTER_SECONDS
    )
    mode = "active" if active else "idle"
    if mode != _mode_logged:
        logger.info(
            "Activity mode -> %s (ws_clients=%d, idle_for=%.0fs, pinned=%s)",
            mode.upper(), _ws_client_count(), seconds_idle(), _keep_awake_pinned(),
        )
        _mode_logged = mode
    return active


def seconds_idle() -> float:
    """Seconds since the last recorded activity (0 while a WS is open)."""
    if _ws_client_count() > 0:
        return 0.0
    return max(0.0, time.time() - _last_activity)


def get_state() -> dict:
    """Snapshot for status endpoints / the Settings UI badge."""
    return {
        "active": is_active(),
        "ws_clients": _ws_client_count(),
        "keep_awake": _keep_awake_pinned(),
        "seconds_since_activity": round(seconds_idle(), 1),
        "idle_after_seconds": IDLE_AFTER_SECONDS,
    }


# ---------------------------------------------------------------------------
# Interruptible idle sleep
# ---------------------------------------------------------------------------

async def idle_sleep(seconds: float, chunk: float = 10.0) -> None:
    """Sleep up to ``seconds`` while idle, waking early once active.

    Loops call this on their idle branch. It naps in short chunks and
    returns the moment :func:`is_active` flips True (e.g. the user opened
    the dashboard), so the next loop iteration resumes full cadence
    within ~``chunk`` seconds.
    """
    waited = 0.0
    while waited < seconds:
        step = min(chunk, seconds - waited)
        await asyncio.sleep(step)
        waited += step
        if is_active():
            return
