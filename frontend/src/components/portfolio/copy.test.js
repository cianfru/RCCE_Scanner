// Words the Portfolio page never shows (Portfolio v2, section 7): a case-insensitive, word-boundary
// scan of every string literal and JSX text in copy.js and portfolio/*.jsx.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";

const DIR = new URL("./", import.meta.url);
const files = ["copy.js", ...readdirSync(DIR).filter(f => f.endsWith(".jsx"))];
const BANNED = [
  /\bwill\b/i, /\bexpect\w*/i, /\blikely\b/i, /\bpredict\w*/i, /\btarget\w*/i, /\bprobabilit\w*/i, /\bodds\b/i,
  /\blarsson\b/i, /\bwarning:/i, /\bconsider\b/i, /\brisk of\b/i, /\bexit board\b/i, /\bexit reading\b/i, /\blive\b/i,
  /\b(you should|consider|time to) close\b/i, /\bclose (it|this|your|now)\b/i,
];

// String literals ("...", '...', `...`) and JSX text between tags, with comments removed.
function texts(src) {
  const code = src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'`])\/\/.*$/gm, "$1");
  const out = [];
  for (const m of code.matchAll(/"((?:[^"\\\n]|\\.)*)"|'((?:[^'\\\n]|\\.)*)'|`((?:[^`\\]|\\.)*)`/g)) out.push(m[1] ?? m[2] ?? m[3]);
  for (const m of code.matchAll(/>([^<>{}]*[A-Za-z][^<>{}]*)</g)) out.push(m[1]);
  return out;
}

test("the scan reads strings and JSX text", () => {
  assert.deepEqual(texts(`const a = "One will"; // will in a comment\n<b>Two</b>`), ["One will", "Two"]);
  assert.ok(files.includes("PortfolioPage.jsx") && files.length > 10, files.join(","));
});

for (const f of files) {
  test(`no banned words in ${f}`, () => {
    const hits = [];
    for (const t of texts(readFileSync(new URL(f, DIR), "utf8"))) {
      for (const re of BANNED) if (re.test(t)) hits.push(`${re} in "${t.slice(0, 80)}"`);
    }
    assert.deepEqual(hits, []);
  });
}
