// The checks row, the rail's end block and the board's order (Portfolio v2, B3 and B4).
// Every rule is per position; a check's count is the positions it hits. Facts only: nothing here
// grades a position, it says which of a few plain conditions hold.
export const EXIT_SIGNALS = new Set(["TRIM", "TRIM_HARD", "RISK_OFF", "NO_LONG"]);
export const LONG_ENTRIES = new Set(["STRONG_LONG", "LIGHT_LONG", "ACCUMULATE", "REVIVAL_SEED", "REVIVAL_SEED_CONFIRMED"]);
export const SHORT_ENTRIES = new Set(["STRONG_SHORT", "LIGHT_SHORT"]);

export const CHECK_KEYS = ["exit", "d1against", "underband", "nostop", "stoppastliq", "liq2atr", "liqaboveband", "tradersleft"];
export const URL_KEYS = { exit: "exit", d1against: "d1against", underband: "underband", nostop: "nostop", stoppastliq: "stoppastliq", liq2atr: "liq2atr", liqaboveband: "liqband", tradersleft: "tradersleft" };
export const LIQ_FACTS = new Set(["stoppastliq", "liq2atr"]);

const closingSide = isLong => (isLong ? "A" : "B");
const n = v => { const x = typeof v === "string" ? parseFloat(v) : v; return Number.isFinite(x) ? x : null; };

// A stop-loss: a stop trigger on the closing side that is reduce-only or the position's own TP/SL.
// Any other stop trigger (a stop entry, say) is just a stop. isLong null: no position, never a stop-loss.
export const isStopLoss = (o, isLong) => isLong != null && !!o?.isTrigger && String(o.orderType || "").startsWith("Stop")
  && o.side === closingSide(isLong) && !!(o.reduceOnly || o.isPositionTpsl);
export const isTakeProfit = o => !!o?.isTrigger && String(o.orderType || "").startsWith("Take Profit");

// One coin's open orders by kind, for the Orders tab: {tp, sl, stop, limit}.
export function orderKinds(list, isLong) {
  const out = { tp: 0, sl: 0, stop: 0, limit: 0 };
  for (const o of list || []) {
    if (isTakeProfit(o)) out.tp += 1;
    else if (isStopLoss(o, isLong)) out.sl += 1;
    else if (o.isTrigger) out.stop += 1;
    else out.limit += 1;
  }
  return out;
}

// Orders on one position's coin, by kind. Stops: reduce-only (or position TP/SL) stop triggers on the
// closing side. TPs: take-profit triggers on the closing side, and reduce-only limits on the closing
// side past the mark in the position's favour (a take-profit ladder placed as limits). Nearest first.
export function ordersFor(pos, orders) {
  const mine = (orders || []).filter(o => o.coin === pos.coin);
  const side = closingSide(pos.isLong);
  const trig = o => n(o.triggerPx) ?? n(o.limitPx);
  const dist = v => Math.abs(v - pos.mark);
  const stops = mine.filter(o => isStopLoss(o, pos.isLong))
    .map(o => ({ px: trig(o), o })).filter(s => s.px != null).sort((a, b) => dist(a.px) - dist(b.px));
  const tpTrig = mine.filter(o => o.isTrigger && String(o.orderType || "").startsWith("Take Profit") && o.side === side)
    .map(o => ({ px: trig(o), o }));
  const tpLimits = mine.filter(o => !o.isTrigger && o.reduceOnly && o.side === side)
    .map(o => ({ px: n(o.limitPx), o })).filter(t => t.px != null && (pos.isLong ? t.px > pos.mark : t.px < pos.mark));
  const tps = tpTrig.concat(tpLimits).filter(t => t.px != null).sort((a, b) => dist(a.px) - dist(b.px));
  return { all: mine, stops, tps };
}

// Mark to liquidation, in % of the mark and in daily ATRs. null without a liquidation price.
export function liqDistance(pos, atr) {
  if (!pos.liq || !pos.mark) return null;
  const gap = Math.abs(pos.mark - pos.liq);
  return { pct: (gap / pos.mark) * 100, atr: atr > 0 ? gap / atr : null };
}
// One scale for ranking: ATRs, or % / 10 where there is no ATR (1.5 ATR ranks with 15%).
export const distKey = d => (d == null ? Infinity : d.atr != null ? d.atr : d.pct / 10);
export const distRed = d => d != null && (d.atr != null ? d.atr < 1.5 : d.pct < 15);
export function distTone(d) {
  if (d == null) return "text3";
  if (d.atr != null) return d.atr < 1.5 ? "red" : d.atr < 3 ? "text1" : "text2";
  return d.pct < 15 ? "red" : d.pct < 25 ? "text1" : "text2";
}

// ctx: the coin's /api/portfolio/context entry; ordersRead: the open orders of this position's venue were read.
export function positionChecks(pos, ctx, { stops = [], ordersRead = true } = {}) {
  const hit = new Set();
  const cov = ctx?.covered ? ctx : null;
  const s4 = cov?.h4?.signal, s1 = cov?.d1?.signal;
  if (pos.isLong && (EXIT_SIGNALS.has(s4) || EXIT_SIGNALS.has(s1))) hit.add("exit");
  if (s1 && (pos.isLong ? SHORT_ENTRIES.has(s1) : LONG_ENTRIES.has(s1))) hit.add("d1against");
  if (pos.isLong && cov?.band?.state === "closed_under") hit.add("underband");
  if (ordersRead && stops.length === 0) hit.add("nostop");
  const stop = stops[0]?.px;
  if (pos.liq && stop != null && (pos.isLong ? stop < pos.liq : stop > pos.liq)) hit.add("stoppastliq");
  const d = liqDistance(pos, cov?.atr_1d);
  if (d && (d.atr != null ? d.atr < 2 : d.pct < 15)) hit.add("liq2atr");
  if (pos.isLong && pos.liq && cov?.band?.hi != null && pos.liq > cov.band.hi) hit.add("liqaboveband");
  const t = cov?.traders?.[pos.side];
  if (t && t.n_day_ago != null && t.n_day_ago >= 5 && t.n_day_ago - t.n >= 2) hit.add("tradersleft");
  return hit;
}

// The rail's one flag: Stop past liq > no stop > Liq above band > Under band; the rest as "+n".
// quietNoStop: "no stop" holds on at least half the rows, so the checks row's count says it once
// and the rows leave it out (a column of the same words would bury the rare flags).
const FLAG_ORDER = ["stoppastliq", "nostop", "liqaboveband", "underband"];
export function flagsOf(checks, { quietNoStop = false } = {}) {
  const list = FLAG_ORDER.filter(k => checks.has(k) && !(quietNoStop && k === "nostop"));
  return { first: list[0] || null, more: list.slice(1) };
}
export const quietNoStop = (counts, n) => n > 0 && (counts?.nostop || 0) >= n / 2;

// Funding carry per day at the current hourly rate (Hyperliquid's metaAndAssetCtxs): negative is
// paid. A positive rate means longs pay shorts. Shown on a row from 0.1% of the notional a day.
export const CARRY_MIN = 0.001;
export const carryPerDay = (pos, rate) => (Number.isFinite(rate) && pos?.value > 0 ? -(pos.isLong ? 1 : -1) * rate * pos.value * 24 : null);
export const carryShown = (pos, rate) => {
  const c = carryPerDay(pos, rate);
  return c != null && Math.abs(c) >= CARRY_MIN * pos.value ? c : null;
};

// The checks that read the scanner's context: unknown (not zero) while that context is missing.
export const CTX_CHECKS = new Set(["exit", "d1against", "underband", "liqaboveband", "tradersleft"]);

// Everything a board row needs, from one position, its context and the venue's orders.
export function buildRow(pos, ctx, orders, { ordersRead = true } = {}) {
  // ordersRead: this venue's open orders were read (main always; xyz only when its read answered).
  const o = ordersFor(pos, orders);
  const read = !!ordersRead;
  const cov = ctx?.covered ? ctx : null;
  const dist = liqDistance(pos, cov?.atr_1d);
  const checks = positionChecks(pos, ctx, { stops: o.stops, ordersRead: read });
  return { ...pos, ctx: cov, covered: !!cov, orders: o.all, stops: o.stops, tps: o.tps, ordersRead: read, dist, checks,
    liqFact: [...checks].some(k => LIQ_FACTS.has(k)) };
}

export function countChecks(rows) {
  const out = Object.fromEntries(CHECK_KEYS.map(k => [k, 0]));
  for (const r of rows || []) for (const k of r.checks) out[k] += 1;
  return out;
}

// Closest (default): rows with a liquidation fact first, then by checks hit, then nearest liquidation.
export function sortRows(rows, sort = "closest") {
  const list = [...(rows || [])];
  if (sort === "size") return list.sort((a, b) => b.value - a.value);
  if (sort === "pnl") return list.sort((a, b) => b.upnl - a.upnl);
  return list.sort((a, b) => (b.liqFact - a.liqFact) || (b.checks.size - a.checks.size) || (distKey(a.dist) - distKey(b.dist)) || (b.value - a.value));
}

// Rows passing any of the selected checks (OR); none selected: all.
export const filterRows = (rows, selected) => (!selected?.size ? rows : rows.filter(r => [...selected].some(k => r.checks.has(k))));

// The position nearest its liquidation (ATR distance, % where there is no ATR) and the next ones.
export function nearestLiq(rows, k = 3) {
  return (rows || []).filter(r => r.dist).sort((a, b) => distKey(a.dist) - distKey(b.dist)).slice(0, k);
}

// The scanner's signal against the position: "with", "against" or "none" (no direction).
export function alignment(signal, isLong) {
  if (LONG_ENTRIES.has(signal)) return isLong ? "with" : "against";
  if (SHORT_ENTRIES.has(signal)) return isLong ? "against" : "with";
  if (EXIT_SIGNALS.has(signal)) return isLong ? "against" : "with";
  return "none";
}

// The REFLEX cell: shares of open notional with / against / no signal / not covered, on one timeframe.
export function reflexShares(rows, tf = "4h") {
  const out = { with: 0, against: 0, none: 0, uncovered: 0, total: 0 };
  for (const r of rows || []) {
    out.total += r.value;
    const sig = r.ctx?.[tf === "1d" ? "d1" : "h4"]?.signal;
    if (!r.covered || !sig) { out.uncovered += r.value; continue; }
    out[alignment(sig, r.isLong)] += r.value;
  }
  return out;
}
