import { useEffect, useRef } from "react";
import { T } from "../theme.js";
import { useTheme } from "../ThemeContext";

export default function TradingViewWidget({ symbol, timeframe = "240" }) {
  const iframeRef = useRef(null);
  const { mode } = useTheme();

  if (!symbol) return null;

  // Convert "BTC/USDT" -> "BINANCE:BTCUSDT"
  const tvSymbol = `BINANCE:${symbol.replace("/", "")}`;

  const bgColor = mode === "dark" ? "000000" : "ffffff";
  const src = `https://s.tradingview.com/widgetembed/?symbol=${encodeURIComponent(tvSymbol)}&interval=${timeframe}&theme=${mode}&style=1&hide_top_toolbar=1&hide_legend=0&save_image=0&hide_volume=0&allow_symbol_change=0&backgroundColor=${bgColor}`;

  return (
    <div style={{
      width: "100%",
      height: 300,
      borderRadius: T.radius,
      overflow: "hidden",
      border: `1px solid ${T.border}`,
      background: T.surface,
      marginBottom: 16,
    }}>
      <iframe
        ref={iframeRef}
        key={`${tvSymbol}-${mode}`}
        src={src}
        title={`TradingView Chart - ${symbol}`}
        style={{
          width: "100%",
          height: "100%",
          border: "none",
          display: "block",
        }}
        loading="lazy"
      />
    </div>
  );
}
