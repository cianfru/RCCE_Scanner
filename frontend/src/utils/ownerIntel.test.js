import test from "node:test";
import assert from "node:assert/strict";
import { ago, areaPath, cellAlpha, countryName, firstDir, inviteStatus, linePath, monthStarts, niceMax, pct, points, shortDate, sortPeople } from "./ownerIntel.js";

const NOW = Date.UTC(2026, 8, 30, 12) / 1000;

test("numbers and dates", () => {
  assert.equal(pct(0.5454), "55%");
  assert.equal(pct(null), "—");
  assert.equal(shortDate("2026-08-12"), "12 Aug");
  assert.equal(shortDate(NOW), "30 Sep");
  assert.equal(ago(NOW - 30, NOW), "now");
  assert.equal(ago(NOW - 600, NOW), "10m");
  assert.equal(ago(NOW - 3 * 3600, NOW), "3h");
  assert.equal(ago(NOW - 2 * 86400, NOW), "2d");
  assert.equal(ago(NOW - 40 * 86400, NOW), "21 Aug");
  assert.equal(ago(null, NOW), "—");
  assert.equal(countryName("IT"), "Italy");
  assert.equal(countryName(null), "Unknown");
});

test("people sort: by column, never-seen last either way", () => {
  const people = [
    { label: "b", first_seen: 10, last_seen: 50, d7: 2, country: "IT" },
    { label: "a", first_seen: 20, last_seen: 90, d7: 5, country: "DE" },
    { label: "c", first_seen: null, last_seen: null, d7: 0, country: null },
  ];
  assert.deepEqual(sortPeople(people).map(p => p.label), ["a", "b", "c"]);
  assert.deepEqual(sortPeople(people, "last_seen", "asc").map(p => p.label), ["b", "a", "c"]);
  assert.deepEqual(sortPeople(people, "d7", "asc").map(p => p.label), ["b", "a", "c"]);
  assert.deepEqual(sortPeople(people, "country", "asc").map(p => p.label), ["a", "b", "c"]);
  assert.deepEqual(sortPeople(people, "label", "desc").map(p => p.label), ["c", "b", "a"]);
  assert.equal(firstDir("label"), "asc");
  assert.equal(firstDir("d28"), "desc");
});

test("chart geometry", () => {
  assert.equal(niceMax(0), 4);
  assert.equal(niceMax(9), 10);
  assert.equal(niceMax(13), 20);
  assert.equal(niceMax(23), 25);
  const pts = points([0, 5, 10], 100, 50, 10);
  assert.deepEqual(pts, [[0, 50], [50, 25], [100, 0]]);
  assert.equal(linePath(pts), "M0.0 50.0L50.0 25.0L100.0 0.0");
  assert.equal(areaPath(pts, 50), "M0.0 50.0L50.0 25.0L100.0 0.0L100.0 50L0.0 50Z");
  assert.deepEqual(points([], 10, 10, 1), []);
  assert.deepEqual(monthStarts([{ day: "2026-08-31" }, { day: "2026-09-01" }]), [{ i: 1, label: "Sep" }]);
});

test("invite states and retention cells", () => {
  assert.equal(inviteStatus({ revoked: NOW - 5 }, NOW).key, "revoked");
  assert.equal(inviteStatus({ expires: NOW - 5 }, NOW).key, "expired");
  assert.equal(inviteStatus({ expires: NOW + 12 * 86400 - 60 }, NOW).text, "12d left");
  assert.equal(inviteStatus({}, NOW).key, "active");
  assert.equal(cellAlpha(0), 0);
  assert.ok(cellAlpha(0.01) >= 0.18);
  assert.equal(cellAlpha(1), 1);
});
