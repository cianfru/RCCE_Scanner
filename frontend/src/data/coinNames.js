// Full names for Hyperliquid perp tickers, for search ("bitcoin" finds BTC). Hand-made for the
// main markets; a ticker missing here is still found by its ticker. The "k" markets (kPEPE,
// kSHIB ...) are keyed by their base ticker without the k.
export const COIN_NAMES = {
  "0G": "0G", "2Z": "DoubleZero", AAVE: "Aave", ACE: "Fusionist", ADA: "Cardano", AERO: "Aerodrome",
  AIXBT: "aixbt", ALGO: "Algorand", ALT: "AltLayer", ANIME: "Animecoin", APE: "ApeCoin", APEX: "ApeX",
  APT: "Aptos", AR: "Arweave", ARB: "Arbitrum", ASTER: "Aster", ATOM: "Cosmos", AVAX: "Avalanche",
  AVNT: "Avantis", AXS: "Axie Infinity", AZTEC: "Aztec", BABY: "Babylon", BANANA: "Banana Gun",
  BCH: "Bitcoin Cash", BERA: "Berachain", BIGTIME: "Big Time", BIO: "Bio Protocol", BLUR: "Blur",
  BNB: "BNB", BOME: "Book of Meme", BONK: "Bonk", BRETT: "Brett", BSV: "Bitcoin SV", BTC: "Bitcoin",
  CAKE: "PancakeSwap", CELO: "Celo", CFX: "Conflux", COMP: "Compound", CRV: "Curve", DASH: "Dash",
  DOGE: "Dogecoin", DOT: "Polkadot", DYDX: "dYdX", DYM: "Dymension", EIGEN: "EigenLayer", ENA: "Ethena",
  ENS: "Ethereum Name Service", ETC: "Ethereum Classic", ETH: "Ethereum", ETHFI: "ether.fi",
  FARTCOIN: "Fartcoin", FET: "Fetch.ai", FIL: "Filecoin", FLOKI: "Floki",
  FOGO: "Fogo", GALA: "Gala", GAS: "Neo Gas", GMT: "STEPN", GMX: "GMX", GOAT: "Goatseus Maximus",
  GRASS: "Grass", GRIFFAIN: "Griffain", HBAR: "Hedera", HEMI: "Hemi", HMSTR: "Hamster Kombat",
  HYPE: "Hyperliquid", HYPER: "Hyperlane", ICP: "Internet Computer", IMX: "Immutable", INIT: "Initia",
  INJ: "Injective", IO: "io.net", IOTA: "IOTA", JTO: "Jito", JUP: "Jupiter", KAITO: "Kaito", KAS: "Kaspa",
  LAYER: "Solayer", LDO: "Lido DAO", LINEA: "Linea", LINK: "Chainlink", LIT: "Lighter", LTC: "Litecoin",
  LUNC: "Terra Classic", MANTA: "Manta Network", ME: "Magic Eden", MEGA: "MegaETH", MELANIA: "Official Melania",
  MEME: "Memecoin", MERL: "Merlin Chain", MET: "Meteora", MINA: "Mina", MNT: "Mantle", MON: "Monad",
  MOODENG: "Moo Deng", MORPHO: "Morpho", MOVE: "Movement", NEAR: "NEAR Protocol", NEIRO: "Neiro",
  NEO: "Neo", NIL: "Nillion", NOT: "Notcoin", NXPC: "NEXPACE", ONDO: "Ondo", OP: "Optimism", ORDI: "ORDI",
  PAXG: "PAX Gold", PENDLE: "Pendle", PENGU: "Pudgy Penguins", PEOPLE: "ConstitutionDAO", PEPE: "Pepe",
  PNUT: "Peanut the Squirrel", POL: "Polygon", POLYX: "Polymesh", POPCAT: "Popcat", PROVE: "Succinct",
  PUMP: "Pump.fun", PURR: "Purr", PYTH: "Pyth Network", RENDER: "Render", RESOLV: "Resolv", REZ: "Renzo",
  RSR: "Reserve Rights", RUNE: "THORChain", S: "Sonic", SAGA: "Saga", SAND: "The Sandbox", SEI: "Sei",
  SHIB: "Shiba Inu", SKY: "Sky", SNX: "Synthetix", SOL: "Solana", SOPH: "Sophon", SPX: "SPX6900",
  STABLE: "Stable", STBL: "STBL", STRK: "Starknet", STX: "Stacks", SUI: "Sui", SUPER: "SuperVerse",
  SUSHI: "SushiSwap", SYRUP: "Maple Finance", TAO: "Bittensor", TIA: "Celestia", TNSR: "Tensor",
  TRB: "Tellor", TRUMP: "Official Trump", TRX: "TRON", TURBO: "Turbo", UMA: "UMA", UNI: "Uniswap",
  USELESS: "Useless Coin", USUAL: "Usual", VIRTUAL: "Virtuals Protocol", VVV: "Venice Token",
  W: "Wormhole", WCT: "WalletConnect", WIF: "dogwifhat", WLD: "Worldcoin", WLFI: "World Liberty Financial",
  XAI: "Xai", XLM: "Stellar", XMR: "Monero", XPL: "Plasma", XRP: "XRP", YGG: "Yield Guild Games",
  ZEC: "Zcash", ZEN: "Horizen", ZETA: "ZetaChain", ZK: "ZKsync", ZORA: "Zora", ZRO: "LayerZero",
};

// The name for a market's base ticker ("KPEPE" or "kPEPE" is Pepe); "" when unknown.
export function coinName(ticker) {
  const t = String(ticker || "").toUpperCase();
  return COIN_NAMES[t] || (t.length > 1 && t[0] === "K" && COIN_NAMES[t.slice(1)]) || "";
}
