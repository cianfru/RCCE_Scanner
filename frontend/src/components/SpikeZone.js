// Lightweight Charts v5 series primitive: where past spikes bottomed, placed from the anchor
// bar (the first bar after the spike's run, known at the time). History, not a forecast.
export default class SpikeZone {
  constructor({ anchorIndex, anchorClose, zone, colors }) {
    this.anchorIndex = anchorIndex;
    this.anchorClose = anchorClose;
    this.zone = zone;
    this.colors = colors;
    this.view = { zOrder: () => "bottom", renderer: () => ({ draw: target => this.draw(target) }) };
  }
  attached({ chart, series, requestUpdate }) { this.chart = chart; this.series = series; requestUpdate(); }
  detached() { this.chart = null; this.series = null; }
  updateAllViews() {}
  paneViews() { return [this.view]; }
  draw(target) {
    if (!this.chart || !this.series || !this.zone) return;
    const ts = this.chart.timeScale();
    const z = this.zone;
    const xa = ts.logicalToCoordinate(this.anchorIndex);
    const x1 = ts.logicalToCoordinate(this.anchorIndex + z.from_bar);
    const x2 = ts.logicalToCoordinate(this.anchorIndex + z.to_bar);
    const xm = ts.logicalToCoordinate(this.anchorIndex + z.median_bar);
    const ya = this.series.priceToCoordinate(this.anchorClose);
    const top = this.series.priceToCoordinate(z.top);
    const bottom = this.series.priceToCoordinate(z.bottom);
    const ym = this.series.priceToCoordinate(z.median_price);
    if ([xa, x1, x2, xm, ya, top, bottom, ym].some(v => v == null || !Number.isFinite(v))) return;
    const c = this.colors;
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      if (x2 < 0 || x1 > mediaSize.width) return;
      ctx.save();
      ctx.fillStyle = c.fill; ctx.fillRect(x1, top, x2 - x1, bottom - top);
      ctx.setLineDash([4, 3]); ctx.strokeStyle = c.line; ctx.lineWidth = 1;
      ctx.strokeRect(x1 + 0.5, top + 0.5, x2 - x1 - 1, bottom - top - 1);
      // From the anchor close to the median low, the typical way down.
      ctx.beginPath(); ctx.moveTo(xa, ya); ctx.lineTo(xm, ym); ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = c.line; ctx.beginPath(); ctx.arc(xm, ym, 3.5, 0, Math.PI * 2); ctx.fill();
      // Label inside the box, at its bottom edge, clear of the candles above.
      ctx.font = "600 12px sans-serif"; ctx.fillStyle = c.text;
      let label = "Where past spikes bottomed";
      if (ctx.measureText(label).width > x2 - x1 - 12) label = "Past spike lows";
      const lx = Math.max(4, Math.min(mediaSize.width - ctx.measureText(label).width - 4, x1 + 6));
      ctx.fillText(label, lx, Math.min(mediaSize.height - 4, bottom - 6));
      ctx.restore();
    });
  }
}
