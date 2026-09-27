// Setup map: pure helpers for SetupMap.jsx (tested in setupMap.test.js). The server
// decides each coin's stage, zone and crowd read (backend/setup_map.py); this file only
// shapes trails, movement and the day's shortlist.

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
