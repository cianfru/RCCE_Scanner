// Radar (the setup map): pure helpers for the Radar page, its map and the scanner strip
// (tested in setupMap.test.js). The server decides each coin's stage, zone and crowd read
// (backend/setup_map.py); this file only shapes trails, movement, the day's shortlist,
// thumbnail extents and map label placement.

export const STAGES = [
  { key: "forming", name: "Forming" },
  { key: "fresh", name: "Just fired" },
  { key: "running", name: "Running" },
  { key: "stretched", name: "Stretched" },
  { key: "leaving", name: "Leaving" },
];
export const ZONE_WORD = { watch: "Watch", late: "Stretched: late", crowded: "Crowded", quiet: "Nobody in yet", outside: "Outside" };
export const CROWD_WORD = { quiet: "Quiet", early: "Early", crowded: "Crowded", against: "Against", holding: "Holding" };
export const SIGNAL_SHORT = {
  STRONG_LONG: "Strong", LIGHT_LONG: "Light", ACCUMULATE: "Accumulate", REVIVAL_SEED: "Revival", REVIVAL_SEED_CONFIRMED: "Revival",
  LIGHT_SHORT: "Light short", STRONG_SHORT: "Strong short", TRIM: "Trim", TRIM_HARD: "Trim hard", NO_LONG: "No long", RISK_OFF: "Risk off", WAIT: "Wait",
};

export const net = c => (c?.traders?.pl || 0) - (c?.traders?.ps || 0);
export const symlog = v => Math.sign(v) * Math.log10(1 + Math.abs(v));
export const inBox = (box, z, n) => z != null && z >= box.z[0] && z <= box.z[1] && n >= box.n[0] && n <= box.n[1];

// Trail points {z, n}; a missing trader reading takes the nearest known one before it,
// else after it (the stored record can have gaps, e.g. across a deploy).
export function trailPoints(c) {
  const t = c?.trail;
  if (!t || !t.z?.length) return null;
  const n = [...t.n];
  for (let k = 0; k < n.length; k++) if (n[k] == null) n[k] = k > 0 ? n[k - 1] : null;
  for (let k = n.length - 1; k >= 0; k--) if (n[k] == null) n[k] = k < n.length - 1 ? n[k + 1] : net(c);
  return t.z.map((z, k) => ({ z, n: n[k] }));
}

export function movement(c, box) {
  const p = trailPoints(c);
  if (!p || p.length < 2) return null;
  const a = p[0], b = p[p.length - 1];
  return { p, dz: b.z - a.z, dn: b.n - a.n, was: inBox(box, a.z, a.n), is: c.zone === "watch" };
}

// The day's shortlist: coins in the box, by priority plus what moved.
export function picks(coins, box, limit = 4) {
  return coins.filter(c => c.zone === "watch").map(c => {
    const m = movement(c, box);
    let s = c.priority || 0;
    if (m && !m.was && m.is) s += 10;
    if (m && m.dn > 0) s += Math.min(15, 5 * m.dn);
    if (c.stage === "fresh") s += 8;
    if (c.stage === "forming" && c.transition && c.transition.need - Math.min(c.transition.seen, c.transition.need) <= 1) s += 8;
    if (c.crowd === "early") s += 10;
    if (c.crowd === "crowded") s -= 10;
    if (c.crowd === "against") s -= 20;
    return { c, m, s };
  }).sort((a, b) => b.s - a.s || a.c.coin.localeCompare(b.c.coin)).slice(0, limit);
}

export function movers(coins, box) {
  const mv = coins.filter(c => c.stage !== "waiting").map(c => ({ c, m: movement(c, box) })).filter(x => x.m);
  return {
    entering: mv.filter(x => !x.m.was && x.m.is).map(x => x.c),
    leaving: mv.filter(x => x.m.was && !x.m.is).map(x => x.c),
    arriving: mv.filter(x => x.m.dn >= 2).sort((a, b) => b.m.dn - a.m.dn).slice(0, 8).map(x => x.c),
  };
}

// What the map shows by default: setups with at least one profitable trader, forming and
// just-fired setups even when nobody holds them, and anything watched or held.
export function visible(coins, { all = false, keep = new Set() } = {}) {
  return coins.filter(c => c.zscore != null && (all || keep.has(c.coin) || (c.stage !== "waiting"
    && ((c.traders?.pl || 0) + (c.traders?.ps || 0) > 0 || c.stage === "forming" || c.stage === "fresh"))));
}

// Position on a trail at fractional step t.
export function at(p, t) {
  if (p.length === 1) return p[0];
  const k = Math.max(0, Math.min(p.length - 2, Math.floor(t))), f = Math.min(1, t - k);
  return { z: p[k].z + (p[k + 1].z - p[k].z) * f, n: p[k].n + (p[k + 1].n - p[k].n) * f };
}

export const pnl = (mine, price) => (mine && price && mine.entry ? (price / mine.entry - 1) * (mine.side === "short" ? -1 : 1) : null);

// Watch toggles: why a change failed, and what to tell the user.
export const WATCH_MESSAGES = {
  admin: "Watching needs the admin key. Add it under Settings.",
  cap: "At most 30 coins can be watched.",
  error: "Could not change the watch list.",
};
export const watchReason = status => (status === 403 ? "admin" : status === 400 ? "cap" : "error");
export function watchToast(coin, result, telegram) {
  if (!result?.ok) return WATCH_MESSAGES[result?.reason] || WATCH_MESSAGES.error;
  if (!result.watching) return `Stopped watching ${coin}`;
  return telegram === "ready" ? `Watching ${coin}. Alerts go to Telegram.` : `Watching ${coin}. Telegram has no chat yet: send /watch to the bot once.`;
}

// A Hyperliquid address (0x and 40 hex digits).
export const isAddress = v => typeof v === "string" && /^0x[0-9a-fA-F]{40}$/.test(v);

// A thumbnail zoomed to the coin's own trail and the Watch box: x in z units, y in symlog
// units, each padded by 12% of its span (at least 0.3) so the dots never touch the edge.
export function thumbExtent(points, box) {
  const zs = [...(points || []).map(p => p.z), box.z[0], box.z[1]].filter(Number.isFinite);
  const ns = [...(points || []).map(p => symlog(p.n)), symlog(box.n[0]), symlog(box.n[1])].filter(Number.isFinite);
  const pad = vs => {
    const lo = Math.min(...vs), hi = Math.max(...vs), p = Math.max(0.3, 0.12 * (hi - lo));
    return [lo - p, hi + p];
  };
  return { x: pad(zs), y: pad(ns) };
}

// The box a label's text takes: w wide by h tall around its baseline point (x, y).
export function labelBox(x, y, anchor, w, h = 13) {
  const x0 = anchor === "start" ? x - 2 : anchor === "end" ? x - w + 2 : x - w / 2;
  return { x0, x1: x0 + w, y0: y - h + 3, y1: y + 3 };
}

const boxesOverlap = (a, b) => a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1;
const boxHitsCircle = (b, cx, cy, r) => {
  const dx = cx - Math.max(b.x0, Math.min(cx, b.x1)), dy = cy - Math.max(b.y0, Math.min(cy, b.y1));
  return dx * dx + dy * dy < r * r;
};

// Map labels without collisions. dots {coin, x, y, r} come in priority order (focused,
// watched, mine, in the box by engine priority, largest trader lean, movers); each takes
// the first of right, left, above, below that stays inside the plot, clears every label
// already placed and clears every other dot's core by 2px. A label with no room is left
// out (hidden). Options: width/height (the plot, or bounds {x0,y0,x1,y1}), charW and h
// (text size), widthOf(coin) for measured widths, others (dots that take no label but
// must not be covered) and avoid (fixed text boxes on the plot).
export function placeLabels(dots, { width, height, bounds, charW = 6.4, h = 13, widthOf, others = [], avoid = [] } = {}) {
  const B = bounds || { x0: 0, y0: 0, x1: width, y1: height };
  const cores = [...dots, ...others];
  const placed = [...avoid];
  const out = new Map();
  for (const d of dots) {
    const w = (widthOf && widthOf(d.coin)) || charW * String(d.coin).length + 4;
    const cands = [
      [d.x + d.r + 4, d.y + 4, "start"],
      [d.x - d.r - 4, d.y + 4, "end"],
      [d.x, d.y - d.r - 6, "middle"],
      [d.x, d.y + d.r + 12, "middle"],
    ];
    for (const [x, y, anchor] of cands) {
      const b = labelBox(x, y, anchor, w, h);
      if (b.x0 < B.x0 || b.x1 > B.x1 || b.y0 < B.y0 || b.y1 > B.y1) continue;
      if (placed.some(p => boxesOverlap(b, p))) continue;
      if (cores.some(o => o !== d && o.coin !== d.coin && boxHitsCircle(b, o.x, o.y, o.r + 2))) continue;
      placed.push(b);
      out.set(d.coin, { x, y, anchor });
      break;
    }
  }
  return out;
}

// The order labels are placed in: focused, watched, mine, in the box by engine priority,
// the largest trader lean, then movers. Only coins in `labelled` (plus the focus) count.
export function labelOrder(coins, { labelled, focus = null, watched = new Set(), mine = new Set(), movers = new Set() } = {}) {
  const rank = c => (c.coin === focus ? 0 : watched.has(c.coin) ? 1 : mine.has(c.coin) ? 2 : c.zone === "watch" ? 3 : movers.has(c.coin) ? 5 : 4);
  return coins.filter(c => c.coin === focus || labelled.has(c.coin)).sort((a, b) => rank(a) - rank(b)
    || (rank(a) === 3 ? (b.priority || 0) - (a.priority || 0) : Math.abs(net(b)) - Math.abs(net(a)))
    || a.coin.localeCompare(b.coin));
}

// The market-wide pulse from /api/hyperlens/intel, as one short line.
export function pulseLine(pulse) {
  if (!pulse) return null;
  const h = pulse.hours || 6;
  if (!pulse.opens) return `Last ${h}h: no opens by profitable traders`;
  return `Last ${h}h: ${pulse.opens} open${pulse.opens === 1 ? "" : "s"} by ${pulse.traders} profitable trader${pulse.traders === 1 ? "" : "s"}, on ${pulse.coins} coin${pulse.coins === 1 ? "" : "s"}`;
}

// A Radar address: timeframe, then the optional focus, sector and view.
export function radarHref({ tf = "1d", focus, sector, view } = {}) {
  const p = new URLSearchParams({ tf: tf === "4h" ? "4h" : "1d" });
  if (focus) p.set("focus", focus);
  if (sector) p.set("sector", sector);
  if (view === "all") p.set("view", "all");
  return `/radar?${p}`;
}
