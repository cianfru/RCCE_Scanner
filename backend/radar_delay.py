"""
The free tier's Radar: the setup map as it was at least REFLEX_FREE_RADAR_DELAY_MIN
minutes ago (60 by default).

Every map the server builds passes through ``note``; one copy per quarter of the delay is
kept (at most five per timeframe), and ``get`` serves the newest copy old enough. The kept
copies are written to the data volume, so a restart does not leave the free Radar empty
for an hour. Only used while access tiers are on.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_dir = Path(os.environ["RAILWAY_VOLUME_MOUNT_PATH"]) if os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") \
    else Path(__file__).resolve().parent / "data"
DIR = _dir
KEEP = 5
_snaps: Dict[str, List[Tuple[float, dict]]] = {}
_loaded: set = set()


def _path(tf: str) -> Path:
    return DIR / f"radar_delayed_{tf}.json"


def _load(tf: str) -> List[Tuple[float, dict]]:
    if tf not in _loaded:
        _loaded.add(tf)
        try:
            _snaps[tf] = [(float(t), b) for t, b in json.loads(_path(tf).read_text())][-KEEP:]
        except (OSError, ValueError, TypeError):
            _snaps.setdefault(tf, [])
    return _snaps.setdefault(tf, [])


def note(tf: str, body: dict, delay_s: float, now: Optional[float] = None) -> bool:
    """Keep this map when the newest kept copy is at least a quarter of the delay older."""
    now = now or time.time()
    snaps = _load(tf)
    if snaps and now - snaps[-1][0] < max(60.0, delay_s / 4):
        return False
    snaps.append((now, body))
    del snaps[:-KEEP]
    try:
        DIR.mkdir(parents=True, exist_ok=True)
        tmp = _path(tf).with_suffix(".tmp")
        tmp.write_text(json.dumps(snaps))
        os.replace(tmp, _path(tf))
    except (OSError, TypeError, ValueError) as exc:
        logger.debug("delayed radar: not saved: %s", exc)
    return True


def get(tf: str, delay_s: float, now: Optional[float] = None) -> dict:
    """The newest kept map at least ``delay_s`` old, marked delayed; an empty map (no coins,
    ``as_of`` None) until one is old enough."""
    now = now or time.time()
    old = [(t, b) for t, b in _load(tf) if now - t >= delay_s]
    if not old:
        return {"tf": tf, "coins": [], "delayed": True, "delay_min": round(delay_s / 60), "as_of": None}
    t, body = old[-1]
    return dict(body, delayed=True, delay_min=round(delay_s / 60), as_of=t)


def reset(path: Optional[Path] = None) -> None:
    global DIR
    if path is not None:
        DIR = Path(path)
    _snaps.clear()
    _loaded.clear()
