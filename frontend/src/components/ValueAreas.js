// Lightweight Charts v5 series primitive: the coin chart's Value layer (/api/auction).
// Per swing (the move from a swing low to the next swing high, or from a high to the next low, and the move
// still running): a box over its candles, its volume by price along the box's left edge, a line at its point
// of control (POC) and lines at the edges of its value area. The last finished swing's three lines run on,
// dashed, to the right edge; while the last price is outside its value area, its POC tag adds the side the
// method trades it from (short below the value area, long above). Right of the last candle: labelled ticks (those three, the opens, prior
// extremes). Violet: the latest major swing's 0.618 to 0.66 pullback zone.
// What happened, drawn where it happened: no forecast.
import { placeRanges, lastDone, histogram, ticks, rangeTicks, pocRule, spread, mergeTicks, fibBands, fibTicks } from "../utils/valueLayer.js";

const LABEL_FONT = "10px 'SF Mono', 'Fira Code', monospace";
const LABEL_GAP = 12;
const PROFILE_SHARE = 0.3;       // a swing's widest histogram bar, as a share of the part of its box in view
const PROFILE_MAX = 120;

export default class ValueAreas {
  constructor(colors) {
    this.colors = colors;        // {ink, poc, fib, bg}: [r, g, b] each
    this.visible = false;
    this.ranges = [];
    this.ticks = [];
    this.bands = [];
    this.hits = [];              // what is drawn where (media pixels), lowest priority first: see hitTest
    this.last = 0;
    // Boxes and lines sit behind the candles; the tick labels go on top so no line strikes through them.
    this.views = ["bottom", "top"].map(z => ({ zOrder: () => z, renderer: () => ({ draw: target => this.draw(target, z) }) }));
  }
  attached({ chart, series, requestUpdate }) { this.chart = chart; this.series = series; this.requestUpdate = requestUpdate; requestUpdate(); }
  detached() { this.chart = null; this.series = null; this.requestUpdate = null; }
  // body: the /api/auction answer (null clears); times: the chart's candle times (seconds); last: the last price.
  setData(body, times, tfSec, colors, last) {
    if (colors) this.colors = colors;
    this.ranges = body && times?.length ? placeRanges(body.ranges, times).map(r => ({ ...r, rows: histogram(r) })) : [];
    this.bands = body ? fibBands(body, times, tfSec) : [];
    const tf = tfSec <= 3600 ? "1h" : tfSec < 86400 ? "4h" : "1d";
    this.rule = pocRule(lastDone(this.ranges), last);      // the side the method trades the last finished swing's POC from
    this.ticks = body ? [...ticks(body, tf), ...rangeTicks(this.ranges, last), ...fibTicks(this.bands)] : [];
    this.last = times?.length ? times.length - 1 : 0;
    this.requestUpdate?.();
  }
  setVisible(v) { this.visible = v; this.requestUpdate?.(); }
  updateAllViews() {}
  paneViews() { return this.views; }
  // What is drawn under a point of the price pane: {kind, ...} for utils/valueLayer.describe, or null.
  // Tags win over lines, lines over the pullback zone, the zone over a swing's box.
  hitTest(x, y) {
    if (!this.visible) return null;
    for (let i = this.hits.length - 1; i >= 0; i--) {
      const h = this.hits[i];
      if (x >= h.x0 && x <= h.x1 && y >= h.y0 && y <= h.y1) return h.info;
    }
    return null;
  }
  // A paint queued while the chart is being torn down finds a disposed chart: skip it.
  draw(target, layer) {
    try { this.paint(target, layer); } catch (e) { if (!/disposed/i.test(String(e?.message))) throw e; }
  }
  paint(target, layer) {
    if (!this.visible || !this.chart || !this.series || !(this.ranges.length || this.bands.length || this.ticks.length)) return;
    const ts = this.chart.timeScale();
    const x0 = ts.logicalToCoordinate(0), x1 = ts.logicalToCoordinate(1);
    const range = ts.getVisibleLogicalRange();
    if (x0 == null || x1 == null || !range) return;
    const half = (x1 - x0) / 2;
    const edge = i => x0 + (x1 - x0) * i - half;            // the left edge of candle i
    const y = p => this.series.priceToCoordinate(p);
    const ink = a => `rgba(${this.colors.ink.join(",")},${a})`;
    const gold = a => `rgba(${this.colors.poc.join(",")},${a})`;
    const violet = a => `rgba(${this.colors.fib.join(",")},${a})`;

    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      const W = mediaSize.width, H = mediaSize.height;
      const line = (xa, xb, yy, color, width = 1, dash = null) => {
        if (yy == null || yy < -2 || yy > H + 2 || xb <= xa) return;
        ctx.beginPath(); ctx.setLineDash(dash || []); ctx.strokeStyle = color; ctx.lineWidth = width;
        const py = Math.round(yy) + (width % 2 ? 0.5 : 0);
        ctx.moveTo(xa, py); ctx.lineTo(xb, py); ctx.stroke();
      };
      ctx.save();
      if (layer === "top") { this.paintTicks(ctx, W, H, edge, y, ink, gold, violet); ctx.restore(); return; }
      const boxes = [], zones = [], lines = [];
      const area = (list, xa, ya, xb, yb, info) => { if (xb > xa && ya != null && yb != null) list.push({ x0: xa, y0: Math.min(ya, yb), x1: xb, y1: Math.max(ya, yb), info }); };
      const near = (xa, xb, yy, info) => { if (yy != null) area(lines, xa, yy - 6, xb, yy + 6, info); };

      // Each swing: a box over its candles, its volume by price from the box's left edge, the edges of its value
      // area and its POC across the box. The move still running is fainter.
      for (const r of this.ranges) {
        if (r.to < range.from - 1 || r.from > range.to + 1) continue;
        const xa = edge(r.from), xb = edge(r.to), top = y(r.high), bottom = y(r.low);
        if (top == null || bottom == null) continue;
        ctx.fillStyle = ink(r.live ? 0.03 : 0.055);
        ctx.fillRect(xa, top, xb - xa, bottom - top);
        area(boxes, xa, top, xb, bottom, { kind: "range", r });
        // Its volume by price, from the box's left edge, or from the pane's when that edge is scrolled out of view.
        const xh = Math.max(xa, 0), maxW = Math.min(PROFILE_MAX, (Math.min(xb, W) - xh) * PROFILE_SHARE);
        for (const row of r.rows) {
          const rt = y(row.high), rb = y(row.low);
          if (rt == null || rb == null || rb < 0 || rt > H || maxW <= 0) continue;
          ctx.fillStyle = row.kind === "poc" ? gold(0.6) : ink(row.kind === "value" ? 0.26 : 0.11);
          ctx.fillRect(xh, rt, Math.max(1, row.share * maxW), Math.max(1, rb - rt - (rb - rt > 3 ? 1 : 0)));
        }
        line(xa, xb, y(r.vah), ink(0.55));
        line(xa, xb, y(r.val), ink(0.55));
        line(xa, xb, y(r.poc), gold(0.95), 2);
        for (const which of ["vah", "val", "poc"]) near(xa, xb, y(r[which]), { kind: "rline", which, r });
      }

      // The last finished swing's three lines run on to the right edge.
      const done = lastDone(this.ranges);
      if (done) {
        const xb = edge(done.to);
        line(xb, W, y(done.vah), ink(0.42), 1, [5, 4]);
        line(xb, W, y(done.val), ink(0.42), 1, [5, 4]);
        line(xb, W, y(done.poc), gold(0.75), 1, [5, 4]);
        for (const which of ["vah", "val", "poc"]) near(xb, W, y(done[which]), { kind: "rline", which, r: done, rule: which === "poc" ? this.rule : null });
      }

      // The 0.618 to 0.66 retracement band of each live major leg, from the leg's start to the right edge,
      // fainter once price has traded into it; and the leg it measures, as a dotted line.
      for (const b of this.bands) {
        const xa = Math.max(0, edge(b.from)), top = y(b.top), bottom = y(b.bottom);
        if (top == null || bottom == null || xa >= W) continue;
        ctx.fillStyle = violet(b.touched ? 0.06 : 0.13);
        ctx.fillRect(xa, top, W - xa, Math.max(1, bottom - top));
        area(zones, xa, top - 3, W, bottom + 3, { kind: "fib", band: b });
        line(xa, W, top, violet(b.touched ? 0.25 : 0.5));
        line(xa, W, bottom, violet(b.touched ? 0.25 : 0.5));
        const ya = b.leg ? y(b.leg.base) : null, yb = b.leg ? y(b.leg.extreme) : null;
        if (ya != null && yb != null) {
          ctx.beginPath(); ctx.setLineDash([2, 4]); ctx.strokeStyle = violet(0.7); ctx.lineWidth = 1;
          ctx.moveTo(edge(b.leg.from) + half, ya); ctx.lineTo(edge(b.leg.to) + half, yb); ctx.stroke();
          ctx.setLineDash([]);
        }
      }
      this.hits = [...boxes, ...zones, ...lines];          // the tags are added on top of these by paintTicks

      ctx.restore();
    });
  }
  // Labelled ticks right of the last candle, where there is room for them. Levels at one price share a label.
  paintTicks(ctx, W, H, edge, y, ink, gold, violet) {
    const xl = edge(this.last + 1) + 6;
    this.hits = this.hits.filter(h => h.info.kind !== "tick");
    if (xl > W - 46) return;
    const rows = mergeTicks(this.ticks.map(t => ({ ...t, y: y(t.price) })).filter(t => t.y != null && t.y > 8 && t.y < H - 8));
    const ys = spread(rows.map(t => t.y), LABEL_GAP);
    ctx.font = LABEL_FONT; ctx.textBaseline = "middle"; ctx.setLineDash([]); ctx.lineJoin = "round";
    rows.forEach((t, i) => {
      const color = t.kind === "poc" ? gold(1) : t.kind === "fib" ? violet(1) : ink(t.kind === "edge" ? 0.75 : 0.92);
      ctx.strokeStyle = color; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(xl, Math.round(t.y) + 0.5); ctx.lineTo(xl + 12, Math.round(t.y) + 0.5);
      ctx.lineTo(xl + 16, Math.round(ys[i]) + 0.5); ctx.stroke();
      // A label wider than the room right of the candles is moved left to end at the pane's edge.
      const tx = Math.min(xl + 19, W - 4 - ctx.measureText(t.label).width);
      ctx.strokeStyle = `rgba(${this.colors.bg.join(",")},0.92)`; ctx.lineWidth = 6;
      ctx.strokeText(t.label, tx, ys[i]);
      ctx.fillStyle = color;
      ctx.fillText(t.label, tx, ys[i]);
      this.hits.push({ x0: Math.min(xl, tx) - 4, x1: tx + ctx.measureText(t.label).width + 6,
        y0: Math.min(t.y, ys[i]) - 8, y1: Math.max(t.y, ys[i]) + 8, info: { kind: "tick", tick: t, bands: this.bands } });
    });
  }
}
