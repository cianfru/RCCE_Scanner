// The coin chart's layers, as its Layers menu lists them: three groups of switches, any number on at once.
// Pure: BMSBChart holds the switches, ChartLayersMenu draws these.

export const LAYER_LABELS = {
  profiles: "Swing profiles", levels: "Levels", zone: "Pullback zone", opens: "Opens, prior highs and lows",
  averages: "Averages", trend: "Trend line", ribbon: "Ribbon", patterns: "Patterns",
  entries: "Trader entries", wallets: "Wallet levels",
};

export const LAYER_GROUPS = [
  { key: "price", label: "Price", items: ["profiles", "levels", "zone", "opens"] },
  { key: "trend", label: "Trend", items: ["averages", "trend", "ribbon", "patterns"] },
  { key: "traders", label: "Traders", items: ["entries", "wallets"] },
];

// The layers one answer of /api/auction serves: read once when any of them is on.
export const AUCTION_LAYERS = ["profiles", "levels", "zone", "opens"];

// The layers a timeframe offers: the trend line and the ribbon are computed on 4H and 1D, patterns on 1D.
export function offered(key, tf) {
  if (key === "trend" || key === "ribbon") return tf !== "1h";
  if (key === "patterns") return tf === "1d";
  return true;
}

// The menu: [{key, label, items: [{key, label, on, note}]}]. on: {layer: boolean}; notes: {layer: text} for a
// layer that is on with nothing to draw yet ("Loading…"); labels: {layer: text} to replace a layer's name
// ("Patterns (2)").
export function menuGroups(tf, on = {}, notes = {}, labels = {}) {
  return LAYER_GROUPS.map(g => ({
    key: g.key, label: g.label,
    items: g.items.filter(k => offered(k, tf)).map(k => ({ key: k, label: labels[k] || LAYER_LABELS[k], on: !!on[k], note: on[k] ? notes[k] || "" : "" })),
  }));
}

// How many of the offered layers are on.
export function layerCount(tf, on = {}) {
  return LAYER_GROUPS.flatMap(g => g.items).filter(k => offered(k, tf) && on[k]).length;
}

// What the chart is still waiting for, in a layer's row: null once there is something to draw.
export function auctionNote(state) {
  return state === "loading" ? "Loading…" : state === "busy" ? "Busy, trying again" : state === "none" ? "No data" : "";
}
