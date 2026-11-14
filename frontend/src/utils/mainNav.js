// The four main tabs (header at 900px and wider, floating tab bar below): which one is active
// for an address, and where each one goes. The Radar left the main tabs on 14 November 2026 (owner's
// request): its axis was the profitable traders, who picked no better than the crowd; /radar still opens.
export const MAIN_TABS = [
  { key: "scanner", label: "Scanner", icon: "1d" },
  { key: "traders", label: "Traders", icon: "hyperlens" },
  { key: "market", label: "Market", icon: "market" },
  { key: "portfolio", label: "Portfolio", icon: "trading" },
];

export const LAST_SCANNER_KEY = "rcce-last-scanner";

// Scanner: /scanner and coin pages; Traders: its views, the leaderboard and trader profiles; Market: the
// market page and its tabs. The Radar, More pages, Settings and unknown addresses have no active tab (null).
export function activeMainTab(pathname) {
  const path = String(pathname || "").replace(/\/+$/, "") || "/";
  if (path === "/scanner") return "scanner";
  if (/^\/scanner\/[^/]+$/.test(path)) return "scanner";
  if (path === "/traders" || path === "/hyperlens" || path === "/traders/leaderboard") return "traders";
  if (/^\/trader\/0x[0-9a-fA-F]{40}$/.test(path)) return "traders";     // a trader's profile
  if (path === "/market") return "market";
  if (path === "/portfolio") return "portfolio";
  return null;
}

// Scanner returns to the last scanner view (filters, search, sort, timeframe). Only /scanner addresses are
// accepted as the saved view.
export function mainTabTargets({ lastScanner } = {}) {
  const scanner = typeof lastScanner === "string" && /^\/scanner(\?|$)/.test(lastScanner) ? lastScanner : "/scanner";
  return {
    scanner,
    traders: "/traders",
    market: "/market",
    portfolio: "/portfolio",
  };
}

export function readLastScanner() {
  try { return sessionStorage.getItem(LAST_SCANNER_KEY); } catch { return null; }
}

export function writeLastScanner(href) {
  try { sessionStorage.setItem(LAST_SCANNER_KEY, href); } catch { /* storage blocked */ }
}
