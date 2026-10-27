// A fill's fee in USD. Perp fills pay in their dex's collateral (USDC on Hyperliquid's own perps); a
// spot buy pays in the token bought (feeToken: HYPE, KNTQ, USDT0, ...), valued here at its mid
// (totals.pricesByName). null when that token has no price now. A fee in a token is never read as
// that many dollars.
export function feeUsd(f, px = null) {
  const fee = parseFloat(f?.fee) || 0;
  const tok = f?.feeToken;
  if (!fee || !tok || tok === "USDC") return fee;
  const p = px?.get?.(tok);
  return p != null ? fee * p : null;
}

// The fee as Hyperliquid charged it: "0.12" (USDC) or "0.12 HYPE".
export function feeText(f, digits = 2) {
  const fee = parseFloat(f?.fee) || 0;
  const tok = f?.feeToken;
  return tok && tok !== "USDC" ? `${fee.toFixed(Math.max(digits, fee && Math.abs(fee) < 0.01 ? 4 : digits))} ${tok}` : fee.toFixed(digits);
}
