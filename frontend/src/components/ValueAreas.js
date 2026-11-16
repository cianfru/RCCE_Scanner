// Lightweight Charts v5 series primitive: the coin chart's Value layer (/api/auction).
// Per session (a day on 4H, a week on 1D): a band over its value area and a line at its point
// of control (POC). A dashed line runs on from a POC price has not traded back to, and the
// last finished session's band edges are carried forward. Left edge: volume by price of the
// sessions in view. Right of the last candle: labelled ticks (opens, prior extremes, the
// previous outer session's value area). What happened, drawn where it happened: no forecast.
import { placeSessions, ticks, composite, spread, mergeTicks } from "../utils/valueLayer.js";

const LABEL_FONT = "10px 'SF Mono', 'Fira Code', monospace";
const LABEL_GAP = 12;
const PROFILE_SHARE = 0.14;      // widest histogram bar, as a share of the pane's width
const PROFILE_MAX = 130;

export default class ValueAreas {
  constructor(colors) {
    this.colors = colors;        // {ink, poc, bg}: [r, g, b] each
    this.visible = false;
    this.placed = [];
    this.ticks = [];
    this.grid = null;
    this.last = 0;
    // Bands and lines sit behind the candles; the tick labels go on top so no line strikes through them.
    this.views = ["bottom", "top"].map(z => ({ zOrder: () => z, renderer: () => ({ draw: target => this.draw(target, z) }) }));
  }
  attached({ chart, series, requestUpdate }) { this.chart = chart; this.series = series; this.requestUpdate = requestUpdate; requestUpdate(); }
  detached() { this.chart = null; this.series = null; this.requestUpdate = null; }
  // body: the /api/auction answer (null clears); times: the chart's candle times (seconds).
  setData(body, times, tfSec, colors) {
    if (colors) this.colors = colors;
    this.placed = body && times?.length ? placeSessions(body.sessions, times, tfSec) : [];
    this.ticks = body ? ticks(body) : [];
    this.grid = body?.grid || null;
    this.last = times?.length ? times.length - 1 : 0;
    this.requestUpdate?.();
  }
  setVisible(v) { this.visible = v; this.requestUpdate?.(); }
  updateAllViews() {}
  paneViews() { return this.views; }
  // A paint queued while the chart is being torn down finds a disposed chart: skip it.
  draw(target, layer) {
    try { this.paint(target, layer); } catch (e) { if (!/disposed/i.test(String(e?.message))) throw e; }
  }
  paint(target, layer) {
    if (!this.visible || !this.chart || !this.series || !this.placed.length) return;
    const ts = this.chart.timeScale();
    const x0 = ts.logicalToCoordinate(0), x1 = ts.logicalToCoordinate(1);
    const range = ts.getVisibleLogicalRange();
    if (x0 == null || x1 == null || !range) return;
    const half = (x1 - x0) / 2;
    const edge = i => x0 + (x1 - x0) * i - half;            // the left edge of candle i
    const y = p => this.series.priceToCoordinate(p);
    const ink = a => `rgba(${this.colors.ink.join(",")},${a})`;
    const gold = a => `rgba(${this.colors.poc.join(",")},${a})`;

    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      const W = mediaSize.width, H = mediaSize.height;
      const line = (xa, xb, yy, color, width = 1, dash = null) => {
        if (yy == null || yy < -2 || yy > H + 2 || xb <= xa) return;
        ctx.beginPath(); ctx.setLineDash(dash || []); ctx.strokeStyle = color; ctx.lineWidth = width;
        const py = Math.round(yy) + (width % 2 ? 0.5 : 0);
        ctx.moveTo(xa, py); ctx.lineTo(xb, py); ctx.stroke();
      };
      ctx.save();
      if (layer === "top") { this.paintTicks(ctx, W, H, edge, y, ink, gold); ctx.restore(); return; }

      // Volume by price of the sessions in view, from the left edge.
      const prof = this.grid ? composite(this.placed, this.grid.rows, range.from, range.to) : null;
      if (prof) {
        const maxW = Math.min(PROFILE_MAX, W * PROFILE_SHARE);
        for (let r = 0; r < prof.v.length; r++) {
          if (!prof.v[r]) continue;
          const top = y(this.grid.low + (r + 1) * this.grid.step), bottom = y(this.grid.low + r * this.grid.step);
          if (top == null || bottom == null || bottom < 0 || top > H) continue;
          const h = Math.max(1, bottom - top - (bottom - top > 3 ? 1 : 0));
          ctx.fillStyle = r === prof.poc ? gold(0.55) : ink(r >= prof.lo && r <= prof.hi ? 0.2 : 0.09);
          ctx.fillRect(0, top, Math.max(1, prof.v[r] / prof.max * maxW), h);
        }
      }

      // Each session: its value area as a band, its POC as a line.
      for (const s of this.placed) {
        if (s.to < range.from - 1 || s.from > range.to + 1) continue;
        const xa = edge(s.from) + 1, xb = edge(s.to) - 1;
        const top = y(s.vah), bottom = y(s.val);
        if (top != null && bottom != null) {
          ctx.fillStyle = ink(s.live ? 0.045 : 0.07);
          ctx.fillRect(xa, top, xb - xa, bottom - top);
          line(xa, xb, top, ink(0.3));
          line(xa, xb, bottom, ink(0.3));
        }
        line(xa, xb, y(s.poc), gold(0.9), 2);
      }

      // The last finished session's band edges carried forward, and every POC not traded back to.
      const done = this.placed.filter(s => !s.live);
      const prev = done[done.length - 1];
      if (prev) {
        line(edge(prev.to), W, y(prev.vah), ink(0.38), 1, [5, 4]);
        line(edge(prev.to), W, y(prev.val), ink(0.38), 1, [5, 4]);
      }
      for (const s of done) {
        if (s.touched == null) line(edge(s.to), W, y(s.poc), gold(0.75), 1, [5, 4]);
      }

      ctx.restore();
    });
  }
  // Labelled ticks right of the last candle, where there is room for them. Levels at one price share a label.
  paintTicks(ctx, W, H, edge, y, ink, gold) {
    const xl = edge(this.last + 1) + 6;
    if (xl > W - 46) return;
    const rows = mergeTicks(this.ticks.map(t => ({ ...t, y: y(t.price) })).filter(t => t.y != null && t.y > 8 && t.y < H - 8));
    const ys = spread(rows.map(t => t.y), LABEL_GAP);
    ctx.font = LABEL_FONT; ctx.textBaseline = "middle"; ctx.setLineDash([]); ctx.lineJoin = "round";
    rows.forEach((t, i) => {
      const color = t.kind === "poc" ? gold(1) : ink(t.kind === "edge" ? 0.75 : 0.92);
      ctx.strokeStyle = color; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(xl, Math.round(t.y) + 0.5); ctx.lineTo(xl + 12, Math.round(t.y) + 0.5);
      ctx.lineTo(xl + 16, Math.round(ys[i]) + 0.5); ctx.stroke();
      // A label wider than the room right of the candles is moved left to end at the pane's edge.
      const tx = Math.min(xl + 19, W - 4 - ctx.measureText(t.label).width);
      ctx.strokeStyle = `rgba(${this.colors.bg.join(",")},0.92)`; ctx.lineWidth = 6;
      ctx.strokeText(t.label, tx, ys[i]);
      ctx.fillStyle = color;
      ctx.fillText(t.label, tx, ys[i]);
    });
  }
}
