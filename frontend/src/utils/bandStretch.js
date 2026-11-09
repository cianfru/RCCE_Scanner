// Band stretch (backend band_stretch.py, tradingview/reflex_band_stretch.pine): how far price sits from the weekly
// band, against how far the coin usually sits from it over two years. Context, not a signal; the engine does not
// read it. Its 1.6 line is the stretch-at-tops study's guide (docs/reviews/stretch-tops-study.md).

// The market's rows by day: { share, coins, above, median } from /api/market-history's stretch block.
export function stretchByDay(data) {
  const s = data?.stretch;
  if (!s?.rows?.length) return new Map();
  const i = Object.fromEntries(s.columns.map((c, k) => [c, k]));
  return new Map(s.rows.map(r => [r[i.day], {
    coins: r[i.coins], above: r[i.above], median: r[i.median], share: r[i.coins] ? r[i.above] / r[i.coins] : null,
  }]));
}
