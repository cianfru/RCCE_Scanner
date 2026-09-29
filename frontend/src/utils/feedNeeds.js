// Which scanner feeds the page on screen shows, so only those are kept fresh.
// scan: the timeframes whose rows are displayed; tradfi: the TradFi page;
// sentiment: the Fear & Greed dial in the scanner summary.
// Feeds a page does not show keep their last copy (every feed loads once at
// start) and are fetched again the moment a page that shows them opens.
// Pages without scanner rows still show the header's data clock: the live
// connection's scan notices keep it current, and without that connection the
// last scanner timeframe is polled as before.
export function feedNeeds(activeTab, { coinPage = false, wsConnected = true, lastScannerTf = "1d" } = {}) {
  if (coinPage || activeTab === "radar" || activeTab === "signals") {
    return { scan: ["4h", "1d"], tradfi: false, sentiment: false };
  }
  if (activeTab === "4h" || activeTab === "1d") return { scan: [activeTab], tradfi: false, sentiment: true };
  const clock = wsConnected ? [] : [lastScannerTf === "4h" ? "4h" : "1d"];
  return { scan: clock, tradfi: activeTab === "tradfi", sentiment: false };
}

// A stable string for effect dependencies.
export function needsKey(needs) {
  return `${[...needs.scan].sort().join(",")}|${needs.tradfi ? 1 : 0}|${needs.sentiment ? 1 : 0}`;
}
