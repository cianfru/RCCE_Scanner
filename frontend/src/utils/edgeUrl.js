// Which API paths are CDN feeds (keep in step with EDGE_PATHS in backend/edge.py), and the
// key a CDN URL carries. Pure helpers, shared by src/edge.js; public/shared-worker.js keeps a
// copy of the same two rules.
export const EDGE_PATHS = new Set([
  "/api/scan",
  "/api/scan/sparklines",
  "/api/scan/row",
  "/api/setup-map",
  "/api/market-history",
  "/api/market-history/spark",
  "/api/hyperlens/consensus",
  "/api/hyperlens/positioning",
  "/api/traders/leaderboard",
  "/api/tradfi",
  "/api/universe",
  "/api/sectors",
  "/api/portfolio/context",
  "/api/portfolio/events",
  "/api/coin-positioning",
]);

export function edgePath(path) {
  const bare = String(path || "").split("?")[0];
  return EDGE_PATHS.has(bare);
}

export function withEdgeKey(url, key) {
  if (!key) return url;
  return `${url}${url.includes("?") ? "&" : "?"}k=${encodeURIComponent(key)}`;
}
