// Radar depth: pure helpers for the Radar's money bubbles, band halos, nearest-centre picking
// and the price ladder of profitable wallets (tested in radarDepth.test.js). The server sends
// each coin's money and weekly band (backend/setup_map.py) and the ladder's positions
// (/api/setup-map/ladder); this file only turns them into sizes, rings, scales and text.

const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const MINUS = "−";

// ------------------------------------------------------------------ formatting
export function fmtUsd(v) {
  if (!v) return "$0";
  const a = Math.abs(v), s = v < 0 ? MINUS : "";
  if (a >= 1e6) return `${s}$${(a / 1e6).toFixed(a >= 1e8 ? 0 : 1)}M`;
  if (a >= 1e3) return `${s}$${Math.round(a / 1e3)}K`;
  return `${s}$${Math.round(a)}`;
}
export const pctText = (v, d = 1) => `${v >= 0 ? "+" : MINUS}${Math.abs(100 * v).toFixed(d)}%`;
export const shortAddr = a => (a && a.length > 12 ? `${a.slice(0, 6)}...${a.slice(-4)}` : a || "");
export const fmtLadderPx = v => (v == null ? "-" : new Intl.NumberFormat("en", { maximumSignificantDigits: 5 }).format(v));

// ------------------------------------------------------------------ size = money
export const grossOf = c => c?.money?.gross_usd || 0;
export const hasMoney = c => grossOf(c) > 0;
// Old payloads (no money field anywhere): the map keeps sizing by wallet count.
export const moneyMode = coins => coins.some(c => c && c.money);
export const rmaxFor = w => (w < 600 ? 20 : 30);
export const maxMoney = coins => Math.max(0, ...coins.map(grossOf));

// Bubble radius: area proportional to the profitable cohort's dollars (long plus short), the
// largest coin on the map at rmax; at least 3.2px with any money; a 2px grey dot without.
export function bubbleRadius(c, G, rmax) {
  if (!hasMoney(c) || !G) return 2;
  return Math.max(3.2, rmax * Math.sqrt(grossOf(c) / G));
}
export const countRadius = c => 4.5 + Math.min(6, Math.sqrt((c?.traders?.pl || 0) + (c?.traders?.ps || 0)));

// The size key: three round amounts at or under the largest, each drawn at least 3px.
const KEY_STEPS = [1e5, 2.5e5, 1e6, 5e6, 25e6, 100e6, 500e6, 2.5e9];
export function legendSizes(G, rmax) {
  if (!G) return [];
  const ok = KEY_STEPS.filter(v => v <= G * 1.05 && rmax * Math.sqrt(v / G) >= 3);
  return ok.slice(-3).map(v => ({ v, r: Math.max(3.2, rmax * Math.sqrt(v / G)) }));
}

// The pink slice: the short share of the dollars, from 12 o'clock clockwise, as a path around
// the bubble's own centre. Shown from 2% on bubbles of 8px and up, and from 40% on smaller ones.
export function shortSlice(r, netLongShare) {
  if (netLongShare == null) return null;
  const sh = 1 - netLongShare;
  if (!((r >= 8 && sh >= 0.02) || sh >= 0.4)) return null;
  const big = r >= 12, rr = r - (big ? 0.75 : 0.5);
  const a = 2 * Math.PI * Math.min(sh, 0.999);
  const x1 = rr * Math.sin(a), y1 = -rr * Math.cos(a);
  return `M0,0 L0,${(-rr).toFixed(2)} A${rr.toFixed(2)},${rr.toFixed(2)} 0 ${a > Math.PI ? 1 : 0} 1 ${x1.toFixed(2)},${y1.toFixed(2)} Z`;
}

// ------------------------------------------------------------------ band halo
// The halo from the coin's weekly band and its price. tone: "red" (the last weekly close
// under the band's lower edge), "violet" (inside, or under it now but not at the close, with
// a red tick), "halo" (above: fill = clamp(1 - d / 0.30, 0, 1), d = price / top - 1), "none".
export const BAND_REACH = 0.3;
export function bandInfo(band, price) {
  if (!band || band.hi == null || band.lo == null) return { state: "none", fill: 0, tone: "none", short: "none", text: "no weekly band" };
  const { lo, hi } = band, wc = band.week_close;
  const px = price || wc;
  if (wc != null && wc < lo) {
    return { state: "closed_under", fill: 1, tone: "red", short: "closed under", text: `last weekly close ${pctText(wc / lo - 1)} under the band` };
  }
  if (px < lo) {
    return { state: "under_now", fill: 1, tone: "violet", tick: true, short: `${pctText(px / lo - 1)} under now`,
      text: `${pctText(px / lo - 1)} under the band now · last close ${wc != null && wc > hi ? "above" : "inside"}` };
  }
  if (px <= hi) return { state: "inside", fill: 1, tone: "violet", short: "inside", text: "inside the band" };
  const d = px / hi - 1;
  return { state: "above", d, fill: clamp(1 - d / BAND_REACH, 0, 1), tone: "halo", short: `${pctText(d)} above`, text: `${pctText(d)} above the band` };
}

// Ring geometry around a bubble of radius r. Tiny bubbles (under 6px) show the ring only from
// half full, inside or under the band; the empty track shows on bubbles of 8px and up.
export function haloRing(r, info) {
  const tiny = r < 6;
  const sw = tiny ? 1.25 : r > 14 ? 2.2 : 1.6;
  const hr = r + (tiny ? 1 : 1.5) + sw / 2;
  const C = 2 * Math.PI * hr;
  const show = info.tone !== "none" && (!tiny || info.fill >= 0.5 || info.state !== "above");
  const track = show && r >= 8;
  const arc = show && info.fill > 0 ? info.fill * C : 0;
  const outer = show && (arc > 0 || track) ? hr + sw / 2 : r;
  return { show, track, hr, sw, C, arc, tick: show && !!info.tick, outer };
}

// ------------------------------------------------------------------ picking
// Nearest centre, not topmost element: small dots within reach of the pointer (nearest first),
// then bubbles the pointer is inside (smallest first, so a small bubble drawn over a big one
// wins), then anything within the tolerance (nearest edge). Coins without money come last.
// items: [{coin, x, y, r, empty}].
export function candidates(items, px, py, { small = false, touch = false } = {}) {
  const tol = small || touch ? 20 : 14, inR = small || touch ? 10 : 6;
  const out = [];
  for (const it of items) {
    const d = Math.hypot(px - it.x, py - it.y);
    const tier = it.r < inR && d <= inR ? 0 : d <= it.r + 1 ? 1 : d <= Math.max(it.r + 1, tol) ? 2 : -1;
    if (tier >= 0) out.push({ it, d, tier });
  }
  out.sort((a, b) => (!!a.it.empty - !!b.it.empty) || (a.tier - b.tier)
    || (a.tier === 0 ? a.d - b.d : a.tier === 1 ? (a.it.r - b.it.r) || (a.d - b.d) : (a.d - a.it.r) - (b.d - b.it.r)));
  return out.map(o => o.it);
}

// Click to step: a click where the last one landed (within 8px, same candidates) takes the
// next coin of the list; a fresh click takes the first, or the second when the first is the
// coin already followed. Returns {coin, last} (coin null: nothing there).
export function stepPick(list, px, py, last, focus) {
  if (!list.length) return { coin: null, last: null };
  const key = list.map(i => i.coin).join();
  let idx = 0;
  if (last && last.key === key && Math.hypot(px - last.px, py - last.py) < 8) idx = (last.idx + 1) % list.length;
  else if (list.length > 1 && list[0].coin === focus) idx = 1;
  return { coin: list[idx].coin, last: { px, py, key, idx } };
}

// Coins drawn at the same spot as one coin (centres within 6px).
export function sameSpot(pos, coin, within = 6) {
  const me = pos?.get(coin);
  if (!me) return [];
  const out = [];
  for (const [k, p] of pos) if (k !== coin && Math.hypot(p.x - me.x, p.y - me.y) < within) out.push(k);
  return out;
}

// ------------------------------------------------------------------ the ladder
export function niceTicks(lo, hi, n) {
  const span = hi - lo;
  if (!(span > 0)) return [];
  const step0 = span / n, mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => span / s <= n) || 10 * mag;
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-12; v += step) out.push(+v.toPrecision(12));
  return out;
}

// The ladder's price range (log scale): price, the band, the mean when it sits within 3x of
// price, and every entry clamped to [price / 8, price * 4]; at least +-4% around price, then
// padded 6% of the log span each side. lim: the clamp range (entries beyond it draw faded at the edge).
export function ladderDomain(price, { band, mean, entries = [] } = {}) {
  const lim = [price / 8, price * 4];
  const vals = [price];
  if (band?.lo && band?.hi) vals.push(band.lo, band.hi);
  if (mean && mean > price / 3 && mean < price * 3) vals.push(mean);
  for (const e of entries) if (e > 0) vals.push(clamp(e, lim[0], lim[1]));
  let lo = Math.min(...vals, price * 0.96), hi = Math.max(...vals, price * 1.04);
  const pad = (Math.log(hi) - Math.log(lo)) * 0.06;
  lo = Math.exp(Math.log(lo) - pad); hi = Math.exp(Math.log(hi) + pad);
  return { lo, hi, lim };
}
export const logScale = (lo, hi, top, bottom) => v => top + (1 - (Math.log(clamp(v, lo, hi)) - Math.log(lo)) / (Math.log(hi) - Math.log(lo))) * (bottom - top);

// Dot radius by position dollars, scaled to the largest wallet in the coin; smaller when a
// side is crowded.
export function ladderRadius(usd, maxUsd, { narrow = false, dense = 0 } = {}) {
  const Rm = (narrow ? 12 : 14) * (dense > 40 ? 0.75 : dense > 20 ? 0.88 : 1);
  return Math.max(2.4, Rm * Math.sqrt(usd / Math.max(1, maxUsd)));
}

// A deterministic beeswarm in one column: largest first, each dot at its own y and the first
// x (centre, then alternating 1.5px steps out) where it overlaps nothing placed; with no free
// slot, the least-overlap one. rows: [{y, r, ...}] -> same rows with x.
export function beeswarm(rows, center, half) {
  const placed = [];
  for (const d of [...rows].sort((a, b) => b.r - a.r || a.y - b.y)) {
    let best = null, bestX = center, bestOv = Infinity;
    for (let k = 0; k < 600; k++) {
      const off = (k % 2 ? 1 : -1) * Math.ceil(k / 2) * 1.5;
      if (Math.abs(off) > Math.max(0, half - d.r)) break;
      const x = center + off;
      let ov = 0;
      for (const p of placed) { const g = p.r + d.r + 1 - Math.hypot(p.x - x, p.y - d.y); if (g > 0) ov += g; }
      if (ov === 0) { best = x; break; }
      if (ov < bestOv - 1e-9) { bestOv = ov; bestX = x; }
    }
    placed.push({ ...d, x: best == null ? bestX : best });
  }
  return placed;
}

// Right-edge labels (band, mean, median) pushed apart so none overlaps: at least `gap` px.
export function spreadLabels(labels, gap = 12) {
  const out = [...labels].sort((a, b) => a.y - b.y).map(l => ({ ...l }));
  for (let i = 1; i < out.length; i++) if (out[i].y - out[i - 1].y < gap) out[i].y = out[i - 1].y + gap;
  return out;
}

// The ladder header's counts and dollars: the ladder's own when loaded, else the map's.
export function ladderCounts(c, lad) {
  if (lad?.counts) return lad.counts;
  return { long: c?.traders?.pl || 0, short: c?.traders?.ps || 0, long_usd: c?.money?.long_usd || 0, short_usd: c?.money?.short_usd || 0 };
}

// ------------------------------------------------------------------ the ladder's wallets
// A trader's profile page: the full address, lowercase.
export const traderPath = address => `/trader/${String(address || "").toLowerCase()}`;

// The largest wallets in the coin for the list under the ladder: by position dollars, then
// address (a stable order), at most `n`.
export function topWallets(positions, n = 5) {
  return [...(positions || [])].sort((a, b) => (b.size_usd || 0) - (a.size_usd || 0) || String(a.address).localeCompare(String(b.address))).slice(0, n);
}

// A wallet's unrealised P&L as a share: on margin when the payload has it (as the coin page's
// trader list shows it), else the price move since its entry.
export const walletPnl = w => (w?.roe != null ? w.roe / 100 : w?.move != null ? w.move / 100 : null);
