export function timeframeFrom(search) {
  return new URLSearchParams(search).get("tf") === "4h" ? "4h" : "1d";
}
export function marketHref(row, timeframe = "1d") {
  const spot = row.market_kind === "spot" || row.symbol?.endsWith("/USDC");
  const symbol = spot ? row.symbol : (row.symbol || "").split("/")[0];
  return `/scanner/${encodeURIComponent(symbol)}?market=${spot ? "spot" : "perpetual"}&tf=${timeframe === "4h" ? "4h" : "1d"}`;
}
export function scannerHref(search) {
  const params = new URLSearchParams(search);
  const saved = params.get("from");
  // Only internal scanner routes can be restored, never an arbitrary redirect.
  if (saved && /^\/scanner(?:\?|$)/.test(saved)) return saved;
  return `/scanner?market=${params.get("market") === "spot" ? "spot" : "perpetual"}&tf=${timeframeFrom(search)}`;
}
export function displaySymbol(symbol) {
  return (symbol || "").replace(/\/(?:USDT|USDC|USD)$/, "");
}
export function divergenceKind(signal, trend) {
  if (["STRONG_LONG", "LIGHT_LONG", "ACCUMULATE"].includes(signal) && trend === "BEARISH") return "opposed";
  if (["LIGHT_SHORT", "TRIM", "RISK_OFF", "NO_LONG"].includes(signal) && trend === "BULLISH") return "opposed";
  if (signal === "WAIT" && trend === "BULLISH") return "waiting";
  return null;
}
// Where the coin page's back button goes: the saved scanner or Radar view, never anywhere else.
export function backHref(search) {
  const p = new URLSearchParams(search);
  const s = p.get("from");
  if (s && /^\/(scanner|radar)(\?|$)/.test(s)) return s;
  return scannerHref(search);
}
