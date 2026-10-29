// The market history page's daily inputs, exported with the page's own code (frontend/src/utils) for
// research/late_uptrends.py: [day, n, uptrend, downtrend, basing, fg, traders long, btc] per day.
//
//   node research/export_page_rows.mjs MARKET_HISTORY.json WALLETS.json OUT.json      (from backend/)
//
// MARKET_HISTORY.json and WALLETS.json: saved /api/market-history and /api/market-history/wallets responses.
import { readFileSync, writeFileSync } from "node:fs";

const FE = new URL("../../frontend/src/utils/", import.meta.url);
const { rowsOf, fearGreedByDay } = await import(new URL("marketHistory.js", FE));
const { byDay } = await import(new URL("walletHistory.js", FE));
const [mhPath, wPath, out] = process.argv.slice(2);
const data = JSON.parse(readFileSync(mhPath, "utf8"));
const wallets = JSON.parse(readFileSync(wPath, "utf8"));
const fg = fearGreedByDay(data);
const crowd = byDay(wallets, { scope: "all" }).crowd;
const rows = rowsOf(data).map(r => [r.day, r.n, r.uptrend + (r.overheated || 0), r.downtrend, r.basing,
  fg.get(r.day) ?? null, crowd?.get(r.day)?.L ?? null, r.btc]);
writeFileSync(out, JSON.stringify({ columns: ["day", "n", "uptrend", "downtrend", "basing", "fg", "traders", "btc"], rows }));
console.log(`${rows.length} days, ${rows[0][0]} to ${rows[rows.length - 1][0]}`);
