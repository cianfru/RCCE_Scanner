import { useEffect, useState } from "react";
import { apiJson } from "../edge.js";

// One coin's band stretch (/api/band-stretch, Hyperliquid daily candles, cached server-side until the next close).
export default function useBandStretch(symbol) {
  const [data, setData] = useState(null);
  useEffect(() => {
    setData(null);
    if (!symbol) return undefined;
    let alive = true;
    apiJson(`/api/band-stretch?symbol=${encodeURIComponent(symbol)}`)
      .then(d => { if (alive) setData(d); })
      .catch(() => {});
    return () => { alive = false; };
  }, [symbol]);
  return data;
}
