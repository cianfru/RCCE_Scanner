// The LEVELS rail (Portfolio v2, B4): one position's levels on one log price line. Price rises to
// the right for longs and shorts alike (the axis is never mirrored). The domain is the near set
// (mark, entry, nearest stop and take-profit, the weekly band, the trend line and your side's
// traders' median entry), padded 8% of its log span and at least ±2% around the mark. Liquidation
// joins it when that keeps the span within 1.5x; otherwise the axis breaks at the costly end (below
// the mark for a long, above it for a short): 10% of the width is kept there, the liquidation tick
// sits 4% from the edge and two slanted strokes mark the break at 9%.

export const PAD = 0.08;
export const MIN_AROUND_MARK = 0.02;
export const LIQ_SPAN_MAX = 1.5;
export const LABEL_GAP = 28;
const L = Math.log;
const ok = v => typeof v === "number" && Number.isFinite(v) && v > 0;

export function railDomain({ mark, entry, stop, tp, band, trend, tradersEntry, liq }) {
  const near = [mark, entry, stop, tp, band?.lo, band?.hi, trend, tradersEntry].filter(ok);
  let lo = Math.min(...near, mark / (1 + MIN_AROUND_MARK));
  let hi = Math.max(...near, mark * (1 + MIN_AROUND_MARK));
  const span = L(hi) - L(lo);
  let brk = null;
  if (ok(liq)) {
    const withLiq = L(Math.max(hi, liq)) - L(Math.min(lo, liq));
    if (withLiq <= LIQ_SPAN_MAX * span) { lo = Math.min(lo, liq); hi = Math.max(hi, liq); }
    else brk = liq < lo ? "left" : "right";
  }
  const s = L(hi) - L(lo);
  return { lo: Math.exp(L(lo) - PAD * s), hi: Math.exp(L(hi) + PAD * s), brk };
}

// width: the rail's drawing width in px. Returns positions (px) for every mark, the hatch, the break
// and up to three labels (mark price > Liq > SL; the lowest drops when two sit within 28 px).
export function railModel({ isLong, mark, entry, liq = null, stops = [], tps = [], band = null, trend = null, tradersEntry = null, width = 400 }) {
  const stop = stops[0]?.px ?? stops[0] ?? null;
  const tp = tps[0]?.px ?? tps[0] ?? null;
  const dom = railDomain({ mark, entry, stop, tp, band, trend, tradersEntry, liq });
  let x0 = 0, x1 = width;
  if (dom.brk === "left") x0 = 0.10 * width;
  if (dom.brk === "right") x1 = 0.90 * width;
  const a = L(dom.lo), b = L(dom.hi);
  const clamp = v => Math.max(1, Math.min(width - 1, v));
  const x = v => (ok(v) ? clamp(x0 + ((L(v) - a) / (b - a)) * (x1 - x0)) : null);
  const liqX = !ok(liq) ? null : dom.brk === "left" ? 0.04 * width : dom.brk === "right" ? 0.96 * width : x(liq);
  // The costly end: below the mark for a long, above it for a short.
  const costly = isLong ? "left" : "right";
  const hatch = liqX == null ? null : costly === "left" ? { x0: 0, x1: liqX } : { x0: liqX, x1: width };
  const breakX = dom.brk === "left" ? 0.09 * width : dom.brk === "right" ? 0.91 * width : null;
  const m = {
    mark: x(mark), entry: x(entry), liq: liqX, stop: x(stop), tp: x(tp), trend: x(trend), traders: x(tradersEntry),
    band: band && ok(band.lo) && ok(band.hi) ? { x0: x(band.lo), x1: x(band.hi) } : null,
  };
  const labels = placeLabels([
    { kind: "mark", x: m.mark, prio: 0 },
    { kind: "liq", x: m.liq, prio: 1 },
    { kind: "sl", x: m.stop, prio: 2 },
  ].filter(l => l.x != null));
  return { domain: dom, x, m, hatch, breakX, costly, labels, moreStops: Math.max(0, stops.length - 1), moreTps: Math.max(0, tps.length - 1) };
}

// Keep labels by priority; one closer than LABEL_GAP px to a kept label is dropped.
export function placeLabels(labels, gap = LABEL_GAP) {
  const kept = [];
  for (const l of [...labels].sort((p, q) => p.prio - q.prio)) {
    if (kept.every(k => Math.abs(k.x - l.x) >= gap)) kept.push(l);
  }
  return kept.sort((p, q) => p.prio - q.prio).slice(0, 3);
}
