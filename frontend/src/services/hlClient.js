/**
 * hlClient.js — Hyperliquid trading client for browser wallet signing.
 *
 * Wraps @nktkas/hyperliquid SDK for market orders, position closes,
 * leverage updates, and read-only info queries.
 */

import { HttpTransport, ExchangeClient, InfoClient } from "@nktkas/hyperliquid";

// ---------------------------------------------------------------------------
// Shared transport + info (no wallet needed for reads)
// ---------------------------------------------------------------------------

const transport = new HttpTransport();
const infoClient = new InfoClient({ transport });

// ---------------------------------------------------------------------------
// Cache: asset meta (name→index, szDecimals)
// ---------------------------------------------------------------------------

let _metaCache = null; // { universe: [...], byName: { BTC: { index: 0, szDecimals: 5, ... } } }
let _metaPromise = null;

async function ensureMeta() {
  if (_metaCache) return _metaCache;
  if (_metaPromise) return _metaPromise;
  _metaPromise = (async () => {
    const raw = await infoClient.meta();
    const byName = {};
    raw.universe.forEach((u, i) => {
      byName[u.name] = { index: i, szDecimals: u.szDecimals, maxLeverage: u.maxLeverage };
    });
    _metaCache = { universe: raw.universe, byName };
    return _metaCache;
  })();
  return _metaPromise;
}

/**
 * Resolve coin name (e.g. "BTC") to its HL asset index.
 */
export async function getAssetIndex(coin) {
  const meta = await ensureMeta();
  const entry = meta.byName[coin];
  if (entry == null) throw new Error(`Unknown asset: ${coin}`);
  return entry.index;
}

/**
 * Get szDecimals for volume rounding.
 */
export async function getSzDecimals(coin) {
  const meta = await ensureMeta();
  const entry = meta.byName[coin];
  if (entry == null) throw new Error(`Unknown asset: ${coin}`);
  return entry.szDecimals;
}

// ---------------------------------------------------------------------------
// Leverage cache (avoid re-signing if unchanged)
// ---------------------------------------------------------------------------

const _leverageCache = new Map(); // "BTC" → lastSetLeverage

// ---------------------------------------------------------------------------
// Read-only queries
// ---------------------------------------------------------------------------

/**
 * Get all mid prices: { "BTC": "95023.5", "ETH": "3421.2", ... }
 */
export async function getAllMids() {
  return infoClient.allMids();
}

// ---------------------------------------------------------------------------
// Volume formatting
// ---------------------------------------------------------------------------

function formatVolume(volume, szDecimals) {
  const factor = Math.pow(10, szDecimals);
  return Math.floor(volume * factor) / factor; // always floor to avoid over-sizing
}

// ---------------------------------------------------------------------------
// Exchange actions (require wallet)
// ---------------------------------------------------------------------------

function makeExchangeConfig(walletClient) {
  return { transport, wallet: walletClient };
}

/**
 * Set leverage for an asset. Skips if already set to same value.
 * Returns true if leverage was actually updated (wallet popup occurred).
 */
export async function setLeverage(walletClient, { coin, leverage, isCross = true }) {
  const cached = _leverageCache.get(coin);
  if (cached === leverage) return false;

  const assetIdx = await getAssetIndex(coin);
  const exchange = new ExchangeClient(makeExchangeConfig(walletClient));
  await exchange.updateLeverage({ asset: assetIdx, leverage, isCross });
  _leverageCache.set(coin, leverage);
  return true;
}

/**
 * Place a market order (IOC at slippage-adjusted price).
 *
 * @param walletClient - viem WalletClient connected to MetaMask/Rabby
 * @param opts.coin     - "BTC", "ETH" etc
 * @param opts.isBuy    - true for long, false for short
 * @param opts.sizeUsd  - position size in USD
 * @param opts.slippage - slippage tolerance (default 0.01 = 1%)
 * @returns { avgPx, totalSz, oid }
 */
export async function placeMarketOrder(walletClient, { coin, isBuy, sizeUsd, slippage = 0.01 }) {
  const [mids, assetIdx, szDec] = await Promise.all([
    getAllMids(),
    getAssetIndex(coin),
    getSzDecimals(coin),
  ]);

  const midPrice = parseFloat(mids[coin]);
  if (!midPrice || midPrice <= 0) throw new Error(`No mid price for ${coin}`);

  // Compute volume
  let volume = sizeUsd / midPrice;
  volume = formatVolume(volume, szDec);
  if (volume <= 0) throw new Error(`Volume too small for $${sizeUsd} of ${coin}`);

  // Slippage-adjusted limit price for IOC
  const limitPrice = isBuy ? midPrice * (1 + slippage) : midPrice * (1 - slippage);
  // Round price to reasonable precision
  const pricePrecision = midPrice > 10000 ? 1 : midPrice > 100 ? 2 : midPrice > 1 ? 4 : 6;
  const priceStr = limitPrice.toFixed(pricePrecision);

  const exchange = new ExchangeClient(makeExchangeConfig(walletClient));
  const result = await exchange.order({
    orders: [{
      a: assetIdx,
      b: isBuy,
      p: priceStr,
      s: volume.toString(),
      r: false,
      t: { limit: { tif: "Ioc" } },
    }],
    grouping: "na",
  });

  // Parse response
  const status = result.response.data.statuses[0];
  if ("error" in status) throw new Error(status.error);
  if ("filled" in status) {
    return {
      avgPx: parseFloat(status.filled.avgPx),
      totalSz: parseFloat(status.filled.totalSz),
      oid: status.filled.oid,
      volume,
      midPrice,
    };
  }
  if ("resting" in status) {
    return { avgPx: midPrice, totalSz: volume, oid: status.resting.oid, volume, midPrice };
  }
  // waitingForFill etc
  return { avgPx: midPrice, totalSz: volume, oid: 0, volume, midPrice };
}

/**
 * Close an entire position (reduce-only IOC).
 *
 * @param walletClient
 * @param opts.coin       - "BTC"
 * @param opts.size       - position size to close (absolute)
 * @param opts.isLong     - true if current position is long (we sell to close)
 * @param opts.slippage   - default 0.02 (2% for closes)
 */
export async function closePosition(walletClient, { coin, size, isLong, slippage = 0.02 }) {
  const [mids, assetIdx, szDec] = await Promise.all([
    getAllMids(),
    getAssetIndex(coin),
    getSzDecimals(coin),
  ]);

  const midPrice = parseFloat(mids[coin]);
  if (!midPrice || midPrice <= 0) throw new Error(`No mid price for ${coin}`);

  // To close a long, we sell (isBuy=false). To close a short, we buy (isBuy=true).
  const isBuy = !isLong;
  const limitPrice = isBuy ? midPrice * (1 + slippage) : midPrice * (1 - slippage);
  const pricePrecision = midPrice > 10000 ? 1 : midPrice > 100 ? 2 : midPrice > 1 ? 4 : 6;
  const priceStr = limitPrice.toFixed(pricePrecision);

  const vol = formatVolume(Math.abs(size), szDec);

  const exchange = new ExchangeClient(makeExchangeConfig(walletClient));
  const result = await exchange.order({
    orders: [{
      a: assetIdx,
      b: isBuy,
      p: priceStr,
      s: vol.toString(),
      r: true, // reduce-only
      t: { limit: { tif: "Ioc" } },
    }],
    grouping: "na",
  });

  const status = result.response.data.statuses[0];
  if ("error" in status) throw new Error(status.error);
  if ("filled" in status) {
    return {
      avgPx: parseFloat(status.filled.avgPx),
      totalSz: parseFloat(status.filled.totalSz),
      oid: status.filled.oid,
    };
  }
  return { avgPx: midPrice, totalSz: vol, oid: 0 };
}
