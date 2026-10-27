// The new page's close and cancel send exactly what the old page (TradingPanel.jsx) sent. The old
// path is TradingPanel's own code, read from its source: PositionCard's arguments and the
// closePosition and cancelOrd it calls. The new path is the board row's arguments (positionsOf ->
// buildRow -> closeArgs) and tradeActions.js. Both run through the real services/hlClient.js and the
// Hyperliquid SDK with a recorded fetch; the requests must be byte-identical. Most cases sign with a
// local-account test signer ({address, signTypedData}); the app itself signs with the viem wallet
// client WalletContext.jsx builds (JSON-RPC, over window.ethereum), covered at the end of this file:
// as WalletContext builds it today (no account), and with an account, which is how signing would work.
import test, { before, after } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { createWalletClient, custom } from "viem";
import { arbitrum } from "viem/chains";
import * as hlClient from "../../services/hlClient.js";
import { kKey } from "../../utils/tickerRenames.js";
import { positionsOf } from "../../utils/portfolio/totals.js";
import { buildRow } from "../../utils/portfolio/checks.js";
import { makeTradeActions, closeArgs, tradable, radarHref } from "./tradeActions.js";

const read = rel => readFileSync(new URL(rel, import.meta.url), "utf8");
const OLD = read("../TradingPanel.jsx");
const PAGE = read("./PortfolioPage.jsx");
const ROW = read("./BoardRow.jsx");
const ORDERS = read("./OrdersList.jsx");

// The source of `head ... { body }` in src, from head to its matching brace.
function block(src, head) {
  const at = src.indexOf(head);
  assert.ok(at >= 0, `not found: ${head}`);
  let i = src.indexOf("{", at + head.length - 1), depth = 0;
  for (; i < src.length; i++) {
    if (src[i] === "{") depth += 1;
    else if (src[i] === "}" && --depth === 0) return src.slice(at, i + 1);
  }
  throw new Error(`unbalanced: ${head}`);
}

// TradingPanel's helpers and actions, compiled from its source.
const oldParseNum = new Function(`${block(OLD, "function parseNum(v)")}; return parseNum;`)();
const oldExecuteAndJournal = new Function(`${block(OLD, "async function executeAndJournal(execute, journal)")}; return executeAndJournal;`)();
const OLD_DEPS = ["readOnly", "walletClient", "window", "setClosing", "setCancelling", "setActionNotice", "executeAndJournal", "hlClient", "fetch", "api", "kKey", "fetchFast", "console"];
const oldClose = new Function(...OLD_DEPS, `${block(OLD, "const closePosition = async (coin, size, isLong) =>")}; return closePosition;`);
const oldCancel = new Function(...OLD_DEPS, `${block(OLD, "const cancelOrd = async (coin, oid) =>")}; return cancelOrd;`);

// PositionCard's arguments: the lines below must stay as they are for this copy to hold.
const OLD_CARD = [
  "const szi = parseNum(pos.position?.szi ?? pos.szi);",
  "const isLong = szi > 0;",
  "const p = pos.position || pos;",
  "const coin = p.coin;             // Hyperliquid's name (kPEPE): what a close is sent under",
  "onClick={() => onClose(coin, Math.abs(szi), isLong)}",
  "onClose={closePosition}",
  // The old page listed the main perps account's positions only (no xyz row, so no xyz close).
  "const positions = useMemo(() => sortPositions((chState?.assetPositions || []).filter(ap => parseNum(ap.position?.szi) !== 0), scanMap4h), [chState, scanMap4h]);",
  "onClick={() => cancelOrd(o.coin, o.oid)}",
  "() => hlClient.getOpenOrders(account)",
];
function oldArgs(ap) {
  const pos = ap;
  const szi = oldParseNum(pos.position?.szi ?? pos.szi);
  const isLong = szi > 0;
  const p = pos.position || pos;
  return [p.coin, Math.abs(szi), isLong];
}

// The new page: the row's Close calls onClose(row) and the page maps the row like this.
const NEW_PAGE = [
  "const { coin, size, isLong } = closeArgs({ coin: row.coin, szi: row.szi });",
  "actions.closePosition(coin, size, isLong);",
  "const onCancel = (coin, oid) => actions.cancelOrd(coin, oid);",
  "const onCancelActivity = (coin, oid) => activityActions.cancelOrd(coin, oid);",
  "() => hlClient.getDexOpenOrders(account, \"\")",
  // Both action sets are made by one function from the same deps; only the notice's place differs.
  "api, hlClient, readOnly, walletClient, setClosing, setCancelling, fetchFast: f.fetchFast,",
];
function newArgs(state) {
  return positionsOf(state, "main").map(p => buildRow(p, null, [])).map(row => {
    const { coin, size, isLong } = closeArgs({ coin: row.coin, szi: row.szi });
    return [coin, size, isLong];
  });
}

// ------------------------------------------------------------------ a recorded Hyperliquid
const META = { universe: [
  { name: "BTC", szDecimals: 5, maxLeverage: 40 }, { name: "ETH", szDecimals: 4, maxLeverage: 25 },
  { name: "kPEPE", szDecimals: 0, maxLeverage: 10 }, { name: "HYPE", szDecimals: 2, maxLeverage: 10 },
], marginTables: [] };
const MIDS = { BTC: "81234.5", ETH: "3021.37", kPEPE: "0.010523", HYPE: "79.125" };
const NOW = 1761550000000;

let log = null;
const json = body => new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
function headersOf(h) {
  return [...new Headers(h || {}).entries()].sort(([a], [b]) => (a < b ? -1 : 1));
}
async function recordedFetch(url, init = {}) {
  const body = typeof init.body === "string" ? init.body : init.body == null ? null : String(init.body);
  log.push({ url: String(url), method: init.method || "GET", headers: headersOf(init.headers), body });
  const u = String(url);
  if (u.endsWith("/info")) {
    const { type } = JSON.parse(body);
    if (type === "meta") return json(META);
    if (type === "allMids") return json(MIDS);
    if (type === "frontendOpenOrders") return json([]);
    throw new Error(`unexpected info ${type}`);
  }
  if (u.endsWith("/exchange")) {
    const { action } = JSON.parse(body);
    if (action.type === "order") {
      const o = action.orders[0];
      return json({ status: "ok", response: { type: "order", data: { statuses: [{ filled: { totalSz: o.s, avgPx: o.p, oid: 777001 } }] } } });
    }
    if (action.type === "cancel") return json({ status: "ok", response: { type: "cancel", data: { statuses: ["success"] } } });
    throw new Error(`unexpected action ${action.type}`);
  }
  if (u.endsWith("/api/trade/log-close")) return json({ ok: true });
  throw new Error(`unexpected url ${u}`);
}

// A test signer (viem local-account shape): a deterministic signature over what it is asked to sign.
let walletN = 0;
function testSigner() {
  walletN += 1;
  const signed = [];
  const stable = v => JSON.stringify(v, (k, x) => (typeof x === "bigint" ? x.toString() : x));
  return {
    address: `0x${String(walletN).padStart(40, "0")}`, signed,
    signTypedData: async args => {
      signed.push(stable(args));
      const h = createHash("sha256").update(stable(args)).digest("hex");
      return `0x${h}${h}1b`;
    },
  };
}

// One run: everything the action sent, what was signed, the notices and the closing/cancelling states.
async function run(fn) {
  const realFetch = globalThis.fetch, realNow = Date.now, realError = console.error;
  log = [];
  const out = { notices: [], states: [], fast: 0 };
  globalThis.fetch = recordedFetch;
  Date.now = () => NOW;
  console.error = () => {};
  try {
    await fn(out);
  } finally {
    globalThis.fetch = realFetch;
    Date.now = realNow;
    console.error = realError;
  }
  return { ...out, requests: log };
}
const common = out => ({
  setClosing: v => out.states.push(["closing", v]), setCancelling: v => out.states.push(["cancelling", v]),
  setActionNotice: v => out.notices.push(v), fetchFast: async () => { out.fast += 1; },
});
const API = "https://api.example";
const quiet = { error: () => {} };

async function oldCloseRun(args) {
  const wallet = testSigner();
  const r = await run(async out => {
    const c = common(out);
    const close = oldClose(false, wallet, { confirm: () => true }, c.setClosing, c.setCancelling, c.setActionNotice,
      oldExecuteAndJournal, hlClient, globalThis.fetch, API, kKey, c.fetchFast, quiet);
    await close(...args);
  });
  return { ...r, signed: wallet.signed };
}
async function newCloseRun(args) {
  const wallet = testSigner();
  const r = await run(async out => {
    // The close sheet answers later, as a person clicking "Close at market" does.
    const confirm = () => new Promise(resolve => setTimeout(() => resolve(true), 5));
    const actions = makeTradeActions({ api: API, hlClient, readOnly: false, walletClient: wallet, ...common(out), confirm });
    await actions.closePosition(...args);
  });
  return { ...r, signed: wallet.signed };
}
async function oldCancelRun(coin, oid) {
  const wallet = testSigner();
  const r = await run(async out => {
    const c = common(out);
    const cancel = oldCancel(false, wallet, { confirm: () => true }, c.setClosing, c.setCancelling, c.setActionNotice,
      oldExecuteAndJournal, hlClient, globalThis.fetch, API, kKey, c.fetchFast, quiet);
    await cancel(coin, oid);
  });
  return { ...r, signed: wallet.signed };
}
async function newCancelRun(coin, oid) {
  const wallet = testSigner();
  const r = await run(async out => {
    const actions = makeTradeActions({ api: API, hlClient, readOnly: false, walletClient: wallet, ...common(out) });
    await actions.cancelOrd(coin, oid);
  });
  return { ...r, signed: wallet.signed };
}

// The account: a k market long, BTC long (one decimal more than BTC's szDecimals, so the size floors
// as in PR #200), an ETH short and a HYPE short; xyz:NVDA in the TradFi account.
const pos = (coin, szi, value) => ({ type: "oneWay", position: { coin, szi, entryPx: "1", positionValue: value, unrealizedPnl: "0",
  returnOnEquity: "0", liquidationPx: null, leverage: { type: "cross", value: 3 }, marginUsed: "1", cumFunding: { sinceOpen: "0" } } });
const MAIN = { assetPositions: [pos("kPEPE", "152340", "1603.07"), pos("BTC", "0.035537", "2886.8"), pos("ETH", "-1.23456", "3730.1"), pos("HYPE", "-358.94", "28401.1")] };
const XYZ = { assetPositions: [pos("xyz:NVDA", "8.123", "1755.2")] };

// Nothing here reaches the network: outside a run, fetch throws. The meta is read once per page
// (hlClient caches it), so it is read once here, before both paths run.
const networkFetch = globalThis.fetch;
before(async () => {
  globalThis.fetch = async url => { throw new Error(`network call outside a recorded run: ${url}`); };
  await run(() => hlClient.getSzDecimals("BTC"));
});
after(() => { globalThis.fetch = networkFetch; });

test("the source lines both paths are copied from are still there", () => {
  for (const line of OLD_CARD) assert.ok(OLD.includes(line), `TradingPanel.jsx: ${line}`);
  for (const line of NEW_PAGE) assert.ok(PAGE.includes(line) || read("./usePortfolioFeeds.js").includes(line), `new page: ${line}`);
  assert.match(ROW, /canClose && tradable\(row\.coin\) && <button type="button" className="pf-close" disabled=\{closing\}[^>]*\n?\s*onClick=\{e => onClose\(row, e\.currentTarget\)\}>/);
  assert.match(ORDERS, /canCancel && tradable\(o\.coin\) && <button[^>]*onClick=\{\(\) => onCancel\(o\.coin, o\.oid\)\}>/);
  // Neither page ever opens or resizes a position.
  const code = src => src.replace(/^\s*\/\/.*$/gm, "");
  assert.doesNotMatch(code(PAGE + ROW + ORDERS + read("./tradeActions.js")), /placeMarketOrder|setLeverage/);
});

test("same arguments: the old card and the new row, for every main position", () => {
  const olds = MAIN.assetPositions.map(oldArgs);
  assert.deepEqual(newArgs(MAIN), olds);
  assert.deepEqual(olds, [["kPEPE", 152340, true], ["BTC", 0.035537, true], ["ETH", 1.23456, false], ["HYPE", 358.94, false]]);
});

test("byte-identical close requests: k market, BTC, and the shorts", async () => {
  const rows = newArgs(MAIN);
  for (const [i, ap] of MAIN.assetPositions.entries()) {
    const before = await oldCloseRun(oldArgs(ap));
    const after = await newCloseRun(rows[i]);
    assert.ok(before.requests.length >= 3, JSON.stringify(before.requests.map(r => r.url)));
    assert.deepEqual(after.requests, before.requests, `requests differ for ${ap.position.coin}`);
    assert.deepEqual(after.signed, before.signed, `signed data differs for ${ap.position.coin}`);
    assert.deepEqual(after.notices, before.notices);
    assert.deepEqual(after.states, before.states);
    assert.equal(after.fast, before.fast);
  }
});

test("the close itself: reduce-only IOC, size floored to szDecimals, the k market under kPEPE, the journal under KPEPE", async () => {
  const sent = {};
  for (const args of newArgs(MAIN)) {
    const r = await newCloseRun(args);
    const ex = r.requests.find(q => q.url.endsWith("/exchange"));
    const { action, nonce } = JSON.parse(ex.body);
    const journal = r.requests.find(q => q.url.endsWith("/api/trade/log-close"));
    sent[args[0]] = { order: action.orders[0], grouping: action.grouping, nonce, journal: JSON.parse(journal.body), journalInit: [journal.method, journal.headers] };
  }
  assert.deepEqual(sent.kPEPE.order, { a: 2, b: false, p: "0.010312", s: "152340", r: true, t: { limit: { tif: "Ioc" } } });
  assert.deepEqual(sent.BTC.order, { a: 0, b: false, p: "79609", s: "0.03553", r: true, t: { limit: { tif: "Ioc" } } });
  assert.deepEqual(sent.ETH.order, { a: 1, b: true, p: "3081.8", s: "1.2345", r: true, t: { limit: { tif: "Ioc" } } });
  assert.deepEqual(sent.HYPE.order, { a: 3, b: true, p: "80.708", s: "358.94", r: true, t: { limit: { tif: "Ioc" } } });
  assert.equal(sent.BTC.grouping, "na");
  assert.equal(sent.BTC.nonce, NOW);
  assert.deepEqual(sent.kPEPE.journal, { symbol: "KPEPE/USDT", exit_price: 0.010312, close_order_id: "777001" });
  assert.deepEqual(sent.HYPE.journal, { symbol: "HYPE/USDT", exit_price: 80.708, close_order_id: "777001" });
  assert.deepEqual(sent.BTC.journalInit, ["POST", [["content-type", "application/json"]]]);
});

test("TradFi (xyz): neither page offers a close; called anyway, both send the same and no order", async () => {
  assert.equal(tradable("xyz:NVDA"), false);
  assert.deepEqual(positionsOf(XYZ, "xyz").map(p => [p.coin, p.venue]), [["xyz:NVDA", "xyz"]]);
  const args = ["xyz:NVDA", 8.123, true];
  const before = await oldCloseRun(args);
  const after = await newCloseRun(args);
  assert.deepEqual(after.requests, before.requests);
  assert.equal(before.requests.filter(q => q.url.endsWith("/exchange")).length, 0);
  assert.deepEqual(after.notices, before.notices);
  assert.match(before.notices.at(-1).text, /^Close could not be confirmed: Unknown asset: xyz:NVDA\./);
});

test("byte-identical cancel requests (no confirm on either page)", async () => {
  for (const [coin, oid] of [["BTC", 586531222372], ["kPEPE", 99], ["HYPE", 1]]) {
    const before = await oldCancelRun(coin, oid);
    const after = await newCancelRun(coin, oid);
    assert.deepEqual(after.requests, before.requests, `cancel ${coin}`);
    assert.deepEqual(after.signed, before.signed);
    assert.deepEqual(after.states, before.states);
    const ex = after.requests.find(q => q.url.endsWith("/exchange"));
    assert.deepEqual(JSON.parse(ex.body).action, { type: "cancel", cancels: [{ a: { BTC: 0, kPEPE: 2, HYPE: 3 }[coin], o: oid }] });
  }
});

test("read-only, no wallet client, or Keep: nothing is sent on either path", async () => {
  for (const [readOnly, wallet, ok] of [[true, testSigner(), true], [false, null, true], [false, testSigner(), false]]) {
    const before = await run(async out => {
      const c = common(out);
      await oldClose(readOnly, wallet, { confirm: () => ok }, c.setClosing, c.setCancelling, c.setActionNotice,
        oldExecuteAndJournal, hlClient, globalThis.fetch, API, kKey, c.fetchFast, quiet)("BTC", 1, true);
    });
    const after = await run(async out => {
      await makeTradeActions({ api: API, hlClient, readOnly, walletClient: wallet, ...common(out), confirm: async () => ok }).closePosition("BTC", 1, true);
    });
    assert.deepEqual(after.requests, []);
    assert.deepEqual(before.requests, []);
    assert.deepEqual(after.states, before.states);
  }
});

test("watch and Radar: the same toggle and key; Radar's focus fixed only for k markets", () => {
  // Old: onWatch(appKey) with appKey = kKey(coin) -> toggleWatch(coin, "4h") and watchToast.
  assert.ok(OLD.includes("onClick={() => onWatch(appKey)}"));
  assert.ok(OLD.includes("const appKey = kKey(coin);"));
  const toggle = "const onWatch = useCallback(async coin => setWatchMsg(watchToast(coin, await toggleWatch(coin, \"4h\"), telegram)), [toggleWatch, telegram]);";
  assert.ok(OLD.includes(toggle));
  assert.ok(PAGE.includes(toggle.replace("setWatchMsg", "setToast")));
  assert.match(ROW, /onClick=\{\(\) => onWatch\(kKey\(row\.coin\)\)\}/);
  // Old link: `/radar?tf=4h&focus=${encodeURIComponent(coin)}` with Hyperliquid's name.
  assert.ok(OLD.includes("to={`/radar?tf=4h&focus=${encodeURIComponent(coin)}`}"));
  const oldHref = coin => `/radar?tf=4h&focus=${encodeURIComponent(coin)}`;
  for (const c of ["BTC", "ETH", "HYPE", "PUMP"]) assert.equal(radarHref(c), oldHref(c));
  assert.equal(radarHref("kPEPE"), "/radar?tf=4h&focus=KPEPE");   // the Radar's key; kPEPE matched nothing there
  assert.match(ROW, /to=\{radarHref\(row\.coin\)\}/);
});

test("the old page's open-orders read and the new one send the same request", async () => {
  const r1 = await run(async () => { await hlClient.getOpenOrders("0x00000000000000000000000000000000000000aa"); });
  const r2 = await run(async () => { await hlClient.getDexOpenOrders("0x00000000000000000000000000000000000000aa", ""); });
  assert.equal(r1.requests.length, 1);
  assert.deepEqual(r2.requests, r1.requests);
});

// ------------------------------------------------- the app's own wallet client (viem, JSON-RPC)
// WalletContext.jsx builds createWalletClient({ chain: arbitrum, transport: custom(window.ethereum) }).
// An injected provider stands in for the browser wallet: it records what it is asked to sign.
const WALLET = read("../../WalletContext.jsx");
// Each run has its own address (the SDK keeps nonces per signer, so a shared one would step the
// second run's nonce); the address is taken out of what the wallet records before comparing.
let injectedN = 0;
function injected() {
  const calls = [];
  injectedN += 1;
  const addr = `0x${String(500 + injectedN).padStart(40, "0")}`;
  return {
    calls, addr,
    request: async ({ method, params }) => {
      calls.push({ method, params: JSON.stringify(params ?? null).replaceAll(addr, "0xSIGNER") });
      if (method === "eth_accounts" || method === "eth_requestAccounts") return [addr];
      if (method === "eth_chainId") return "0xa4b1";
      if (method === "eth_signTypedData_v4") return `0x${"11".repeat(32)}${"22".repeat(32)}1b`;
      throw new Error(`unexpected ${method}`);
    },
  };
}
async function closeWith(path, makeWallet, args) {
  const provider = injected();
  const wallet = makeWallet(provider);
  const r = await run(async out => {
    if (path === "old") {
      const c = common(out);
      await oldClose(false, wallet, { confirm: () => true }, c.setClosing, c.setCancelling, c.setActionNotice,
        oldExecuteAndJournal, hlClient, globalThis.fetch, API, kKey, c.fetchFast, quiet)(...args);
    } else {
      const confirm = () => new Promise(resolve => setTimeout(() => resolve(true), 5));
      await makeTradeActions({ api: API, hlClient, readOnly: false, walletClient: wallet, ...common(out), confirm }).closePosition(...args);
    }
  });
  return { ...r, wallet: provider.calls };
}
async function cancelWith(path, makeWallet, coin, oid) {
  const provider = injected();
  const wallet = makeWallet(provider);
  const r = await run(async out => {
    if (path === "old") {
      const c = common(out);
      await oldCancel(false, wallet, { confirm: () => true }, c.setClosing, c.setCancelling, c.setActionNotice,
        oldExecuteAndJournal, hlClient, globalThis.fetch, API, kKey, c.fetchFast, quiet)(coin, oid);
    } else {
      await makeTradeActions({ api: API, hlClient, readOnly: false, walletClient: wallet, ...common(out) }).cancelOrd(coin, oid);
    }
  });
  return { ...r, wallet: provider.calls };
}

test("the app's wallet client as WalletContext builds it: both pages fail the same way, before the wallet is asked", async () => {
  // The shape this test copies; if WalletContext changes, this test must be looked at again.
  assert.match(WALLET, /createWalletClient\(\{\s*chain: arbitrum,\s*transport: custom\(window\.ethereum\),\s*\}\)/);
  const asBuilt = provider => createWalletClient({ chain: arbitrum, transport: custom(provider) });
  for (const args of newArgs(MAIN)) {
    const before = await closeWith("old", asBuilt, args);
    const after = await closeWith("new", asBuilt, args);
    assert.deepEqual(after.requests, before.requests, `close ${args[0]}`);
    assert.deepEqual(after.notices, before.notices);
    assert.deepEqual(after.states, before.states);
    // viem has no account to sign with: nothing reaches the wallet or the exchange.
    assert.equal(before.wallet.filter(c => c.method === "eth_signTypedData_v4").length, 0);
    assert.equal(before.requests.filter(q => q.url.endsWith("/exchange")).length, 0);
    assert.equal(before.notices.at(-1).tone, "error");
  }
  const before = await cancelWith("old", asBuilt, "BTC", 586531222372);
  const after = await cancelWith("new", asBuilt, "BTC", 586531222372);
  assert.deepEqual(after.requests, before.requests);
  assert.deepEqual(after.notices, before.notices);
  assert.equal(before.requests.filter(q => q.url.endsWith("/exchange")).length, 0);
});

test("the app's wallet client with an account: the same typed data to the wallet and byte-identical requests", async () => {
  // Not what WalletContext builds today (see above); this covers the JSON-RPC signing path itself.
  const withAccount = provider => createWalletClient({ account: provider.addr, chain: arbitrum, transport: custom(provider) });
  for (const args of newArgs(MAIN)) {
    const before = await closeWith("old", withAccount, args);
    const after = await closeWith("new", withAccount, args);
    const signs = before.wallet.filter(c => c.method === "eth_signTypedData_v4");
    assert.equal(signs.length, 1, `close ${args[0]}: one signature`);
    assert.deepEqual(after.wallet, before.wallet, `close ${args[0]}: what the wallet is asked`);
    assert.deepEqual(after.requests, before.requests, `close ${args[0]}: requests`);
    assert.equal(after.requests.filter(q => q.url.endsWith("/exchange")).length, 1);
    assert.deepEqual(after.notices, before.notices);
  }
  const before = await cancelWith("old", withAccount, "kPEPE", 99);
  const after = await cancelWith("new", withAccount, "kPEPE", 99);
  assert.deepEqual(after.wallet, before.wallet);
  assert.deepEqual(after.requests, before.requests);
});
