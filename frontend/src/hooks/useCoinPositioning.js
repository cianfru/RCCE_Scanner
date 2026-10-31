import { useEffect, useState } from "react";
import { apiJson } from "../edge.js";
import { getBaseSymbol } from "../theme.js";
import { pollWhileVisible } from "../utils/visiblePoll.js";

// A coin's long/short record for the chart's bottom pane (/api/coin-positioning, an edge feed):
// 90 days, the most the chart's 4H view shows; read again every 10 minutes while visible.
// Returns {data, failed}: failed while the last read failed (the last good data stays shown).
export default function useCoinPositioning(symbol, enabled = true) {
  const coin = symbol ? getBaseSymbol(symbol) : "";
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    setData(null);
    setFailed(false);
    if (!enabled || !coin || coin.toLowerCase().startsWith("xyz:")) return undefined;
    let alive = true;
    const load = () => apiJson(`/api/coin-positioning?coin=${encodeURIComponent(coin)}&days=90`)
      .then(d => { if (alive) { setData(d); setFailed(false); } })
      .catch(() => { if (alive) setFailed(true); });
    load();
    const stop = pollWhileVisible(load, 600_000);
    return () => { alive = false; stop(); };
  }, [coin, enabled]);
  return { data, failed };
}
