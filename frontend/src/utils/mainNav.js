// The four main tabs (header at 900px and wider, floating tab bar below): which one is active
// for an address, and where each one goes.
export const MAIN_TABS = [
  { key: "scanner", label: "Scanner", icon: "1d" },
  { key: "radar", label: "Radar", icon: "radar" },
  { key: "traders", label: "Traders", icon: "hyperlens" },
  { key: "portfolio", label: "Portfolio", icon: "trading" },
];

export const LAST_SCANNER_KEY = "rcce-last-scanner";

// Scanner: /scanner and coin pages; Radar: /radar and coin pages opened from it; Traders: its
// views, the leaderboard and trader profiles.
// More pages, Settings and unknown addresses have no active tab (null).
export function activeMainTab(pathname, search = "") {
  const path = String(pathname || "").replace(/\/+$/, "") || "/";
  if (path === "/scanner") return "scanner";
  if (/^\/scanner\/[^/]+$/.test(path)) {
    const from = new URLSearchParams(search).get("from") || "";
    return from.startsWith("/radar") ? "radar" : "scanner";
  }
  if (path === "/radar") return "radar";
  if (path === "/traders" || path === "/hyperlens" || path === "/traders/leaderboard") return "traders";
  if (/^\/trader\/0x[0-9a-fA-F]{40}$/.test(path)) return "traders";     // a trader's profile
  if (path === "/portfolio") return "portfolio";
  return null;
}

// Scanner returns to the last scanner view (filters, search, sort, timeframe); Radar opens on
// the last scanner timeframe. Only /scanner addresses are accepted as the saved view.
export function mainTabTargets({ lastScanner, lastScannerTf } = {}) {
  const scanner = typeof lastScanner === "string" && /^\/scanner(\?|$)/.test(lastScanner) ? lastScanner : "/scanner";
  return {
    scanner,
    radar: `/radar?tf=${lastScannerTf === "4h" ? "4h" : "1d"}`,
    traders: "/traders",
    portfolio: "/portfolio",
  };
}

export function readLastScanner() {
  try { return sessionStorage.getItem(LAST_SCANNER_KEY); } catch { return null; }
}

export function writeLastScanner(href) {
  try { sessionStorage.setItem(LAST_SCANNER_KEY, href); } catch { /* storage blocked */ }
}
