// Number and time formats for the Portfolio page. Mono, tabular figures are applied by CSS.
const MINUS = "−";

export function num(v) {
  if (v == null || v === "") return null;
  const n = typeof v === "string" ? parseFloat(v) : v;
  return Number.isFinite(n) ? n : null;
}

const trimZero = s => (s.includes(".") ? s.replace(/\.?0+$/, "") : s);

// "$128.5K", "$28.6K", "$412", "$2.1K", "$1.24M". sign: a leading + for gains; losses always carry a minus.
export function usd(v, { sign = false, exact = false } = {}) {
  const n = num(v);
  if (n == null) return "—";
  const a = Math.abs(n);
  let body;
  if (exact) body = a.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  else if (a >= 1e9) body = `${trimZero((a / 1e9).toFixed(2))}B`;
  else if (a >= 1e6) body = `${trimZero((a / 1e6).toFixed(2))}M`;
  else if (a >= 1e3) body = `${trimZero((a / 1e3).toFixed(1))}K`;
  else body = a >= 10 || a === 0 ? String(Math.round(a)) : trimZero(a.toFixed(2));
  if (body === "0" || body === "0.00") return "$0";
  const lead = n < 0 ? MINUS : sign ? "+" : "";
  return `${lead}$${body}`;
}

// Prices with five significant figures, grouped: 80,219 · 79.13 · 0.004512.
export function px(v) {
  const n = num(v);
  if (n == null) return "—";
  return new Intl.NumberFormat("en-US", { maximumSignificantDigits: n >= 1e4 ? 6 : 5 }).format(n);
}

// A price at fixed decimals, so a column lines up on the point ("80.000" beside "79.883").
export function pxFixed(v, decimals) {
  const n = num(v);
  if (n == null) return "—";
  if (decimals == null) return px(n);
  return n.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}
// Decimals per coin for a list of fills ({coin, px}): five significant figures at the coin's highest
// price (Hyperliquid's own precision), so 79.883 and 80.000 share three decimals and BTC has none.
export const decimalsAt = v => (v > 0 ? Math.max(0, Math.min(6, 5 - (Math.floor(Math.log10(v)) + 1))) : 0);
export function decimalsByCoin(list) {
  const top = new Map();
  for (const f of list || []) {
    const v = Math.abs(num(f.px) ?? 0);
    if (v > (top.get(f.coin) ?? 0)) top.set(f.coin, v);
  }
  return new Map([...top].map(([c, v]) => [c, decimalsAt(v)]));
}

// "31%"; under 10, one decimal ("7.7%").
export function pct(v, { sign = false, digits = null } = {}) {
  const n = num(v);
  if (n == null) return "—";
  const a = Math.abs(n);
  const d = digits != null ? digits : a < 10 ? 1 : 0;
  let body = trimZero(a.toFixed(d)) || "0";
  // Rounding never reaches 100% from below: a trigger 99.96% away reads −99.9%, not −100%.
  if (a < 100 && parseFloat(body) >= 100) body = "99.9";
  return `${n < 0 && body !== "0" ? MINUS : sign && n > 0 ? "+" : ""}${body}%`;
}

// Daily ATRs to liquidation: one decimal under 10 ("1.4"), whole from 10 ("14").
export const atrNum = v => (num(v) == null ? "—" : v >= 10 ? String(Math.round(v)) : v.toFixed(1));

export const signed = (v, d = 1) => {
  const n = num(v);
  if (n == null) return "—";
  return `${n < 0 ? MINUS : "+"}${Math.abs(n).toFixed(d)}`;
};

// A size with the market's szDecimals (never rounded for a trading call: display only).
export function size(v, decimals = null) {
  const n = num(v);
  if (n == null) return "—";
  const a = Math.abs(n);
  if (decimals != null) return a.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  return a.toLocaleString("en-US", { maximumFractionDigits: 6 });
}

// Durations: "35m", "14h", "2d", "6d 4h" (with hours when under 10 days and long=true).
export function age(sec, { long = false } = {}) {
  const s = Math.max(0, Math.round(num(sec) ?? 0));
  if (s < 3600) return `${Math.max(1, Math.round(s / 60))}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600);
  return long && d < 10 && h ? `${d}d ${h}h` : `${d}d`;
}

export function ago(ms, now = Date.now()) {
  const s = Math.max(0, Math.round((now - ms) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ago`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const two = n => String(n).padStart(2, "0");
// In the viewer's time zone: "26 Oct 14:05", "Sun 21:40", "26 Sep".
export const stamp = ms => { const d = new Date(ms); return `${d.getDate()} ${MONTHS[d.getMonth()]} ${two(d.getHours())}:${two(d.getMinutes())}`; };
export const weekdayTime = ms => { const d = new Date(ms); return `${DAYS[d.getDay()]} ${two(d.getHours())}:${two(d.getMinutes())}`; };
export const dayMonth = ms => { const d = new Date(ms); return `${d.getDate()} ${MONTHS[d.getMonth()]}`; };
export const hhmm = ms => { const d = new Date(ms); return `${two(d.getHours())}:${two(d.getMinutes())}`; };
export const monthName = (y, m) => `${["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"][m]} ${y}`;
// UTC day key "2026-10-26".
export const dayKey = ms => new Date(ms).toISOString().slice(0, 10);

// Time to the next 4H, daily and weekly candle close (UTC): {h4, d1, w1} in seconds.
export function closeClock(nowMs = Date.now()) {
  const s = Math.floor(nowMs / 1000);
  const h4 = 4 * 3600 - (s % (4 * 3600));
  const d1 = 86400 - (s % 86400);
  // Weekly candles close Monday 00:00 UTC (day 4 of the epoch was a Monday).
  const day = Math.floor(s / 86400);
  const toMon = (7 - ((day - 4) % 7 + 7) % 7) % 7 || 7;
  const w1 = (toMon - 1) * 86400 + d1;
  return { h4, d1, w1 };
}
export const clockText = sec => {
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60);
  return sec >= 2 * 86400 ? `${Math.floor(sec / 86400)}d` : `${h}:${two(m)}`;
};
