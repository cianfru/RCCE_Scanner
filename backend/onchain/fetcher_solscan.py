"""
Solscan Pro API client.

Solscan provides richer free-tier access than Etherscan, including
top-holder lists and filtered transfer queries.

Auth: ``token`` header with API key.
Free tier: 10 M computing units.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT_S = 15
_MAX_RETRIES = 2
_RETRY_DELAY_S = 2.0


# ---------------------------------------------------------------------------
# Transfer record (mirrors EtherscanTransfer shape for easy merging)
# ---------------------------------------------------------------------------

@dataclass
class SolscanTransfer:
    tx_hash: str
    block_number: int
    timestamp: int
    from_addr: str
    to_addr: str
    token_symbol: str
    token_name: str
    token_contract: str
    value: float
    decimals: int
    chain: str = "solana"


@dataclass
class SolscanTokenInfo:
    contract: str
    symbol: str
    name: str
    decimals: int
    total_supply: float


@dataclass
class SolscanHolder:
    address: str
    amount: float
    decimals: int
    rank: int


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class SolscanFetcher:
    """Rate-limited async client for Solscan Pro API."""

    def __init__(self, api_key: str) -> None:
        self._base = "https://pro-api.solscan.io/v2.0"
        self._headers = {"token": api_key, "Accept": "application/json"}
        self._sem = asyncio.Semaphore(8)
        self._session: Optional[aiohttp.ClientSession] = None

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT_S)
            self._session = aiohttp.ClientSession(
                timeout=timeout, headers=self._headers,
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    # ── Low-level request ──────────────────────────────────────────────────

    async def _request(self, path: str, params: Optional[dict] = None) -> dict:
        """Rate-limited GET with retry."""
        url = f"{self._base}{path}"
        session = self._get_session()
        last_exc: Optional[Exception] = None

        for attempt in range(_MAX_RETRIES + 1):
            async with self._sem:
                try:
                    async with session.get(url, params=params or {}) as resp:
                        if resp.status == 429:
                            logger.warning("Solscan rate limited, backing off")
                            await asyncio.sleep(2.0)
                            continue
                        resp.raise_for_status()
                        data = await resp.json()
                        return data
                except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                    last_exc = exc
                    logger.warning(
                        "Solscan request failed (attempt %d/%d): %s",
                        attempt + 1, _MAX_RETRIES + 1, exc,
                    )
            if attempt < _MAX_RETRIES:
                await asyncio.sleep(_RETRY_DELAY_S)

        logger.error("Solscan request exhausted retries")
        return {"success": False, "data": [], "error": str(last_exc)}

    # ── Token metadata ─────────────────────────────────────────────────────

    async def get_token_meta(self, token_address: str) -> Optional[SolscanTokenInfo]:
        """Resolve token symbol, name, decimals, supply."""
        data = await self._request("/token/meta", {"address": token_address})
        info = data.get("data") if data.get("success") else data

        if not info or not isinstance(info, dict):
            return None

        try:
            decimals = int(info.get("decimals", 9))
            supply_raw = float(info.get("supply", 0))
            return SolscanTokenInfo(
                contract=token_address,
                symbol=info.get("symbol", ""),
                name=info.get("name", ""),
                decimals=decimals,
                total_supply=supply_raw / (10 ** decimals) if decimals > 0 else supply_raw,
            )
        except (ValueError, TypeError) as exc:
            logger.warning("Failed to parse Solscan token meta: %s", exc)
            return None

    # ── Token transfers ────────────────────────────────────────────────────

    async def get_token_transfers(
        self,
        token_address: str,
        page: int = 1,
        page_size: int = 40,
    ) -> List[SolscanTransfer]:
        """Fetch recent transfers for a Solana token."""
        params = {
            "address": token_address,
            "page": str(page),
            "page_size": str(page_size),
        }
        data = await self._request("/token/transfer", params)
        items = data.get("data", []) if data.get("success") else data.get("data", [])

        if not isinstance(items, list):
            return []

        results: List[SolscanTransfer] = []
        for tx in items:
            if not isinstance(tx, dict):
                continue
            try:
                decimals = int(tx.get("token_decimals", tx.get("decimals", 9)))
                raw_amount = float(tx.get("amount", 0))
                human_value = raw_amount / (10 ** decimals) if decimals > 0 else raw_amount

                results.append(SolscanTransfer(
                    tx_hash=tx.get("trans_id", tx.get("signature", "")),
                    block_number=int(tx.get("block_id", tx.get("slot", 0))),
                    timestamp=int(tx.get("block_time", tx.get("time", 0))),
                    from_addr=tx.get("from_address", tx.get("source_owner", "")),
                    to_addr=tx.get("to_address", tx.get("destination_owner", "")),
                    token_symbol=tx.get("token_symbol", tx.get("symbol", "")),
                    token_name=tx.get("token_name", tx.get("name", "")),
                    token_contract=token_address,
                    value=human_value,
                    decimals=decimals,
                ))
            except (ValueError, TypeError) as exc:
                logger.debug("Skipping malformed Solscan transfer: %s", exc)

        return results

    # ── Token holders ──────────────────────────────────────────────────────

    async def get_token_holders(
        self,
        token_address: str,
        page: int = 1,
        page_size: int = 40,
    ) -> List[SolscanHolder]:
        """Fetch top holders for a Solana token (free tier supported)."""
        params = {
            "address": token_address,
            "page": str(page),
            "page_size": str(page_size),
        }
        data = await self._request("/token/holders", params)
        items = data.get("data", []) if data.get("success") else data.get("data", [])

        if not isinstance(items, list):
            return []

        results: List[SolscanHolder] = []
        for i, h in enumerate(items):
            if not isinstance(h, dict):
                continue
            try:
                decimals = int(h.get("decimals", 9))
                raw_amount = float(h.get("amount", 0))
                results.append(SolscanHolder(
                    address=h.get("owner", h.get("address", "")),
                    amount=raw_amount / (10 ** decimals) if decimals > 0 else raw_amount,
                    decimals=decimals,
                    rank=i + 1 + (page - 1) * page_size,
                ))
            except (ValueError, TypeError):
                continue

        return results

    # ── Account activity ───────────────────────────────────────────────────

    async def get_account_transfers(
        self,
        address: str,
        token_address: Optional[str] = None,
        page_size: int = 30,
    ) -> List[SolscanTransfer]:
        """Fetch recent transfers for a specific wallet."""
        params: dict = {
            "address": address,
            "page_size": str(page_size),
        }
        if token_address:
            params["token"] = token_address

        data = await self._request("/account/transfer", params)
        items = data.get("data", []) if data.get("success") else data.get("data", [])

        if not isinstance(items, list):
            return []

        results: List[SolscanTransfer] = []
        for tx in items:
            if not isinstance(tx, dict):
                continue
            try:
                decimals = int(tx.get("token_decimals", tx.get("decimals", 9)))
                raw_amount = float(tx.get("amount", 0))
                human_value = raw_amount / (10 ** decimals) if decimals > 0 else raw_amount

                results.append(SolscanTransfer(
                    tx_hash=tx.get("trans_id", tx.get("signature", "")),
                    block_number=int(tx.get("block_id", tx.get("slot", 0))),
                    timestamp=int(tx.get("block_time", tx.get("time", 0))),
                    from_addr=tx.get("from_address", tx.get("source_owner", "")),
                    to_addr=tx.get("to_address", tx.get("destination_owner", "")),
                    token_symbol=tx.get("token_symbol", tx.get("symbol", "")),
                    token_name=tx.get("token_name", tx.get("name", "")),
                    token_contract=tx.get("token_address", ""),
                    value=human_value,
                    decimals=decimals,
                ))
            except (ValueError, TypeError):
                continue

        return results
