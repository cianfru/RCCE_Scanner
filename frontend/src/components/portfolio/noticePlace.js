// Where a Close or Cancel outcome (the action notice) shows, at every width. TradingPanel.jsx showed it
// in the section it came from, or at page level when that section was not on screen; this page does
// the same with its own places:
//   "sheet"     the phone sheet, while it is open on that coin;
//   "row"       under the coin's board row (desktop) or card (phone), while that row is on screen
//               (not filtered out by a check, not past a collapsed group's first rows);
//   "activity"  the top of the Activity orders, for a Cancel pressed there;
//   "page"      above the board, when none of these is on screen (the position is gone, say).
// notice.origin: "row" (a row, its detail or the phone sheet) or "activity".
export function noticePlace(notice, { sheetCoin = null, shownCoins = new Set() } = {}) {
  if (!notice) return null;
  if (notice.origin === "activity") return "activity";
  if (sheetCoin && sheetCoin === notice.coin) return "sheet";
  if (shownCoins.has(notice.coin)) return "row";
  return "page";
}
