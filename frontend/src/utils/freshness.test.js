import test from "node:test";
import assert from "node:assert/strict";
import { freshness, freshnessText, ageShort, ageLong, clockLabel, STALE_S } from "./freshness.js";

const NOW = new Date(2026, 8, 27, 15, 33, 34).getTime();   // local 15:33:34

test("live: data time is the refresh time minus the cache age", () => {
  const f = freshness({ lastRefresh: new Date(NOW - 30_000), cacheAge: 90, error: null, now: NOW });
  assert.equal(f.state, "live");
  assert.equal(+f.dataTime, NOW - 120_000);
  assert.equal(f.ageS, 120);
  assert.equal(f.ageLabel, "2m");
});

test("stale from 900s (three missed 5-minute syntheses); 899s is still live", () => {
  assert.equal(STALE_S, 900);
  assert.equal(freshness({ lastRefresh: NOW - 901_000, cacheAge: 0, now: NOW }).state, "stale");
  assert.equal(freshness({ lastRefresh: NOW - 600_000, cacheAge: 301, now: NOW }).state, "stale");
  assert.equal(freshness({ lastRefresh: NOW - 899_000, cacheAge: 0, now: NOW }).state, "live");
});

test("down whenever the feed reports an error, even with fresh data", () => {
  assert.equal(freshness({ lastRefresh: NOW - 1000, cacheAge: 1, error: "API error 502", now: NOW }).state, "down");
  assert.equal(freshness({ lastRefresh: null, cacheAge: null, error: "Failed to fetch", now: NOW }).state, "down");
});

test("nothing received yet: no state, no label", () => {
  const f = freshness({ lastRefresh: null, cacheAge: null, error: null, now: NOW });
  assert.equal(f.state, null);
  assert.equal(f.dataTime, null);
  assert.equal(f.ageLabel, "");
  assert.deepEqual(freshnessText(f), { long: "", medium: "", title: "", aria: "" });
});

test("bad inputs do not produce negative or NaN ages", () => {
  const f = freshness({ lastRefresh: NOW + 5000, cacheAge: NaN, now: NOW });
  assert.equal(f.ageS, 0);
  assert.equal(f.ageLabel, "now");
});

test("short and long age labels", () => {
  assert.equal(ageShort(0), "now");
  assert.equal(ageShort(59), "now");
  assert.equal(ageShort(60), "1m");
  assert.equal(ageShort(3599), "59m");
  assert.equal(ageShort(3600), "1h");
  assert.equal(ageShort(86400 * 2), "2d");
  assert.equal(ageLong(30), "just now");
  assert.equal(ageLong(60), "1 minute ago");
  assert.equal(ageLong(120), "2 minutes ago");
  assert.equal(ageLong(7200), "2 hours ago");
  assert.equal(ageLong(86400), "1 day ago");
});

test("clock is 24-hour with leading zeros", () => {
  assert.equal(clockLabel(new Date(2026, 0, 1, 9, 5, 7)), "09:05");
  assert.equal(clockLabel(new Date(2026, 0, 1, 9, 5, 7), true), "09:05:07");
  assert.equal(clockLabel(null), "");
});

test("header texts by width, tooltip and accessible name", () => {
  const f = freshness({ lastRefresh: NOW, cacheAge: 120, now: NOW });   // data from 15:31:34
  const t = freshnessText(f);
  assert.equal(t.long, "Updated 15:31 · 2m");
  assert.equal(t.medium, "15:31 · 2m");
  assert.equal(t.title, "Last scan 15:31:34, 2 minutes ago");
  assert.equal(t.aria, "Updated 2 minutes ago");
  const late = freshnessText(freshness({ lastRefresh: NOW, cacheAge: 1200, now: NOW }));
  assert.equal(late.title, "Last scan 15:13:34, 20 minutes ago (late)");
});
