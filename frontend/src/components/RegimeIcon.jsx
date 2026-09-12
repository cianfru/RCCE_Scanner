// One intuitive glyph per market-cycle phase. Icons live here (not in
// theme.js) so theme.js stays React-free for the plain node tests.
import { Layers, TrendingUp, Flame, Repeat, TrendingDown, ArrowDownToLine, Minus } from "lucide-react";

// Absorption: an arrow sinking into liquidity. Lucide has no such glyph, so
// this is drawn in its idiom (24 grid, 2px round stroke, currentColor) and
// exposes the same size/strokeWidth API as the lucide components.
function Absorb({ size = 24, strokeWidth = 2, ...rest }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" {...rest}>
      <path d="M12 3v9" />
      <path d="M8.5 8.5 12 12l3.5-3.5" />
      <path d="M2 16.5q2.5-2 5 0t5 0 5 0 5 0" />
      <path d="M2 20.5q2.5-2 5 0t5 0 5 0 5 0" />
    </svg>
  );
}
import { REGIME_META } from "../theme.js";

const ICONS = {
  ACCUM: Layers,
  MARKUP: TrendingUp,
  BLOWOFF: Flame,
  REACC: Repeat,
  MARKDOWN: TrendingDown,
  CAP: ArrowDownToLine,
  ABSORBING: Absorb,
  FLAT: Minus,
};

export default function RegimeIcon({ regime, size = 14, style }) {
  const Icon = ICONS[regime] || ICONS.FLAT;
  const rm = REGIME_META[regime] || REGIME_META.FLAT;
  return <Icon size={size} strokeWidth={2.25} aria-hidden="true" style={{ color: rm.color, flexShrink: 0, ...style }} />;
}
