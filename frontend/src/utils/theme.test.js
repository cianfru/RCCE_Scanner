import test from "node:test";
import assert from "node:assert/strict";
import { alpha, col, applyTheme, themeVars, T } from "../theme.js";

// theme.js guards `document`, so it imports cleanly under node. applyTheme needs a
// minimal DOM; this stub records what it writes.
function withDom(fn) {
  const props = {};
  const meta = { content: "#04060C", setAttribute(name, value) { if (name === "content") this.content = value; } };
  const saved = globalThis.document;
  globalThis.document = {
    documentElement: { style: { setProperty: (k, v) => { props[k] = v; } }, dataset: {} },
    querySelector: sel => (sel === 'meta[name="theme-color"]' ? meta : null),
  };
  try { return fn({ props, meta, root: globalThis.document.documentElement }); }
  finally {
    applyTheme("dark");
    if (saved === undefined) delete globalThis.document; else globalThis.document = saved;
  }
}

test("alpha mixes any colour, including CSS variables, with transparent", () => {
  assert.equal(alpha("var(--t-accent)", 19), "color-mix(in srgb, var(--t-accent) 19%, transparent)");
  assert.equal(alpha("#34d399", 80), "color-mix(in srgb, #34d399 80%, transparent)");
});

test("col returns the input hex unchanged in dark mode", () => {
  for (const hex of ["#34d399", "#7dd3fc", "#8b8f98", "#123456", "#97FCE4"]) assert.equal(col(hex), hex);
});

test("light mode maps the new hues to their darker equivalents", () => {
  withDom(() => {
    applyTheme("light");
    const expected = {
      "#7dd3fc": "#0369a1", "#fda4af": "#be123c", "#fcd34d": "#a16207", "#8b8f94": "#52525b",
      "#7d9b95": "#4f6f69", "#8b8f98": "#6b7280", "#f3ba2f": "#a16207", "#f7a600": "#b45309",
    };
    for (const [dark, light] of Object.entries(expected)) {
      assert.equal(col(dark), light, dark);
      assert.equal(col(dark.toUpperCase()), light, `${dark} upper-case`);
    }
    assert.equal(col("#34d399"), "#047857", "existing entries still map");
    applyTheme("dark");
    assert.equal(col("#7dd3fc"), "#7dd3fc");
  });
});

test("applyTheme sets the browser theme-color and the new tokens", () => {
  withDom(({ props, meta, root }) => {
    applyTheme("light");
    assert.equal(meta.content, "#ffffff");
    assert.equal(root.dataset.theme, "light");
    assert.equal(props["--t-profit"], "#047857");
    assert.equal(props["--t-loss"], "#dc2626");
    assert.equal(props["--t-stickyBg"], "linear-gradient(rgba(0,0,0,0.04),rgba(0,0,0,0.04)), #ffffff");
    applyTheme("dark");
    assert.equal(meta.content, "#04060C");
    assert.equal(props["--t-profit"], "#34d399");
    assert.equal(props["--t-loss"], "#f87171");
    assert.match(props["--t-stickyBg"], /#04060C$/);
  });
});

test("T references the new tokens and every palette defines them", () => {
  assert.equal(T.profit, "var(--t-profit)");
  assert.equal(T.loss, "var(--t-loss)");
  assert.equal(T.stickyBg, "var(--t-stickyBg)");
  for (const mode of ["dark", "light"]) {
    const vars = themeVars(mode);
    for (const key of ["--t-profit", "--t-loss", "--t-stickyBg"]) assert.ok(vars[key], `${mode} ${key}`);
  }
});
