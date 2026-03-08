"""
kraken_pairs.py
~~~~~~~~~~~~~~~
Symbol mapping between scanner format (BTC/USDT) and Kraken format (BTCUSD).
Auto-discovers which scanner symbols are tradeable on Kraken.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Kraken naming quirks
# ---------------------------------------------------------------------------
# Kraken returns some pairs with X/Z prefixes (legacy naming):
#   BTCUSD  → response key might be XXBTZUSD
#   ETHUSD  → response key might be XETHZUSD
# But the INPUT pair format is always simple: BTCUSD, ETHUSD, SOLUSD, etc.
# We only need the input format for placing orders; the response key
# normalization is handled by _normalize_response_key().

# Some scanner symbols need special mapping on Kraken
_PAIR_OVERRIDES: Dict[str, str] = {
    "MATIC/USDT": "MATICUSD",   # Kraken hasn't migrated to POL yet for trading
    "PEPE/USDT": "PEPEUSD",     # Kraken uses PEPE not PEPE1000
}

# Known non-existent pairs on Kraken (skip the ticker check)
_SKIP_PAIRS = {"MEME/USDT", "W/USDT", "CAKE/USDT", "GMT/USDT"}


def scanner_to_kraken(symbol: str) -> Optional[str]:
    """Convert scanner symbol to Kraken pair format.

    BTC/USDT → BTCUSD
    ETH/USDT → ETHUSD

    Returns None for symbols that can't be mapped.
    """
    if symbol in _SKIP_PAIRS:
        return None
    if symbol in _PAIR_OVERRIDES:
        return _PAIR_OVERRIDES[symbol]

    parts = symbol.split("/")
    if len(parts) != 2:
        return None

    base, quote = parts
    # Scanner uses USDT; Kraken pairs are typically quoted in USD
    kraken_quote = "USD" if quote == "USDT" else quote
    return f"{base}{kraken_quote}"


def kraken_to_scanner(pair: str) -> str:
    """Convert Kraken pair back to scanner format.

    BTCUSD → BTC/USDT
    """
    # Strip the USD suffix and add /USDT
    if pair.endswith("USD"):
        base = pair[:-3]
        return f"{base}/USDT"
    return pair


async def discover_tradeable_pairs(
    scanner_symbols: List[str],
    kraken_path: Optional[str] = None,
) -> Dict[str, str]:
    """Check which scanner symbols are available on Kraken.

    Parameters
    ----------
    scanner_symbols : list
        List of scanner symbols (e.g. ["BTC/USDT", "ETH/USDT", ...])
    kraken_path : str, optional
        Path to kraken binary. Auto-detected if None.

    Returns
    -------
    dict
        Mapping of {scanner_symbol: kraken_pair} for available pairs.
    """
    if kraken_path is None:
        kraken_path = _find_kraken_binary()
    if kraken_path is None:
        logger.error("kraken-cli not found in PATH")
        return {}

    # Build candidate pairs
    candidates: Dict[str, str] = {}  # {scanner_sym: kraken_pair}
    for sym in scanner_symbols:
        kp = scanner_to_kraken(sym)
        if kp:
            candidates[sym] = kp

    if not candidates:
        return {}

    # Batch-check via ticker (Kraken supports multiple pairs in one call)
    # But too many at once may hit API limits, so chunk into groups of 20
    available: Dict[str, str] = {}
    items = list(candidates.items())

    for i in range(0, len(items), 20):
        chunk = items[i:i + 20]
        kraken_pairs = [kp for _, kp in chunk]
        sym_map = {kp: sym for sym, kp in chunk}

        try:
            proc = await asyncio.create_subprocess_exec(
                kraken_path, "ticker", *kraken_pairs, "-o", "json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)

            if proc.returncode == 0 and stdout:
                data = json.loads(stdout.decode())
                if "error" not in data:
                    # All pairs in this chunk are valid
                    for sym, kp in chunk:
                        available[sym] = kp
                    logger.info(
                        "Kraken batch check: %d/%d pairs valid",
                        len(chunk), len(chunk),
                    )
                else:
                    # Some pairs invalid — check individually
                    logger.info("Batch check returned error, checking individually...")
                    for sym, kp in chunk:
                        if await _check_single_pair(kraken_path, kp):
                            available[sym] = kp
            else:
                # Batch failed — check individually
                for sym, kp in chunk:
                    if await _check_single_pair(kraken_path, kp):
                        available[sym] = kp

        except (asyncio.TimeoutError, Exception) as e:
            logger.warning("Batch ticker check failed: %s — checking individually", e)
            for sym, kp in chunk:
                if await _check_single_pair(kraken_path, kp):
                    available[sym] = kp

        # Small delay between chunks to respect rate limits
        if i + 20 < len(items):
            await asyncio.sleep(1)

    logger.info(
        "Kraken pair discovery: %d/%d scanner symbols available for trading",
        len(available), len(scanner_symbols),
    )
    return available


async def _check_single_pair(kraken_path: str, pair: str) -> bool:
    """Check if a single pair exists on Kraken."""
    try:
        proc = await asyncio.create_subprocess_exec(
            kraken_path, "ticker", pair, "-o", "json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
        if proc.returncode == 0 and stdout:
            data = json.loads(stdout.decode())
            return "error" not in data
    except Exception:
        pass
    return False


def _find_kraken_binary() -> Optional[str]:
    """Find the kraken binary in PATH or common locations."""
    import os

    # Check PATH
    found = shutil.which("kraken")
    if found:
        return found

    # Check common install locations
    for candidate in [
        os.path.expanduser("~/.cargo/bin/kraken"),
        "/usr/local/bin/kraken",
        "/opt/homebrew/bin/kraken",
    ]:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate

    return None


def get_kraken_binary() -> Optional[str]:
    """Return the path to the kraken binary, or None if not found."""
    return _find_kraken_binary()
