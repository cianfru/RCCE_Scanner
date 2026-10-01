// The landing preview's markets: one row per coin, USDT quote preferred when a coin has two.
export const PREVIEW_COINS = ["BTC", "ETH", "SOL", "HYPE", "LINK"];

// Daily values change only at the daily close, so the landing refreshes every five minutes.
export const PREVIEW_REFRESH_MS = 5 * 60 * 1000;

export function previewRows(results) {
  if (!Array.isArray(results)) return [];
  const wanted = new Set(PREVIEW_COINS);
  const rows = results.filter(row => wanted.has(String(row?.symbol || "").split("/")[0]) && /\/(USDT|USD|USDC)$/.test(row.symbol));
  const byCoin = new Map();
  for (const row of [...rows].sort((a, b) => Number(b.symbol.endsWith("/USDT")) - Number(a.symbol.endsWith("/USDT")))) {
    const coin = row.symbol.split("/")[0];
    if (!byCoin.has(coin)) byCoin.set(coin, row);
  }
  return [...byCoin.values()];
}
