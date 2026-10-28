"""
Derive options wallets for the market history page's Derive drawer (docs/reviews/derive-smart-wallets.md): how
Derive's Smart options wallets were positioned at each daily close, as ranked at the time and as ranked today, and
the premium they paid on new puts. Exploration, not a study: context, not a signal.

The rows come from seeds/derive_smart_seed.json, built by hand from Cowboy's records of Derive options trades
(backend/backtest/derive_smart_series.py). Nothing here reads Derive or Cowboy at run time, so the feed ends on the
seed's last day ("through") until the seed is rebuilt.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

SEED_PATH = Path(__file__).resolve().parent / "seeds" / "derive_smart_seed.json"

_view: Optional[dict] = None


def view() -> dict:
    """The seed as served: columns, rows, tops per coin and the dates it covers ({} without a seed)."""
    global _view
    if _view is None:
        try:
            _view = json.loads(SEED_PATH.read_text())
        except FileNotFoundError:
            _view = {}
    return _view
