// Incremental fills (Portfolio v2, section 6.3). Each refresh asks Hyperliquid for fills from the last
// cached fill time, inclusive (userFillsByTime, aggregateByTime). The answer replaces every cached fill
// at or after that time (a window replace): fills in the boundary millisecond are neither lost nor
// duplicated, and an aggregated fill that grew since the last read is replaced, not added twice.
export const WINDOW_DAYS = 30;

const byTime = (a, b) => a.time - b.time || String(a.tid ?? "").localeCompare(String(b.tid ?? ""));

export function mergeWindow(cached, incoming, startTime) {
  const keep = (cached || []).filter(f => f.time < startTime);
  return keep.concat((incoming || []).filter(f => f.time >= startTime)).sort(byTime);
}

// The next incremental read starts at the newest cached fill (inclusive); the first one 30 days back.
export function nextStart(cached, now = Date.now(), days = WINDOW_DAYS) {
  if (!cached?.length) return now - days * 86400_000;
  return cached.reduce((m, f) => Math.max(m, f.time), 0);
}

export const trimWindow = (fills, now = Date.now(), days = WINDOW_DAYS) => (fills || []).filter(f => f.time >= now - days * 86400_000);

// Funding is the same: one row per coin per hour, keyed by time and coin.
export function mergeFunding(cached, incoming, startTime) {
  const keep = (cached || []).filter(f => f.time < startTime);
  return keep.concat((incoming || []).filter(f => f.time >= startTime)).sort((a, b) => a.time - b.time || String(a.delta?.coin).localeCompare(String(b.delta?.coin)));
}
