import { useEffect, useState } from "react";
import { apiJson } from "../edge.js";
import { getBaseSymbol } from "../theme.js";
import { pollWhileVisible } from "../utils/visiblePoll.js";

// The last 24 hours of a coin's long/short, one reading per 30 minutes (/api/coin-positioning/recent,
// an edge feed). Read every 5 minutes while visible: the current slot fills as readings arrive.
export default function useCoinPositioningRecent(symbol, enabled = true) {
  const coin = symbol ? getBaseSymbol(symbol) : "";
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    setData(null);
    setFailed(false);
    if (!enabled || !coin || coin.toLowerCase().startsWith("xyz:")) return undefined;
    let alive = true;
    const load = () => apiJson(`/api/coin-positioning/recent?coin=${encodeURIComponent(coin)}&hours=24`)
      .then(d => { if (alive) { setData(d); setFailed(false); } })
      .catch(() => { if (alive) setFailed(true); });
    load();
    const stop = pollWhileVisible(load, 300_000);
    return () => { alive = false; stop(); };
  }, [coin, enabled]);
  return { data, failed };
}
