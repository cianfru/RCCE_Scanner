// Pure helpers and copy for the market history page's Derive drawer (/api/market-history/derive): how Derive's
// Smart options wallets were positioned at each daily close, as ranked at the time and as ranked today, and the
// premium they paid on new puts. Exploration, not a study: context, not a signal.

const DAY_MS = 86_400_000;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export const COINS = [{ key: "BTC", label: "BTC" }, { key: "ETH", label: "ETH" }, { key: "ALL", label: "All coins" }];
export const RANGES = [{ key: "1y", label: "1Y", days: 365 }, { key: "all", label: "All", days: null }];

const dayDate = day => { const d = new Date(day * DAY_MS); return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`; };

// The coin whose price a view draws: ETH for ETH, BTC for BTC and for all coins together.
export const priceCoin = coin => (coin === "ETH" ? "ETH" : "BTC");

// One coin's rows, oldest first: { day, price, pitL, pitS, nowL, nowS, pitPuts, nowPuts }.
export function deriveRows(data, coin) {
  if (!data?.rows?.length) return [];
  const ix = Object.fromEntries(data.columns.map((c, i) => [c, i]));
  const p = ix[priceCoin(coin) === "ETH" ? "eth" : "btc"];
  const at = f => ix[`${coin}.${f}`];
  const k = { pitL: at("pit_long"), pitS: at("pit_short"), nowL: at("now_long"), nowS: at("now_short"),
    pitPuts: at("pit_puts"), nowPuts: at("now_puts") };
  if (Object.values(k).some(i => i == null)) return [];
  return data.rows.map(r => ({ day: r[0], price: r[p] || null, pitL: r[k.pitL], pitS: r[k.pitS], nowL: r[k.nowL],
    nowS: r[k.nowS], pitPuts: r[k.pitPuts], nowPuts: r[k.nowPuts] }));
}

export function inRange(rows, key) {
  const r = RANGES.find(x => x.key === key);
  if (!r?.days || !rows.length) return rows;
  const from = rows[rows.length - 1].day - r.days;
  return rows.filter(x => x.day >= from);
}

// Weeks from Monday (day 4 since 1970 was a Monday): [{ day: the week's Monday, sum, days }], oldest first.
export function weekly(rows, field) {
  const out = [];
  for (const r of rows) {
    const monday = r.day - ((r.day + 3) % 7);
    const last = out[out.length - 1];
    if (last && last.day === monday) { last.sum += r[field] || 0; last.days++; } else out.push({ day: monday, sum: r[field] || 0, days: 1 });
  }
  return out;
}

// The tops drawn for a coin (BTC's for all coins), inside [d0, d1].
export const topsIn = (data, coin, d0, d1) => (data?.tops?.[priceCoin(coin)] || []).filter(d => d >= d0 && d <= d1);

// The bar scale for weekly puts: the 95th percentile of the weeks shown (taller weeks are notched), at least $10k.
export function putScale(weeks) {
  const xs = weeks.map(w => w.sum).filter(v => v > 0).sort((a, b) => a - b);
  const p95 = xs.length ? xs[Math.min(xs.length - 1, Math.ceil(0.95 * xs.length) - 1)] : 0;
  return Math.max(10_000, p95) * 1.08;
}

export const money = v => {
  if (v == null) return "—";
  const a = Math.abs(v);
  return a >= 1e6 ? `$${(v / 1e6).toFixed(1)}M` : a >= 1e3 ? `$${Math.round(v / 1e3)}k` : `$${Math.round(v)}`;
};

// ---------------------------------------------------------------- copy

export const DCOPY = {
  open: "Derive options",
  title: "Derive options: Smart wallets",
  close: "Close",
  loading: "Loading Derive history…",
  unavailable: "Derive history is unavailable right now.",
  coinLabel: "Coin",
  rangeLabel: "Range",
  sub: (through, n) => `Derive's best options traders against the price, data to ${dayDate(through)}${n ? ` · ${n} Smart wallets today` : ""}.`,
  panel: {
    price: coin => `${priceCoin(coin)} · tops marked`,
    pit: "Smart wallets, ranked at the time",
    now: "Today's Smart wallets, looking back",
    puts: "New puts bought per week, ranked at the time",
  },
  long: "net long",
  short: "net short",
  readout: {
    price: coin => priceCoin(coin),
    pit: "Ranked at the time",
    now: "Today's, looking back",
    puts: "New puts that week",
    counts: (l, s) => `${l} long · ${s} short`,
  },
  // Popovers: each 90 words or fewer.
  pop: {
    aboutTitle: "Derive options",
    about: () => ["Built from Cowboy's records of every Derive options trade since December 2023, with the same wallets and ranking as its app. Did Smart wallets turn short or buy puts as the market rolled over? The middle panels show who was short, ranked as they stood at the time and as they rank today; the bottom one, their new puts.",
      "Exploration, not a study: context, not a signal."],
    priceTitle: "Price and tops",
    price: () => ["Derive's daily index close (before 31 Oct 2024, the next day's 08:00 UTC settlement or the day's average index). Dashed lines: tops, the highest close within 30 days either side that was followed by a fall of 15% or more within 90 days. They are found with the closes after them, so they mark where tops were."],
    pitTitle: "Ranked at the time",
    pit: () => ["Derive's best directional options wallets as they ranked at each close, from what was known then: Cowboy's ranking replayed day by day, market makers, income sellers and hedgers left out. Green, up from zero: wallets whose open options delta was net long by $1,000 or more. Red, down: net short."],
    nowTitle: "Today's Smart wallets",
    now: n => [`The same count for ${n ? `today's ${n}` : "today's"} Smart wallets, each in its past. They rank on all their trades so far, including the falls they caught, so looking back they read shorter before tops than the wallets that ranked best at the time.`],
    putsTitle: "New puts",
    puts: () => ["Premium paid on new long puts (a wallet's long put position growing that day), summed per week, by the Smart wallets as ranked at the time. Buying back sold puts is left out. Weeks taller than the chart are notched; the readout has the amount."],
  },
};
