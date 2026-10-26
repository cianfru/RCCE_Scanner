// Colours for canvas charts, read from the page's own tokens (--t-*, and the --rd-* set scoped to
// .pf-page) so both themes follow without new values.
export function cssVar(el, name) {
  const node = el || (typeof document !== "undefined" ? document.documentElement : null);
  return node ? getComputedStyle(node).getPropertyValue(name).trim() : "";
}

// A colour at an opacity, for a canvas: rgba from hex or rgb(a); anything else unchanged.
export function fade(color, a) {
  const c = String(color || "").trim();
  let m = c.match(/^#([0-9a-f]{6})$/i);
  if (m) {
    const n = parseInt(m[1], 16);
    return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
  }
  m = c.match(/^#([0-9a-f]{3})$/i);
  if (m) {
    const [r, g, b] = m[1].split("").map(h => parseInt(h + h, 16));
    return `rgba(${r},${g},${b},${a})`;
  }
  m = c.match(/^rgba?\(([^)]+)\)$/i);
  if (m) {
    const [r, g, b, a0 = 1] = m[1].split(",").map(s => parseFloat(s));
    return `rgba(${r},${g},${b},${a0 * a})`;
  }
  return c;
}

export function palette(el) {
  const v = n => cssVar(el, n);
  return {
    text1: v("--t-text1"), text2: v("--t-text2"), text3: v("--t-text3"), text4: v("--t-text4"),
    accent: v("--t-accent"), profit: v("--t-profit"), loss: v("--t-loss"), border: v("--t-border"),
    grid: v("--t-chartGrid"), chartText: v("--t-chartText"), cross: v("--t-chartCross"), label: v("--t-chartLabel"),
    bg: v("--t-bg"), red: v("--rd-red"), bandline: v("--rd-bandline"), band: v("--rd-band"),
  };
}
