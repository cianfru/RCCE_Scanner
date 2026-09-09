import { useEffect, useState } from "react";
const API = import.meta.env.VITE_API_URL || "http://localhost:8000";
export default function UniverseCoverage({timeframe}) {
  const [data, setData] = useState(null);
  const [search, setSearch] = useState("");
  useEffect(() => {
    let cancelled = false;
    const load = () => fetch(`${API}/api/universe?timeframe=${timeframe}`).then(r => {if(!r.ok) throw Error();return r.json();}).then(d => {if(!cancelled) setData(d);}).catch(() => {});
    load(); const timer = setInterval(load, 60000);
    return () => {cancelled = true;clearInterval(timer);};
  }, [timeframe]);
  if (!data) return null;
  const markets = data.markets || [];
  const pending = markets.filter(m => m.analysis_status !== "ready").length;
  return <details className="universe-coverage">
    <summary>{markets.length} Hyperliquid markets · Perpetuals & spot-only tokens{pending ? ` · ${pending} awaiting analysis` : ""}{data.stale ? " · Listing refresh delayed" : ""}</summary>
    <p>Listings refresh automatically. Tokens with a perpetual appear once; spot-only tokens use their native market. Analysis requires sufficient candle history. Priority markets refresh about every 5 minutes, other perpetuals every 15 minutes, and spot-only markets every 30 minutes. Cold markets, unavailable history and idle periods refresh less often; busy queues can take longer. Prices update separately. HIP-3 remains under TradFi.</p>
    <input aria-label="Search Hyperliquid listings" placeholder="Find a listed token…" value={search} onChange={e=>setSearch(e.target.value)}/>
    <div className="universe-markets">{markets.filter(m=>m.symbol.toLowerCase().includes(search.toLowerCase())).map(m=><div key={m.symbol}><span>{m.base}<small> · {m.kind}</small></span><span>{m.analysis_status === "ready" ? "In scanner" : "Awaiting analysis"}{m.candles_checked_at && <small> · Candles checked {new Date(m.candles_checked_at * 1000).toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"})}</small>}</span></div>)}</div>
  </details>;
}
