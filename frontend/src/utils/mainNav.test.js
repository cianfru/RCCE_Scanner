import test from "node:test";
import assert from "node:assert/strict";
import { activeMainTab, mainTabTargets, MAIN_TABS } from "./mainNav.js";

test("four main tabs in order", () => {
  assert.deepEqual(MAIN_TABS.map(t => t.label), ["Scanner", "Radar", "Traders", "Portfolio"]);
});

test("scanner and coin pages activate Scanner; coin pages opened from the Radar activate Radar", () => {
  assert.equal(activeMainTab("/scanner", "?tf=4h&market=spot"), "scanner");
  assert.equal(activeMainTab("/scanner/", ""), "scanner");
  assert.equal(activeMainTab("/scanner/BTC", "?market=perpetual&tf=1d"), "scanner");
  assert.equal(activeMainTab("/scanner/BTC", "?from=" + encodeURIComponent("/scanner?tf=4h")), "scanner");
  assert.equal(activeMainTab("/scanner/BTC", "?tf=1d&from=" + encodeURIComponent("/radar?tf=1d&focus=BTC")), "radar");
  assert.equal(activeMainTab("/radar", "?tf=4h"), "radar");
  assert.equal(activeMainTab("/traders", ""), "traders");
  assert.equal(activeMainTab("/traders/leaderboard", ""), "traders");
  assert.equal(activeMainTab("/trader/0x91867345424fb158888ff9c5f1b1b2e7cd7d65d5", ""), "traders");
  assert.equal(activeMainTab("/portfolio", ""), "portfolio");
});

test("More pages, settings and unknown addresses have no active tab", () => {
  for (const p of ["/signals", "/analytics", "/tradfi", "/backtest", "/executor", "/ai", "/settings", "/nope", "/scanner/BTC/extra", "/trader/0x123", "/trader"])
    assert.equal(activeMainTab(p, ""), null, p);
});

test("targets: last scanner view, Radar on the last timeframe", () => {
  assert.deepEqual(mainTabTargets({ lastScanner: "/scanner?market=spot&tf=4h&q=ETH", lastScannerTf: "4h" }), {
    scanner: "/scanner?market=spot&tf=4h&q=ETH", radar: "/radar?tf=4h", traders: "/traders", portfolio: "/portfolio",
  });
  assert.equal(mainTabTargets({}).scanner, "/scanner");
  assert.equal(mainTabTargets({}).radar, "/radar?tf=1d");
  for (const bad of ["https://example.com", "//evil", "/scanner.evil", "/radar", null])
    assert.equal(mainTabTargets({ lastScanner: bad }).scanner, "/scanner", String(bad));
});
