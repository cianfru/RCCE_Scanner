// Pure helpers and copy for the wallet panels of the market history page (/api/market-history/wallets):
// how many smart-money wallets and whales were net long and net short at each daily close.
// Shares are of the group's wallets that day (flat wallets count in the total), so a growing group does not
// read as more longs. Each share's z-score compares a day with the Z_WINDOW days before it.

const DAY_MS = 86_400_000;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MINUS = "−";

export const Z_WINDOW = 90;        // days before each day that its z-score is measured against (the day left out)
export const Z_MIN = 30;           // fewer earlier days with data than this: no z-score
export const Z_SCALE = 3;          // the z panel runs from −3 to +3; beyond, the line is clipped
export const Z_GUIDE = 2;

export const GROUPS = [
  { key: "smart", label: "Smart money" },
  { key: "whales", label: "Whales" },
];

export const WALLET_MODES = [{ key: "z", label: "Z-score" }, { key: "share", label: "Share" }];

const monthYear = day => { const d = new Date(day * DAY_MS); return `${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`; };
const dayDate = day => { const d = new Date(day * DAY_MS); return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`; };
export const pct = x => (x == null ? "—" : `${Math.round(100 * x)}%`);
export const signedZ = z => (z == null ? "—" : `${z > 0.005 ? "+" : z < -0.005 ? MINUS : ""}${Math.abs(z).toFixed(1)}`);

// One group's rows as objects, oldest first, with the long and short shares (L, S) and their z-scores.
export function groupRows(data, key, { window = Z_WINDOW, min = Z_MIN } = {}) {
  const raw = data?.groups?.[key];
  if (!raw?.length) return [];
  const cols = data.columns;
  const rows = raw.map(r => {
    const o = Object.fromEntries(cols.map((c, i) => [c, r[i]]));
    const n = o.wallets || 0;
    return { ...o, L: n ? o.long / n : null, S: n ? o.short / n : null, rebuilt: !!o.rebuilt };
  }).sort((a, b) => a.day - b.day);
  const zL = trailingZ(rows, "L", window, min);
  const zS = trailingZ(rows, "S", window, min);
  return rows.map((r, i) => ({ ...r, zL: zL[i], zS: zS[i] }));
}

// Each row's value against the rows from `window` days before it up to the day before (the day itself left
// out, so a day is read against what came before it, as it would have been then). Null with fewer than `min`
// earlier values or no spread.
export function trailingZ(rows, field, window = Z_WINDOW, min = Z_MIN) {
  const out = new Array(rows.length).fill(null);
  let lo = 0, sum = 0, sq = 0, n = 0;
  for (let i = 0; i < rows.length; i++) {
    const day = rows[i].day;
    // Window: rows with day in [day - window, day - 1]; rows before index i that fell out of it leave.
    while (lo < i && rows[lo].day < day - window) {
      const v = rows[lo][field];
      if (v != null) { sum -= v; sq -= v * v; n--; }
      lo++;
    }
    const v = rows[i][field];
    if (v != null && n >= min) {
      const mean = sum / n;
      const sd = Math.sqrt(Math.max(0, sq / n - mean * mean));
      out[i] = sd > 1e-9 ? (v - mean) / sd : null;
    }
    if (v != null) { sum += v; sq += v * v; n++; }
  }
  return out;
}

// { smart: Map(day -> row), whales: ... } for joining onto the market history rows.
export function byDay(data, opts) {
  const out = {};
  for (const g of GROUPS) out[g.key] = new Map(groupRows(data, g.key, opts).map(r => [r.day, r]));
  return out;
}

// The latest row of a group (the KPI and the readout's Today).
export const latestOf = (data, key) => { const rows = groupRows(data, key); return rows.length ? rows[rows.length - 1] : null; };

// First day any group has data, for the panels' "from" mark.
export function firstDay(data) {
  const days = GROUPS.flatMap(g => (data?.groups?.[g.key] || []).map(r => r[0]));
  return days.length ? Math.min(...days) : null;
}

// Rough count words for the readout: "412 of 1,084" (the rebuilt days are estimates from a sample).
export const ofWallets = r => (r?.wallets ? `${r.long.toLocaleString("en-US")} long · ${r.short.toLocaleString("en-US")} short of ${r.wallets.toLocaleString("en-US")}` : "—");

// ---------------------------------------------------------------- copy

export const WCOPY = {
  modeLabel: "Wallet panels",
  from: day => `Wallet data from ${monthYear(day)}`,
  long: "long",
  short: "short",
  readout: (r, mode) => (r == null ? "—" : mode === "share"
    ? `${pct(r.L)} long · ${pct(r.S)} short`
    : `${pct(r.L)} long · ${pct(r.S)} short · z ${signedZ(r.zL)} / ${signedZ(r.zS)}`),
  kpi: { label: g => g.label, sub: "long · short" },
  // Popovers: each 90 words or fewer. ctx: { rebuiltTo, recordedFrom, overlap (the feed's check for this group), mode }.
  pop: {
    title: g => g.label,
    group: (g, ctx = {}) => {
      const who = g.key === "smart"
        ? "Wallets with $100K+ all-time PnL and $10K+ perp equity"
        : "Wallets with $1M+ perp equity";
      const draw = ctx.mode === "share"
        ? "Green, up: the share of these wallets long. Red, down: the share short."
        : `Green: the long share's z-score against the prior ${Z_WINDOW} days. Red, drawn downward: the short share's; more shorts reach lower.`;
      const o = ctx.overlap;
      const rebuilt = "rebuilt from Hyperliquid fills for a weighted sample";
      const src = !ctx.rebuiltTo ? "Recorded by Reflex's wallet sweep."
        : !ctx.recordedFrom ? `${rebuilt[0].toUpperCase()}${rebuilt.slice(1)}.`
          : `Before ${dayDate(ctx.recordedFrom)} ${rebuilt}${o ? `, set to the recorded level (${Math.round(Math.max(o.long_pts, o.short_pts))} points apart where both exist)` : ""}; since, recorded by Reflex's wallet sweep.`;
      return [
        `${who}, as they stood each day, counted once each: long or short by net dollar position at the 00:00 UTC close; flat ones count in the total.`,
        `${draw} ${src} Context, not a signal.`,
      ];
    },
  },
};
