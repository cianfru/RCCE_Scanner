"""
yf_source.py
~~~~~~~~~~~~

yfinance downloads for the TradFi markets Hyperliquid's HIP-3 candles do not cover (DXY and
VIX today). yfinance and pandas cost ~65 MB of RSS for the life of any process that imports
them, so data_fetcher runs this module as a short-lived child process
(``python yf_source.py <timeframe> <ticker>...``) that prints the parsed bars as JSON and exits.
It imports nothing heavy at module level so the parent can import it without that cost.
"""

from __future__ import annotations

import contextlib
import json
import sys
from typing import Dict, List, Optional

FIELDS = ("timestamp", "open", "high", "low", "close", "volume")


def period_for(timeframe: str) -> tuple:
    """(yfinance period, yfinance interval) for a scanner timeframe."""
    if timeframe == "4h":
        # yfinance max for hourly data is 730 days; fetch 2 years
        return "2y", "1h"
    elif timeframe == "1d":
        return "5y", "1d"
    elif timeframe == "1w":
        return "10y", "1wk"
    return "5y", "1d"


def parse(df, timeframe: str) -> Optional[dict]:
    """Convert a yfinance DataFrame into the standard OHLCV dict.

    For 4h timeframe: yfinance only supports 1h, so we resample to 4h.
    """
    import numpy as np
    if df is None or df.empty:
        return None

    # yfinance returns columns: Open, High, Low, Close, Volume
    # Drop rows with NaN close
    df = df.dropna(subset=["Close"])
    if df.empty:
        return None

    # Resample 1h → 4h if needed
    if timeframe == "4h":
        df = df.resample("4h").agg({
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum",
        }).dropna(subset=["Close"])
        if df.empty:
            return None

    timestamps = np.array([int(ts.timestamp() * 1000) for ts in df.index], dtype=np.float64)
    return {
        "timestamp": timestamps,
        "open":      df["Open"].values.astype(np.float64),
        "high":      df["High"].values.astype(np.float64),
        "low":       df["Low"].values.astype(np.float64),
        "close":     df["Close"].values.astype(np.float64),
        "volume":    df["Volume"].values.astype(np.float64),
    }


def download_batch(tickers: List[str], timeframe: str) -> Dict[str, Optional[dict]]:
    """One yf.download for all tickers, parsed per ticker (None where it has no data).
    Raises when the download itself fails."""
    import yfinance as yf
    period, interval = period_for(timeframe)
    df_all = yf.download(
        tickers,
        period=period,
        interval=interval,
        group_by="ticker",
        threads=True,
    )
    out: Dict[str, Optional[dict]] = {}
    for ticker in tickers:
        try:
            # Single ticker: yf.download returns a flat DataFrame
            df = df_all if len(tickers) == 1 else df_all[ticker]
            out[ticker] = parse(df, timeframe)
        except Exception:
            out[ticker] = None
    return out


def loaded_files() -> List[str]:
    """Source, bytecode and shared-library files this process read: once it exits, the parent drops
    their cached pages (they would stay charged to the container's memory)."""
    out = set()
    for mod in list(sys.modules.values()):
        for path in (getattr(mod, "__file__", None), getattr(getattr(mod, "__spec__", None), "cached", None)):
            if path:
                out.add(path)
    try:
        with open("/proc/self/maps") as f:
            for line in f:
                path = line.split()[-1] if len(line.split()) >= 6 else ""
                if path.startswith("/") and ".so" in path:
                    out.add(path)
    except OSError:
        pass
    return sorted(out)


def encode(results: Optional[Dict[str, Optional[dict]]], error: Optional[str] = None,
           files: Optional[List[str]] = None) -> str:
    """The child's answer. Bars as JSON lists: Python floats round-trip exactly; NaN stays NaN."""
    bars = {t: (None if d is None else {f: [float(x) for x in d[f]] for f in FIELDS})
            for t, d in (results or {}).items()}
    return json.dumps({"ok": error is None, "error": error, "bars": bars, "files": files or []})


def decode(text: str) -> dict:
    """{"ok", "error", "bars": {ticker: OHLCV dict of float64 arrays or None}, "files"}."""
    import numpy as np
    raw = json.loads(text)
    raw["bars"] = {t: (None if d is None else {f: np.asarray(d[f], dtype=np.float64) for f in FIELDS})
                   for t, d in raw.get("bars", {}).items()}
    return raw


def main(argv: List[str]) -> int:
    timeframe, tickers = argv[0], argv[1:]
    results, error = None, None
    # yfinance prints its progress bar to stdout; stdout carries only the JSON answer.
    with contextlib.redirect_stdout(sys.stderr):
        try:
            results = download_batch(tickers, timeframe)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:300]
    sys.stdout.write(encode(results, error, loaded_files()))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
