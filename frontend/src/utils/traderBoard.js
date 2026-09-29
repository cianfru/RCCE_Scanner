// Trader leaderboard and trader profile: routes, number formats, and the fill marks drawn on a
// coin chart (one mark per candle, kind and side).

export const WINDOWS = [
  { key: "7d", label: "7d" },
  { key: "30d", label: "30d" },
  { key: "all", label: "All time" },
];
export const WINDOW_KEYS = new Set(WINDOWS.map(w => w.key));
export const windowLabel = key => (WINDOWS.find(w => w.key === key) || WINDOWS[1]).label;

// The profile's address: /trader/<0x + 40 hex>, always lowercase.
const ADDRESS_RE = /^0x[0-9a-f]{40}$/i;
export const isAddress = a => ADDRESS_RE.test(String(a || ""));
export const profilePath = address => `/trader/${String(address || "").toLowerCase()}`;
export function addressFromPath(pathname) {
  const m = /^\/trader\/([^/]+)\/?$/.exec(String(pathname || ""));
  return m && isAddress(m[1]) ? m[1] : null;
}

// Account size bands (same cut-offs as the API's).
export function sizeBand(av) {
  if (!(av > 0)) return null;
  if (av >= 10e6) return "$10M+";
  if (av >= 1e6) return "$1M–10M";
  if (av >= 250e3) return "$250K–1M";
  if (av >= 50e3) return "$50K–250K";
  return "<$50K";
}

const MINUS = "−";
const signOf = v => (v > 0 ? "+" : v < 0 ? MINUS : "");

// "$1.59M", "$482K", "$950"; two decimals under $1K would be noise at this scale.
export function fmtMoney(v) {
  if (v == null || !Number.isFinite(v)) return "—";
  const a = Math.abs(v);
  if (a >= 1e9) return `$${(a / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `$${(a / 1e6).toFixed(a >= 1e8 ? 0 : a >= 1e7 ? 1 : 2)}M`;
  if (a >= 1e3) return `$${Math.round(a / 1e3)}K`;
  return `$${Math.round(a)}`;
}
export const fmtPnl = v => (v == null || !Number.isFinite(v) ? "—" : `${signOf(Math.round(v))}${fmtMoney(v)}`);

export function fmtRoi(v) {
  if (v == null || !Number.isFinite(v)) return "—";
  const a = Math.abs(v);
  const n = a >= 100 ? Math.round(a).toLocaleString("en-US") : a >= 10 ? a.toFixed(0) : a.toFixed(1);
  return `${signOf(v)}${n}%`;
}
export const fmtRate = v => (v == null || !Number.isFinite(v) ? "—" : `${Math.round(v)}%`);

// Prices with sensible precision for anything from BTC to PEPE.
export function fmtPrice(v) {
  if (v == null || !Number.isFinite(v)) return "—";
  const a = Math.abs(v);
  const digits = a >= 1000 ? 0 : a >= 100 ? 1 : a >= 1 ? 3 : a >= 0.01 ? 4 : 6;
  return v.toLocaleString("en-US", { minimumFractionDigits: a >= 1000 ? 0 : Math.min(digits, 2), maximumFractionDigits: digits });
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export const fmtDay = t => { const d = new Date(t * 1000); return `${d.getDate()} ${MONTHS[d.getMonth()]}`; };
export function fmtStamp(t) {
  const d = new Date(t * 1000);
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

// "3d 4h", "5h 20m", "12m", "40s".
export function fmtDuration(sec) {
  if (sec == null || !Number.isFinite(sec) || sec < 0) return "—";
  const d = Math.floor(sec / 86400), h = Math.floor((sec % 86400) / 3600), m = Math.floor((sec % 3600) / 60);
  if (d >= 30) return `${d}d`;
  if (d) return h ? `${d}d ${h}h` : `${d}d`;
  if (h) return m ? `${h}h ${m}m` : `${h}h`;
  if (m) return `${m}m`;
  return `${Math.max(0, Math.round(sec))}s`;
}

// The coin logos of a leaderboard row: at most `max`, and how many more.
export function coinStrip(coins, max = 5) {
  const list = Array.isArray(coins) ? coins : [];
  return { shown: list.slice(0, max), more: Math.max(0, list.length - max) };
}

// Chart timeframe for a span of fills: 4H covers ~100 days (the server's 600 bars), 1D beyond.
export function chartTimeframe(fromSec, nowSec = Date.now() / 1000) {
  return fromSec != null && nowSec - fromSec < 80 * 86400 ? "4h" : "1d";
}

// Index of the candle a time falls in: the last candle opening at or before it; -1 before the first.
export function barIndex(candleTimes, t) {
  if (!candleTimes?.length || t < candleTimes[0]) return -1;
  let lo = 0, hi = candleTimes.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (candleTimes[mid] <= t) lo = mid; else hi = mid - 1;
  }
  return lo;
}

export const KIND_WORD = { open: "Opened", add: "Added", trim: "Trimmed", close: "Closed", flip: "Flipped" };
const KIND_ORDER = { open: 0, add: 1, flip: 2, trim: 3, close: 4 };

// Fills (from /api/traders/{address}/fills) as chart marks: one per candle, kind and side, at the
// average price of those fills. usd: their dollars; n: how many fills; t0/t1: first and last.
// A buy (opening or adding a long, trimming or closing a short) points up.
export function fillMarks(fills, candleTimes) {
  const groups = new Map();
  for (const f of fills || []) {
    const i = barIndex(candleTimes, f.t);
    if (i < 0) continue;
    const key = `${i}|${f.kind}|${f.side}`;
    let g = groups.get(key);
    if (!g) {
      g = { index: i, time: candleTimes[i], kind: f.kind, side: f.side, usd: 0, sz: 0, n: 0, t0: f.t, t1: f.t, pnl: 0 };
      groups.set(key, g);
    }
    g.usd += f.usd || 0;
    g.sz += f.sz || 0;
    g.n += 1;
    g.pnl += f.pnl || 0;
    g.t0 = Math.min(g.t0, f.t);
    g.t1 = Math.max(g.t1, f.t);
  }
  const out = [...groups.values()].map(g => ({ ...g, px: g.sz ? g.usd / g.sz : null, buy: isBuy(g.kind, g.side) }));
  out.sort((a, b) => a.index - b.index || KIND_ORDER[a.kind] - KIND_ORDER[b.kind]);
  return out;
}

export function isBuy(kind, side) {
  const growing = kind === "open" || kind === "add" || kind === "flip";
  return growing ? side === "long" : side === "short";
}

// Mark radius from its dollars against the largest mark on the chart: 3.5 to 9 px (area-like).
export function markRadius(usd, maxUsd, kind) {
  const base = maxUsd > 0 ? 3.5 + 5.5 * Math.sqrt(Math.max(0, usd) / maxUsd) : 4.5;
  return kind === "trim" ? Math.max(3.5, base * 0.8) : base;
}

// Counts per kind for a legend or a one-line summary ("12 adds · 3 trims").
export function kindCounts(fills) {
  const c = { open: 0, add: 0, trim: 0, close: 0, flip: 0 };
  for (const f of fills || []) if (f.kind in c) c[f.kind] += 1;
  return c;
}

// Time range to load and show for a closed position: its life plus a margin either side.
export function tripRange(trip, nowSec = Date.now() / 1000) {
  const start = trip.opened_at ?? trip.first_t ?? trip.closed_at;
  const end = trip.closed_at ?? nowSec;
  const pad = Math.max(3600, (end - start) * 0.25);
  return { since: start - 60, until: end + 60, from: start - pad, to: Math.min(nowSec, end + pad) };
}

// Coins most traded in the closed positions on hand, for the history's coin filter.
export function topCoins(trips, max = 6) {
  const n = new Map();
  for (const t of trips || []) n.set(t.coin, (n.get(t.coin) || 0) + 1);
  return [...n.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, max).map(([c]) => c);
}
