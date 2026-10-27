// The close and cancel paths are the ones TradingPanel.jsx used, unchanged (Portfolio v2, section 5).
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { makeTradeActions, closeArgs, tradable, executeAndJournal } from "./tradeActions.js";

function harness(over = {}) {
  const calls = { close: [], cancel: [], fetch: [], notices: [], closing: [], cancelling: [], fast: 0 };
  const hlClient = {
    closePosition: async (wc, args) => { calls.close.push({ wc, args }); return { avgPx: 79.86, totalSz: 358.94, oid: 4242 }; },
    cancelOrder: async (wc, args) => { calls.cancel.push({ wc, args }); return { status: "ok" }; },
    placeMarketOrder: async () => { throw new Error("never from this page"); },
    setLeverage: async () => { throw new Error("never from this page"); },
  };
  const deps = {
    api: "https://api.example", hlClient, readOnly: false, walletClient: { id: "wallet" },
    setClosing: v => calls.closing.push(v), setCancelling: v => calls.cancelling.push(v),
    setActionNotice: v => calls.notices.push(v), fetchFast: async () => { calls.fast += 1; },
    confirm: () => true, fetch: async (url, init) => { calls.fetch.push({ url, init }); return { ok: true, status: 200 }; },
    ...over,
  };
  return { calls, actions: makeTradeActions(deps), hlClient };
}

test("closePosition receives the raw coin, |szi| as reported and the side, at 2% slippage", async () => {
  const position = { coin: "kPEPE", szi: "-12345.678912" };
  const { coin, size, isLong } = closeArgs(position);
  assert.deepEqual({ coin, size, isLong }, { coin: "kPEPE", size: 12345.678912, isLong: false });
  const { calls, actions } = harness();
  await actions.closePosition(coin, size, isLong);
  assert.deepEqual(calls.close, [{ wc: { id: "wallet" }, args: { coin: "kPEPE", size: 12345.678912, isLong: false, slippage: 0.02 } }]);
  assert.deepEqual(calls.closing, ["kPEPE", null]);
  assert.equal(calls.fast, 1);
});

test("the log-close request is identical to TradingPanel's", async () => {
  const { calls, actions } = harness();
  await actions.closePosition("HYPE", 358.94, true);
  assert.equal(calls.fetch.length, 1);
  const { url, init } = calls.fetch[0];
  assert.equal(url, "https://api.example/api/trade/log-close");
  assert.deepEqual(init, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbol: "HYPE/USDT", exit_price: 79.86, close_order_id: "4242" }) });
  assert.equal(calls.notices.at(-1).text, "HYPE closed. Order 4242. Journal synced.");
  // k markets journal under the app's key.
  const k = harness();
  await k.actions.closePosition("kPEPE", 1, true);
  assert.equal(JSON.parse(k.calls.fetch[0].init.body).symbol, "KPEPE/USDT");
});

test("same notices: journal pending and failure", async () => {
  const pending = harness({ fetch: async () => ({ ok: false, status: 500 }) });
  await pending.actions.closePosition("BTC", 0.03553, true);
  assert.equal(pending.calls.notices.at(-1).text, "BTC closed. Order 4242. Journal sync pending; do not close again.");
  const failing = harness();
  failing.hlClient.closePosition = async () => { throw new Error("Insufficient margin"); };
  await failing.actions.closePosition("BTC", 0.03553, true);
  assert.equal(failing.calls.notices.at(-1).tone, "error");
  assert.equal(failing.calls.notices.at(-1).text, "Close could not be confirmed: Insufficient margin. Refresh positions and check the exchange before trying again.");
  assert.deepEqual(failing.calls.closing, ["BTC", null]);
});

test("cancelOrder receives {coin, oid} with no confirm", async () => {
  let asked = 0;
  const { calls, actions } = harness({ confirm: () => { asked += 1; return true; } });
  await actions.cancelOrd("LINK", 586531222372);
  assert.deepEqual(calls.cancel, [{ wc: { id: "wallet" }, args: { coin: "LINK", oid: 586531222372 } }]);
  assert.equal(asked, 0);
  assert.deepEqual(calls.cancelling, [586531222372, null]);
  assert.equal(calls.fast, 1);
});

test("read-only or no walletClient returns early; a declined confirm sends nothing", async () => {
  for (const over of [{ readOnly: true }, { walletClient: null }, { confirm: () => false }]) {
    const { calls, actions } = harness(over);
    await actions.closePosition("HYPE", 1, true);
    if (!over.confirm) await actions.cancelOrd("HYPE", 1);
    assert.equal(calls.close.length + calls.cancel.length + calls.fetch.length, 0);
    assert.equal(calls.closing.length, 0);
  }
});

test("xyz and other builder-dex rows are never closed or cancelled from this page", () => {
  assert.equal(tradable("HYPE"), true);
  assert.equal(tradable("kPEPE"), true);
  assert.equal(tradable("xyz:MSTR"), false);
  assert.equal(tradable("para:PAPER"), false);
  assert.equal(tradable("@107"), false);
  // The components gate Close and Cancel on tradable().
  const read = f => readFileSync(new URL(f, import.meta.url), "utf8");
  assert.match(read("./BoardRow.jsx"), /tradable\(row\.coin\)/);
  assert.match(read("./OrdersList.jsx"), /tradable\(/);
  assert.doesNotMatch(read("./PortfolioPage.jsx") + read("./BoardRow.jsx") + read("./OrdersList.jsx"), /placeMarketOrder|setLeverage/);
});

test("the close waits for the sheet: nothing is sent until it answers, Keep sends nothing", async () => {
  let answer;
  const { calls, actions } = harness({ confirm: () => new Promise(resolve => { answer = resolve; }) });
  const pending = actions.closePosition("HYPE", 358.94, true);
  await new Promise(r => setTimeout(r, 5));
  assert.equal(calls.close.length + calls.fetch.length + calls.closing.length, 0);
  answer(true);
  await pending;
  assert.equal(calls.close.length, 1);
  const kept = harness({ confirm: async () => false });
  await kept.actions.closePosition("HYPE", 358.94, true);
  assert.equal(kept.calls.close.length + kept.calls.fetch.length, 0);
  // The page passes the sheet as the confirm; window.confirm stays only as the fallback.
  const page = readFileSync(new URL("./PortfolioPage.jsx", import.meta.url), "utf8");
  assert.match(page, /confirm: coin => new Promise\(resolve => \{/);
  const r = await executeAndJournal(async () => ({ oid: 1 }), async () => { throw new Error("down"); });
  assert.deepEqual(r, { execution: { oid: 1 }, journalPending: true });
});
