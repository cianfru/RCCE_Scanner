"""
Sector, ecosystem and size tier for each market (display and grouping only).

Two dimensions, because a coin can be both: *sector* is what the project does
(Memes, AI, DeFi...), *ecosystem* is the chain it lives on (Solana, Base...). So
Seeker is Infrastructure on Solana, and WIF is Memes on Solana.

Curated by hand for the Hyperliquid perp universe (September 2026). Unknown coins
fall back to "Other" with no ecosystem; nothing in the signal path reads this.
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

SECTORS = (
    "Majors", "Layer 1", "Layer 2", "Payments", "DeFi", "Exchanges", "Memes", "AI",
    "Gaming & NFT", "Infrastructure", "RWA & Stablecoins", "Privacy", "Other",
)

_S = {
    # Majors and base layers
    "BTC": ("Majors", "Bitcoin"), "ETH": ("Majors", "Ethereum"),
    "SOL": ("Layer 1", "Solana"), "BNB": ("Layer 1", "BNB"), "ADA": ("Layer 1", None), "AVAX": ("Layer 1", None),
    "DOT": ("Layer 1", None), "ATOM": ("Layer 1", None), "NEAR": ("Layer 1", None), "APT": ("Layer 1", None),
    "SUI": ("Layer 1", None), "SEI": ("Layer 1", None), "ALGO": ("Layer 1", None), "HBAR": ("Layer 1", None),
    "ICP": ("Layer 1", None), "KAS": ("Layer 1", None), "ETC": ("Layer 1", None), "TRX": ("Layer 1", None),
    "TON": ("Layer 1", "TON"), "BERA": ("Layer 1", None), "CFX": ("Layer 1", None), "IOTA": ("Layer 1", None),
    "MINA": ("Layer 1", None), "NEO": ("Layer 1", None), "GAS": ("Layer 1", None), "INJ": ("Layer 1", None),
    "INIT": ("Layer 1", None), "S": ("Layer 1", None), "SAGA": ("Layer 1", None), "MON": ("Layer 1", None),
    "FOGO": ("Layer 1", None), "XPL": ("Layer 1", None), "kLUNC": ("Layer 1", None),
    # Layer 2s
    "ARB": ("Layer 2", "Arbitrum"), "OP": ("Layer 2", "Ethereum"), "POL": ("Layer 2", "Ethereum"),
    "STRK": ("Layer 2", "Ethereum"), "ZK": ("Layer 2", "Ethereum"), "MNT": ("Layer 2", "Ethereum"),
    "LINEA": ("Layer 2", "Ethereum"), "MANTA": ("Layer 2", "Ethereum"), "CELO": ("Layer 2", "Ethereum"),
    "MEGA": ("Layer 2", "Ethereum"), "SOPH": ("Layer 2", "Ethereum"), "MOVE": ("Layer 2", "Ethereum"),
    "ALT": ("Layer 2", "Ethereum"), "STX": ("Layer 2", "Bitcoin"), "MERL": ("Layer 2", "Bitcoin"),
    "HEMI": ("Layer 2", "Bitcoin"),
    # Payments
    "XRP": ("Payments", None), "XLM": ("Payments", None), "LTC": ("Payments", None), "BCH": ("Payments", None),
    "BSV": ("Payments", None),
    # Privacy
    "XMR": ("Privacy", None), "ZEC": ("Privacy", None), "DASH": ("Privacy", None), "ZEN": ("Privacy", "Base"),
    "AZTEC": ("Privacy", "Ethereum"), "ZAMA": ("Privacy", "Ethereum"),
    # DeFi
    "AAVE": ("DeFi", "Ethereum"), "UNI": ("DeFi", "Ethereum"), "LDO": ("DeFi", "Ethereum"), "CRV": ("DeFi", "Ethereum"),
    "COMP": ("DeFi", "Ethereum"), "MORPHO": ("DeFi", "Ethereum"), "PENDLE": ("DeFi", "Ethereum"),
    "ENA": ("DeFi", "Ethereum"), "ETHFI": ("DeFi", "Ethereum"), "SKY": ("DeFi", "Ethereum"), "SNX": ("DeFi", "Ethereum"),
    "SUSHI": ("DeFi", "Ethereum"), "REZ": ("DeFi", "Ethereum"), "RESOLV": ("DeFi", "Ethereum"),
    "SYRUP": ("DeFi", "Ethereum"), "WLFI": ("DeFi", "Ethereum"), "AERO": ("DeFi", "Base"), "CAKE": ("DeFi", "BNB"),
    "JUP": ("DeFi", "Solana"), "JTO": ("DeFi", "Solana"), "MET": ("DeFi", "Solana"), "RUNE": ("DeFi", None),
    # Exchanges and trading
    "HYPE": ("Exchanges", "Hyperliquid"), "DYDX": ("Exchanges", None), "GMX": ("Exchanges", "Arbitrum"),
    "ASTER": ("Exchanges", "BNB"), "APEX": ("Exchanges", None), "AVNT": ("Exchanges", "Base"),
    "LIT": ("Exchanges", "Ethereum"), "BANANA": ("Exchanges", "Ethereum"),
    # Memes
    "DOGE": ("Memes", None), "kSHIB": ("Memes", "Ethereum"), "kPEPE": ("Memes", "Ethereum"),
    "kFLOKI": ("Memes", "BNB"), "kNEIRO": ("Memes", "Ethereum"), "kBONK": ("Memes", "Solana"),
    "WIF": ("Memes", "Solana"), "POPCAT": ("Memes", "Solana"), "BOME": ("Memes", "Solana"),
    "PNUT": ("Memes", "Solana"), "MOODENG": ("Memes", "Solana"), "FARTCOIN": ("Memes", "Solana"),
    "TRUMP": ("Memes", "Solana"), "MELANIA": ("Memes", "Solana"), "USELESS": ("Memes", "Solana"),
    "PUMP": ("Memes", "Solana"), "GOAT": ("Memes", "Solana"), "BRETT": ("Memes", "Base"),
    "SPX": ("Memes", "Ethereum"), "PENGU": ("Memes", "Ethereum"), "MEME": ("Memes", "Ethereum"),
    "TURBO": ("Memes", "Ethereum"), "PEOPLE": ("Memes", "Ethereum"), "NOT": ("Memes", "TON"),
    "ORDI": ("Memes", "Bitcoin"), "PURR": ("Memes", "Hyperliquid"),
    # AI
    "TAO": ("AI", None), "FET": ("AI", None), "RENDER": ("AI", "Solana"), "WLD": ("AI", None),
    "VIRTUAL": ("AI", "Base"), "AIXBT": ("AI", "Base"), "VVV": ("AI", "Base"), "KAITO": ("AI", "Base"),
    "GRIFFAIN": ("AI", "Solana"), "GRASS": ("AI", "Solana"), "IO": ("AI", "Solana"), "0G": ("AI", None),
    "NIL": ("AI", None),
    # Gaming and NFT
    "APE": ("Gaming & NFT", "Ethereum"), "AXS": ("Gaming & NFT", "Ethereum"), "SAND": ("Gaming & NFT", "Ethereum"),
    "GALA": ("Gaming & NFT", "Ethereum"), "IMX": ("Gaming & NFT", "Ethereum"), "BIGTIME": ("Gaming & NFT", "Ethereum"),
    "BLUR": ("Gaming & NFT", "Ethereum"), "YGG": ("Gaming & NFT", "Ethereum"), "SUPER": ("Gaming & NFT", "Ethereum"),
    "ANIME": ("Gaming & NFT", "Arbitrum"), "XAI": ("Gaming & NFT", "Arbitrum"), "ACE": ("Gaming & NFT", "BNB"),
    "GMT": ("Gaming & NFT", "Solana"), "ME": ("Gaming & NFT", "Solana"), "TNSR": ("Gaming & NFT", "Solana"),
    "HMSTR": ("Gaming & NFT", "TON"), "NXPC": ("Gaming & NFT", None),
    # Infrastructure (oracles, interoperability, storage, restaking, DePIN)
    "LINK": ("Infrastructure", "Ethereum"), "PYTH": ("Infrastructure", "Solana"), "UMA": ("Infrastructure", "Ethereum"),
    "TRB": ("Infrastructure", "Ethereum"), "ZRO": ("Infrastructure", None), "W": ("Infrastructure", "Solana"),
    "HYPER": ("Infrastructure", None), "ZETA": ("Infrastructure", None), "WCT": ("Infrastructure", None),
    "FIL": ("Infrastructure", None), "AR": ("Infrastructure", None), "TIA": ("Infrastructure", None),
    "DYM": ("Infrastructure", None), "EIGEN": ("Infrastructure", "Ethereum"), "ENS": ("Infrastructure", "Ethereum"),
    "PROVE": ("Infrastructure", "Ethereum"), "BABY": ("Infrastructure", "Bitcoin"), "SKR": ("Infrastructure", "Solana"),
    "LAYER": ("Infrastructure", "Solana"), "2Z": ("Infrastructure", "Solana"), "SEDA": ("Infrastructure", None),
    # Real-world assets and stablecoins
    "ONDO": ("RWA & Stablecoins", "Ethereum"), "PAXG": ("RWA & Stablecoins", "Ethereum"),
    "XAUT": ("RWA & Stablecoins", "Ethereum"), "POLYX": ("RWA & Stablecoins", None),
    "RSR": ("RWA & Stablecoins", "Ethereum"), "USUAL": ("RWA & Stablecoins", "Ethereum"),
    "STABLE": ("RWA & Stablecoins", None), "STBL": ("RWA & Stablecoins", None), "CC": ("RWA & Stablecoins", None),
    "USDE": ("RWA & Stablecoins", "Ethereum"), "USDT": ("RWA & Stablecoins", None),
}


_S.update({"FART": _S["FARTCOIN"], "VIRT": _S["VIRTUAL"], "ZORA": ("Other", "Base")})   # spot tickers and alias
# HyperLens reports some coins under exchange-neutral names (kPEPE -> PEPE, RENDER -> RNDR).
_S.update({k: _S[f"k{k}"] for k in ("PEPE", "SHIB", "BONK", "FLOKI", "NEIRO", "LUNC")})
_S.update({"RNDR": _S["RENDER"], "FTM": _S["S"], "MATIC": _S["POL"]})


def _lookup(coin: str) -> Optional[Tuple[str, Optional[str]]]:
    if coin in _S:
        return _S[coin]
    up = coin.upper()
    for key in (up, re.sub(r"\d+$", "", up)):
        if key in _S:
            return _S[key]
        # Hyperliquid spot wrappers: UBTC, USOL, HPENGU, FXRP...
        if len(key) > 2 and key[0] in "UHF" and key[1:] in _S:
            return _S[key[1:]]
    return None


def classify(symbol: str, coin: Optional[str] = None) -> Tuple[str, Optional[str]]:
    # Spot markets carry Hyperliquid's internal coin id ("@107"), so the symbol's base is tried too.
    base = symbol.split("/")[0].split(":")[-1]
    return (coin and _lookup(coin)) or _lookup(base) or ("Other", None)


def size_tier(positioning: Optional[dict]) -> Optional[str]:
    """Large / Mid / Small by open interest (volume when OI is missing)."""
    p = positioning or {}
    oi, vol = p.get("oi_value") or 0.0, p.get("volume_24h") or 0.0
    size = oi or vol / 4.0
    if not size:
        return None
    return "Large" if size >= 100e6 else "Mid" if size >= 10e6 else "Small"


def groups(coin: str) -> Tuple[str, ...]:
    """Group keys for sector views: ("sector:AI", "ecosystem:Solana", "pocket:AI|Solana")."""
    sector, eco = classify(coin, coin)
    if not eco:
        return (f"sector:{sector}",)
    return (f"sector:{sector}", f"ecosystem:{eco}", f"pocket:{sector}|{eco}")
