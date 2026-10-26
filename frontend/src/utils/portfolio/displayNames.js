// Display names for Hyperliquid coins (Portfolio v2). "xyz:MSTR" shows as MSTR with a TradFi suffix,
// a spot pair "@107" as its base token (spotMeta), "kPEPE" as KPEPE (the app's key). A display name
// never reaches a trading call, a log-close or order matching: those keep the raw `coin`.
import { kKey } from "../tickerRenames.js";

// "main" (Hyperliquid's own perps), "spot" (@n pairs), or the builder dex ("xyz", "para", ...).
export function venueOf(coin) {
  if (typeof coin !== "string" || !coin) return "main";
  if (coin.startsWith("@") || coin.includes("/")) return "spot";
  const i = coin.indexOf(":");
  return i > 0 ? coin.slice(0, i) : "main";
}

export const isMainDex = coin => venueOf(coin) === "main";

// "@107" -> "HYPE" from spotMeta's universe (the pair's base token); canonical pairs ("PURR/USDC") too.
export function spotNames(spotMeta) {
  const out = new Map();
  if (!spotMeta?.universe || !spotMeta?.tokens) return out;
  const tokens = new Map(spotMeta.tokens.map(t => [t.index, t.name]));
  for (const u of spotMeta.universe) {
    const base = tokens.get(u.tokens?.[0]);
    if (base) out.set(u.name, base);
  }
  return out;
}

// { name, suffix, venue }: suffix is "TradFi" on xyz rows, the dex name on other builder dexes.
export function displayName(coin, names = null) {
  const venue = venueOf(coin);
  if (!coin) return { name: "", suffix: null, venue };
  if (venue === "spot") return { name: names?.get?.(coin) || coin, suffix: null, venue };
  if (venue !== "main") {
    const name = coin.slice(coin.indexOf(":") + 1);
    return { name, suffix: venue === "xyz" ? "TradFi" : venue, venue };
  }
  return { name: kKey(coin), suffix: null, venue };
}

// The token logo key for a coin ("HYPE/USDT"); builder-dex coins fall back to their monogram.
export const logoSymbol = coin => `${displayName(coin).name}/USDT`;
