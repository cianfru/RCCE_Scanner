// The scan list comes in two parts (backend/scan_view.py): the rows without their sparklines
// (/api/scan?view=list, new every pass) and the sparklines by symbol (/api/scan/sparklines,
// new only when a candle closes). These helpers put them back together, and lay a coin's full
// row (/api/scan/row) over its list row for the coin page and the detail panel.

export function mergeSparklines(rows, sparks) {
  if (!Array.isArray(rows)) return rows;
  const map = sparks && typeof sparks === "object" ? sparks : {};
  return rows.map(r => (r && r.sparkline === undefined ? { ...r, sparkline: map[r.symbol] || [] } : r));
}

// Full-row fields win (the list row has slimmed copies of some), except the live price,
// which the list row keeps current from the WebSocket.
export function withFullRow(row, full) {
  if (!row || !full || full.symbol !== row.symbol) return row;
  const out = { ...row, ...full, price: row.price };
  if (row.sparkline && row.sparkline.length) out.sparkline = row.sparkline;
  return out;
}

export function rowQuery(row, version) {
  const q = new URLSearchParams({ symbol: row.symbol, timeframe: row.timeframe || "4h" });
  if (row.market_kind) q.set("market", row.market_kind);
  if (version != null) q.set("v", String(version));
  return `/api/scan/row?${q}`;
}
