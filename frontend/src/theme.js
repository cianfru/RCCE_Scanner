// ─── THEME PALETTES ─────────────────────────────────────────────────────────

const DARK = {
  bg:          "#0a0a0c",
  surface:     "rgba(255,255,255,0.05)",
  surfaceH:    "rgba(255,255,255,0.09)",
  border:      "rgba(255,255,255,0.12)",
  borderH:     "rgba(255,255,255,0.20)",
  text1:       "#f5f5f7",
  text2:       "#d1d1d6",
  text3:       "#98989f",
  text4:       "#6e6e73",
  accent:      "#22d3ee",
  accentDim:   "rgba(34,211,238,0.12)",
  // Overlay opacities (white on dark)
  overlay02:   "rgba(255,255,255,0.02)",
  overlay03:   "rgba(255,255,255,0.03)",
  overlay04:   "rgba(255,255,255,0.04)",
  overlay06:   "rgba(255,255,255,0.06)",
  overlay08:   "rgba(255,255,255,0.08)",
  overlay10:   "rgba(255,255,255,0.10)",
  overlay12:   "rgba(255,255,255,0.12)",
  overlay15:   "rgba(255,255,255,0.15)",
  overlay20:   "rgba(255,255,255,0.20)",
  overlay25:   "rgba(255,255,255,0.25)",
  overlay30:   "rgba(255,255,255,0.30)",
  // Shadows
  shadow:      "rgba(0,0,0,0.3)",
  shadowDeep:  "rgba(0,0,0,0.5)",
  shadowHeavy: "rgba(0,0,0,0.85)",
  // Composite backgrounds
  glassBg:     "linear-gradient(180deg, rgba(255,255,255,0.06) 0%, rgba(255,255,255,0.02) 100%)",
  glassInset:  "inset 0 1px 0 rgba(255,255,255,0.04)",
  glassShadow: "0 2px 12px rgba(0,0,0,0.3)",
  headerBg:    "linear-gradient(180deg, rgba(18,18,20,0.92) 0%, rgba(10,10,12,0.88) 100%)",
  popoverBg:   "linear-gradient(180deg, rgba(30,30,34,0.98), rgba(20,20,24,0.98))",
  drawerBg:    "linear-gradient(180deg, rgba(20,20,22,0.92) 0%, rgba(10,10,12,0.94) 100%)",
  selectBg:    "#1c1c1e",
  scrollThumb: "rgba(255,255,255,0.12)",
  scrollHover: "rgba(255,255,255,0.25)",
  // Chart-specific (resolved values for canvas/libraries)
  chartGrid:   "rgba(255,255,255,0.03)",
  chartCross:  "rgba(34,211,238,0.3)",
  chartLabel:  "#1a1a1a",
  chartText:   "#98989f",
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
};

// ─── APPLY THEME (sets CSS custom properties on :root) ──────────────────────

export function applyTheme(mode) {
  const tokens = mode === "light" ? LIGHT : DARK;
  const root = document.documentElement;
  for (const [key, val] of Object.entries(tokens)) {
    root.style.setProperty(`--t-${key}`, val);
  }
  root.dataset.theme = mode;
}

// Apply on module load to prevent flash
applyTheme(localStorage.getItem("rcce-theme") || "dark");

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
  // Static (not theme-dependent)
  font:        "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
  mono:        "'SF Mono', 'Fira Code', monospace",
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
  textXs:   10,   // smallest allowed (no 8-9px)
  textSm:   11,   // secondary labels, captions
  textBase: 12,   // body text, table cells, badges
  textMd:   13,   // emphasized data values
  textLg:   14,   // primary text, nav items
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
  cyan:     "#22d3ee",
  cyanDim:  "#67e8f9",
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
  MARKUP:    { color: "#34d399", bg: "rgba(52,211,153,0.08)", glow: "rgba(52,211,153,0.25)", label: "MARKUP",    glyph: "\u2197" },
  BLOWOFF:   { color: "#f87171", bg: "rgba(248,113,113,0.08)", glow: "rgba(248,113,113,0.25)", label: "BLOWOFF",   glyph: "\u25b2\u25b2" },
  REACC:     { color: "#22d3ee", bg: "rgba(34,211,238,0.08)",  glow: "rgba(34,211,238,0.25)",  label: "REACC",     glyph: "\u25c6" },
  MARKDOWN:  { color: "#fb923c", bg: "rgba(251,146,60,0.08)",  glow: "rgba(251,146,60,0.25)",  label: "MARKDOWN",  glyph: "\u25bc" },
  CAP:       { color: "#c084fc", bg: "rgba(192,132,252,0.08)", glow: "rgba(192,132,252,0.25)", label: "CAP",       glyph: "\u25bc\u25bc" },
  ACCUM:     { color: "#6ee7b7", bg: "rgba(110,231,183,0.08)", glow: "rgba(110,231,183,0.25)", label: "ACCUM",     glyph: "\u25c7" },
  ABSORBING: { color: "#d8b4fe", bg: "rgba(216,180,254,0.08)", glow: "rgba(216,180,254,0.25)", label: "ABSORBING", glyph: "\u2715" },
  FLAT:      { color: "#52525b", bg: "rgba(82,82,91,0.06)",    glow: "rgba(82,82,91,0.15)",    label: "FLAT",      glyph: "\u2014" },
};

// ─── SIGNAL METADATA ────────────────────────────────────────────────────────

export const SIGNAL_META = {
  STRONG_LONG:  { color: "#34d399", label: "STRONG LONG",  dot: "\u25cf" },
  LIGHT_LONG:   { color: "#6ee7b7", label: "LIGHT LONG",   dot: "\u25cf" },
  ACCUMULATE:   { color: "#22d3ee", label: "ACCUMULATE",    dot: "\u25c6" },
  REVIVAL_SEED: { color: "#67e8f9", label: "REVIVAL",       dot: "\u25cf" },
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
  ENTRY:     { color: "#22d3ee", glyph: "\u25b6", label: "ENTRY" },
  EXIT:      { color: "#fb923c", glyph: "\u25a0", label: "EXIT" },
  LATERAL:   { color: "#52525b", glyph: "\u2192", label: "LATERAL" },
  INITIAL:   { color: "#c084fc", glyph: "\u25c6", label: "INITIAL" },
};

// ─── COLOR HELPERS ──────────────────────────────────────────────────────────

export function heatColor(heat) {
  if (heat == null) return "#3f3f46";
  if (heat >= 80) return "#f87171";
  if (heat >= 60) return "#fb923c";
  if (heat >= 40) return "#fbbf24";
  if (heat >= 20) return "#34d399";
  return "#3f3f46";
}

export function phaseColor(phase) {
  return { Exhaustion: "#fbbf24", Entry: "#34d399", Fading: "#fb923c", Extension: "#22d3ee", Neutral: "#52525b" }[phase] || "#52525b";
}

export function exhaustMeta(state) {
  return {
    EXHAUSTED_FLOOR: { color: "#22d3ee", text: "FLOOR" },
    CLIMAX:          { color: "#fbbf24", text: "CLIMAX" },
    ABSORBING:       { color: "#67e8f9", text: "ABSORB" },
    BEAR_ZONE:       { color: "#f87171", text: "BEAR" },
    NEUTRAL:         { color: "#3f3f46", text: "\u2014" },
  }[state] || { color: "#3f3f46", text: "\u2014" };
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
  else if (z <= 0) color = "#22d3ee";
  else if (z <= 1.2) color = "#34d399";
  else if (z <= 2.0) color = "#fbbf24";
  else color = "#f87171";
  return { pct, color };
}

export function getBaseSymbol(sym) {
  if (sym.endsWith("/BTC")) return sym.replace("/BTC", "/\u20bf");
  return sym.replace("/USDT", "");
}

export function formatCacheAge(seconds) {
  if (!seconds) return "\u2014";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  return `${Math.round(seconds / 60)}m`;
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
  "RNDR/USDT": 19, "FET/USDT": 20,
  // 21-30
  "TAO/USDT": 21,  "ATOM/USDT": 22, "STX/USDT": 23, "FIL/USDT": 24,
  "OP/USDT": 25,   "ARB/USDT": 26,  "INJ/USDT": 27, "AAVE/USDT": 28,
  "VET/USDT": 29,  "IMX/USDT": 30,
  // 31-40
  "MKR/USDT": 31,  "GRT/USDT": 32,  "SEI/USDT": 33, "TIA/USDT": 34,
  "WLD/USDT": 35,  "LDO/USDT": 36,  "FTM/USDT": 37, "ALGO/USDT": 38,
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
  "GMT/USDT": 61,  "GALA/USDT": 62, "W/USDT": 63,   "MATIC/USDT": 64,
  "MEME/USDT": 65,
  // BTC pairs (same rank as USDT)
  "ETH/BTC": 2,  "SOL/BTC": 4,  "XRP/BTC": 5,  "ADA/BTC": 7,
  "LINK/BTC": 10, "DOT/BTC": 14, "AVAX/BTC": 8, "DOGE/BTC": 6,
};
