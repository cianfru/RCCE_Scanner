import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { displayName, spotNames, venueOf, isMainDex } from "./displayNames.js";

const spotMeta = JSON.parse(readFileSync(new URL("./__fixtures__/spotMeta.json", import.meta.url), "utf8"));

test("xyz:MSTR shows as MSTR with the TradFi suffix", () => {
  assert.deepEqual(displayName("xyz:MSTR"), { name: "MSTR", suffix: "TradFi", venue: "xyz" });
  assert.deepEqual(displayName("para:PAPER"), { name: "PAPER", suffix: "para", venue: "para" });
});

test("@107 resolves through spotMeta", () => {
  const names = spotNames(spotMeta);
  assert.equal(names.get("@107"), "HYPE");
  assert.deepEqual(displayName("@107", names), { name: "HYPE", suffix: null, venue: "spot" });
  assert.equal(displayName("@99999", names).name, "@99999");
});

test("kPEPE shows as KPEPE; plain coins stay", () => {
  assert.equal(displayName("kPEPE").name, "KPEPE");
  assert.equal(displayName("HYPE").name, "HYPE");
  assert.equal(displayName("KAITO").name, "KAITO");
});

test("venues", () => {
  assert.equal(venueOf("BTC"), "main");
  assert.equal(venueOf("xyz:NVDA"), "xyz");
  assert.equal(venueOf("@107"), "spot");
  assert.ok(isMainDex("kPEPE") && !isMainDex("xyz:NVDA") && !isMainDex("@142"));
});
