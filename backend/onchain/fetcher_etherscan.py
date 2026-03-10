"""
Etherscan / Basescan API client.

Both Etherscan (Ethereum) and Basescan (Base L2) share the identical API
format, so this single client works for both — just pass different
``api_base`` and ``api_key`` at construction time.

Free-tier limits: 5 calls / second, 100 000 calls / day.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT_S = 15
_MAX_RETRIES = 2
_RETRY_DELAY_S = 2.0


# ---------------------------------------------------------------------------
# Transfer record
# ---------------------------------------------------------------------------

@dataclass
class EtherscanTransfer:
    tx_hash: str
    block_number: int
    timestamp: int
    from_addr: str
    to_addr: str
    token_symbol: str
    token_name: str
    token_contract: str
    value: float              # human-readable (divided by decimals)
    decimals: int
    chain: str


# ---------------------------------------------------------------------------
# Token metadata
# ---------------------------------------------------------------------------

@dataclass
class EtherscanTokenInfo:
    contract: str
    symbol: str
    name: str
    decimals: int
    total_supply: float


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class EtherscanFetcher:
    """Rate-limited async client for Etherscan-format APIs."""

    def __init__(self, chain_id: str, api_base: str, api_key: str) -> None:
        self._chain = chain_id
        self._base = api_base.rstrip("/")
        self._key = api_key
        self._sem = asyncio.Semaphore(4)           # stay under 5/sec
        self._session: Optional[aiohttp.ClientSession] = None

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT_S)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    # ── Low-level request ──────────────────────────────────────────────────

    async def _request(self, params: dict) -> dict:
        """Rate-limited GET with retry."""
        params["apikey"] = self._key
        session = self._get_session()
        last_exc: Optional[Exception] = None

        for attempt in range(_MAX_RETRIES + 1):
            async with self._sem:
                try:
                    async with session.get(self._base, params=params) as resp:
                        resp.raise_for_status()
                        data = await resp.json()
                        # Etherscan wraps errors in {"status":"0","message":"..."}
                        if data.get("status") == "0" and "No transactions found" not in data.get("message", ""):
                            msg = data.get("message", "unknown error")
                            if "rate limit" in msg.lower():
                                logger.warning("Rate limited on %s, backing off", self._chain)
                                await asyncio.sleep(1.5)
                                continue
                            # Some "0" status is OK (e.g. empty result)
                            if data.get("result") is not None:
                                return data
                            logger.warning("Etherscan error on %s: %s", self._chain, msg)
                        return data
                except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                    last_exc = exc
                    logger.warning(
                        "Etherscan request failed (%s, attempt %d/%d): %s",
                        self._chain, attempt + 1, _MAX_RETRIES + 1, exc,
                    )
            if attempt < _MAX_RETRIES:
                await asyncio.sleep(_RETRY_DELAY_S)

        logger.error("Etherscan request exhausted retries on %s", self._chain)
        return {"status": "0", "result": [], "message": str(last_exc)}

    # ── Token transfers ────────────────────────────────────────────────────

    async def get_token_transfers(
        self,
        contract: str,
        start_block: int = 0,
        page: int = 1,
        offset: int = 200,
        sort: str = "desc",
    ) -> List[EtherscanTransfer]:
        """Fetch ERC-20 token transfers for a contract address."""
        params = {
            "module": "account",
            "action": "tokentx",
            "contractaddress": contract,
            "startblock": str(start_block),
            "endblock": "99999999",
            "page": str(page),
            "offset": str(offset),
            "sort": sort,
        }
        data = await self._request(params)
        results: List[EtherscanTransfer] = []

        for tx in data.get("result", []) or []:
            if not isinstance(tx, dict):
                continue
            try:
                decimals = int(tx.get("tokenDecimal", 18))
                raw_value = int(tx.get("value", 0))
                human_value = raw_value / (10 ** decimals) if decimals > 0 else raw_value

                results.append(EtherscanTransfer(
                    tx_hash=tx.get("hash", ""),
                    block_number=int(tx.get("blockNumber", 0)),
                    timestamp=int(tx.get("timeStamp", 0)),
                    from_addr=tx.get("from", "").lower(),
                    to_addr=tx.get("to", "").lower(),
                    token_symbol=tx.get("tokenSymbol", ""),
                    token_name=tx.get("tokenName", ""),
                    token_contract=tx.get("contractAddress", "").lower(),
                    value=human_value,
                    decimals=decimals,
                    chain=self._chain,
                ))
            except (ValueError, TypeError) as exc:
                logger.debug("Skipping malformed transfer: %s", exc)

        return results

    async def get_address_transfers(
        self,
        address: str,
        contract: str,
        start_block: int = 0,
        offset: int = 100,
    ) -> List[EtherscanTransfer]:
        """Fetch token transfers for a specific wallet + contract."""
        params = {
            "module": "account",
            "action": "tokentx",
            "address": address,
            "contractaddress": contract,
            "startblock": str(start_block),
            "endblock": "99999999",
            "page": "1",
            "offset": str(offset),
            "sort": "desc",
        }
        data = await self._request(params)
        results: List[EtherscanTransfer] = []

        for tx in data.get("result", []) or []:
            if not isinstance(tx, dict):
                continue
            try:
                decimals = int(tx.get("tokenDecimal", 18))
                raw_value = int(tx.get("value", 0))
                human_value = raw_value / (10 ** decimals) if decimals > 0 else raw_value

                results.append(EtherscanTransfer(
                    tx_hash=tx.get("hash", ""),
                    block_number=int(tx.get("blockNumber", 0)),
                    timestamp=int(tx.get("timeStamp", 0)),
                    from_addr=tx.get("from", "").lower(),
                    to_addr=tx.get("to", "").lower(),
                    token_symbol=tx.get("tokenSymbol", ""),
                    token_name=tx.get("tokenName", ""),
                    token_contract=tx.get("contractAddress", "").lower(),
                    value=human_value,
                    decimals=decimals,
                    chain=self._chain,
                ))
            except (ValueError, TypeError):
                continue

        return results

    async def get_token_info(self, contract: str) -> Optional[EtherscanTokenInfo]:
        """Resolve token metadata (symbol, name, decimals, supply).

        Strategy: fetch a single recent transfer first (fast, always works),
        then try the tokeninfo endpoint as an enrichment (may be PRO-only).
        This avoids the 15-45s timeout penalty on free tier.
        """
        # Fast path: infer metadata from a single transfer (always available)
        transfers = await self.get_token_transfers(contract, offset=1, sort="desc")
        if transfers:
            t = transfers[0]
            info = EtherscanTokenInfo(
                contract=contract.lower(),
                symbol=t.token_symbol,
                name=t.token_name,
                decimals=t.decimals,
                total_supply=0,
            )
            # Optionally try tokeninfo for total_supply (non-blocking, skip on error)
            try:
                params = {
                    "module": "token",
                    "action": "tokeninfo",
                    "contractaddress": contract,
                }
                data = await asyncio.wait_for(self._request(params), timeout=5)
                result = data.get("result")
                if isinstance(result, list) and len(result) > 0:
                    ti = result[0]
                    decimals = int(ti.get("divisor", info.decimals))
                    total_raw = int(ti.get("totalSupply", 0))
                    info.total_supply = total_raw / (10 ** decimals) if decimals > 0 else total_raw
                    # Prefer tokeninfo name/symbol if available
                    if ti.get("symbol"):
                        info.symbol = ti["symbol"]
                    if ti.get("tokenName") or ti.get("name"):
                        info.name = ti.get("tokenName", ti.get("name", info.name))
            except (asyncio.TimeoutError, Exception) as exc:
                logger.debug("tokeninfo enrichment skipped for %s: %s", contract[:12], exc)

            return info

        return None
