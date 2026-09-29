// Live prices from the WebSocket over scan rows. A refreshed scan carries the
// price its rows were computed at; ticks after that are newer, and a price that
// has not moved 0.01% since it was last sent is not sent again, so the latest
// known tick is laid back over fresh rows. Returns the same array when nothing changes.
export function overlayPrices(rows, live) {
  if (!rows?.length || !live?.size) return rows;
  let changed = false;
  const next = rows.map(r => {
    const p = live.get(r.symbol);
    if (p === undefined || p === r.price) return r;
    changed = true;
    return { ...r, price: p };
  });
  return changed ? next : rows;
}

// Which symbols moved, and which way, between the last known prices and new ticks.
// Updates `known` in place. Symbols seen for the first time do not flash.
export function priceMoves(known, ticks) {
  const flashes = new Map();
  for (const [sym, price] of Object.entries(ticks || {})) {
    const old = known.get(sym);
    if (old !== undefined && price !== old) flashes.set(sym, price > old ? "up" : "down");
    known.set(sym, price);
  }
  return flashes;
}
