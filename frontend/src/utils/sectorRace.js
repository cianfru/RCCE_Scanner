// Shapes /api/sectors series for the race chart and the pocket matrix.

// Rebase the last `range` days to 100 at the window's first day.
export function rebase(values, range) {
  const vs = values.slice(-(range + 1));
  const first = vs.find(Number.isFinite);
  return first ? vs.map(v => (Number.isFinite(v) ? (100 * v) / first : null)) : vs.map(() => null);
}

// mode "rel": each group divided by BTC (100 = level with BTC); "abs": price, rebased.
export function raceLines(data, by, range, mode) {
  if (!data?.dates?.length) return { dates: [], btc: [], lines: [] };
  const dates = data.dates.slice(-(range + 1));
  const btc = rebase(data.btc, range);
  const lines = Object.entries(data.groups || {})
    .filter(([k]) => k.startsWith(`${by}:`))
    .map(([k, g]) => {
      const raw = rebase(g.index, range);
      const values = mode === "rel" ? raw.map((v, i) => (Number.isFinite(v) && btc[i] ? (100 * v) / btc[i] : null)) : raw;
      const last = [...values].reverse().find(Number.isFinite);
      return { name: k.slice(by.length + 1), n: g.n, coins: g.coins, values, last };
    })
    .filter(l => Number.isFinite(l.last));
  return { dates, btc, lines };
}

// Pocket matrix: sectors x ecosystems, each cell the pocket's move against BTC (%).
export function pocketGrid(data, range, { maxCols = 7 } = {}) {
  const cells = {};
  const btc = rebase(data?.btc || [], range);
  const bLast = btc[btc.length - 1];
  for (const [k, g] of Object.entries(data?.groups || {})) {
    if (!k.startsWith("pocket:")) continue;
    const [sector, eco] = k.slice(7).split("|");
    const v = rebase(g.index, range);
    const last = v[v.length - 1];
    if (!Number.isFinite(last) || !bLast) continue;
    cells[`${sector}|${eco}`] = { sector, eco, n: g.n, coins: g.coins, rel: (100 * last) / bLast - 100 };
  }
  const count = key => Object.values(cells).filter(c => c[key] && true).reduce((m, c) => ((m[c[key]] = (m[c[key]] || 0) + c.n), m), {});
  const cols = Object.entries(count("eco")).sort((a, b) => b[1] - a[1]).slice(0, maxCols).map(([e]) => e);
  const rows = Object.entries(count("sector")).filter(([s]) => cols.some(e => cells[`${s}|${e}`])).sort((a, b) => b[1] - a[1]).map(([s]) => s);
  return { rows, cols, cells };
}
