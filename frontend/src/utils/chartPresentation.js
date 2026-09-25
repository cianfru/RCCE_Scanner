export function candleChange(candle) {
  if (!candle || !Number.isFinite(candle.open) || candle.open <= 0 || !Number.isFinite(candle.close)) return null;
  return (candle.close - candle.open) / candle.open * 100;
}
export function rangeRuler(reference, percentage) {
  if (!Number.isFinite(reference) || reference <= 0 || !Number.isFinite(percentage) || percentage <= 0) return null;
  const size = reference * percentage / 100;
  // Centred only to illustrate magnitude. These are NOT forecast price bounds.
  return {size, top:reference + size / 2, bottom:reference - size / 2};
}
