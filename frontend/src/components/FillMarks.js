// Lightweight Charts v5 series primitive: one trader's fills on a coin chart, at the price they
// filled (marks from utils/traderBoard.fillMarks). Opens and adds are filled arrows in the side's
// colour (up for buying, down for selling; an open gets a ring), trims are smaller hollow circles,
// closes are crosses, and a flip is a diamond in the new side's colour.
import { markRadius } from "../utils/traderBoard.js";

export default class FillMarks {
  constructor(colors) {
    this.colors = colors;       // {long, short, ring}
    this.marks = [];
    this.hits = [];
    this.view = { zOrder: () => "top", renderer: () => ({ draw: target => this.draw(target) }) };
  }
  attached({ chart, series, requestUpdate }) { this.chart = chart; this.series = series; this.requestUpdate = requestUpdate; requestUpdate(); }
  detached() { this.chart = null; this.series = null; this.requestUpdate = null; }
  setMarks(marks, colors) {
    this.marks = marks || [];
    if (colors) this.colors = colors;
    this.requestUpdate?.();
  }
  updateAllViews() {}
  paneViews() { return [this.view]; }
  // The mark under a point (media pixels), or null.
  hitTest(x, y) {
    let best = null, bestD = Infinity;
    for (const h of this.hits) {
      const d = Math.hypot(h.x - x, h.y - y);
      if (d <= h.r + 5 && d < bestD) { best = h.mark; bestD = d; }
    }
    return best;
  }
  draw(target) {
    try { this.paint(target); } catch (e) { if (!/disposed/i.test(String(e?.message))) throw e; }
  }
  paint(target) {
    this.hits = [];
    if (!this.chart || !this.series || !this.marks.length) return;
    const ts = this.chart.timeScale();
    const maxUsd = Math.max(...this.marks.map(m => m.usd || 0));
    const c = this.colors;
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      ctx.save();
      for (const m of this.marks) {
        const x = ts.logicalToCoordinate(m.index);
        const y = m.px == null ? null : this.series.priceToCoordinate(m.px);
        if (x == null || y == null || !Number.isFinite(x) || !Number.isFinite(y) || x < -10 || x > mediaSize.width + 10) continue;
        const r = markRadius(m.usd, maxUsd, m.kind);
        const color = m.side === "long" ? c.long : c.short;
        ctx.lineJoin = "round";
        if (m.kind === "trim") {
          ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2);
          ctx.lineWidth = 1.6; ctx.strokeStyle = color; ctx.stroke();
        } else if (m.kind === "close") {
          const k = Math.max(3.5, r * 0.85);
          ctx.beginPath(); ctx.moveTo(x - k, y - k); ctx.lineTo(x + k, y + k); ctx.moveTo(x + k, y - k); ctx.lineTo(x - k, y + k);
          ctx.lineWidth = 3.5; ctx.strokeStyle = c.ring; ctx.stroke();
          ctx.lineWidth = 2; ctx.strokeStyle = color; ctx.stroke();
        } else if (m.kind === "flip") {
          const k = r + 1.5;
          ctx.beginPath(); ctx.moveTo(x, y - k); ctx.lineTo(x + k, y); ctx.lineTo(x, y + k); ctx.lineTo(x - k, y); ctx.closePath();
          ctx.fillStyle = color; ctx.fill(); ctx.lineWidth = 1.5; ctx.strokeStyle = c.ring; ctx.stroke();
        } else {
          // Arrow centred on the fill price, pointing the way the order traded.
          const h = r * 1.9, w = r * 1.15, dir = m.buy ? -1 : 1;
          const tipY = y + dir * h / 2;
          ctx.beginPath(); ctx.moveTo(x, tipY); ctx.lineTo(x + w, tipY - dir * h); ctx.lineTo(x - w, tipY - dir * h); ctx.closePath();
          ctx.fillStyle = color; ctx.fill();
          ctx.lineWidth = m.kind === "open" ? 2 : 1; ctx.strokeStyle = m.kind === "open" ? c.ring : c.edge || c.ring; ctx.stroke();
          if (m.kind === "open") { ctx.lineWidth = 1; ctx.strokeStyle = color; ctx.stroke(); }
        }
        this.hits.push({ x, y, r: Math.max(r, 5), mark: m });
      }
      ctx.restore();
    });
  }
}
