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

// Vertical bands, px from the track (negative is above): where each glyph and text is drawn.
// Desktop: mark price above, Liq and SL under; the take-profit glyph and the traders' diamond sit
// just above the track, the stop glyph just under it. Compact (phone cards): a 32 px rail.
export const BANDS = {
  full: { mark: [-20, -10], under: [11, 20], tpMore: [-13, -5], slMore: [3, 11] },
  compact: { mark: [-18, -9], under: [5, 14] },
};
const GLYPHS = { tp: [-11, -5], sl: [5, 11], traders: [-11.5, -6.5], entry: [-4.5, 4.5], tick: [-8, 8], liq: [-7, 7], trend: [-6, 6], brk: [-6, 6], visit: [-5, 5] };
// Text sizes (px) and an approximate width when no measure is given: Geist Mono is 0.6 em a figure.
export const TEXT_PX = { mark: 11, label: 11, more: 11 };
const approx = (text, size) => String(text).length * size * 0.6;

// width: the rail's drawing width in px. text: {mark} (the mark price as shown); measure(text,
// size, kind): a text's width in px. Returns positions (px) for every mark, the hatch, the break and
// the texts that fit (placeLabels).
export function railModel({ isLong, mark, entry, liq = null, stops = [], tps = [], band = null, trend = null, tradersEntry = null, visitMark = null,
  width = 400, compact = false, text = {}, measure = approx }) {
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
    // Where the mark was on the last visit; only when it falls inside the drawn domain.
    visit: ok(visitMark) && visitMark > dom.lo && visitMark < dom.hi && Math.abs(L(visitMark / mark)) > 1e-6 ? x(visitMark) : null,
  };
  const moreStops = Math.max(0, stops.length - 1), moreTps = Math.max(0, tps.length - 1);

  // Glyphs: always drawn; they block texts.
  const g = (id, at, half, band) => (at == null ? null : { id, x0: at - half, x1: at + half, y0: band[0], y1: band[1] });
  const obstacles = [
    g("tp", m.tp, 3.5, GLYPHS.tp), g("sl", m.stop, 3.5, GLYPHS.sl), g("traders", m.traders, 2.5, GLYPHS.traders),
    g("entry", m.entry, 4.5, GLYPHS.entry), g("mark", m.mark, 1, GLYPHS.tick), g("liq", m.liq, 1, GLYPHS.liq),
    g("trend", m.trend, 1, GLYPHS.trend), g("brk", breakX, 5.5, GLYPHS.brk),
  ].filter(Boolean);

  // Texts by priority: mark price 0, Liq 1, SL 2, the take-profits' "+n" 3, the stops' "+n" 4.
  const B = compact ? BANDS.compact : BANDS.full;
  const away = at => (at >= (m.mark ?? at) ? "start" : "end");
  const markText = text.mark ?? "";
  const texts = [];
  const add = (kind, at, str, size, band, prio, anchors, extra = {}) => {
    if (at == null || !str) return;
    texts.push({ kind, x: at, text: str, w: measure(str, size, kind), size, band, prio, anchors, ...extra });
  };
  add("mark", m.mark, markText, TEXT_PX.mark, B.mark, 0, ["middle", "end", "start"], { keep: true });
  // Under a broken axis Liq leans to the outer edge, clear of the break strokes; on a phone card it
  // is left out when the break sits within 24 px of the edge.
  const liqAnchors = dom.brk === "left" ? ["end"] : dom.brk === "right" ? ["start"] : ["middle", "start", "end"];
  const liqRoom = !compact || breakX == null || (breakX >= 24 && breakX <= width - 24);
  if (liqRoom) add("liq", m.liq, "Liq", TEXT_PX.label, B.under, 1, liqAnchors);
  if (!compact) {
    add("sl", m.stop, "SL", TEXT_PX.label, B.under, 2, ["middle", "start", "end"]);
    // "+n" sits on the side of its glyph away from the mark, 5 px clear of it; it never shifts.
    if (moreTps > 0 && m.tp != null) add("tpMore", m.tp + (away(m.tp) === "start" ? 6 : -6), `+${moreTps}`, TEXT_PX.more, B.tpMore, 3, [away(m.tp)], { fixed: true, own: "tp" });
    if (moreStops > 0 && m.stop != null) add("slMore", m.stop + (away(m.stop) === "start" ? 6 : -6), `+${moreStops}`, TEXT_PX.more, B.slMore, 4, [away(m.stop)], { fixed: true, own: "sl" });
  }
  const labels = placeLabels(texts, obstacles, { width });
  return { domain: dom, x, m, hatch, breakX, costly, labels, moreStops, moreTps };
}

// Texts in priority order, each at the first anchor where it hits no glyph and no text kept before
// it (boxes overlap in both x, with `pad` px, and y). A text that would leave the rail is shifted
// back inside, except a fixed one ("+n"), which is dropped instead. The mark price (keep) is always
// placed, at its least crowded anchor. Returns [{kind, text, x0, w, size}] for textAnchor="start".
export function placeLabels(texts, obstacles = [], { width = Infinity, pad = 3 } = {}) {
  const taken = [...obstacles];
  const out = [];
  const hit = (p, q) => p.x0 < q.x1 + pad && q.x0 < p.x1 + pad && p.y0 < q.y1 && q.y0 < p.y1;
  for (const t of [...texts].sort((p, q) => p.prio - q.prio)) {
    let best = null;
    for (const anchor of t.anchors || ["middle"]) {
      let x0 = anchor === "middle" ? t.x - t.w / 2 : anchor === "end" ? t.x - t.w : t.x;
      if (x0 < 0 || x0 + t.w > width) {
        if (t.fixed) continue;
        x0 = Math.max(0, Math.min(width - t.w, x0));
      }
      const box = { x0, x1: x0 + t.w, y0: t.band[0], y1: t.band[1] };
      const n = taken.filter(o => o.id !== t.own && o.id !== t.kind && hit(box, o)).length;
      if (!best || n < best.n) best = { box, n };
      if (n === 0) break;
    }
    if (!best || (best.n > 0 && !t.keep)) continue;
    taken.push({ ...best.box, id: `text:${t.kind}` });
    out.push({ kind: t.kind, text: t.text, x0: best.box.x0, w: t.w, size: t.size });
  }
  return out;
}
