import { useEffect, useState } from "react";
const API = import.meta.env.VITE_API_URL || "http://localhost:8000";
const checkedAt = m => m.candles_checked_at && <small> · Candles checked {new Date(m.candles_checked_at * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</small>;
const NAMES = 8;
const groupBy = (rows, key) => [...rows.reduce((acc, r) => acc.set(key(r), [...(acc.get(key(r)) || []), r]), new Map())].sort((a, b) => b[1].length - a[1].length);
// One line per reason: what, why, how many, and the first names.
function Exception({ kind, reason, markets }) {
  const names = markets.slice(0, NAMES).map(m => m.base).join(", ");
  return <div className="universe-exception">
    <b data-kind={kind === "Excluded" ? "excluded" : "pending"}>{kind}</b>
    <span className="universe-exception-count">{markets.length}</span>
    <span>{reason}</span>
    <span className="universe-exception-names">{names}{markets.length > NAMES ? ` +${markets.length - NAMES}` : ""}</span>
  </div>;
}

export default function UniverseCoverage({timeframe, marketKind = "perpetual"}) {
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);
  const [search, setSearch] = useState("");
  useEffect(() => {
    let cancelled = false;
    const load = () => fetch(`${API}/api/universe?timeframe=${timeframe}`).then(r => {if(!r.ok) throw Error();return r.json();}).then(d => {if(!cancelled) {setData(d); setFailed(false);}}).catch(() => {if(!cancelled) setFailed(true);});
    load(); const timer = setInterval(load, 60000);
    return () => {cancelled = true;clearInterval(timer);};
  }, [timeframe]);
  // While the listing loads, keep the line's height so the sectors below do not jump.
  if (!data) return failed ? null : <div className="universe-coverage universe-coverage-pending" aria-hidden="true" />;
  const markets = (data.markets || []).filter(m => m.kind === marketKind);
  const pendingRows = markets.filter(m => m.analysis_status === "pending");
  const excludedRows = markets.filter(m => m.analysis_status === "excluded");
  const pending = pendingRows.length, excluded = excludedRows.length;
  const q = search.toLowerCase();
  return <details className="universe-coverage">
    <summary>{markets.length} Hyperliquid {marketKind === "spot" ? "spot markets" : "perpetuals"}{excluded ? ` · ${excluded} excluded by quality filters` : ""}{pending ? ` · ${pending} awaiting analysis` : ""}{data.stale ? " · Listing refresh delayed" : ""}</summary>
    {(excluded > 0 || pending > 0) && <div className="universe-exceptions">
      {groupBy(excludedRows, m => m.exclusion_reason || "Quality filters").map(([reason, ms]) =>
        <Exception key={reason} kind="Excluded" reason={reason} markets={ms} />)}
      {pending > 0 && <Exception kind="Awaiting analysis" reason="Not enough candle history yet" markets={pendingRows} />}
    </div>}
    <input aria-label="Search Hyperliquid listings" placeholder="Find a listed token…" value={search} onChange={e=>setSearch(e.target.value)}/>
    <div className="universe-markets">{markets.filter(m=>m.symbol.toLowerCase().includes(q)).map(m=><div key={m.symbol}><span>{m.base}<small> · {m.kind}</small></span><span>{m.exclusion_reason || (m.analysis_status === "ready" ? "In scanner" : "Awaiting analysis")}{checkedAt(m)}</span></div>)}</div>
    <p>Listings refresh automatically. Perpetual and spot markets use their own native candles. Analysis requires sufficient candle history. Favorites and reference markets refresh about every 15 minutes; other perpetuals and spot markets refresh about hourly. Cold markets, unavailable history and idle periods refresh less often; busy queues can take longer. Prices update separately. HIP-3 remains under TradFi.</p>
    {marketKind === "spot" && <p>Spot requires at least ${Number(data.spot_min_volume_usd || 25000).toLocaleString()} in 24-hour USDC volume and usable recent candles. Volume is an activity filter, not a guarantee of order-book liquidity. Excluded markets are not scanned for signals.</p>}
  </details>;
}
