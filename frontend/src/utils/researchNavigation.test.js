import test from "node:test";
import assert from "node:assert/strict";
import {marketHref,timeframeFrom,scannerHref,backHref,displaySymbol,divergenceKind} from "./researchNavigation.js";
test("4H spot drilldown preserves full symbol, market and timeframe",()=>{
 const href=marketHref({symbol:"UMON/USDC",market_kind:"spot"},"4h");
 assert.equal(href,"/scanner/UMON%2FUSDC?market=spot&tf=4h");assert.equal(timeframeFrom(href.split("?")[1]),"4h");
});
test("return links restore filters but reject external destinations",()=>{
 assert.equal(scannerHref("?from="+encodeURIComponent("/scanner?tf=4h&q=BTC&market=spot")),"/scanner?tf=4h&q=BTC&market=spot");
 for(const from of ["https://example.com","//example.com","/scanner.evil","/scanner/BTC"])
 assert.equal(scannerHref("?market=spot&tf=4h&from="+encodeURIComponent(from)),"/scanner?market=spot&tf=4h");
});
test("quote formatting never corrupts a USDC base symbol or HIP-3 name",()=>{
 for(const [raw,expected] of [["ZAMA/USDC","ZAMA"],["BTC/USDT","BTC"],["ETH/USD","ETH"],["xyz:GOLD","xyz:GOLD"],["USDC","USDC"]]) assert.equal(displaySymbol(raw),expected);
});
test("waiting differs from directional opposition",()=>{
 assert.equal(divergenceKind("WAIT","BULLISH"),"waiting");
 assert.equal(divergenceKind("STRONG_LONG","BEARISH"),"opposed");
 assert.equal(divergenceKind("WAIT","NEUTRAL"),null);
});
test("back link returns to the saved scanner or Radar view only",()=>{
 const radar="/radar?tf=1d&focus=TIA";
 assert.equal(backHref("?market=perpetual&tf=1d&from="+encodeURIComponent(radar)),radar);
 assert.equal(backHref("?from="+encodeURIComponent("/radar")),"/radar");
 const scanner="/scanner?signal=STRONG_LONG&sort=zscore";
 assert.equal(backHref("?tf=4h&from="+encodeURIComponent(scanner)),scanner);
 for(const from of ["/radarx","//evil.com","https://x","/scanner/BTC","/radar/extra","/scannerx?tf=4h"])
  assert.equal(backHref("?market=spot&tf=4h&from="+encodeURIComponent(from)),"/scanner?market=spot&tf=4h",from);
 assert.equal(backHref("?market=perpetual"),"/scanner?market=perpetual&tf=1d");
});
