// ─── DESIGN TOKENS ───────────────────────────────────────────────────────────

export const T = {
  bg:        "#0a0a0c",
  surface:   "rgba(255,255,255,0.05)",
  surfaceH:  "rgba(255,255,255,0.09)",
  border:    "rgba(255,255,255,0.12)",
  borderH:   "rgba(255,255,255,0.20)",
  text1:     "#f5f5f7",
  text2:     "#d1d1d6",
  text3:     "#98989f",
  text4:     "#6e6e73",
  accent:    "#22d3ee",
  accentDim: "rgba(34,211,238,0.12)",
  font:      "'SF Pro Display', -apple-system, BlinkMacSystemFont, 'Inter', sans-serif",
  mono:      "'SF Mono', 'JetBrains Mono', 'Fira Code', monospace",
  radius:    "14px",
  radiusSm:  "10px",
  radiusXs:  "8px",
};

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
