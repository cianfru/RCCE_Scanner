export const SCANNER_COLUMNS = [
  [null,             "#",       480],   // row rank; hidden on phones so the signal fits on screen
  ["priority_score", "PRI",     0],     // composite ranking 0-100 — always visible
  ["symbol",         "SYMBOL",  0],     // includes price sub-label on desktop
  ["regime",         "REGIME",  0],
  [null,             "SIGNAL",  0],
  ["zscore",         "Z-SCORE", 480],
  [null,             "SPARK",   640],   // moved after Z-SCORE, hidden on small mobile
  [null,             "COND",    640],   // conditions met — entry quality
  ["heat",           "HEAT",    640],   // bar + phase sub-label
  [null,             "CVD",     768],   // net taker pressure
  [null,             "CONF",    768],   // multi-TF confluence
  [null,             "DIV",     900],
  [null,             "EXHAUST", 1024],  // state + ✓ when floor confirmed
  ["energy",         "ENERGY",  1024],
  [null,             "SM",      1200],  // HyperLens smart money consensus
  [null,             "OI",      1440],  // OI trend — wide monitors only
];

// Scanner grid fit (spec 4.2): minimum column widths in px, padding included, for the
// 12 / 10 / 8px cell-padding tiers, and the order columns leave in when the grid is narrow.
// REGIME carries the whole Regime/Signal pair; SIGNAL always travels with it. The cheap
// columns (OI, then #) go before the 8px tier; ranked columns then go 3 first, 12 last.
// PRI, SYMBOL and the pair are never dropped. `sort` names a sort key a column has only
// in the scanner (the tuple above stays as the landing uses it).
export const COLUMN_FIT = {
  '#':       { w: [45, 41, 37],    rank: 'cheap2' },
  PRI:       { w: [63, 59, 55] },
  SYMBOL:    { w: [150, 146, 142] },
  REGIME:    { w: [331, 327, 323] },
  SIGNAL:    { w: [0, 0, 0] },
  'Z-SCORE': { w: [150, 146, 142], rank: 12 },
  SPARK:     { w: [96, 92, 88],    rank: 11 },
  COND:      { w: [65, 61, 57],    rank: 10, sort: 'conditions' },
  HEAT:      { w: [79, 75, 71],    rank: 9 },
  CVD:       { w: [68, 64, 60],    rank: 7 },
  CONF:      { w: [75, 71, 67],    rank: 4 },
  DIV:       { w: [70, 66, 62],    rank: 6 },
  EXHAUST:   { w: [86, 82, 78],    rank: 5 },
  ENERGY:    { w: [76, 72, 68],    rank: 3 },
  SM:        { w: [74, 70, 66],    rank: 8 },
  OI:        { w: [86, 82, 78],    rank: 'cheap1' },
};
