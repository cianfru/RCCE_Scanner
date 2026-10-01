// The order wires the manual trade panel signs for Hyperliquid (services/hlClient.js), kept pure so
// they can be tested. The coin arrives under the app's key ("BTC", "KPEPE") and leaves under
// Hyperliquid's name ("BTC", "kPEPE"): its asset index, szDecimals and mid price are all looked up
// under that name. A k market's price is per 1,000 tokens, so size = USD / price is in k-units.
import { hlName } from "./tickerRenames.js";

// Hyperliquid's meta -> { byName: { kPEPE: { index, szDecimals, maxLeverage } }, universe }.
export function metaIndex(universe) {
  const byName = {};
  (universe || []).forEach((u, i) => {
    byName[u.name] = { index: i, szDecimals: u.szDecimals, maxLeverage: u.maxLeverage };
  });
  return { universe: universe || [], byName };
}

// The meta entry for an app key, under Hyperliquid's name; throws for an unknown asset.
export function assetFor(coin, byName) {
  const name = hlName(coin, byName);
  const entry = byName[name];
  if (entry == null) throw new Error(`Unknown asset: ${coin}`);
  return { name, ...entry };
}

// x * 10^d as a count of steps, with float noise (0.29 * 100 = 28.999999999999996) snapped back to
// the step it stands for, so a floor or a ceil does not slip a whole step.
function steps(x, d) {
  const n = x * Math.pow(10, d);
  const r = Math.round(n);
  return Math.abs(n - r) <= 1e-9 * Math.max(1, Math.abs(n)) ? r : n;
}

// Size floored to the market's szDecimals (never over-sized, so a close never exceeds the position).
export function formatVolume(volume, szDecimals) {
  return Math.floor(steps(volume, szDecimals)) / Math.pow(10, szDecimals);
}

// Hyperliquid's perp price rule: at most 5 significant figures and at most (6 - szDecimals) decimal
// places; an integer price is always allowed. `round` is "up", "down" or "nearest": a marketable buy
// limit rounds up and a sell limit rounds down, so the slippage limit stays on the marketable side.
// Returns a plain decimal string without trailing zeros.
export function formatPrice(px, szDecimals, round = "nearest") {
  if (!Number.isFinite(px) || px <= 0) throw new Error(`Invalid price: ${px}`);
  if (Number.isInteger(px)) return String(px);
  let mag = Math.floor(Math.log10(px));                    // place of the first significant digit
  if (Math.pow(10, mag) > px) mag -= 1;
  else if (Math.pow(10, mag + 1) <= px) mag += 1;
  const decimals = Math.max(0, Math.min(6 - szDecimals, 4 - mag));
  const n = steps(px, decimals);
  const k = round === "up" ? Math.ceil(n) : round === "down" ? Math.floor(n) : Math.round(n);
  if (k <= 0) throw new Error(`Price ${px} rounds to zero`);
  const s = (k / Math.pow(10, decimals)).toFixed(decimals);
  return decimals > 0 ? s.replace(/0+$/, "").replace(/\.$/, "") : s;
}

function limitPrice(midPrice, isBuy, slippage, szDecimals) {
  const px = isBuy ? midPrice * (1 + slippage) : midPrice * (1 - slippage);
  return formatPrice(px, szDecimals, isBuy ? "up" : "down");
}

function midFor(name, coin, mids) {
  const mid = parseFloat(mids[name]);
  if (!mid || mid <= 0) throw new Error(`No mid price for ${coin}`);
  return mid;
}

// A market order (IOC at a slippage-adjusted limit) for `sizeUsd` of `coin`.
export function marketOrderWire({ coin, isBuy, sizeUsd, slippage = 0.01 }, byName, mids) {
  const asset = assetFor(coin, byName);
  const midPrice = midFor(asset.name, coin, mids);
  const volume = formatVolume(sizeUsd / midPrice, asset.szDecimals);
  if (volume <= 0) throw new Error(`Volume too small for $${sizeUsd} of ${coin}`);
  return {
    name: asset.name, midPrice, volume,
    order: { a: asset.index, b: isBuy, p: limitPrice(midPrice, isBuy, slippage, asset.szDecimals), s: volume.toString(), r: false, t: { limit: { tif: "Ioc" } } },
  };
}

// A reduce-only IOC closing `size` of a position in `coin`.
export function closeOrderWire({ coin, size, isLong, slippage = 0.02 }, byName, mids) {
  const asset = assetFor(coin, byName);
  const midPrice = midFor(asset.name, coin, mids);
  const isBuy = !isLong;
  const volume = formatVolume(Math.abs(size), asset.szDecimals);
  if (volume <= 0) throw new Error(`Volume too small to close ${coin}`);
  return {
    name: asset.name, midPrice, volume,
    order: { a: asset.index, b: isBuy, p: limitPrice(midPrice, isBuy, slippage, asset.szDecimals), s: volume.toString(), r: true, t: { limit: { tif: "Ioc" } } },
  };
}
