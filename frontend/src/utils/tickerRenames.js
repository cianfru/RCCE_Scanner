// Tickers Hyperliquid renamed: the old perp was delisted and the coin trades under the new name
// (backend/ticker_renames.py). The app keys these markets by the current names; names saved in
// this browser before the rename are mapped when they are read.
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
