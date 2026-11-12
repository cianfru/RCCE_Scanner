// Radar (band view): pure helpers. The server sends each coin's band z
// (backend setup_map.band_reading: distance from the weekly band's mid, scaled to how far the coin usually sits
// from it; the last eight daily readings) and four heat signs (setup_map.heat_signs). This file counts the signs,
// lists what changed and places labels. Context, not a signal.

export const BAND_LINE = 1.6;                       // band_stretch.LINE: the stretch-at-tops study's guide
export const XB = [-3.5, 4];                        // the widest band z range; readings outside sit at the edge
export const SIGNS = ["band", "heat", "funding", "traders"];
export const SIGN_WORD = {
  band: "Far above its band",
  heat: "Heat engine hot",
  funding: "Funding crowded long",
  traders: "Traders crowded or leaving",
};

export const bandZ = c => c?.band_z?.z ?? null;
export const heatCount = c => SIGNS.reduce((n, k) => n + (c?.heat_signs?.[k] === true ? 1 : 0), 0);
export const trailDelta = c => {
  const n = (c?.trail?.n || []).filter(v => v != null);
  return n.length >= 2 ? n[n.length - 1] - n[0] : 0;
};

// Crossed the band (its mid) within the readings: now on one side, some earlier day on the other.
// Returns "up", "down" or null.
export function crossed(c) {
  const d = (c?.band_z?.days || []).filter(v => v != null);
  if (d.length < 2) return null;
  const now = d[d.length - 1], before = d.slice(0, -1);
  if (now >= 0 && before.some(v => v < 0)) return "up";
  if (now < 0 && before.some(v => v >= 0)) return "down";
  return null;
}

// What changed: crossed above or below the band this week, profitable traders arriving over the trail
// (at least 2 more net long), and hot coins (3 or 4 signs). Each list sorted, at most `limit`.
export function bandChanges(coins, limit = 6) {
  const by = (f, cmp) => coins.filter(f).sort(cmp).slice(0, limit);
  const name = (a, b) => a.coin.localeCompare(b.coin);
  return {
    up: by(c => crossed(c) === "up", (a, b) => bandZ(b) - bandZ(a) || name(a, b)),
    down: by(c => crossed(c) === "down", (a, b) => bandZ(a) - bandZ(b) || name(a, b)),
    arriving: by(c => trailDelta(c) >= 2, (a, b) => trailDelta(b) - trailDelta(a) || name(a, b)),
    hot: by(c => heatCount(c) >= 3, (a, b) => heatCount(b) - heatCount(a) || (bandZ(b) ?? -9) - (bandZ(a) ?? -9) || name(a, b)),
  };
}

// The coins the map draws: every coin with a band reading in "All coins"; otherwise coins with profitable
// traders in them, two or more signs, a crossing this week, or kept (watched, held, followed).
export function bandVisible(coins, { all = false, keep = new Set() } = {}) {
  return coins.filter(c => bandZ(c) != null && (all || keep.has(c.coin) || (c.traders?.pl || 0) + (c.traders?.ps || 0) > 0
    || heatCount(c) >= 2 || crossed(c) != null));
}

export const clampX = (z, d = XB) => Math.max(d[0], Math.min(d[1], z));

// The map's x range for today's readings: always the band (0) and the stretch line with room either side,
// widened to the lowest and highest reading (a little margin), never beyond XB.
export function xDomain(zs) {
  const v = zs.filter(z => z != null && Number.isFinite(z));
  const lo = Math.min(-1.5, ...v.map(z => z - 0.3)), hi = Math.max(BAND_LINE + 0.6, ...v.map(z => z + 0.3));
  return [Math.max(XB[0], Math.floor(lo * 2) / 2), Math.min(XB[1], Math.ceil(hi * 2) / 2)];
}

// Labels without overlap: items {key, x, y, r, w, h, rank}, highest rank first; each tries right, left, above,
// below its bubble inside [0, W] x [0, H], clear of other labels and of the bubbles in `obstacles` ({key, x, y, r}),
// and is dropped when every side collides. Returns key -> {x, y, anchor}.
export function placeBandLabels(items, W, H, max = 24, obstacles = []) {
  const out = new Map(), boxes = [];
  const blocked = b => obstacles.some(o => o.key !== b.key && b.x < o.x + o.r && o.x - o.r < b.x + b.w && b.y < o.y + o.r && o.y - o.r < b.y + b.h);
  const hit = b => boxes.some(o => b.x < o.x + o.w + 4 && o.x < b.x + b.w + 4 && b.y < o.y + o.h && o.y < b.y + b.h);
  for (const it of [...items].sort((a, b) => b.rank - a.rank)) {
    if (out.size >= max) break;
    const g = it.r + 3;
    const tries = [
      { x: it.x + g, y: it.y - it.h / 2, anchor: "start" },
      { x: it.x - g - it.w, y: it.y - it.h / 2, anchor: "end" },
      { x: it.x - it.w / 2, y: it.y - g - it.h, anchor: "middle" },
      { x: it.x - it.w / 2, y: it.y + g, anchor: "middle" },
    ];
    for (const t of tries) {
      const b = { key: it.key, x: t.x, y: t.y, w: it.w, h: it.h };
      if (b.x < 0 || b.y < 0 || b.x + b.w > W || b.y + b.h > H || hit(b) || blocked(b)) continue;
      boxes.push(b);
      out.set(it.key, { x: t.anchor === "start" ? b.x : t.anchor === "end" ? b.x + b.w : b.x + b.w / 2, y: b.y + b.h / 2, anchor: t.anchor });
      break;
    }
  }
  return out;
}

const MINUS = "−";
export const zText = z => (z == null ? "-" : `${z < 0 ? MINUS : z > 0 ? "+" : ""}${Math.abs(z).toFixed(1)}`);
export const pctFromBand = p => (p == null ? "" : `${p < 0 ? MINUS : "+"}${Math.abs(p) >= 10 ? Math.round(Math.abs(p)) : Math.abs(p).toFixed(1)}%`);
