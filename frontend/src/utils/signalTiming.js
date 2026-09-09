// API first-seen times and chart times are Unix seconds. Never substitute "now".
export function signalCandleTime(candles, firstSeen, intervalSeconds) {
  if (!Number.isFinite(firstSeen) || firstSeen <= 0 || !candles?.length || intervalSeconds <= 0) return null;
  let candle = null;
  for (const bar of candles) {
    if (bar.time > firstSeen) break;
    candle = bar;
  }
  return candle && firstSeen < candle.time + intervalSeconds ? candle.time : null;
}
