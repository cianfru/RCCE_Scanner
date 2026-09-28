export function candleChange(candle) {
  if (!candle || !Number.isFinite(candle.open) || candle.open <= 0 || !Number.isFinite(candle.close)) return null;
  return (candle.close - candle.open) / candle.open * 100;
}
