// Incremental fills (Portfolio v2, section 6.3). Each refresh asks Hyperliquid for fills from the last
// cached fill time, inclusive (userFillsByTime, aggregateByTime). The answer replaces every cached fill
// at or after that time (a window replace): fills in the boundary millisecond are neither lost nor
// duplicated, and an aggregated fill that grew since the last read is replaced, not added twice.
export const WINDOW_DAYS = 30;

export const byTime = (a, b) => a.time - b.time || String(a.tid ?? "").localeCompare(String(b.tid ?? ""));

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
export const byFundingTime = (a, b) => a.time - b.time || String(a.delta?.coin).localeCompare(String(b.delta?.coin));
export function mergeFunding(cached, incoming, startTime) {
  const keep = (cached || []).filter(f => f.time < startTime);
  return keep.concat((incoming || []).filter(f => f.time >= startTime)).sort(byFundingTime);
}

// Paging. Hyperliquid answers a time-range read oldest first, at most `size` items (2000 fills, 500
// funding rows). A short page settles everything from its start on; a full page settles [start, its
// last time), since the items of its last millisecond may go on in the next page, which starts there.
// next: where the next page starts (null: nothing more to read).
export function pageRange(page, start, size) {
  if ((page || []).length < size) return { lo: start, hi: Infinity, next: null };
  const last = page.reduce((m, x) => Math.max(m, x.time), start);
  if (last <= start) return { lo: start, hi: start, next: start + 1 };     // a whole page in one millisecond
  return { lo: start, hi: last - 1, next: last };
}

// The cached list with [lo, hi] replaced by the page's items in that range; everything outside it is
// kept, so a later page that fails never takes away what an earlier one settled.
export function mergeRange(cached, page, lo, hi, cmp = byTime) {
  const keep = (cached || []).filter(x => x.time < lo || x.time > hi);
  return keep.concat((page || []).filter(x => x.time >= lo && x.time <= hi)).sort(cmp);
}
