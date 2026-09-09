export const SCANNER_COLUMNS = [
  [null,             "#",       0],
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
