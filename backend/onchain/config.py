"""
On-chain tracker configuration — chain definitions, known wallets, thresholds.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Chain definitions
# ---------------------------------------------------------------------------

CHAINS: dict = {
    "ethereum": {
        "name": "Ethereum",
        "short": "ETH",
        "color": "#627eea",
        "api_base": "https://api.etherscan.io/v2/api",
        "chain_id": "1",
        "api_key_env": "ETHERSCAN_API_KEY",
        "api_type": "etherscan",       # shared fetcher for etherscan-format APIs
        "rate_limit": 5,               # calls per second (free tier)
        "native_symbol": "ETH",
        "explorer": "https://etherscan.io",
    },
    "base": {
        "name": "Base",
        "short": "BASE",
        "color": "#0052ff",
        "api_base": "https://api.etherscan.io/v2/api",
        "chain_id": "8453",
        "api_key_env": "BASESCAN_API_KEY",
        "api_type": "etherscan",
        "rate_limit": 5,
        "native_symbol": "ETH",
        "explorer": "https://basescan.org",
    },
    "solana": {
        "name": "Solana",
        "short": "SOL",
        "color": "#9945ff",
        "api_base": "https://pro-api.solscan.io/v2.0",
        "api_key_env": "SOLSCAN_API_KEY",
        "api_type": "solscan",
        "rate_limit": 10,
        "native_symbol": "SOL",
        "explorer": "https://solscan.io",
    },
}

# ---------------------------------------------------------------------------
# Known whale wallets (seed data)
# ---------------------------------------------------------------------------

KNOWN_WHALE_SEEDS: dict = {
    "ethereum": {
        # Market makers
        "0x0000000000000000000000000000000000000000": "Burn Address",
        "0xF977814e90dA44bFA03b6295A0616a897441aceC": "Binance Hot 8",
        "0x28C6c06298d514Db089934071355E5743bf21d60": "Binance Hot 14",
        "0x21a31Ee1afC51d94C2eFcCAa2092aD1028285549": "Binance Hot 15",
        "0xDFd5293D8e347dFe59E90eFd55b2956a1343963d": "Binance Hot 16",
        "0x56Eddb7aa87536c09CCc2793473599fD21A8b17F": "Binance Hot 17",
        "0x47ac0Fb4F2D84898e4D9E7b4DaB3C24507a6D503": "Binance Cold",
        "0xBE0eB53F46cd790Cd13851d5EFf43D12404d33E8": "Binance Cold 2",
        "0xd6216fC19DB775Df9774a6E33526131dA7D19a2c": "KuCoin Hot",
        "0xf89d7b9c864f589bbF53a82105107622B35EaA40": "Bybit Hot",
        "0x1AB4973a48dc892Cd9971ECE8e01DcC7688f8F23": "Wintermute",
        "0xDBF5E9c5206d0dB70a90108bf936DA60221dC080": "Wintermute 2",
        "0x9507c04B10486547584C37bCBd931B5a4BF54A51": "Jump Trading",
        "0xCa8Fa8f0b631EcdB18Cda619C4Fc9d197c8aFfCa": "Jump Trading 2",
        "0xE8C060F8052E07423f71D445277c61AC5138A2e5": "Cumberland",
        "0x6Cc5F688a315f3dC28A7781717a9A798a59fDA7b": "Alameda Research",
        "0x77134cbC06cB00b66F4c7e623D5fdBF6777635EC": "Galaxy Digital",
        "0x7858E59e0C01EA06Df3aF3D20aC7B0003275D4Bf": "Paradigm",
        "0xa1D8d972560C2f8144AF871Db508F0B0B10a3fBf": "a16z",
    },
    "base": {
        "0x0000000000000000000000000000000000000000": "Burn Address",
        "0x3304E22DDaa22bCdC5fCa2269b418046aE7b566A": "Coinbase Bridge",
        "0x1AB4973a48dc892Cd9971ECE8e01DcC7688f8F23": "Wintermute",
    },
    "solana": {
        "5tzFkiKscjHsFKhFJDbnTraKFjNcDjNQkSz1UhbR5M87": "Wintermute",
        "CJqXEB5LuoSFmEYNMg1i2KHLZ68VHR1P7zMEHafmmnnM": "Jump Trading",
        "2VfCkgJBrd5fRwdqKoMaWNFnFGRnZqEgTbfSKE3Kd8q4": "Alameda Research",
        "DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK": "Binance",
        "3yFwqXBfZY4jBVUafQ1YEXw189y2dN3V5KQq9uzBDy1E": "FTX Estate",
        "HN7cABqLq46Es1jh92dQQisAq662SmxELLLsHHe4YWrH": "Raydium",
    },
}

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

# USD value above which a single transfer is flagged
LARGE_TX_USD: float = 50_000.0

# Minimum USD holdings to be classified as a "whale" for a given token
WHALE_HOLDING_USD: float = 100_000.0

# Accumulation detection parameters
ACCUMULATION_WINDOW: int = 20       # look at last N transfers per wallet
ACCUMULATION_MIN_BUYS: int = 7      # min buy transactions in window to flag

# Distribution detection parameters
DISTRIBUTION_MIN_SELLS: int = 5     # min sell transactions in window to flag

# Trending detection
TRENDING_MIN_WHALE_WALLETS: int = 3   # distinct whale wallets active in 24h
TRENDING_LOOKBACK_HOURS: int = 24

# ---------------------------------------------------------------------------
# Polling intervals (seconds)
# ---------------------------------------------------------------------------

POLL_INTERVAL_TRANSFERS: int = 120   # 2 minutes
POLL_INTERVAL_HOLDERS: int = 600     # 10 minutes

# ---------------------------------------------------------------------------
# Cache limits
# ---------------------------------------------------------------------------

MAX_TRANSFERS_PER_TOKEN: int = 300   # keep last N transfers in memory
MAX_ALERTS: int = 100                # keep last N alerts
MAX_TRENDING: int = 20               # max trending tokens to surface

# ---------------------------------------------------------------------------
# CoinGecko price endpoint (for USD estimation)
# ---------------------------------------------------------------------------

COINGECKO_PRICE_URL = "https://api.coingecko.com/api/v3/simple/price"
PRICE_CACHE_TTL: int = 300           # 5 minutes
