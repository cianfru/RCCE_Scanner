"""
AIXBT Social Intelligence Client
Fetches narrative momentum, whale signals, and risk alerts from AIXBT API.
Used by /api/confirm/{symbol} and the Claude Skill for entry confirmation.

Auth: Supports both API key (env: AIXBT_API_KEY) and x402 pay-per-request
      (env: AIXBT_WALLET_KEY). x402 auto-purchases 1-day keys via USDC on Base.
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────
AIXBT_API_BASE = "https://api.aixbt.tech/v2"
_KEY_FILE = Path(__file__).resolve().parent / "data" / "aixbt_key.json"
_DATA_DIR = Path(__file__).resolve().parent / "data"

# Cache TTL: don't hammer AIXBT on every confirm request
_CACHE_TTL = 300  # 5 minutes

# x402 purchase lock to prevent concurrent purchases
_purchase_lock = asyncio.Lock()

# In-memory key store — survives container lifetime even if key file is lost
_mem_key: Dict[str, Any] = {}  # {"api_key": str, "expires_ts": float}

# Cooldown: don't attempt another purchase within 10 minutes of a failure
_last_purchase_attempt: float = 0
_PURCHASE_COOLDOWN = 600  # 10 minutes


def _get_api_key() -> str:
    """
    Resolve AIXBT API key from (in priority order):
    1. AIXBT_API_KEY env var (manual key)
    2. In-memory key store (survives within container lifetime)
    3. data/aixbt_key.json (x402-purchased key, persists across restarts if volume mounted)
    """
    now_ms = time.time() * 1000

    # Priority 1: env var
    key = os.environ.get("AIXBT_API_KEY", "").strip()
    if key:
        return key

    # Priority 2: in-memory key (survives even if file is lost)
    if _mem_key.get("api_key") and _mem_key.get("expires_ts", 0) > now_ms + 3_600_000:
        return _mem_key["api_key"]

    # Priority 3: x402-purchased key file
    if _KEY_FILE.exists():
        try:
            data = json.loads(_KEY_FILE.read_text())
            expires_ts = data.get("expires_ts", 0)
            # Key still valid (with 1hr buffer)
            if expires_ts > now_ms + 3_600_000:
                api_key = data.get("api_key", "")
                # Promote to memory so we don't lose it
                _mem_key["api_key"] = api_key
                _mem_key["expires_ts"] = expires_ts
                return api_key
            else:
                log.info("AIXBT key expired, will attempt x402 renewal")
        except Exception as e:
            log.warning("Failed to read AIXBT key file: %s", e)

    return ""


async def _try_x402_purchase() -> str:
    """Attempt to purchase a 1-day AIXBT API key via x402 Python SDK.

    Safety measures:
    - asyncio.Lock prevents concurrent purchases
    - Re-checks memory + file inside lock (another request may have bought while waiting)
    - 10-minute cooldown after any failed attempt to prevent drain
    - Key saved to both file AND memory (memory survives if file is lost)
    """
    global _last_purchase_attempt

    wallet_key = os.environ.get("AIXBT_WALLET_KEY", "").strip()
    if not wallet_key:
        log.debug("No AIXBT_WALLET_KEY set — AIXBT unavailable")
        return ""

    async with _purchase_lock:
        now_ms = time.time() * 1000

        # Re-check in-memory key (another request may have purchased while we waited)
        if _mem_key.get("api_key") and _mem_key.get("expires_ts", 0) > now_ms + 3_600_000:
            return _mem_key["api_key"]

        # Re-check key file
        if _KEY_FILE.exists():
            try:
                data = json.loads(_KEY_FILE.read_text())
                if data.get("expires_ts", 0) > now_ms + 3_600_000:
                    api_key = data.get("api_key", "")
                    _mem_key["api_key"] = api_key
                    _mem_key["expires_ts"] = data["expires_ts"]
                    return api_key
            except Exception:
                pass

        # Cooldown check: don't attempt purchase if we recently failed
        if _last_purchase_attempt and (time.time() - _last_purchase_attempt) < _PURCHASE_COOLDOWN:
            remaining = int(_PURCHASE_COOLDOWN - (time.time() - _last_purchase_attempt))
            log.warning("x402 purchase on cooldown (%ds remaining) — skipping to prevent drain", remaining)
            return ""

        _last_purchase_attempt = time.time()
        log.info("Purchasing AIXBT 1-day key via x402 (Python)...")
        try:
            from eth_account import Account
            from x402 import x402ClientSync
            from x402.mechanisms.evm import EthAccountSigner
            from x402.mechanisms.evm.exact.register import register_exact_evm_client
            from x402.http.clients import x402_requests

            # Create signer from wallet private key
            account = Account.from_key(wallet_key)
            signer = EthAccountSigner(account)
            log.info("x402 wallet: %s", account.address)

            # Initialize x402 client and register EVM payment scheme
            client = x402ClientSync()
            register_exact_evm_client(client, signer)

            # Purchase the key — x402 handles 402 → sign → retry automatically
            url = "https://api.aixbt.tech/x402/v2/api-keys/1d"
            with x402_requests(client) as session:
                response = session.post(url)

            if response.status_code not in (200, 201):
                log.error("x402 purchase failed (%d): %s", response.status_code, response.text[:200])
                return ""

            result = response.json()
            api_key = result.get("data", {}).get("apiKey") or result.get("apiKey") or result.get("key", "")

            if not api_key:
                log.error("x402 purchase succeeded but no key in response: %s", result)
                return ""

            # Save key to BOTH memory and file
            now = time.time() * 1000  # ms
            duration_ms = 24 * 60 * 60 * 1000
            expires_ts = now + duration_ms

            # Memory (primary — survives file loss)
            _mem_key["api_key"] = api_key
            _mem_key["expires_ts"] = expires_ts

            # File (secondary — survives container restart if volume mounted)
            key_data = {
                "api_key": api_key,
                "purchased_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "expires_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(expires_ts / 1000)),
                "expires_ts": expires_ts,
                "duration": "1d",
                "wallet": account.address,
            }
            _DATA_DIR.mkdir(parents=True, exist_ok=True)
            _KEY_FILE.write_text(json.dumps(key_data, indent=2))

            # Clear cooldown on success
            _last_purchase_attempt = 0

            log.info("AIXBT key purchased successfully via x402 (expires %s)", key_data["expires_at"])
            return api_key

        except ImportError as e:
            log.warning("x402 Python deps not installed (%s) — run: pip install x402[requests,evm]", e)
            return ""
        except Exception as e:
            if "insufficient" in str(e).lower():
                log.error("x402: Insufficient USDC balance. Fund wallet on Base chain.")
            else:
                log.error("x402 purchase error: %s", e)
            return ""


async def _try_x402_purchase_with_error() -> tuple:
    """Wrapper that returns (key, error_string) for diagnostics.
    IMPORTANT: Never retry a real x402 payment — each attempt costs $1.
    """
    wallet_key = os.environ.get("AIXBT_WALLET_KEY", "").strip()
    if not wallet_key:
        return "", "no wallet key"
    try:
        key = await _try_x402_purchase()
        if key:
            return key, ""
        # Purchase returned empty — report last known error without retrying
        return "", "x402 purchase returned empty (check logs for details)"
    except Exception as e:
        return "", str(e)[:200]


# ── Symbol → AIXBT project name mapping ──────────────────────────────
# AIXBT uses project names (e.g. "bitcoin"), scanner uses pairs (e.g. "BTC/USDT")
_SYMBOL_MAP = {
    "BTC":  "bitcoin",
    "ETH":  "ethereum",
    "SOL":  "solana",
    "BNB":  "bnb",
    "XRP":  "xrp",
    "ADA":  "cardano",
    "AVAX": "avalanche",
    "DOGE": "dogecoin",
    "DOT":  "polkadot",
    "LINK": "chainlink",
    "MATIC": "polygon",
    "POL":  "polygon",
    "UNI":  "uniswap",
    "AAVE": "aave",
    "OP":   "optimism",
    "ARB":  "arbitrum",
    "SUI":  "sui",
    "APT":  "aptos",
    "NEAR": "near-protocol",
    "FIL":  "filecoin",
    "ATOM": "cosmos",
    "INJ":  "injective",
    "TIA":  "celestia",
    "SEI":  "sei",
    "STX":  "stacks",
    "IMX":  "immutable-x",
    "RENDER": "render",
    "FET":  "fetch-ai",
    "PEPE": "pepe",
    "WIF":  "dogwifhat",
    "BONK": "bonk",
    "SHIB": "shiba-inu",
    "FLOKI": "floki",
    "LTC":  "litecoin",
    "BCH":  "bitcoin-cash",
    "ETC":  "ethereum-classic",
    "ALGO": "algorand",
    "FTM":  "fantom",
    "SAND": "the-sandbox",
    "MANA": "decentraland",
    "AXS":  "axie-infinity",
    "CRV":  "curve-dao",
    "MKR":  "maker",
    "COMP": "compound",
    "SNX":  "synthetix",
    "LDO":  "lido-dao",
    "RUNE": "thorchain",
    "ENS":  "ethereum-name-service",
    "WLD":  "worldcoin",
    "JUP":  "jupiter",
    "W":    "wormhole",
    "ONDO": "ondo-finance",
    "ENA":  "ethena",
    "PENDLE": "pendle",
    "TAO":  "bittensor",
    "KAS":  "kaspa",
    "TON":  "toncoin",
    "TRX":  "tron",
}


def _resolve_name(symbol: str) -> str:
    """Convert scanner symbol (e.g. 'BTC/USDT' or 'BTCUSDT') to AIXBT name."""
    base = symbol.upper().replace("/USDT", "").replace("USDT", "").replace("/USD", "").strip()
    return _SYMBOL_MAP.get(base, base.lower())


# ── Data Classes ─────────────────────────────────────────────────────

@dataclass
class AIXBTSignal:
    """A structured signal from AIXBT community intelligence."""
    category: str = ""
    description: str = ""
    detected_at: str = ""
    reinforced_at: str = ""
    clusters: int = 0

    @property
    def is_risk(self) -> bool:
        return self.category in ("RISK_ALERT", "REGULATORY")

    @property
    def is_bullish(self) -> bool:
        return self.category in (
            "WHALE_ACTIVITY", "PARTNERSHIP", "TECH_EVENT",
            "ONCHAIN_METRICS", "MARKET_ACTIVITY",
        )


@dataclass
class AIXBTConfirmation:
    """Structured AIXBT confirmation data for a project."""
    project_name: str = ""
    project_id: str = ""
    found: bool = False

    # Scores
    momentum_score: float = 0.0
    popularity_score: float = 0.0

    # Signals breakdown
    signals: List[AIXBTSignal] = field(default_factory=list)
    signal_count: int = 0
    risk_alert_count: int = 0
    bullish_signal_count: int = 0
    whale_signals: int = 0

    # Derived verdict
    narrative_strength: str = "UNKNOWN"   # STRONG, MODERATE, WEAK, NONE
    risk_level: str = "UNKNOWN"           # LOW, MEDIUM, HIGH
    confirmation: str = "UNAVAILABLE"     # CONFIRMED, NEUTRAL, CAUTION, DENIED

    # Meta
    error: str = ""
    cached: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_name": self.project_name,
            "found": self.found,
            "momentum_score": self.momentum_score,
            "popularity_score": self.popularity_score,
            "signal_count": self.signal_count,
            "risk_alert_count": self.risk_alert_count,
            "bullish_signal_count": self.bullish_signal_count,
            "whale_signals": self.whale_signals,
            "narrative_strength": self.narrative_strength,
            "risk_level": self.risk_level,
            "confirmation": self.confirmation,
            "top_signals": [
                {
                    "category": s.category,
                    "description": s.description,
                    "clusters": s.clusters,
                    "reinforced_at": s.reinforced_at,
                }
                for s in self.signals[:5]
            ],
            "error": self.error,
            "cached": self.cached,
        }


# ── In-memory cache ──────────────────────────────────────────────────
_cache: Dict[str, tuple] = {}  # name -> (timestamp, AIXBTConfirmation)


# ── Core API Client ──────────────────────────────────────────────────

async def _get(session: aiohttp.ClientSession, path: str, params: dict = None, api_key: str = "") -> Optional[dict]:
    """Make authenticated GET request to AIXBT API."""
    url = f"{AIXBT_API_BASE}{path}"
    headers = {}
    if api_key:
        headers["x-api-key"] = api_key
    try:
        async with session.get(url, headers=headers, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                return await resp.json()
            elif resp.status == 402:
                log.warning("AIXBT: 402 Payment Required — set AIXBT_WALLET_KEY for auto-purchase")
                return None
            elif resp.status == 429:
                log.warning("AIXBT: Rate limited")
                return None
            else:
                log.warning("AIXBT %s returned %d", path, resp.status)
                return None
    except Exception as e:
        log.error("AIXBT request failed: %s", e)
        return None


async def confirm_symbol(symbol: str) -> AIXBTConfirmation:
    """
    Fetch AIXBT social intelligence for a symbol and produce
    a structured confirmation verdict.
    """
    name = _resolve_name(symbol)

    # Check cache
    if name in _cache:
        ts, cached_data = _cache[name]
        if time.time() - ts < _CACHE_TTL:
            cached_data.cached = True
            return cached_data

    result = AIXBTConfirmation(project_name=name)

    api_key = _get_api_key()
    x402_error = ""
    if not api_key:
        # Try auto-purchase via x402 (async)
        api_key, x402_error = await _try_x402_purchase_with_error()
    if not api_key:
        err_detail = f" [x402: {x402_error}]" if x402_error else ""
        result.error = f"No AIXBT access — set AIXBT_API_KEY or AIXBT_WALLET_KEY (x402){err_detail}"
        result.confirmation = "UNAVAILABLE"
        return result

    async with aiohttp.ClientSession() as session:
        # Step 1: Find the project
        data = await _get(session, "/projects", {"names": name, "limit": 1}, api_key=api_key)
        if not data or not data.get("data"):
            result.error = f"Project '{name}' not found on AIXBT"
            result.found = False
            return result

        project = data["data"][0]
        result.found = True
        result.project_id = project.get("id", "")
        result.momentum_score = project.get("momentumScore", 0) or 0
        result.popularity_score = project.get("popularityScore", 0) or 0

        # Step 2: Fetch recent signals
        signals_data = await _get(
            session,
            "/signals",
            {"projectIds": result.project_id, "limit": 50},
            api_key=api_key,
        )

        if signals_data and signals_data.get("data"):
            for s in signals_data["data"]:
                sig = AIXBTSignal(
                    category=s.get("category", ""),
                    description=s.get("description", ""),
                    detected_at=s.get("detectedAt", ""),
                    reinforced_at=s.get("reinforcedAt", ""),
                    clusters=len(s.get("clusters", [])),
                )
                result.signals.append(sig)

        # Count signals by type
        result.signal_count = len(result.signals)
        result.risk_alert_count = sum(1 for s in result.signals if s.is_risk)
        result.bullish_signal_count = sum(1 for s in result.signals if s.is_bullish)
        result.whale_signals = sum(
            1 for s in result.signals if s.category == "WHALE_ACTIVITY"
        )

    # ── Derive narrative strength ────────────────────────────────
    mom = result.momentum_score
    pop = result.popularity_score
    bullish = result.bullish_signal_count

    if mom >= 5 and bullish >= 3:
        result.narrative_strength = "STRONG"
    elif mom >= 2 or bullish >= 2:
        result.narrative_strength = "MODERATE"
    elif mom >= 1 or bullish >= 1:
        result.narrative_strength = "WEAK"
    else:
        result.narrative_strength = "NONE"

    # ── Derive risk level ────────────────────────────────────────
    risks = result.risk_alert_count
    if risks >= 3:
        result.risk_level = "HIGH"
    elif risks >= 1:
        result.risk_level = "MEDIUM"
    else:
        result.risk_level = "LOW"

    # ── Derive confirmation verdict ──────────────────────────────
    # Logic: cross-reference narrative + risk
    if result.risk_level == "HIGH":
        result.confirmation = "DENIED"
    elif result.narrative_strength == "STRONG" and result.risk_level == "LOW":
        result.confirmation = "CONFIRMED"
    elif result.narrative_strength in ("STRONG", "MODERATE") and result.risk_level != "HIGH":
        result.confirmation = "NEUTRAL"
    elif result.narrative_strength in ("WEAK", "NONE"):
        result.confirmation = "CAUTION"
    else:
        result.confirmation = "NEUTRAL"

    # Cache result
    _cache[name] = (time.time(), result)
    return result


# ── Full Confirmation Report ─────────────────────────────────────────

async def build_confirmation_report(
    symbol: str,
    scanner_data: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    Build a complete confirmation report combining scanner data + AIXBT.
    Used by the /api/confirm endpoint and the Claude Skill.
    """
    aixbt = await confirm_symbol(symbol)

    report: Dict[str, Any] = {
        "symbol": symbol,
        "timestamp": time.time(),
        "aixbt": aixbt.to_dict(),
    }

    if scanner_data:
        report["scanner"] = {
            "signal": scanner_data.get("signal", "WAIT"),
            "signal_reason": scanner_data.get("signal_reason", ""),
            "regime": scanner_data.get("regime", ""),
            "confidence": scanner_data.get("confidence", 0),
            "conditions_met": scanner_data.get("conditions_met", 0),
            "conditions_total": scanner_data.get("conditions_total", 0),
            "effective_conditions": scanner_data.get("effective_conditions", 0),
            "zscore": scanner_data.get("zscore", 0),
            "heat": scanner_data.get("heat", 0),
            "heat_phase": scanner_data.get("heat_phase", ""),
            "exhaustion_state": scanner_data.get("exhaustion_state", ""),
            "floor_confirmed": scanner_data.get("floor_confirmed", False),
            "is_absorption": scanner_data.get("is_absorption", False),
            "divergence": scanner_data.get("divergence"),
            "price": scanner_data.get("price", 0),
            "vol_scale": scanner_data.get("vol_scale", 1.0),
            "signal_warnings": scanner_data.get("signal_warnings", []),
        }

    # ── Final Verdict ────────────────────────────────────────────
    # Combine scanner signal + AIXBT confirmation
    scanner_signal = scanner_data.get("signal", "WAIT") if scanner_data else "WAIT"
    aixbt_conf = aixbt.confirmation

    entry_signals = {"STRONG_LONG", "LIGHT_LONG", "ACCUMULATE", "REVIVAL_SEED", "REVIVAL_SEED_CONFIRMED"}
    exit_signals = {"TRIM", "TRIM_HARD", "RISK_OFF", "NO_LONG", "LIGHT_SHORT"}

    if scanner_signal in entry_signals:
        if aixbt_conf == "CONFIRMED":
            verdict = "GO"
            verdict_reason = f"Scanner says {scanner_signal} + AIXBT narrative CONFIRMED (momentum {aixbt.momentum_score:.1f}, {aixbt.bullish_signal_count} bullish signals)"
        elif aixbt_conf == "DENIED":
            verdict = "NO"
            verdict_reason = f"Scanner says {scanner_signal} BUT AIXBT flags {aixbt.risk_alert_count} risk alerts — narrative DENIED"
        elif aixbt_conf == "CAUTION":
            verdict = "WAIT"
            verdict_reason = f"Scanner says {scanner_signal} but AIXBT narrative is weak (momentum {aixbt.momentum_score:.1f}) — needs more confirmation"
        elif aixbt_conf == "UNAVAILABLE":
            verdict = "MANUAL"
            verdict_reason = f"Scanner says {scanner_signal} — AIXBT unavailable ({aixbt.error}), confirm manually"
        else:
            verdict = "LEAN_GO"
            verdict_reason = f"Scanner says {scanner_signal}, AIXBT neutral (momentum {aixbt.momentum_score:.1f}) — proceed with caution"
    elif scanner_signal in exit_signals:
        verdict = "EXIT"
        verdict_reason = f"Scanner says {scanner_signal} — exit/reduce position"
    else:
        verdict = "WAIT"
        verdict_reason = f"Scanner says {scanner_signal} — no entry conditions"

    report["verdict"] = {
        "action": verdict,
        "reason": verdict_reason,
        "scanner_signal": scanner_signal,
        "aixbt_confirmation": aixbt_conf,
    }

    return report
