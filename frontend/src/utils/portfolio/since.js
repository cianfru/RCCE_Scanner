// "Since" (Portfolio v2, B2): what changed since this browser's last visit, kept on this device only.
// Two slots under reflex.pf.snap.v1.<address>: {base, cur}. On load, a `cur` older than 30 minutes
// becomes the baseline; `cur` is rewritten every 60 s while the page is visible and when it is hidden
// or left. Every storage read and write is guarded: blocked storage behaves as a first visit.
import { EXIT_SIGNALS, LONG_ENTRIES, SHORT_ENTRIES } from "./checks.js";

export const SNAP_VERSION = 1;
export const BASE_AFTER_MS = 30 * 60 * 1000;
export const snapKey = addr => `reflex.pf.snap.v1.${String(addr || "").toLowerCase()}`;

export function readSlots(storage, addr, now = Date.now()) {
  try {
    const raw = storage?.getItem(snapKey(addr));
    const s = raw ? JSON.parse(raw) : {};
    let base = s?.base?.v === SNAP_VERSION ? s.base : null;
    const cur = s?.cur?.v === SNAP_VERSION ? s.cur : null;
    if (cur && now - cur.t > BASE_AFTER_MS) base = cur;
    return { base, cur, ok: true };
  } catch {
    return { base: null, cur: null, ok: false };
  }
}

export function writeCurrent(storage, addr, base, snap) {
  try {
    storage?.setItem(snapKey(addr), JSON.stringify({ base: base || null, cur: snap }));
    return true;
  } catch {
    return false;
  }
}

// rows: board rows (checks.buildRow); t in ms.
export function buildSnapshot({ t, equity, upnl, lastFillT, rows }) {
  const coins = {};
  for (const r of rows || []) {
    const c = r.ctx;
    const tr = c?.traders;
    coins[r.coin] = {
      side: r.side, szi: r.szi, upnl: round(r.upnl, 2), mark: r.mark,
      liqPct: r.dist ? round(r.dist.pct, 2) : null, liqAtr: r.dist?.atr != null ? round(r.dist.atr, 2) : null,
      h4: c?.h4?.signal ?? null, d1: c?.d1?.signal ?? null, reg4h: c?.h4?.regime ?? null, heat: c?.h4?.heat ?? null,
      band: c?.band?.state ?? null, tl: tr?.long?.n ?? null, ts: tr?.short?.n ?? null,
    };
  }
  return { v: SNAP_VERSION, t, equity: round(equity, 2), upnl: round(upnl, 2), lastFillT: lastFillT ?? null, coins };
}
const round = (v, d) => (v == null || !Number.isFinite(v) ? null : Math.round(v * 10 ** d) / 10 ** d);

// Against the side: an exit or a short entry on a long, a long entry on a short.
export const signalAgainst = (sig, side) => (side === "long" ? EXIT_SIGNALS.has(sig) || SHORT_ENTRIES.has(sig) : LONG_ENTRIES.has(sig));
const crossed = (a, b, level) => a != null && b != null && (a < level) !== (b < level);

// Change cells, most important first (B2's ranking). base, cur: snapshots; trips: closed round trips
// (fillTrips.roundTrips().closed) for the "Closed ... $" cells.
export function sinceChanges(base, cur, { trips = [] } = {}) {
  if (!base || !cur) return [];
  const out = [];
  const add = (rank, sub, cell) => out.push({ rank, sub, ...cell });
  const bc = base.coins || {}, cc = cur.coins || {};
  for (const [coin, c] of Object.entries(cc)) {
    const b = bc[coin];
    if (!b || b.side !== c.side) add(1, 0, { kind: "trip", coin, opened: true, side: c.side });
  }
  for (const [coin, b] of Object.entries(bc)) {
    const c = cc[coin];
    if (c && c.side === b.side) continue;
    const trip = trips.find(t => t.coin === coin && t.closedAt * 1000 > base.t);
    add(1, 0, { kind: "trip", coin, opened: false, side: b.side, pnl: trip ? trip.pnl : null });
  }
  for (const [coin, c] of Object.entries(cc)) {
    const b = bc[coin];
    if (!b || b.side !== c.side) continue;
    const nowRed = c.liqAtr != null ? c.liqAtr < 1.5 : c.liqPct != null && c.liqPct < 15;
    const wasRed = b.liqAtr != null ? b.liqAtr < 1.5 : b.liqPct != null && b.liqPct < 15;
    if (c.liqPct != null && b.liqPct != null && (b.liqPct - c.liqPct >= 5 || (nowRed && !wasRed)))
      add(2, -(b.liqPct - c.liqPct), { kind: "liq", coin, from: b.liqPct, to: c.liqPct, red: nowRed });
    for (const tf of ["h4", "d1"]) {
      if (c[tf] && b[tf] && c[tf] !== b[tf]) {
        const against = signalAgainst(c[tf], c.side);
        add(3, against ? 0 : 1, { kind: "signal", coin, tf, from: b[tf], to: c[tf], against });
      }
    }
    if (c.reg4h && b.reg4h && c.reg4h !== b.reg4h) add(4, 0, { kind: "regime", coin, from: b.reg4h, to: c.reg4h });
    if (c.band && b.band && c.band !== b.band) add(5, 0, { kind: "band", coin, from: b.band, to: c.band });
    if (crossed(b.heat, c.heat, 85) || crossed(b.heat, c.heat, 95)) add(6, 0, { kind: "heat", coin, from: b.heat, to: c.heat });
    const mine = c.side === "long" ? "tl" : "ts";
    const holders = (c.tl ?? 0) + (c.ts ?? 0);
    if (c[mine] != null && b[mine] != null && Math.abs(c[mine] - b[mine]) >= 2 && holders >= 5)
      add(7, 0, { kind: "traders", coin, from: [b.tl, b.ts], to: [c.tl, c.ts], side: c.side });
    if (c.mark && b.mark) {
      const ch = (c.mark / b.mark - 1) * 100;
      if (Math.abs(ch) >= 5) add(8, -Math.abs(ch), { kind: "price", coin, change: ch });
    }
  }
  return out.sort((p, q) => p.rank - q.rank || p.sub - q.sub || String(p.coin).localeCompare(String(q.coin)));
}

// The first cell's line: P&L since the baseline (closed P&L net of fees, funding, and the change in
// open P&L) and the fills since.
export function sinceSummary(base, { fills = [], funding = [], upnl = 0 } = {}) {
  if (!base) return null;
  const after = fills.filter(f => f.time > base.t);
  const realised = after.reduce((s, f) => s + (parseFloat(f.closedPnl) || 0) - (parseFloat(f.fee) || 0), 0);
  const fund = funding.filter(f => f.time > base.t).reduce((s, f) => s + (parseFloat(f.delta?.usdc) || 0), 0);
  const open = base.upnl != null ? upnl - base.upnl : 0;
  return { t: base.t, pnl: realised + fund + open, fills: after.length };
}
