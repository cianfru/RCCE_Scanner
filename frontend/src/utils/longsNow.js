// The scanner's list of long signals (components/LongsNow.jsx): the coins with a long signal on the timeframe, in
// the scanner's priority order, each joined to its Radar reading (against BTC, profitable traders, band distance,
// heat signs). Ordering stays the priority score: the ranking and relative band studies
// (docs/reviews/ranking-study.md, relative-band-study.md) found that strength did not pick better trades. Context.

export const LONG_SIGNALS = new Set(["STRONG_LONG", "LIGHT_LONG", "REVIVAL_SEED", "REVIVAL_SEED_CONFIRMED"]);
export const SIGNAL_WORD = { STRONG_LONG: "Strong", LIGHT_LONG: "Light", REVIVAL_SEED: "Revival", REVIVAL_SEED_CONFIRMED: "Revival" };

// rows: the scan's rows for the timeframe; coins: the setup map's coins. Returns [{row, c}] sorted by priority
// (highest first), then by name.
export function longsNow(rows, coins) {
  const by = new Map((coins || []).map(c => [c.symbol, c]));
  return (rows || []).filter(r => LONG_SIGNALS.has(r.signal) && (r.market_kind || "perpetual") === "perpetual")
    .map(r => ({ row: r, c: by.get(r.symbol) || null }))
    .sort((a, b) => (b.row.priority_score || 0) - (a.row.priority_score || 0) || String(a.row.symbol).localeCompare(String(b.row.symbol)));
}

const MINUS = "−";
export const pctText = v => (v == null ? "-" : `${v > 0 ? "+" : v < 0 ? MINUS : ""}${Math.abs(v) >= 10 ? Math.round(Math.abs(v)) : Math.abs(v).toFixed(1)}%`);

// ---------------------------------------------------------------- against BTC (setup map "vs_btc", /api/vs-btc)
export const STATE_WORD = { above: "Above", inside: "Inside", under: "Under" };
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
// A day number (days since 1 January 1970) as "8 May", with the year when it is not `thisYear`.
export function dayText(day, thisYear = new Date().getUTCFullYear()) {
  if (day == null) return "";
  const d = new Date(day * 86400000);
  const y = d.getUTCFullYear();
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}${y !== thisYear ? ` ${y}` : ""}`;
}

// "Above · since 8 May": today's state and, when above or under, the first close on that side since the ratio last
// closed on the other side of the band.
export function vsBtcLine(v, thisYear) {
  if (!v) return "";
  const since = v.since != null ? ` · since ${dayText(v.since, thisYear)}` : "";
  return `${STATE_WORD[v.state] || ""}${since}`;
}

// The sparkline: paths for the ratio and the band (a closed polygon between its edges) in a w x h box, on a shared
// scale of the finite values. Points without a band are left out of the band polygon.
export function sparkPaths(spark, w, h, pad = 2) {
  const r = spark?.r || [], lo = spark?.lo || [], hi = spark?.hi || [];
  const vals = [...r, ...lo, ...hi].filter(v => v != null && Number.isFinite(v));
  if (r.length < 2 || !vals.length) return null;
  const mn = Math.min(...vals), mx = Math.max(...vals), span = mx - mn || 1;
  const X = k => pad + (k / (r.length - 1)) * (w - 2 * pad);
  const Y = v => pad + (1 - (v - mn) / span) * (h - 2 * pad);
  const line = r.map((v, k) => (v == null ? null : `${X(k).toFixed(1)},${Y(v).toFixed(1)}`)).filter(Boolean);
  const idx = r.map((_, k) => k).filter(k => lo[k] != null && hi[k] != null);
  const band = idx.length > 1 ? [...idx.map(k => `${X(k).toFixed(1)},${Y(hi[k]).toFixed(1)}`), ...idx.slice().reverse().map(k => `${X(k).toFixed(1)},${Y(lo[k]).toFixed(1)}`)] : [];
  return { line: `M${line.join(" L")}`, band: band.length ? `M${band.join(" L")} Z` : null, end: { x: X(r.length - 1), y: Y(r[r.length - 1]) } };
}
