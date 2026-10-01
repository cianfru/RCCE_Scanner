// Tickers Hyperliquid renamed: the old perp was delisted and the coin trades under the new name
// (backend/ticker_renames.py). The app keys these markets by the current names; names saved in
// this browser before the rename are mapped when they are read.
import { K_BASES } from "../data/coinNames.js";

export const RENAMED = { FTM: "S", MATIC: "POL", RNDR: "RENDER" };

// "MATIC" -> "POL", "MATIC/USDT" -> "POL/USDT"; anything else unchanged.
export function currentSymbol(symbol) {
  if (typeof symbol !== "string" || !symbol) return symbol;
  const i = symbol.indexOf("/");
  const base = i < 0 ? symbol : symbol.slice(0, i);
  const now = Object.prototype.hasOwnProperty.call(RENAMED, base) ? RENAMED[base] : null;
  return now ? now + (i < 0 ? "" : symbol.slice(i)) : symbol;
}

// A saved list with old names mapped, order kept, duplicates dropped; `changed` when any moved.
export function currentSymbols(list) {
  const out = [], seen = new Set();
  let changed = false;
  for (const s of Array.isArray(list) ? list : []) {
    const c = currentSymbol(s);
    if (c !== s) changed = true;
    if (!seen.has(c)) { seen.add(c); out.push(c); } else changed = true;
  }
  return { list: out, changed };
}

// Hyperliquid's "k" markets (perps quoted per 1,000 tokens) are named kPEPE there and keyed KPEPE
// in the app (backend ticker_renames.k_key / hl_name). Hyperliquid's answers are keyed back with
// kKey; anything sent to Hyperliquid goes out under hlName.
const K_HL = /^k[A-Z0-9]+$/;

// "kPEPE" -> "KPEPE"; anything else unchanged.
export function kKey(name) {
  return typeof name === "string" && K_HL.test(name) ? "K" + name.slice(1) : name;
}

// "kPEPE/USDT" -> "KPEPE/USDT"; anything else unchanged.
export function kSymbol(symbol) {
  if (typeof symbol !== "string") return symbol;
  const i = symbol.indexOf("/");
  return i < 0 ? kKey(symbol) : kKey(symbol.slice(0, i)) + symbol.slice(i);
}

// The app's key -> Hyperliquid's name: "KPEPE" -> "kPEPE". `known` (Hyperliquid's names, from its
// meta) also resolves a k market listed after K_BASES; KAS and KAITO stay as they are.
export function hlName(coin, known = null) {
  if (typeof coin !== "string" || coin.length < 2 || coin[0] !== "K") return coin;
  const k = "k" + coin.slice(1);
  if (K_BASES.has(coin.slice(1))) return k;
  const has = n => known != null && Object.prototype.hasOwnProperty.call(known, n);
  return !has(coin) && has(k) ? k : coin;
}
