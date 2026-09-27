import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

// A hex alpha suffix only works on a literal hex colour. Appended to a var(--t-*) token
// (T.border plus "22" renders "var(--t-border)22") it makes the whole declaration invalid,
// so the browser silently drops it. Use alpha(T.x, pct) from theme.js instead.
const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const TOKEN_HEX = /\$\{T\.(bg|surface\w*|border\w*|text[1-4]|accent\w*|overlay\d+|shadow\w*|selectBg|profit|loss|stickyBg)\}[0-9a-fA-F]{2}\b/;
const RATE_HEX = /\$\{rateColor\([^}]*\)\}[0-9a-fA-F]{2}/;
// The login screen keeps its look exactly, including these two invalid colours.
const ALLOW = new Set(["components/AuthGate.jsx"]);

function sources(dir) {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) { if (entry.name !== "node_modules") out.push(...sources(full)); }
    else if (/\.jsx?$/.test(entry.name)) out.push(full);
  }
  return out;
}

test("the guard patterns catch the invalid forms and pass the valid ones", () => {
  const d = "$";
  assert.match(`${d}{T.border}22`, TOKEN_HEX);
  assert.match(`${d}{T.accent}cc`, TOKEN_HEX);
  assert.match(`${d}{T.overlay04}30`, TOKEN_HEX);
  assert.match(`${d}{rateColor(b.win_rate)}30`, RATE_HEX);
  assert.doesNotMatch(`${d}{T.cyan}0a`, TOKEN_HEX, "static hex tokens may take a suffix");
  assert.doesNotMatch(`${d}{T.border}`, TOKEN_HEX);
  assert.doesNotMatch(`1px solid ${d}{T.border} `, TOKEN_HEX);
});

test("no CSS-variable token gets a hex alpha suffix", () => {
  const files = sources(SRC);
  assert.ok(files.length > 50, `scanned ${files.length} files under ${SRC}`);
  const hits = [];
  for (const file of files) {
    const rel = path.relative(SRC, file).split(path.sep).join("/");
    if (ALLOW.has(rel)) continue;
    fs.readFileSync(file, "utf8").split("\n").forEach((line, i) => {
      if (TOKEN_HEX.test(line) || RATE_HEX.test(line)) hits.push(`${rel}:${i + 1}: ${line.trim()}`);
    });
  }
  assert.deepEqual(hits, [], `use alpha(T.x, pct) instead:\n${hits.join("\n")}`);
});
