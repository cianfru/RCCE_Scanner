// Hyperliquid's per-IP request weight (docs: "REST requests share an aggregated weight limit of 1200
// per minute"; /exchange requests count against the same limit). The Portfolio page counts what it
// reads, so its history reads (30 days of fills and funding) wait while the last minute is busy and a
// reload plus a close always fit under the limit.
//
// Weights from the docs: clearinghouseState, spotClearinghouseState, allMids 2; every other info
// request 20; userFills, userFillsByTime and userFunding add 1 per 20 items returned, candleSnapshot
// 1 per 60.
export const LIMIT = 1200;
// History pages are sent only while the last minute's total, with the page, stays at or under this.
export const HISTORY_CAP = 420;

const LIGHT = new Set(["clearinghouseState", "spotClearinghouseState", "allMids"]);
const PER_20 = new Set(["userFills", "userFillsByTime", "userFunding"]);

export function weightOf(type, items = 0) {
  if (LIGHT.has(type)) return 2;
  if (PER_20.has(type)) return 20 + Math.floor(Math.max(0, items) / 20);
  if (type === "candleSnapshot") return 20 + Math.floor(Math.max(0, items) / 60);
  return 20;
}

// A sliding one-minute total of what this tab has sent.
export class Meter {
  constructor(windowMs = 60_000) { this.windowMs = windowMs; this.log = []; }
  add(w, t = Date.now()) { if (w > 0) this.log.push([t, w]); return w; }
  spent(t = Date.now()) {
    const from = t - this.windowMs;
    this.log = this.log.filter(([at]) => at > from);
    return this.log.reduce((s, [at, w]) => s + (at <= t ? w : 0), 0);
  }
  allows(w, cap = HISTORY_CAP, t = Date.now()) { return this.spent(t) + w <= cap; }
}

// The page's meter: the feeds, the funding-rate reads and the position chart's candles all count here.
export const meter = new Meter();
