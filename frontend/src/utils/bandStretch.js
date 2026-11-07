// Band stretch (backend band_stretch.py, tradingview/reflex_band_stretch.pine): how far price sits from the weekly
// band, against how far the coin usually sits from it over two years. Context, not a signal; the engine does not
// read it. The 1.6 line is the stretch-at-tops study's guide (docs/reviews/stretch-tops-study.md).

export const STRETCH_LINE = 1.6;

const signed = (v, d = 2) => `${v >= 0 ? "+" : ""}${v.toFixed(d)}`;

// The coin page's reading: band z and the distance from the band mid, or null when not available.
export function stretchReading(r) {
  if (!r?.available || r.a == null) return null;
  return {
    value: signed(r.a),
    pct: r.pct == null ? null : `${signed(r.pct, 0)}%`,
    tone: r.a >= STRETCH_LINE ? "hot" : r.a <= -STRETCH_LINE ? "cold" : null,
  };
}

// The market's rows by day: { share, coins, above, median } from /api/market-history's stretch block.
export function stretchByDay(data) {
  const s = data?.stretch;
  if (!s?.rows?.length) return new Map();
  const i = Object.fromEntries(s.columns.map((c, k) => [c, k]));
  return new Map(s.rows.map(r => [r[i.day], {
    coins: r[i.coins], above: r[i.above], median: r[i.median], share: r[i.coins] ? r[i.above] / r[i.coins] : null,
  }]));
}

export const SCOPY = {
  label: "Band stretch",
  help: "Band stretch: how far price sits from the weekly band (20-week SMA and 21-week EMA), against how far this coin usually sits from it over two years. In the stretch study, 1.6 or more came in the two weeks before about 6 in 10 tops on coins it was not set on. Context, not a signal.",
  marketHelp: "Coins stretched: the share of the market history's coins at band stretch 1.6 or more, each read against its own usual distance from its weekly band. Context, not a signal.",
};
