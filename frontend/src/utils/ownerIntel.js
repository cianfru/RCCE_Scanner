// The owner's Intel page, the pure parts (tested in ownerIntel.test.js). The page is
// pages/IntelPage.jsx; the data comes from /api/owner/intel (backend usage.py summary).

const DAY_S = 86400;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export const pct = x => (x == null || !Number.isFinite(x) ? "—" : `${Math.round(x * 100)}%`);

// "12 Aug" for a date (ISO day string or unix seconds).
export function shortDate(v) {
  const d = typeof v === "string" ? new Date(`${v}T12:00:00Z`) : new Date(v * 1000);
  if (Number.isNaN(d.getTime())) return "—";
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`;
}

// How long ago, compact: "now", "5m", "3h", "2d", then the date.
export function ago(ts, now) {
  if (!ts) return "—";
  const s = Math.max(0, now - ts);
  if (s < 120) return "now";
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < DAY_S) return `${Math.floor(s / 3600)}h`;
  if (s < 14 * DAY_S) return `${Math.floor(s / DAY_S)}d`;
  return shortDate(ts);
}

let regionNames = null;
export function countryName(cc) {
  if (!cc) return "Unknown";
  try {
    regionNames = regionNames || new Intl.DisplayNames(["en"], { type: "region" });
    return regionNames.of(cc) || cc;
  } catch {
    return cc;
  }
}

// People sort: a column and a direction; people never seen and missing values go last.
const SORT_VALUE = {
  label: p => (p.label || "").toLowerCase(),
  first_seen: p => p.first_seen,
  last_seen: p => p.last_seen,
  d7: p => (p.first_seen ? p.d7 : null),
  d28: p => (p.first_seen ? p.d28 : null),
  country: p => p.country || null,
  device: p => p.device || null,
  wallet: p => (p.first_seen ? (p.wallet ? 1 : 0) : null),
  telegram: p => (p.first_seen ? (p.telegram ? 1 : 0) : null),
};
export const SORT_KEYS = Object.keys(SORT_VALUE);

export function sortPeople(people, key = "last_seen", dir = "desc") {
  const value = SORT_VALUE[key] || SORT_VALUE.last_seen;
  const flip = dir === "asc" ? 1 : -1;
  return [...(people || [])].sort((a, b) => {
    const va = value(a), vb = value(b);
    if (va == null && vb == null) return (a.label || "").localeCompare(b.label || "");
    if (va == null) return 1;
    if (vb == null) return -1;
    if (va < vb) return -flip;
    if (va > vb) return flip;
    return (a.label || "").localeCompare(b.label || "");
  });
}

// A header's first click: names and places A to Z, numbers and times highest first.
export const firstDir = key => (key === "label" || key === "country" || key === "device" ? "asc" : "desc");

// The y-axis top: a round number at or above the data (at least 4, so a few people still read).
export function niceMax(n) {
  const v = Math.max(4, Number(n) || 0);
  const mag = 10 ** Math.floor(Math.log10(v));
  for (const m of [1, 2, 2.5, 4, 5, 10]) if (m * mag >= v) return m * mag;
  return 10 * mag;
}

// Points of a daily series in a w x h box (index -> x, value -> y from max down to 0).
export function points(values, w, h, max) {
  const n = values.length;
  if (!n) return [];
  const step = n > 1 ? w / (n - 1) : 0;
  return values.map((v, i) => [i * step, h - (max ? (v / max) * h : 0)]);
}

export function linePath(pts) {
  return pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`).join("");
}

export function areaPath(pts, h) {
  if (!pts.length) return "";
  return `${linePath(pts)}L${pts.at(-1)[0].toFixed(1)} ${h}L${pts[0][0].toFixed(1)} ${h}Z`;
}

// Indexes of the days that start a month, for the x-axis labels.
export function monthStarts(days) {
  return (days || []).map((d, i) => [d.day, i]).filter(([day]) => day.endsWith("-01")).map(([day, i]) => ({ i, label: MONTHS[+day.slice(5, 7) - 1] }));
}

// An invite's state for the list.
export function inviteStatus(inv, now) {
  if (inv.revoked) return { key: "revoked", text: "Revoked" };
  if (inv.expires && inv.expires <= now) return { key: "expired", text: "Expired" };
  if (inv.expires) return { key: "expires", text: `${Math.max(1, Math.ceil((inv.expires - now) / DAY_S))}d left` };
  return { key: "active", text: "Active" };
}

// A retention cell's fill strength: 0 stays a faint outline, any activity at least 0.18.
export const cellAlpha = share => (share > 0 ? 0.18 + 0.82 * Math.min(1, share) : 0);
