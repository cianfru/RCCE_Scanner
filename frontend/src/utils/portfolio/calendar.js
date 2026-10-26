// The P&L calendar (Portfolio v2, B6): realised P&L per UTC day, from the fills and funding on hand:
// Σ(closedPnl − fee) + Σ funding. Open P&L is not included.
import { dayKey } from "./format.js";

export function dailyPnl(fills, funding) {
  const days = new Map();
  const get = k => days.get(k) || (days.set(k, { net: 0, closed: 0, fees: 0, funding: 0, closes: 0 }), days.get(k));
  for (const f of fills || []) {
    const d = get(dayKey(f.time));
    const pnl = parseFloat(f.closedPnl) || 0, fee = parseFloat(f.fee) || 0;
    d.closed += pnl; d.fees += fee; d.net += pnl - fee;
    if (/Close|>/.test(String(f.dir || ""))) d.closes += 1;
  }
  for (const f of funding || []) {
    const d = get(dayKey(f.time));
    const v = parseFloat(f.delta?.usdc) || 0;
    d.funding += v; d.net += v;
  }
  return days;
}

// Five colour steps of |day| against the month's 90th percentile (1..5; 0 for a flat day).
export function steps(values) {
  const abs = values.map(v => Math.abs(v)).filter(v => v > 0).sort((a, b) => a - b);
  const p90 = abs.length ? abs[Math.min(abs.length - 1, Math.floor(0.9 * (abs.length - 1)))] : 0;
  return v => (!v || !p90 ? 0 : Math.max(1, Math.min(5, Math.ceil((Math.abs(v) / p90) * 5))));
}

// Weeks of one month (UTC), Monday first: [{days: [{key, day, inMonth}], week: Σ net}].
export function monthGrid(y, m, days) {
  const first = Date.UTC(y, m, 1);
  const startDow = (new Date(first).getUTCDay() + 6) % 7;     // Monday = 0
  const n = new Date(Date.UTC(y, m + 1, 0)).getUTCDate();
  const cells = [];
  for (let i = 0; i < startDow; i++) cells.push(null);
  for (let d = 1; d <= n; d++) cells.push(new Date(Date.UTC(y, m, d)).toISOString().slice(0, 10));
  while (cells.length % 7) cells.push(null);
  const weeks = [];
  for (let i = 0; i < cells.length; i += 7) {
    const row = cells.slice(i, i + 7);
    weeks.push({ days: row, week: row.reduce((s, k) => s + (k && days.get(k) ? days.get(k).net : 0), 0) });
  }
  return weeks;
}
