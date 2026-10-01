// ─── THEME PALETTES ─────────────────────────────────────────────────────────

// Hyperliquid palette — Aquamarine #97FCE4, Firefly #0F3933, Ebony #04060C,
// Foam #F5FEFD. Matches the marketing landing.
const DARK = {
  bg:          "#04060C",
  surface:     "rgba(15,57,51,0.32)",
  surfaceH:    "rgba(15,57,51,0.55)",
  border:      "rgba(151,252,228,0.16)",
  borderH:     "rgba(151,252,228,0.30)",
  text1:       "#F5FEFD",
  text2:       "rgba(245,254,253,0.82)",
  text3:       "rgba(245,254,253,0.60)",
  text4:       "rgba(245,254,253,0.58)",
  accent:      "#97FCE4",
  accentDim:   "rgba(151,252,228,0.12)",
  // Overlay opacities (aquamarine on ebony)
  overlay02:   "rgba(151,252,228,0.02)",
  overlay03:   "rgba(151,252,228,0.03)",
  overlay04:   "rgba(151,252,228,0.04)",
  overlay06:   "rgba(151,252,228,0.06)",
  overlay08:   "rgba(151,252,228,0.08)",
  overlay10:   "rgba(151,252,228,0.10)",
  overlay12:   "rgba(151,252,228,0.12)",
  overlay15:   "rgba(151,252,228,0.15)",
  overlay20:   "rgba(151,252,228,0.20)",
  overlay25:   "rgba(151,252,228,0.25)",
  overlay30:   "rgba(151,252,228,0.30)",
  // Shadows
  shadow:      "rgba(0,0,0,0.35)",
  shadowDeep:  "rgba(0,0,0,0.55)",
  shadowHeavy: "rgba(0,0,0,0.88)",
  // Composite backgrounds
  glassBg:     "linear-gradient(180deg, rgba(15,57,51,0.30) 0%, rgba(15,57,51,0.10) 100%)",
  glassInset:  "inset 0 1px 0 rgba(245,254,253,0.06)",
  glassShadow: "0 2px 12px rgba(0,0,0,0.35)",
  headerBg:    "linear-gradient(180deg, rgba(9,20,18,0.92) 0%, rgba(4,6,12,0.9) 100%)",
  popoverBg:   "linear-gradient(180deg, rgba(12,25,22,0.98), rgba(6,12,14,0.98))",
  drawerBg:    "linear-gradient(180deg, rgba(10,22,20,0.94) 0%, rgba(4,6,12,0.95) 100%)",
  selectBg:    "#0a1512",
  scrollThumb: "rgba(151,252,228,0.16)",
  scrollHover: "rgba(151,252,228,0.30)",
  // Chart-specific (resolved values for canvas/libraries)
  chartGrid:   "rgba(151,252,228,0.04)",
  chartCross:  "rgba(151,252,228,0.35)",
  chartLabel:  "#04060C",
  chartText:   "rgba(245,254,253,0.60)",
  // P&L and the opaque sticky-row background (surface tint composited over bg)
  profit:      "#34d399",
  loss:        "#f87171",
  stickyBg:    "linear-gradient(rgba(15,57,51,0.32),rgba(15,57,51,0.32)), linear-gradient(rgba(15,57,51,0.30),rgba(15,57,51,0.30)), #04060C",
  // Brushed metal (metal_rules.md): the header plate, the wordmark, the selected-tab steel bar
  // and the one machined edge on a page's hero card. Never on data. terminal.css composes them.
  metalPlateHi:      "#0f1f1a",
  metalPlateMid:     "#0a1613",
  metalPlateLo:      "#060e0c",
  metalSheen:        "rgba(200,255,236,.08)",
  metalShadeTop:     "rgba(235,255,249,.045)",
  metalShadeLo:      "rgba(0,0,0,.18)",
  metalRim:          "rgba(170,252,231,.22)",
  metalRimLo:        "rgba(151,252,228,.08)",
  metalRimHot:       "rgba(222,255,247,.78)",
  metalRimHotLo:     "rgba(222,255,247,0)",
  metalRimFoot:      "rgba(151,252,228,0)",
  metalBevel:        "inset 0 1px 0 rgba(225,255,247,.05), inset 0 -1px 0 rgba(0,0,0,.32)",
  metalDrop:         "0 1px 0 rgba(0,0,0,.4), 0 12px 32px -12px rgba(0,0,0,.6)",
  metalMarkShadow:   "drop-shadow(0 1px 1.5px rgba(0,0,0,.5))",
  metalEdgeLo:       "rgba(70,120,108,.45)",
  metalEdgeMid:      "rgba(120,172,158,.70)",
  metalEdgeHi:       "rgba(186,232,217,.85)",
  metalEdgeSpec:     "rgba(236,255,249,.95)",
  metalEdgeShade:    "rgba(0,0,0,.40)",
  metalBar:          "linear-gradient(90deg,#5fb3a0 0%,#97fce4 22%,#d2fff3 38%,#a9fce8 54%,#86e6cf 76%,#5fb3a0 100%)",
  metalBarBevel:     "rgba(255,255,255,.34)",
  metalType:         "linear-gradient(90deg,#c2ded6 0%,#f4fffc 14%,#d4ebe4 27%,#aecfc5 41%,#e6f8f3 56%,#f8fffd 63%,#bcd9d0 78%,#eefcf8 91%,#cfe6df 100%)",
  metalTypeHorizon:  "linear-gradient(180deg,#fff 0%,#fff 42%,#d6e3df 58%,#f4f8f7 100%)",
};

const LIGHT = {
  bg:          "#ffffff",
  surface:     "rgba(0,0,0,0.04)",
  surfaceH:    "rgba(0,0,0,0.07)",
  border:      "rgba(0,0,0,0.15)",
  borderH:     "rgba(0,0,0,0.25)",
  text1:       "#000000",
  text2:       "#1c1c1e",
  text3:       "#48484a",
  text4:       "#636366",
  accent:      "#0e7490",
  accentDim:   "rgba(14,116,144,0.10)",
  // Overlay opacities (black on light)
  overlay02:   "rgba(0,0,0,0.02)",
  overlay03:   "rgba(0,0,0,0.03)",
  overlay04:   "rgba(0,0,0,0.04)",
  overlay06:   "rgba(0,0,0,0.05)",
  overlay08:   "rgba(0,0,0,0.06)",
  overlay10:   "rgba(0,0,0,0.08)",
  overlay12:   "rgba(0,0,0,0.10)",
  overlay15:   "rgba(0,0,0,0.13)",
  overlay20:   "rgba(0,0,0,0.16)",
  overlay25:   "rgba(0,0,0,0.20)",
  overlay30:   "rgba(0,0,0,0.24)",
  // Shadows
  shadow:      "rgba(0,0,0,0.08)",
  shadowDeep:  "rgba(0,0,0,0.14)",
  shadowHeavy: "rgba(0,0,0,0.30)",
  // Composite backgrounds
  glassBg:     "linear-gradient(180deg, rgba(255,255,255,0.85) 0%, rgba(255,255,255,0.65) 100%)",
  glassInset:  "inset 0 1px 0 rgba(255,255,255,0.7)",
  glassShadow: "0 2px 12px rgba(0,0,0,0.08)",
  headerBg:    "linear-gradient(180deg, rgba(255,255,255,0.94) 0%, rgba(245,245,247,0.90) 100%)",
  popoverBg:   "linear-gradient(180deg, rgba(255,255,255,0.98), rgba(248,248,250,0.98))",
  drawerBg:    "linear-gradient(180deg, rgba(255,255,255,0.95) 0%, rgba(248,248,250,0.98) 100%)",
  selectBg:    "#ffffff",
  scrollThumb: "rgba(0,0,0,0.15)",
  scrollHover: "rgba(0,0,0,0.30)",
  // Chart-specific (resolved values for canvas/libraries)
  chartGrid:   "rgba(0,0,0,0.06)",
  chartCross:  "rgba(14,116,144,0.3)",
  chartLabel:  "#f5f5f7",
  chartText:   "#48484a",
  // P&L and the opaque sticky-row background (surface tint composited over bg)
  profit:      "#047857",
  loss:        "#dc2626",
  stickyBg:    "linear-gradient(rgba(0,0,0,0.04),rgba(0,0,0,0.04)), #ffffff",
  // Brushed metal, light: flat satin; highlights are a rise in the #0e7490 teal, never white on white.
  metalPlateHi:      "#fdfefe",
  metalPlateMid:     "#f8fbfa",
  metalPlateLo:      "#f3f7f6",
  metalSheen:        "rgba(255,255,255,.75)",
  metalShadeTop:     "rgba(255,255,255,0)",
  metalShadeLo:      "rgba(0,0,0,0)",
  metalRim:          "rgba(0,30,26,.12)",
  metalRimLo:        "rgba(0,30,26,.15)",
  metalRimHot:       "rgba(14,116,144,.60)",
  metalRimHotLo:     "rgba(14,116,144,0)",
  metalRimFoot:      "rgba(14,116,144,.20)",
  metalBevel:        "inset 0 1px 0 #fff",
  metalDrop:         "0 8px 24px -14px rgba(0,40,30,.12)",
  metalMarkShadow:   "none",
  metalEdgeLo:       "rgba(14,116,144,.14)",
  metalEdgeMid:      "rgba(14,116,144,.30)",
  metalEdgeHi:       "rgba(14,116,144,.50)",
  metalEdgeSpec:     "rgba(14,116,144,.72)",
  metalEdgeShade:    "rgba(0,0,0,0)",
  metalBar:          "linear-gradient(90deg,#0b5a69 0%,#1f7f91 24%,#5fb0bd 40%,#268a9c 56%,#0f6b7c 78%,#0b5a69 100%)",
  metalBarBevel:     "rgba(255,255,255,.30)",
  metalType:         "linear-gradient(90deg,#1d2a27 0%,#3a4c47 14%,#18231f 27%,#080d0c 41%,#2c3b37 56%,#34463f 63%,#121b19 78%,#2d3d38 91%,#1b2724 100%)",
  metalTypeHorizon:  "linear-gradient(180deg,#fff 0%,#fff 44%,#dfe6e4 60%,#fff 100%)",
};

// ─── APPLY THEME (sets CSS custom properties on :root) ──────────────────────

// Dark-theme hues are pastel for a near-black background; on white they fall
// below readable contrast. col() maps each product hue to a darker equivalent in
// light mode; applyTheme repaints the shared colour tables in place, and the
// colour helpers below call col() at render time.
const LIGHT_HUES = {
  "#34d399": "#047857", "#6ee7b7": "#0f766e", "#f87171": "#dc2626", "#ef4444": "#b91c1c",
  "#fbbf24": "#b45309", "#97fce4": "#0e7490", "#b8fff0": "#0f766e", "#c084fc": "#7e22ce",
  "#d8b4fe": "#8b5cf6", "#fb923c": "#c2410c", "#52525b": "#6b7280", "#3f3f46": "#a1a1aa",
  "#71717a": "#6b7280", "#cf9185": "#b4533f", "#b5a5db": "#6d5bb0", "#91b9e8": "#2f6fb5",
  "#e3b341": "#a16207", "#facc15": "#a16207", "#d8a094": "#b4533f", "#a78bfa": "#6d28d9",
  "#c4b5fd": "#6d28d9", "#c6a46d": "#8a6a2f", "#b6a07c": "#7a6440",
  "#7dd3fc": "#0369a1", "#fda4af": "#be123c", "#fcd34d": "#a16207", "#8b8f94": "#52525b",
  "#7d9b95": "#7f9993", "#8b8f98": "#6b7280", "#f3ba2f": "#a16207", "#f7a600": "#b45309",
};
let currentMode = "dark";

// A translucent version of any colour, including var(--t-*) tokens: `${T.x}NN` hex
// suffixes only work on literal hex values and silently drop the whole declaration otherwise.
export function alpha(color, pct) {
  return `color-mix(in srgb, ${color} ${pct}%, transparent)`;
}

export const isLightMode = () => currentMode === "light";

export function col(hex) {
  return currentMode === "light" ? (LIGHT_HUES[String(hex).toLowerCase()] || hex) : hex;
}
const darkCopies = new WeakMap();
function repaint(meta, keys) {
  if (!darkCopies.has(meta)) darkCopies.set(meta, { ...meta });
  const dark = darkCopies.get(meta);
  for (const key of keys) if (typeof dark[key] === "string") meta[key] = col(dark[key]);
  if (dark.bg && dark.color) {
    meta.bg = currentMode === "light" ? `${col(dark.color)}12` : dark.bg;
    meta.glow = currentMode === "light" ? `${col(dark.color)}26` : dark.glow;
  }
}

export function applyTheme(mode) {
  currentMode = mode === "light" ? "light" : "dark";
  for (const table of [REGIME_META, SIGNAL_META, TRANSITION_META]) {
    for (const meta of Object.values(table)) repaint(meta, ["color"]);
  }
  repaint(T, ["green", "greenDim", "red", "redDark", "yellow", "cyan", "cyanDim", "purple", "purpleDim", "orange", "gray", "grayDim"]);
  const tokens = mode === "light" ? LIGHT : DARK;
  const root = document.documentElement;
  for (const [key, val] of Object.entries(tokens)) {
    root.style.setProperty(`--t-${key}`, val);
  }
  root.dataset.theme = mode;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", mode === "light" ? "#ffffff" : "#04060C");
}

// One palette's raw token value (for SVG paint that cannot use a CSS gradient, like the metal wordmark).
export function themeToken(mode, key) {
  return (mode === "light" ? LIGHT : DARK)[key];
}

// The --t-* variables of one palette as an inline style, for a block that keeps its
// colours whatever the app theme is (the always-dark landing embeds the terminal table).
export function themeVars(mode) {
  const tokens = mode === "light" ? LIGHT : DARK;
  return Object.fromEntries(Object.entries(tokens).map(([key, val]) => [`--t-${key}`, val]));
}


// ─── DESIGN TOKENS (CSS variable references) ───────────────────────────────

export const T = {
  // Colors (theme-dependent → CSS vars)
  bg:          "var(--t-bg)",
  surface:     "var(--t-surface)",
  surfaceH:    "var(--t-surfaceH)",
  border:      "var(--t-border)",
  borderH:     "var(--t-borderH)",
  text1:       "var(--t-text1)",
  text2:       "var(--t-text2)",
  text3:       "var(--t-text3)",
  text4:       "var(--t-text4)",
  accent:      "var(--t-accent)",
  accentDim:   "var(--t-accentDim)",
  // Overlays
  overlay02:   "var(--t-overlay02)",
  overlay03:   "var(--t-overlay03)",
  overlay04:   "var(--t-overlay04)",
  overlay06:   "var(--t-overlay06)",
  overlay08:   "var(--t-overlay08)",
  overlay10:   "var(--t-overlay10)",
  overlay12:   "var(--t-overlay12)",
  overlay15:   "var(--t-overlay15)",
  overlay20:   "var(--t-overlay20)",
  overlay25:   "var(--t-overlay25)",
  overlay30:   "var(--t-overlay30)",
  // Shadows
  shadow:      "var(--t-shadow)",
  shadowDeep:  "var(--t-shadowDeep)",
  shadowHeavy: "var(--t-shadowHeavy)",
  // Composite backgrounds
  glassBg:     "var(--t-glassBg)",
  glassInset:  "var(--t-glassInset)",
  glassShadow: "var(--t-glassShadow)",
  headerBg:    "var(--t-headerBg)",
  popoverBg:   "var(--t-popoverBg)",
  drawerBg:    "var(--t-drawerBg)",
  selectBg:    "var(--t-selectBg)",
  scrollThumb: "var(--t-scrollThumb)",
  scrollHover: "var(--t-scrollHover)",
  profit:      "var(--t-profit)",
  loss:        "var(--t-loss)",
  stickyBg:    "var(--t-stickyBg)",
  // Static (not theme-dependent)
  font:        "'Geist', -apple-system, BlinkMacSystemFont, sans-serif",
  mono:        "'Geist Mono', 'SF Mono', monospace",
  radius:      "14px",
  radiusSm:    "10px",
  radiusXs:    "8px",

  // ─── SPACING SCALE (4px grid) ─────────────────────────────────────────────
  sp1:  4,
  sp2:  8,
  sp3:  12,
  sp4:  16,
  sp5:  20,
  sp6:  24,
  sp8:  32,
  sp10: 40,

  // ─── TYPE SCALE ───────────────────────────────────────────────────────────
  textXs:   12,   // smallest allowed
  textSm:   13,   // secondary labels, captions
  textBase: 14,   // body text, table cells, badges
  textMd:   14,   // emphasized data values
  textLg:   15,   // primary text, nav items
  textXl:   18,   // section titles
  text2xl:  24,   // stat card numbers
  text3xl:  32,   // hero display (if needed)

  // ─── MOBILE TYPE SCALE (use with isMobile) ────────────────────────────────
  mTextXs:   12,   // was 10 — minimum readable on mobile
  mTextSm:   13,   // was 11
  mTextBase: 14,   // was 12 — body text
  mTextMd:   15,   // was 13
  mTextLg:   16,   // was 14
  mTextXl:   20,   // was 18 — section titles
  mText2xl:  28,   // was 24 — stat card numbers
  mText3xl:  36,   // was 32

  // ─── SEMANTIC COLORS (static) ─────────────────────────────────────────────
  green:    "#34d399",
  greenDim: "#6ee7b7",
  red:      "#f87171",
  redDark:  "#ef4444",
  yellow:   "#fbbf24",
  cyan:     "#97FCE4",
  cyanDim:  "#b8fff0",
  purple:   "#c084fc",
  purpleDim:"#d8b4fe",
  orange:   "#fb923c",
  gray:     "#52525b",
  grayDim:  "#3f3f46",
};

/** Return mobile-scaled font size: `m(T.textBase, isMobile)` → 14 on mobile, 12 on desktop */
export function m(desktopSize, isMobile) {
  if (!isMobile) return desktopSize;
  const MAP = { 10: 12, 11: 13, 12: 14, 13: 15, 14: 16, 18: 20, 24: 28, 32: 36 };
  return MAP[desktopSize] || Math.round(desktopSize * 1.18);
}

// Helper to get resolved CSS variable value (for canvas/library APIs)
export function resolveToken(key) {
  return getComputedStyle(document.documentElement).getPropertyValue(`--t-${key}`).trim();
}

// ─── REGIME METADATA ────────────────────────────────────────────────────────

export const REGIME_META = {
  MARKUP:    { color: "#97FCE4", bg: "rgba(151,252,228,0.055)", glow: "rgba(151,252,228,0.12)", label: "MARKUP", name: "Uptrend", hint: "Price trending above its mean",    glyph: "\u2197" },
  BLOWOFF:   { color: "#f87171", bg: "rgba(248,113,113,0.08)", glow: "rgba(248,113,113,0.25)", label: "BLOWOFF", name: "Overheated", hint: "Extreme overextension — reversal risk",   glyph: "\u25b2\u25b2" },
  REACC:     { color: "#b5a5db", bg: "rgba(181,165,219,0.055)", glow: "rgba(181,165,219,0.12)",  label: "REACC", name: "Re-accumulating", hint: "Pullback within an uptrend",     glyph: "\u25c6" },
  MARKDOWN:  { color: "#cf9185", bg: "rgba(207,145,133,0.055)", glow: "rgba(207,145,133,0.12)",  label: "MARKDOWN", name: "Downtrend", hint: "Price trending below its mean",  glyph: "\u25bc" },
  CAP:       { color: "#c084fc", bg: "rgba(192,132,252,0.08)", glow: "rgba(192,132,252,0.25)", label: "CAP", name: "Capitulation", hint: "Panic flush toward a floor",       glyph: "\u25bc\u25bc" },
  ACCUM:     { color: "#91b9e8", bg: "rgba(145,185,232,0.055)", glow: "rgba(145,185,232,0.12)", label: "ACCUM", name: "Accumulation", hint: "Building a base after a decline",     glyph: "\u25c7" },
  ABSORBING: { color: "#d8b4fe", bg: "rgba(216,180,254,0.08)", glow: "rgba(216,180,254,0.25)", label: "ABSORBING", name: "Absorbing", hint: "Supply being absorbed — no long", glyph: "\u2715" },
  FLAT:      { color: "#52525b", bg: "rgba(82,82,91,0.06)",    glow: "rgba(82,82,91,0.15)",    label: "FLAT", name: "Flat", hint: "No clear regime",      glyph: "\u2014" },
};

// ─── SIGNAL METADATA ────────────────────────────────────────────────────────

export const SIGNAL_META = {
  LIGHT_SHORT:  { color: "#cf9185", label: "LIGHT SHORT", dot: "\u25cf" },
  STRONG_SHORT: { color: "#f87171", label: "STRONG SHORT", dot: "\u25cf" },
  REVIVAL_SEED_CONFIRMED: { color: "#b8fff0", label: "REVIVAL CONFIRMED", dot: "\u25cf" },
  STRONG_LONG:  { color: "#34d399", label: "STRONG LONG",  dot: "\u25cf" },
  LIGHT_LONG:   { color: "#6ee7b7", label: "LIGHT LONG",   dot: "\u25cf" },
  ACCUMULATE:   { color: "#97FCE4", label: "ACCUMULATE",    dot: "\u25c6" },
  REVIVAL_SEED: { color: "#b8fff0", label: "REVIVAL",       dot: "\u25cf" },
  WAIT:         { color: "#52525b", label: "WAIT",          dot: "\u25cb" },
  TRIM:         { color: "#fbbf24", label: "TRIM",          dot: "\u25cf" },
  TRIM_HARD:    { color: "#f87171", label: "TRIM HARD",     dot: "\u25cf" },
  RISK_OFF:     { color: "#ef4444", label: "RISK-OFF",      dot: "\u25cf" },
  NO_LONG:      { color: "#d8b4fe", label: "NO LONG",       dot: "\u2715" },
};

export const REGIME_ORDER = ["BLOWOFF","MARKUP","REACC","ACCUM","CAP","MARKDOWN","ABSORBING","FLAT"];

// ─── TRANSITION METADATA ───────────────────────────────────────────────────

export const TRANSITION_META = {
  UPGRADE:   { color: "#34d399", glyph: "\u2191", label: "UPGRADE" },
  DOWNGRADE: { color: "#f87171", glyph: "\u2193", label: "DOWNGRADE" },
  ENTRY:     { color: "#97FCE4", glyph: "\u25b6", label: "ENTRY" },
  EXIT:      { color: "#fb923c", glyph: "\u25a0", label: "EXIT" },
  LATERAL:   { color: "#52525b", glyph: "\u2192", label: "LATERAL" },
  INITIAL:   { color: "#c084fc", glyph: "\u25c6", label: "INITIAL" },
};

// ─── COLOR HELPERS ──────────────────────────────────────────────────────────

// Neutral readings use the secondary text colour: the old greys read as missing data.
export function heatColor(heat) {
  if (heat == null) return T.text3;
  if (heat >= 80) return col("#f87171");
  if (heat >= 60) return col("#fb923c");
  if (heat >= 40) return col("#fbbf24");
  if (heat >= 20) return col("#34d399");
  return T.text3;
}

export function phaseColor(phase) {
  const hue = { Exhaustion: "#fbbf24", Entry: "#34d399", Fading: "#fb923c", Extension: "#97FCE4" }[phase];
  return hue ? col(hue) : T.text3;
}

export function exhaustMeta(state) {
  const meta = {
    EXHAUSTED_FLOOR: { color: "#97FCE4", text: "FLOOR" },
    CLIMAX:          { color: "#fbbf24", text: "CLIMAX" },
    ABSORBING:       { color: "#b8fff0", text: "ABSORB" },
    BEAR_ZONE:       { color: "#f87171", text: "BEAR" },
    NEUTRAL:         { color: null, text: "\u2014" },
  }[state] || { color: null, text: "\u2014" };
  return { ...meta, color: meta.color ? col(meta.color) : T.text3 };
}

// ─── FORMAT HELPERS ─────────────────────────────────────────────────────────

export function fmt(val, decimals = 2, suffix = "") {
  if (val === null || val === undefined || isNaN(val)) return "\u2014";
  return `${Number(val).toFixed(decimals)}${suffix}`;
}

export function zBar(z) {
  if (z === null || z === undefined) return null;
  const clamped = Math.max(-3, Math.min(3, z));
  const pct = ((clamped + 3) / 6) * 100;
  let color = "#71717a";
  if (z <= -1) color = "#c084fc";
  else if (z <= 0) color = "#97FCE4";
  else if (z <= 1.2) color = "#34d399";
  else if (z <= 2.0) color = "#fbbf24";
  else color = "#fb923c";   // stretched, not bearish: red is kept for downside
  return { pct, color: col(color) };
}

export function getBaseSymbol(sym) {
  if (sym.endsWith("/BTC")) return sym.replace("/BTC", "/\u20bf");
  return sym.split("/")[0];
}

// Coins where Binance's TradingView chart carries old/delisted ticker history
// that would confuse the chart. Map to an exchange that only has the current token.
const _TV_EXCHANGE_OVERRIDES = {
  "OMNI": "COINBASE",  // Binance OMNIUSDT shows OmniLayer (2019-2021) + Omni Network (2024+)
};

// onBinance: the market has a Binance perp (positioning.source === "binance").
// Without one the BINANCE ticker does not exist, so there is no chart to link (null).
export function getTVSymbol(sym, onBinance = true) {
  const base = getBaseSymbol(sym).replace("/\u20bf", ""); // strip /₿ if BTC-quoted
  if (!onBinance && !_TV_EXCHANGE_OVERRIDES[base]) return null;
  const exchange = _TV_EXCHANGE_OVERRIDES[base] || "BINANCE";
  const quote = exchange === "COINBASE" ? "USD" : sym.endsWith("/BTC") ? "BTC" : "USDT";
  return `${exchange}:${base}${quote}`;
}

// ─── MARKET CAP RANK (static lookup for default sort) ──────────────────────

export const MCAP_RANK = {
  // Top 10
  "BTC/USDT": 1,  "ETH/USDT": 2,  "BNB/USDT": 3,  "SOL/USDT": 4,
  "XRP/USDT": 5,  "DOGE/USDT": 6,  "ADA/USDT": 7,  "AVAX/USDT": 8,
  "TRX/USDT": 9,  "LINK/USDT": 10,
  // 11-20
  "TON/USDT": 11, "SUI/USDT": 12, "HBAR/USDT": 13, "DOT/USDT": 14,
  "NEAR/USDT": 15, "ICP/USDT": 16, "UNI/USDT": 17, "APT/USDT": 18,
  "RENDER/USDT": 19, "FET/USDT": 20,
  // 21-30
  "TAO/USDT": 21,  "ATOM/USDT": 22, "STX/USDT": 23, "FIL/USDT": 24,
  "OP/USDT": 25,   "ARB/USDT": 26,  "INJ/USDT": 27, "AAVE/USDT": 28,
  "VET/USDT": 29,  "IMX/USDT": 30,
  // 31-40
  "MKR/USDT": 31,  "GRT/USDT": 32,  "SEI/USDT": 33, "TIA/USDT": 34,
  "WLD/USDT": 35,  "LDO/USDT": 36,  "S/USDT": 37, "ALGO/USDT": 38,
  "RUNE/USDT": 39, "SHIB/USDT": 40,
  // 41-50
  "PEPE/USDT": 41, "DYDX/USDT": 42, "ENS/USDT": 43, "WIF/USDT": 44,
  "BONK/USDT": 45, "FLOKI/USDT": 46, "PYTH/USDT": 47, "JUP/USDT": 48,
  "JTO/USDT": 49,  "STRK/USDT": 50,
  // 51-60
  "BLUR/USDT": 51, "ORDI/USDT": 52, "CRV/USDT": 53, "SNX/USDT": 54,
  "COMP/USDT": 55, "OCEAN/USDT": 56, "SAND/USDT": 57, "MANA/USDT": 58,
  "AXS/USDT": 59,  "CAKE/USDT": 60,
  // 61-70
  "GMT/USDT": 61,  "GALA/USDT": 62, "W/USDT": 63,   "POL/USDT": 64,
  "MEME/USDT": 65,
  // BTC pairs (same rank as USDT)
  "ETH/BTC": 2,  "SOL/BTC": 4,  "XRP/BTC": 5,  "ADA/BTC": 7,
  "LINK/BTC": 10, "DOT/BTC": 14, "AVAX/BTC": 8, "DOGE/BTC": 6,
};

// Apply on module load to prevent flash (after the colour tables exist).
if (typeof document !== "undefined") applyTheme(localStorage.getItem("rcce-theme") || "dark");   // no DOM under node tests
