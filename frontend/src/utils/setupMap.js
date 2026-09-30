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
export const ZONE_WORD = { watch: "Early setup", late: "Stretched: late", crowded: "Crowded", quiet: "Nobody in yet", outside: "Outside" };
export const CROWD_WORD = { quiet: "Quiet", early: "Early", crowded: "Crowded", against: "Against", holding: "Holding" };
export const SIGNAL_SHORT = {
  STRONG_LONG: "Strong", LIGHT_LONG: "Light", ACCUMULATE: "Accumulate", REVIVAL_SEED: "Revival", REVIVAL_SEED_CONFIRMED: "Revival",
  LIGHT_SHORT: "Light short", STRONG_SHORT: "Strong short", TRIM: "Trim", TRIM_HARD: "Trim hard", NO_LONG: "No long", RISK_OFF: "Risk off", WAIT: "Wait",
};

export const net = c => (c?.traders?.pl || 0) - (c?.traders?.ps || 0);

// ------------------------------------------------------------------ Long / Short / Both
// The map's side switch. Long (the default): up is profitable traders net long, size the dollars
// they hold. Short: up is profitable traders net short (short minus long, lockstep groups once, as
// the server counts them) and size the dollars short. Both: placed as Long, each bubble split into
// dollars long and short. The switch only changes what the page draws (the forward test logs Long).
export const SIDES = [{ key: "long", label: "Long" }, { key: "short", label: "Short" }, { key: "both", label: "Both" }];
export const sideOf = v => (v === "short" || v === "both" ? v : "long");
export const netShort = c => (c?.traders?.ps || 0) - (c?.traders?.pl || 0);
// Up on the map for a side: net short in Short, net long otherwise.
export const netFor = (c, side) => (side === "short" ? netShort(c) : net(c));

// Stretched and shorted (the Short view's zone, top right): stretched at least SHORT_ZONE_Z and at
// least SHORT_ZONE_N profitable traders net short.
export const SHORT_ZONE_Z = 1.5;
export const SHORT_ZONE_N = 3;
export const inShortZone = c => c?.zscore != null && c.zscore >= SHORT_ZONE_Z && netShort(c) >= SHORT_ZONE_N;

// Most shorted: coins with profitable traders net short, most net short first, then the dollars
// short, then the name. At most `limit`.
export function mostShorted(coins, limit = 6) {
  return coins.filter(c => c && c.zscore != null && netShort(c) >= 1)
    .sort((a, b) => netShort(b) - netShort(a) || (b.money?.short_usd || 0) - (a.money?.short_usd || 0) || a.coin.localeCompare(b.coin))
    .slice(0, limit);
}

// A Most shorted row's line: "12 short · $3.4M" (no dollars when the payload has none).
export function shortLine(c, fmtUsd) {
  const n = c?.traders?.ps || 0, u = c?.money?.short_usd || 0;
  return `${n} short${u > 0 ? ` · ${fmtUsd(u)}` : ""}`;
}
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

// A trail for a side: the stored record keeps long minus short at each close, so net short is its
// negative (Short); Long and Both use it as it is.
export function sideTrail(c, side) {
  const p = trailPoints(c);
  return p && side === "short" ? p.map(v => ({ z: v.z, n: v.n == null ? v.n : 0 - v.n })) : p;
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

// The trail step at which a coin last came into the box (the trail's length when the server's
// zone says it is in but its last point is not), or null when it is not in the box now, has no
// trail, or sat in the box for the whole trail.
function entryStep(c, box) {
  if (c.zone !== "watch") return null;
  const p = trailPoints(c);
  if (!p || p.length < 2) return null;
  let k = p.length - 1;
  while (k >= 0 && inBox(box, p[k].z, p[k].n)) k--;
  return k < 0 ? null : k + 1;
}

// New early setups (coins that came into the box within the trail), newest first: the step
// each one came in, then the engine's priority. At most `limit`.
export function newEarly(coins, box, limit = 6) {
  const out = [];
  for (const c of coins) {
    const at = entryStep(c, box);
    if (at != null) out.push({ c, at });
  }
  return out.sort((a, b) => b.at - a.at || (b.c.priority || 0) - (a.c.priority || 0) || a.c.coin.localeCompare(b.c.coin))
    .slice(0, limit).map(x => x.c);
}

// When a new early setup came into the box: the time (seconds) of its first trail step in it.
export function enteredAt(c, box) {
  const k = entryStep(c, box);
  const t = c.trail?.t;
  return k == null || !t?.length ? null : t[Math.min(k, t.length - 1)] ?? null;
}

// Time since a moment, short: "now" under an hour, "8h" under two days, then "3d".
export function sinceText(tSec, nowSec) {
  if (tSec == null || nowSec == null) return "";
  const h = Math.floor(Math.max(0, nowSec - tSec) / 3600);
  return h < 1 ? "now" : h < 48 ? `${h}h` : `${Math.floor(h / 24)}d`;
}

// The profitable traders in a coin, for a list row: "3 traders · $1.2M" ("1 trader", no
// dollars when the payload has none).
export function tradersLine(c, fmtUsd) {
  const n = (c?.traders?.pl || 0) + (c?.traders?.ps || 0);
  const g = c?.money?.gross_usd || 0;
  return `${n} trader${n === 1 ? "" : "s"}${g > 0 ? ` · ${fmtUsd(g)}` : ""}`;
}

// What the map shows by default: setups with at least one profitable trader, forming and
// just-fired setups even when nobody holds them, and anything watched or held. The Short view
// (side "short") also shows every coin profitable traders are net short, setup or not.
export function visible(coins, { all = false, keep = new Set(), side = "long" } = {}) {
  return coins.filter(c => c.zscore != null && (all || keep.has(c.coin) || (side === "short" && netShort(c) >= 1) || (c.stage !== "waiting"
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

// A thumbnail zoomed to the coin's own trail: x in z units, y in symlog units. The trail sets
// the scale, at least minZ / minN wide so a coin that barely moved is not blown up. A Watch box
// edge joins the view only when it sits close (the view stays within 1.5x the trail's span), so
// the box reads as a tinted area or one edge and never shrinks the trail: the trail always spans
// at least half the thumbnail once it moved minZ. Padded by 14% each side for the dots.
export function thumbExtent(points, box, { minZ = 0.25, minN = 0.3 } = {}) {
  const axis = (vals, edges, min) => {
    edges = edges.filter(Number.isFinite);
    vals = vals.filter(Number.isFinite);
    if (!vals.length) vals = edges.length ? edges : [0];
    let lo = Math.min(...vals), hi = Math.max(...vals);
    if (hi - lo < min) { const m = (lo + hi) / 2; lo = m - min / 2; hi = m + min / 2; }
    const cap = 1.5 * (hi - lo);
    for (const e of [...edges].sort((a, b) => Math.max(lo - a, a - hi) - Math.max(lo - b, b - hi))) {
      if (e < lo && hi - e <= cap) lo = e;
      else if (e > hi && e - lo <= cap) hi = e;
    }
    const p = 0.14 * (hi - lo);
    return [lo - p, hi + p];
  };
  const p = points || [];
  return { x: axis(p.map(v => v.z), box.z, minZ), y: axis(p.map(v => symlog(v.n)), box.n.map(symlog), minN) };
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
// force: the followed coin, whose label always shows (the other dots are dimmed). When no
// side is free it takes the first side clear of other labels that covers only dots drawn
// under it, else the first clear of other labels, else the first inside the plot, else the
// right. relax (small maps):
// a label with no free side may cover the cores of dots drawn under it (under(d, o), by
// default every dot), never another label or the fixed text.
// insideMin: a dot with a core of at least this radius (d.core, else d.r) whose name fits
// inside it takes the label at its centre first, clear of the smaller dots drawn over it.
export function placeLabels(dots, { width, height, bounds, charW = 6.4, h = 13, widthOf, others = [], avoid = [], force = null, relax = false, under = () => true, insideMin = Infinity } = {}) {
  const B = bounds || { x0: 0, y0: 0, x1: width, y1: height };
  const cores = [...dots, ...others];
  const placed = [...avoid];
  const out = new Map();
  for (const d of dots) {
    const w = (widthOf && widthOf(d.coin)) || charW * String(d.coin).length + 4;
    const core = d.core ?? d.r;
    if (core >= insideMin && Math.hypot(w / 2, 6) < core - 1) {
      const b = labelBox(d.x, d.y + 4, "middle", w, h);
      const over = cores.filter(o => o.coin !== d.coin && (o.core ?? o.r) <= core && (o.core ?? o.r) > 3);
      if (!placed.some(p => boxesOverlap(b, p)) && !over.some(o => boxHitsCircle(b, o.x, o.y, (o.core ?? o.r) + 2))) {
        placed.push(b);
        out.set(d.coin, { x: d.x, y: d.y + 4, anchor: "middle", inside: true });
        continue;
      }
    }
    const cands = [
      [d.x + d.r + 4, d.y + 4, "start"],
      [d.x - d.r - 4, d.y + 4, "end"],
      [d.x, d.y - d.r - 6, "middle"],
      [d.x, d.y + d.r + 12, "middle"],
    ].map(([x, y, anchor]) => ({ x, y, anchor, b: labelBox(x, y, anchor, w, h) }));
    const inside = ({ b }) => b.x0 >= B.x0 && b.x1 <= B.x1 && b.y0 >= B.y0 && b.y1 <= B.y1;
    const clearOfLabels = ({ b }) => !placed.some(p => boxesOverlap(b, p));
    const clearOfCores = ({ b }, soft) => !cores.some(o => o !== d && o.coin !== d.coin && !(soft && under(d, o)) && boxHitsCircle(b, o.x, o.y, o.r + 2));
    let pick = cands.find(c => inside(c) && clearOfLabels(c) && clearOfCores(c, false));
    if (!pick && (relax || force === d.coin)) pick = cands.find(c => inside(c) && clearOfLabels(c) && clearOfCores(c, true));
    if (!pick && force === d.coin) pick = cands.find(c => inside(c) && clearOfLabels(c)) || cands.find(inside) || cands[0];
    if (!pick) continue;
    placed.push(pick.b);
    out.set(d.coin, { x: pick.x, y: pick.y, anchor: pick.anchor });
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

// A Radar address: timeframe, then the optional focus, sector and view.
export function radarHref({ tf = "1d", focus, sector, view } = {}) {
  const p = new URLSearchParams({ tf: tf === "4h" ? "4h" : "1d" });
  if (focus) p.set("focus", focus);
  if (sector) p.set("sector", sector);
  if (view === "all") p.set("view", "all");
  return `/radar?${p}`;
}

// The Radar forward test's one line in the (i) (/api/radar/forward-test): days logged and the
// early-setup events with an outcome so far, against the declared minimum. "" without a status.
export function forwardLine(st) {
  if (!st || st.days_logged == null) return "";
  if (!st.days_logged) return "Forward test: logging from the next daily close.";
  const n = st.H1?.scored || 0, d = st.days_logged;
  return `Forward test: ${d} day${d === 1 ? "" : "s"} logged, ${n} event${n === 1 ? "" : "s"} scored (needs ${st.min_events || 30}).`;
}
