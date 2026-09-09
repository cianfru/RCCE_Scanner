import { useEffect, useState } from "react";
const API = import.meta.env.VITE_API_URL || "http://localhost:8000";
export default function UniverseCoverage({timeframe, marketKind = "perpetual"}) {
  const [data, setData] = useState(null);
  const [search, setSearch] = useState("");
  useEffect(() => {
    let cancelled = false;
    const load = () => fetch(`${API}/api/universe?timeframe=${timeframe}`).then(r => {if(!r.ok) throw Error();return r.json();}).then(d => {if(!cancelled) setData(d);}).catch(() => {});
    load(); const timer = setInterval(load, 60000);
    return () => {cancelled = true;clearInterval(timer);};
  }, [timeframe]);
  if (!data) return null;
  const markets = (data.markets || []).filter(m => m.kind === marketKind);
  const pending = markets.filter(m => m.analysis_status === "pending").length;
  const excluded = markets.filter(m => m.analysis_status === "excluded").length;
  return <details className="universe-coverage">
    <summary>{markets.length} Hyperliquid {marketKind === "spot" ? "spot markets" : "perpetuals"}{excluded ? ` · ${excluded} excluded by quality filters` : ""}{pending ? ` · ${pending} awaiting analysis` : ""}{data.stale ? " · Listing refresh delayed" : ""}</summary>
    <p>Listings refresh automatically. Perpetual and spot markets use their own native candles. Analysis requires sufficient candle history. Favorites and reference markets refresh about every 15 minutes; other perpetuals and spot markets refresh about hourly. Cold markets, unavailable history and idle periods refresh less often; busy queues can take longer. Prices update separately. HIP-3 remains under TradFi.</p>
    {marketKind === "spot" && <p>Spot requires at least ${Number(data.spot_min_volume_usd || 25000).toLocaleString()} in 24-hour USDC volume and usable recent candles. Volume is an activity filter, not a guarantee of order-book liquidity. Excluded markets are not scanned for signals.</p>}
    <input aria-label="Search Hyperliquid listings" placeholder="Find a listed token…" value={search} onChange={e=>setSearch(e.target.value)}/>
    <div className="universe-markets">{markets.filter(m=>m.symbol.toLowerCase().includes(search.toLowerCase())).map(m=><div key={m.symbol}><span>{m.base}<small> · {m.kind}</small></span><span>{m.exclusion_reason || (m.analysis_status === "ready" ? "In scanner" : "Awaiting analysis")}{m.candles_checked_at && <small> · Candles checked {new Date(m.candles_checked_at * 1000).toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"})}</small>}</span></div>)}</div>
  </details>;
}
