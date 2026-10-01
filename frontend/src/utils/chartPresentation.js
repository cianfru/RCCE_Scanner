export function candleChange(candle) {
  if (!candle || !Number.isFinite(candle.open) || candle.open <= 0 || !Number.isFinite(candle.close)) return null;
  return (candle.close - candle.open) / candle.open * 100;
}

// The chart's Trend line in words: the engine's baseline (/api/chart `trend`). 1D bars are days.
export function trendNote(trend, tf) {
  const unit = tf === "1d" ? "day" : "bar";
  if (trend?.kind === "average") return `${trend.bars || 200}-${unit} average of price (log scale): too little history for the 300-${unit} trend line.`;
  return `${trend?.bars || 300}-${unit} trend line of price (log scale).`;
}
