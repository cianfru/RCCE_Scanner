// A Close or Cancel outcome is always somewhere on screen (trading review): the phone sheet, the row
// or card, the Activity orders, or above the board; and one wallet's outcome never shows under another.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { noticePlace } from "./noticePlace.js";

const PAGE = readFileSync(new URL("./PortfolioPage.jsx", import.meta.url), "utf8");
const err = (coin, origin = "row", section = "positions") => ({ section, coin, tone: "error", origin, text: "Close could not be confirmed: x." });

test("phone: a failed close shows in the open sheet, then under the card, then above the board", () => {
  const n = err("BTC");
  assert.equal(noticePlace(n, { sheetCoin: "BTC", shownCoins: new Set(["BTC", "HYPE"]) }), "sheet");
  assert.equal(noticePlace(n, { sheetCoin: null, shownCoins: new Set(["BTC", "HYPE"]) }), "row");
  // Filtered out by a check, or past a collapsed group's first rows: above the board.
  assert.equal(noticePlace(n, { sheetCoin: null, shownCoins: new Set(["HYPE"]) }), "page");
});

test("desktop: under the row while it is shown; a Cancel from Activity at the top of the orders", () => {
  assert.equal(noticePlace(err("BTC"), { shownCoins: new Set(["BTC"]) }), "row");
  assert.equal(noticePlace(err("BTC"), { shownCoins: new Set() }), "page");
  assert.equal(noticePlace(err("BTC", "activity", "orders"), { shownCoins: new Set(["BTC"]) }), "activity");
  assert.equal(noticePlace(null, {}), null);
});

test("the page renders every place, and the notice is scoped to the address", () => {
  for (const where of ["row", "sheet", "activity", "page"]) assert.ok(PAGE.includes(`noticeAt("${where}"`), `no ${where} notice`);
  // The phone card has its notice, and the sheet too.
  assert.match(PAGE, /<PhoneCard[\s\S]{0,300}\{noticeAt\("row", row\.coin\)\}/);
  assert.match(PAGE, /<div className="pf-sh-acts">[\s\S]{0,200}\{noticeAt\("sheet", sheetRow\.coin\)\}\s*<Actions row=\{sheetRow\}/);
  // Cleared on every address change (as TradingPanel did), and an outcome for an earlier address dropped.
  assert.match(PAGE, /useEffect\(\(\) => \{ setNotice\(null\); \}, \[account\]\);/);
  assert.match(PAGE, /setActionNotice: v => \{ if \(accountRef\.current === owner\) setNotice/);
  // The shown rows are the groups' shown rows (collapsed groups counted).
  assert.match(PAGE, /groupShown\(groups\[k\], expanded\.has\(k\)\)/);
});
