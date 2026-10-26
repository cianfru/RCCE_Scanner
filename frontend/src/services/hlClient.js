/**
 * hlClient.js — Hyperliquid trading client for browser wallet signing.
 *
 * Wraps @nktkas/hyperliquid SDK for market orders, position closes,
 * leverage updates, and read-only info queries.
 */

import { HttpTransport, ExchangeClient, InfoClient } from "@nktkas/hyperliquid";
import { metaIndex, assetFor, marketOrderWire, closeOrderWire } from "../utils/hlOrder.js";

// Coins arrive under the app's key ("KPEPE") and are sent under Hyperliquid's name ("kPEPE"):
// asset index, szDecimals and mid price are all looked up by that name (utils/hlOrder.js).

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
    _metaCache = metaIndex(raw.universe);
    return _metaCache;
  })();
  return _metaPromise;
}

/**
 * Resolve a coin ("BTC", "KPEPE") to its HL asset index.
 */
export async function getAssetIndex(coin) {
  const meta = await ensureMeta();
  return assetFor(coin, meta.byName).index;
}

/**
 * Get szDecimals for volume rounding (a k market's own: kPEPE's, not PEPE's).
 */
export async function getSzDecimals(coin) {
  const meta = await ensureMeta();
  return assetFor(coin, meta.byName).szDecimals;
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
  const meta = await ensureMeta();
  const asset = assetFor(coin, meta.byName);
  const cached = _leverageCache.get(asset.name);
  if (cached === leverage) return false;

  const exchange = new ExchangeClient(makeExchangeConfig(walletClient));
  await exchange.updateLeverage({ asset: asset.index, leverage, isCross });
  _leverageCache.set(asset.name, leverage);
  return true;
}

/**
 * Place a market order (IOC at slippage-adjusted price).
 *
 * @param walletClient - viem WalletClient connected to MetaMask/Rabby
 * @param opts.coin     - "BTC", "ETH", "KPEPE" etc (the app's key)
 * @param opts.isBuy    - true for long, false for short
 * @param opts.sizeUsd  - position size in USD
 * @param opts.slippage - slippage tolerance (default 0.01 = 1%)
 * @returns { avgPx, totalSz, oid }
 */
export async function placeMarketOrder(walletClient, { coin, isBuy, sizeUsd, slippage = 0.01 }) {
  const [mids, meta] = await Promise.all([getAllMids(), ensureMeta()]);
  const { order, volume, midPrice } = marketOrderWire({ coin, isBuy, sizeUsd, slippage }, meta.byName, mids);

  const exchange = new ExchangeClient(makeExchangeConfig(walletClient));
  const result = await exchange.order({ orders: [order], grouping: "na" });

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
 * @param opts.coin       - "BTC", "KPEPE" or Hyperliquid's "kPEPE"
 * @param opts.size       - position size to close (absolute)
 * @param opts.isLong     - true if current position is long (we sell to close)
 * @param opts.slippage   - default 0.02 (2% for closes)
 */
export async function closePosition(walletClient, { coin, size, isLong, slippage = 0.02 }) {
  const [mids, meta] = await Promise.all([getAllMids(), ensureMeta()]);
  // To close a long, we sell; to close a short, we buy (reduce-only).
  const { order, volume: vol, midPrice } = closeOrderWire({ coin, size, isLong, slippage }, meta.byName, mids);

  const exchange = new ExchangeClient(makeExchangeConfig(walletClient));
  const result = await exchange.order({ orders: [order], grouping: "na" });

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

// ---------------------------------------------------------------------------
// Portfolio read-only queries (no wallet needed)
// ---------------------------------------------------------------------------

const PERIOD_MAP = {
  "1D": "perpDay", "1W": "perpWeek", "1M": "perpMonth", "ALL": "perpAllTime",
  day: "day", week: "week", month: "month", allTime: "allTime",
  perpDay: "perpDay", perpWeek: "perpWeek", perpMonth: "perpMonth", perpAllTime: "perpAllTime",
};

/**
 * Get historical portfolio data (account value, PnL, volume) by time period.
 * Returns { perpDay, perpWeek, perpMonth, perpAllTime, ... } each with
 * { accountValueHistory: [{time,value}], pnlHistory: [{time,value}], vlm }
 */
export async function getPortfolio(address) {
  const raw = await infoClient.portfolio({ user: address });
  const byPeriod = {};
  for (const [period, data] of raw) {
    byPeriod[period] = {
      accountValueHistory: data.accountValueHistory.map(([ts, val]) => ({
        time: Math.floor(ts / 1000),
        value: parseFloat(val),
      })),
      pnlHistory: data.pnlHistory.map(([ts, val]) => ({
        time: Math.floor(ts / 1000),
        value: parseFloat(val),
      })),
      vlm: parseFloat(data.vlm),
    };
  }
  return byPeriod;
}

/** Resolve a friendly period key (e.g. "1W") to the SDK period name. */
export function resolvePeriod(key) {
  return PERIOD_MAP[key] || key;
}

/**
 * Get full clearinghouse state (margin, positions, withdrawable).
 */
export async function getClearinghouseState(address) {
  return infoClient.clearinghouseState({ user: address });
}

/**
 * Get xyz DEX (HIP-3 TradFi) clearinghouse state.
 */
export async function getXyzClearinghouseState(address) {
  return infoClient.clearinghouseState({ user: address, dex: "xyz" });
}

/**
 * Get spot balances (token holdings).
 */
export async function getSpotState(address) {
  return infoClient.spotClearinghouseState({ user: address });
}

/**
 * Get open orders with frontend display fields.
 */
export async function getOpenOrders(address) {
  return infoClient.frontendOpenOrders({ user: address });
}

/**
 * Get user trade fills (with closedPnl, fee, dir).
 */
export async function getUserFills(address) {
  return infoClient.userFills({ user: address, aggregateByTime: true });
}

/**
 * Get funding payment history.
 */
export async function getUserFunding(address, startTime) {
  const params = { user: address };
  if (startTime) params.startTime = startTime;
  return infoClient.userFunding(params);
}

// ---------------------------------------------------------------------------
// Portfolio v2 reads (read-only info calls; nothing here signs or trades)
// ---------------------------------------------------------------------------

/** Clearinghouse state on one builder dex ("xyz", "para", ...). */
export async function getDexClearinghouseState(address, dex) {
  return infoClient.clearinghouseState({ user: address, dex });
}

/** Open orders on one dex (main when dex is empty). */
export async function getDexOpenOrders(address, dex = "") {
  return infoClient.frontendOpenOrders(dex ? { user: address, dex } : { user: address });
}

/** Fills from startTime (ms, inclusive), aggregated by time like getUserFills. */
export async function getUserFillsByTime(address, startTime, endTime) {
  const params = { user: address, startTime, aggregateByTime: true };
  if (endTime) params.endTime = endTime;
  return infoClient.userFillsByTime(params);
}

/** Candles: interval "1h" | "4h" | "1d"; times in ms. */
export async function getCandles(coin, interval, startTime, endTime) {
  return infoClient.candleSnapshot({ coin, interval, startTime, endTime });
}

export async function getPerpDexs() {
  return infoClient.perpDexs();
}

export async function getSpotMeta() {
  return infoClient.spotMeta();
}

/** Mids on one builder dex (main: getAllMids). */
export async function getDexMids(dex) {
  return infoClient.allMids({ dex });
}

export async function getDelegatorSummary(address) {
  return infoClient.delegatorSummary({ user: address });
}

export async function getVaultEquities(address) {
  return infoClient.userVaultEquities({ user: address });
}

/** Earn: supplied and borrowed per token. */
export async function getBorrowLendState(address) {
  return infoClient.borrowLendUserState({ user: address });
}

/** "disabled" unless spot balances back the perps account (a unified account). */
export async function getUserAbstraction(address) {
  return infoClient.userAbstraction({ user: address });
}

/** Funding rates and marks for one dex (main when dex is empty). */
export async function getMetaAndAssetCtxs(dex = "") {
  return infoClient.metaAndAssetCtxs(dex ? { dex } : undefined);
}

/**
 * Cancel an open order (requires wallet signature).
 */
export async function cancelOrder(walletClient, { coin, oid }) {
  const assetIdx = await getAssetIndex(coin);
  const exchange = new ExchangeClient(makeExchangeConfig(walletClient));
  return exchange.cancel({ cancels: [{ a: assetIdx, o: oid }] });
}
