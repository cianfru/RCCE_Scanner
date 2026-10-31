// Pure helpers and copy for the wallet panels of the market history page (/api/market-history/wallets): how
// Hyperliquid's smart money, whales and profitable traders stood (long or short) at each daily close.
// Every panel starts at zero: longs rise above the line in green, shorts fall below it in red, so no longs reads
// 0 and more shorts reach lower.
// - Smart money and whales: shares of the group's wallets that day (flat wallets count in the total), so a growing
//   group does not read as more longs.
// - Profitable traders (the roster Reflex's HyperLens follows, picked again every day by the last 30 days' return;
//   Outrider's crowd): shares of their open positions, each wallet-coin position once, as Outrider's pulse counts
//   them; the two shares sum to 100%.

const DAY_MS = 86_400_000;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export const GROUPS = [
  { key: "smart", label: "Smart money" },
  { key: "whales", label: "Whales" },
  { key: "crowd", label: "Profitable traders", positions: true },
];

// All markets (net dollar position) or one main coin (long or short that coin); the feed's COINS.
export const SCOPES = [{ key: "all", label: "All markets" }, { key: "BTC", label: "BTC" }, { key: "ETH", label: "ETH" },
  { key: "SOL", label: "SOL" }, { key: "HYPE", label: "HYPE" }];

const monthYear = day => { const d = new Date(day * DAY_MS); return `${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`; };
const dayDate = day => { const d = new Date(day * DAY_MS); return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`; };
export const pct = x => (x == null ? "—" : `${Math.round(100 * x)}%`);
const num = n => Math.round(n).toLocaleString("en-US");

const asObj = (cols, r) => Object.fromEntries(cols.map((c, i) => [c, r[i]]));

// One group's rows as objects, oldest first, with the long and short shares (L, S). With a coin scope the long and
// short counts are that coin's: for smart money and whales still out of the group's wallets that day, for
// profitable traders out of their positions in that coin.
export function groupRows(data, key, { scope = "all" } = {}) {
  if (key === "crowd") return crowdRows(data, scope);
  const raw = data?.groups?.[key];
  if (!raw?.length) return [];
  let base = raw.map(r => asObj(data.columns, r));
  if (scope !== "all") {
    const wallets = new Map(base.map(o => [o.day, o.wallets]));
    base = (data.coins?.[scope]?.[key] || []).map(r => asObj(data.coin_columns, r))
      .filter(o => wallets.has(o.day)).map(o => ({ ...o, wallets: wallets.get(o.day) }));
  }
  return base.map(o => {
    const n = o.wallets || 0;
    return { ...o, L: n ? o.long / n : null, S: n ? o.short / n : null, rebuilt: !!o.rebuilt };
  }).sort((a, b) => a.day - b.day);
}

// Profitable traders: the share of positions long (rebuilt days carry only the share; recorded days the counts too).
function crowdRows(data, scope) {
  const c = data?.crowd;
  if (!c) return [];
  const rows = scope === "all" ? (c.rows || []).map(r => asObj(c.columns, r))
    : (c.coins?.[scope] || []).map(r => asObj(c.coin_columns, r));
  return rows.map(o => {
    const n = (o.long ?? 0) + (o.short ?? 0);
    const L = o.long_share ?? (n ? o.long / n : null);
    return { ...o, positions: o.long == null ? null : n, L, S: L == null ? null : 1 - L, rebuilt: !!o.rebuilt };
  }).filter(o => o.L != null).sort((a, b) => a.day - b.day);
}

// { smart: Map(day -> row), whales: ..., crowd: ... } for joining onto the market history rows.
export function byDay(data, opts) {
  const out = {};
  for (const g of GROUPS) out[g.key] = new Map(groupRows(data, g.key, opts).map(r => [r.day, r]));
  return out;
}

// The latest row of a group (the KPI and the readout's Today).
export const latestOf = (data, key, scope = "all") => {
  const rows = groupRows(data, key, { scope });
  return rows.length ? rows[rows.length - 1] : null;
};

// First day a group has data, for its panel's "from" mark.
export function firstDay(data, key) {
  const rows = key ? groupRows(data, key) : GROUPS.flatMap(g => groupRows(data, g.key));
  return rows.length ? Math.min(...rows.map(r => r.day)) : null;
}

// Panel scale: the half-height, a round step at or above the largest share any panel shows (at least 20%).
export function shareScale(rows, keys) {
  let m = 0;
  for (const r of rows) for (const k of keys) { const w = r.wallet?.[k]; if (w) m = Math.max(m, w.L ?? 0, w.S ?? 0); }
  return [0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1].find(s => s >= m * 1.05) || 1;
}

// ---------------------------------------------------------------- copy

export const WCOPY = {
  scopeLabel: "Wallet positions in",
  groupLabel: "Wallet group",
  label: (g, scope) => (scope && scope !== "all" ? `${g.label} · ${scope}` : g.label),
  from: day => `Data from ${monthYear(day)}`,
  long: "long",
  short: "short",
  // The readout line: shares, with the counts behind them where the day has them.
  readout: (r, g) => {
    if (r == null) return "—";
    const shares = `${pct(r.L)} long · ${pct(r.S)} short`;
    if (g?.positions) return r.positions ? `${shares} of ${num(r.positions)} positions` : `${shares} of positions`;
    return r.wallets ? `${shares} of ${num(r.wallets)} wallets` : shares;
  },
  // The chart's hover box: the shares, coloured there, and the count behind them on a line of its own.
  tip: (r, g) => {
    if (r?.L == null) return null;
    const n = g?.positions ? r.positions : r.wallets;
    return { long: `${pct(r.L)} long`, short: `${pct(r.S)} short`,
      of: n ? `of ${num(n)} ${g?.positions ? "positions" : "wallets"}` : null };
  },
  kpi: {
    sub: (g, scope) => `${g?.positions ? "positions" : "wallets"} long · short${scope && scope !== "all" ? ` ${scope}` : ""}`,
  },
  // Popovers: each 90 words or fewer. ctx: { rebuiltTo, recordedFrom, overlap (the feed's check for this group),
  // scope ("all" or a coin), crowd (the feed's crowd block, for profitable traders) }.
  pop: {
    title: g => g.label,
    group: (g, ctx = {}) => {
      const coin = ctx.scope && ctx.scope !== "all" ? ctx.scope : null;
      if (g.positions) return crowdPop(ctx, coin);
      const who = g.key === "smart"
        ? "Wallets with $100K+ all-time PnL and $10K+ perp equity"
        : "Wallets with $1M+ perp equity";
      const o = ctx.overlap;
      const rebuilt = "rebuilt from Hyperliquid fills for a weighted sample";
      const src = !ctx.rebuiltTo ? "Recorded by Reflex's wallet sweep."
        : !ctx.recordedFrom ? `${rebuilt[0].toUpperCase()}${rebuilt.slice(1)}.`
          : `Before ${dayDate(ctx.recordedFrom)} ${rebuilt}${o ? `, set to the recorded level${coin ? "" : ` (${Math.round(Math.max(o.long_pts, o.short_pts))} points apart where both exist)`}` : ""}; since, recorded by Reflex's wallet sweep.`;
      const count = coin
        ? `each counted once: long or short ${coin} at the 00:00 UTC close; those without a ${coin} position count in the total.`
        : "each counted once: long or short by net dollar position at the 00:00 UTC close; flat ones count in the total.";
      return [`${who}, as they stood each day, ${count}`,
        `Green, up from zero: the share long. Red, down from zero: the share short. ${src} Context, not a signal.`];
    },
  },
};

function crowdPop(ctx, coin) {
  const c = ctx.crowd || {};
  const from = c.recorded_from;
  const gap = coin ? null : c.overlap?.gap_pts;     // all markets' figure: each coin is moved by its own
  const rebuilt = "rebuilt with the same pick among wallets whose trades are rebuilt (once smart money or whales), so smaller accounts are missing";
  const src = c.rebuilt && from ? `Before ${dayDate(from)}: ${rebuilt}; set to the recorded level${gap != null ? ` (${Math.round(gap)} points apart where both exist)` : ""}. Since: recorded at each 00:00 UTC close.`
    : c.rebuilt ? `${rebuilt[0].toUpperCase()}${rebuilt.slice(1)}.` : "Recorded by Reflex at each 00:00 UTC close.";
  return [`Picked again every day: the best 600 Hyperliquid wallets by 30-day return (30%+, $10K+, in profit before, market makers out), as HyperLens follows them (Outrider's crowd). Each open ${coin ? `${coin} position` : "position"} counts once. As last month's winners, they lean the way that month went.`,
    `${src} Context, not a signal.`];
}
