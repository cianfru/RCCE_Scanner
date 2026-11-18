import test from "node:test";
import assert from "node:assert/strict";
import { LAYER_GROUPS, LAYER_LABELS, AUCTION_LAYERS, offered, menuGroups, layerCount, auctionNote } from "./chartLayers.js";

test("every layer has a name and sits in one group", () => {
  const keys = LAYER_GROUPS.flatMap(g => g.items);
  assert.equal(new Set(keys).size, keys.length);
  assert.deepEqual([...keys].sort(), Object.keys(LAYER_LABELS).sort());
  assert.deepEqual(LAYER_GROUPS.map(g => g.label), ["Price", "Trend", "Traders"]);
  assert.ok(AUCTION_LAYERS.every(k => LAYER_GROUPS[0].items.includes(k)));
});

test("the trend line and the ribbon are offered on 4H and 1D, patterns on 1D", () => {
  assert.deepEqual(["trend", "ribbon", "patterns"].map(k => offered(k, "1h")), [false, false, false]);
  assert.deepEqual(["trend", "ribbon", "patterns"].map(k => offered(k, "4h")), [true, true, false]);
  assert.deepEqual(["trend", "ribbon", "patterns"].map(k => offered(k, "1d")), [true, true, true]);
  assert.ok(["profiles", "levels", "zone", "opens", "averages", "entries", "wallets"].every(k => offered(k, "1h")));
});

test("the menu lists each group's offered layers with what is on", () => {
  const menu = menuGroups("4h", { levels: true, averages: true }, { levels: "Loading…", profiles: "Loading…" }, { patterns: "Patterns (2)" });
  assert.deepEqual(menu.map(g => [g.label, g.items.map(i => i.key)]),
    [["Price", ["profiles", "levels", "zone", "opens"]], ["Trend", ["averages", "trend", "ribbon"]], ["Traders", ["entries", "wallets"]]]);
  const levels = menu[0].items[1];
  assert.deepEqual(levels, { key: "levels", label: "Levels", on: true, note: "Loading…" });
  assert.equal(menu[0].items[0].note, "");                        // a note only on a layer that is on
  assert.equal(menuGroups("1d", {}, {}, { patterns: "Patterns (2)" })[1].items[3].label, "Patterns (2)");
  assert.equal(menuGroups("1h")[1].items.length, 1);              // 1H: averages only
});

test("the count is of the layers that are on and offered", () => {
  assert.equal(layerCount("1d", {}), 0);
  assert.equal(layerCount("1d", { levels: true, trend: true, patterns: true }), 3);
  assert.equal(layerCount("1h", { levels: true, trend: true, patterns: true }), 1);     // trend and patterns are not on a 1H chart
});

test("what a layer is waiting for, in words", () => {
  assert.deepEqual(["loading", "busy", "none", null].map(auctionNote), ["Loading…", "Busy, trying again", "No data", ""]);
});

test("no forecast words in the menu", () => {
  const all = [...Object.values(LAYER_LABELS), ...LAYER_GROUPS.map(g => g.label), ...["loading", "busy", "none"].map(auctionNote)].join(" ");
  assert.doesNotMatch(all, /\b(will|expect|expected|likely|predict|target|probability|odds)\b/i);
});
