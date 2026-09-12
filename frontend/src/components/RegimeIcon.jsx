// One intuitive glyph per market-cycle phase. Icons live here (not in
// theme.js) so theme.js stays React-free for the plain node tests.
import { Layers, TrendingUp, Flame, Repeat, TrendingDown, ArrowDownToLine, CircleSlash, Minus } from "lucide-react";
import { REGIME_META } from "../theme.js";

const ICONS = {
  ACCUM: Layers,
  MARKUP: TrendingUp,
  BLOWOFF: Flame,
  REACC: Repeat,
  MARKDOWN: TrendingDown,
  CAP: ArrowDownToLine,
  ABSORBING: CircleSlash,
  FLAT: Minus,
};

export default function RegimeIcon({ regime, size = 14, style }) {
  const Icon = ICONS[regime] || ICONS.FLAT;
  const rm = REGIME_META[regime] || REGIME_META.FLAT;
  return <Icon size={size} strokeWidth={2.25} aria-hidden="true" style={{ color: rm.color, flexShrink: 0, ...style }} />;
}
