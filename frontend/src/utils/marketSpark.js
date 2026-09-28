// The Market consensus card's sparkline button: geometry for the last 90 days of Uptrend share and the faint stub of
// past paths after today (min to max only: the walk-forward check did not pass for the Uptrend bands, so no middle
// line), and the one-time dot that marks the button until the Market history drawer has been opened once.

export const SPARK = { w: 64, h: 16, pad: 1.5 };
export const SEEN_KEY = "reflex-market-history-seen";

const r2 = v => Math.round(v * 100) / 100;
const clamp01 = v => Math.min(1, Math.max(0, v));

// Paths for an SVG of w x h: `line` (history), `stub` (closed polygon, or null) and `end` ([x, y] of today).
// One time scale for both parts, so the stub's width is its share of days (30 of 119 is about a quarter).
// The y scale is the full 0-100% range: the share is a head count, a fixed scale keeps it honest. Null when
// there is nothing to draw (the caller shows the plain icon).
export function sparkGeometry(spark, { w = SPARK.w, h = SPARK.h, pad = SPARK.pad } = {}) {
  const days = (Array.isArray(spark?.days) ? spark.days : []).filter(d => Array.isArray(d) && Number.isFinite(d[0]) && Number.isFinite(d[1]));
  if (days.length < 2) return null;
  const first = days[0][0];
  const today = Number.isFinite(spark.today) ? spark.today : days[days.length - 1][0];
  const st = validStub(spark.stub);
  const last = today + (st ? st.k[st.k.length - 1] : 0);
  const span = Math.max(1, last - first);
  const x = day => r2(pad + ((day - first) / span) * (w - 2 * pad));
  const y = v => r2(pad + (1 - clamp01(v)) * (h - 2 * pad));
  const line = days.map((d, i) => `${i ? "L" : "M"}${x(d[0])},${y(d[1])}`).join("");
  const endDay = days[days.length - 1];
  let stub = null;
  if (st) {
    const hi = st.k.map((k, i) => `${x(today + k)},${y(st.hi[i])}`);
    const lo = st.k.map((k, i) => `${x(today + k)},${y(st.lo[i])}`).reverse();
    stub = `M${hi.join("L")}L${lo.join("L")}Z`;
  }
  return { w, h, line, stub, end: [x(endDay[0]), y(endDay[1])] };
}

function validStub(s) {
  if (!s || !Array.isArray(s.k) || s.k.length < 2 || s.k[0] !== 0) return null;      // anchored at today
  if (!Array.isArray(s.lo) || !Array.isArray(s.hi) || s.lo.length !== s.k.length || s.hi.length !== s.k.length) return null;
  const ok = s.k.every((k, i) => Number.isFinite(k) && Number.isFinite(s.lo[i]) && Number.isFinite(s.hi[i]) && s.lo[i] <= s.hi[i]);
  return ok ? s : null;
}

// The browser's localStorage, or null when reading it throws (blocked site data, some private windows).
export function getStorage() {
  try {
    return typeof window !== "undefined" && window.localStorage ? window.localStorage : null;
  } catch {
    return null;
  }
}

// Whether to show the one-time dot. Only when storage can be read AND written and the flag is not set: storage
// that cannot keep the flag would bring the dot back on every visit, so no storage means no dot.
export function showHistoryDot(storage) {
  if (!storage) return false;
  try {
    if (storage.getItem(SEEN_KEY) === "1") return false;
    storage.setItem(SEEN_KEY + "-probe", "1");
    storage.removeItem(SEEN_KEY + "-probe");
    return true;
  } catch {
    return false;
  }
}

// Remember that the drawer was opened. Never throws; true when stored.
export function markHistorySeen(storage) {
  if (!storage) return false;
  try {
    storage.setItem(SEEN_KEY, "1");
    return true;
  } catch {
    return false;
  }
}
