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

// Size floored to the market's szDecimals (never over-sized).
export function formatVolume(volume, szDecimals) {
  const factor = Math.pow(10, szDecimals);
  return Math.floor(volume * factor) / factor;
}

function limitPrice(midPrice, isBuy, slippage) {
  const px = isBuy ? midPrice * (1 + slippage) : midPrice * (1 - slippage);
  const precision = midPrice > 10000 ? 1 : midPrice > 100 ? 2 : midPrice > 1 ? 4 : 6;
  return px.toFixed(precision);
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
    order: { a: asset.index, b: isBuy, p: limitPrice(midPrice, isBuy, slippage), s: volume.toString(), r: false, t: { limit: { tif: "Ioc" } } },
  };
}

// A reduce-only IOC closing `size` of a position in `coin`.
export function closeOrderWire({ coin, size, isLong, slippage = 0.02 }, byName, mids) {
  const asset = assetFor(coin, byName);
  const midPrice = midFor(asset.name, coin, mids);
  const isBuy = !isLong;
  const volume = formatVolume(Math.abs(size), asset.szDecimals);
  return {
    name: asset.name, midPrice, volume,
    order: { a: asset.index, b: isBuy, p: limitPrice(midPrice, isBuy, slippage), s: volume.toString(), r: true, t: { limit: { tif: "Ioc" } } },
  };
}
