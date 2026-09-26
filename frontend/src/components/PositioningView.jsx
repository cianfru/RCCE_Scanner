import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import Tabs from "./Tabs.jsx";
import TokenLogo from "./TokenLogo.jsx";
import HelpTip from "./HelpTip.jsx";
import { T, col, SIGNAL_META, REGIME_META } from "../theme.js";
import { MAP_FILTERS, MAP_MIN_TRADERS, matchOf, vsEntry } from "../utils/positioning.js";
import { usd } from "../utils/traders.js";

const API_BASE = import.meta.env.VITE_API_URL || "";
const GROUPS = [
  { key: "profitable", label: "Profitable traders" },
  { key: "large", label: "Large accounts" },
];
const FILTERS = [
  { key: "all", label: "All" },
  { key: "agree", label: "Agree with engine", title: "Traders lean the same way as the engine's 4H signal" },
  { key: "opposed", label: "Opposed", title: "Traders lean against the engine's 4H signal" },
  { key: "new", label: "New in 24h", title: "Coins where these wallets opened a position in the last 24 hours" },
  { key: "converging", label: "Converging", title: "Two or more profitable traders opened the same side within 24 hours" },
];
const SIDE_COLOR = { long: "#7dd3fc", short: "#fda4af" };

const sentence = s => (s ? s.charAt(0) + s.slice(1).toLowerCase() : "");
const pct = v => (v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`);
const when = ts => new Date(ts * 1000).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

function Side({ s, side }) {
  if (!s?.n) return <span className="pos-dim">—</span>;
  return <>
    <b style={{ color: col(SIDE_COLOR[side]) }}>{s.n}</b> <span className="pos-dim">{usd(s.usd)}</span>
    <div className="pos-sub">{s.in_profit} of {s.n} in profit</div>
  </>;
}

function Engine({ e }) {
  if (!e) return <span className="pos-dim">not scanned</span>;
  const sig = SIGNAL_META[e.signal], reg = REGIME_META[e.regime];
  return <>
    <span style={{ color: col(sig?.color || "#8b8f94") }}>{sentence(sig?.label || e.signal)}</span>
    <div className="pos-sub">{reg?.name || e.regime}{e.zscore != null ? ` · z ${e.zscore.toFixed(1)}` : ""}</div>
  </>;
}

export default function PositioningView() {
  const [group, setGroup] = useState("profitable");
  const [filter, setFilter] = useState("all");
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;
    const load = () => fetch(`${API_BASE}/api/hyperlens/positioning?cohort=${group}`)
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(d => { if (!cancelled) { setData(d); setError(null); } })
      .catch(e => { if (!cancelled) setError(e.message); });
    setData(null);
    load();
    const id = setInterval(load, 300_000);
    return () => { cancelled = true; clearInterval(id); };
  }, [group]);

  const rows = useMemo(() => (data?.rows || []).filter(MAP_FILTERS[filter]), [data, filter]);
  const counts = useMemo(() => Object.fromEntries(FILTERS.map(f => [f.key, (data?.rows || []).filter(MAP_FILTERS[f.key]).length])), [data]);
  const who = group === "profitable" ? "profitable traders" : "large accounts";

  return (
    <div className="pos">
      <div className="coh-controls">
        <Tabs small label="Wallet group" items={GROUPS} value={group} onChange={setGroup} />
        <Tabs small label="Show" items={FILTERS.map(f => ({ ...f, label: `${f.label}${data ? ` (${counts[f.key]})` : ""}` }))} value={filter} onChange={setFilter} />
      </div>
      <p className="coh-intro">
        {data ? <>{data.wallets} {who} hold positions on {data.rows.length} coins. Updated {when(data.updated_at)}.</> : error ? `Positioning unavailable (${error}).` : "Loading positioning…"}
        {" "}<HelpTip title="Positioning map" width={380}>
          <p>Every coin where tracked wallets hold a perpetual position, from the latest wallet readings (about every 30 minutes). Per side: how many wallets, their dollars, how many are in profit at the current price, and where price stands against their median entry.</p>
          <p>Agree: at least {MAP_MIN_TRADERS} {who} lean the same way as the engine's 4H signal (long signals against longs, exits or a downtrend against shorts). Opposed: they lean against it. Whether agreement leads price is being recorded; until then this is information, not a signal.</p>
        </HelpTip>
      </p>
      {data && !rows.length && <p className="coh-muted">No coins match this filter right now.</p>}
      {rows.length > 0 && (
        <div className="pos-wrap">
          <table className="pos-table">
            <thead>
              <tr>
                <th>Coin</th><th className="pos-sides">Long</th><th className="pos-sides">Short</th><th className="pos-narrow">Traders</th>
                <th className="pos-wide" title="Current price against the longs' median entry">Price vs long entry</th>
                <th className="pos-wide" title="Current price against the shorts' median entry">Price vs short entry</th>
                <th className="pos-wide">New 24h</th>
                <th>Engine 4H</th><th className="pos-wide">Engine 1D</th><th className="pos-wide">Match</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => {
                const m = matchOf(r);
                const o = r.opens_24h || {};
                return (
                  <tr key={r.coin} onClick={() => navigate(`/scanner/${encodeURIComponent(r.coin)}`)} tabIndex={0}
                    onKeyDown={e => { if (e.key === "Enter") navigate(`/scanner/${encodeURIComponent(r.coin)}`); }}>
                    <td>
                      <span className="pos-coin"><TokenLogo symbol={`${r.coin}/USDT`} size={20} /> {r.coin}</span>
                      {r.convergence && <div className="pos-sub" style={{ color: col(SIDE_COLOR[r.convergence.side]) }}>Converging {r.convergence.side} · {r.convergence.n}</div>}
                      {m && <div className={`pos-sub pos-match-narrow pos-${m}`}>{m === "agree" ? "Agrees with engine" : "Opposes engine"}</div>}
                    </td>
                    <td className="pos-sides"><Side s={r.long} side="long" /></td>
                    <td className="pos-sides"><Side s={r.short} side="short" /></td>
                    <td className="pos-narrow">
                      <b style={{ color: col(SIDE_COLOR.long) }}>{r.long?.n || 0}</b> long
                      <div className="pos-sub"><b style={{ color: col(SIDE_COLOR.short) }}>{r.short?.n || 0}</b> short</div>
                    </td>
                    <td className="pos-wide">{pct(vsEntry(r, "long"))}</td>
                    <td className="pos-wide">{pct(vsEntry(r, "short"))}</td>
                    <td className="pos-wide">{o.long || o.short ? <>{o.long ? `${o.long} long` : ""}{o.long && o.short ? ", " : ""}{o.short ? `${o.short} short` : ""}</> : <span className="pos-dim">—</span>}</td>
                    <td><Engine e={r.engine?.["4h"]} /></td>
                    <td className="pos-wide"><Engine e={r.engine?.["1d"]} /></td>
                    <td className="pos-wide">{m ? <span className={`pos-match pos-${m}`}>{m === "agree" ? "Agree" : "Opposed"}</span> : <span className="pos-dim">—</span>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="coh-muted">New positions are counted since tracking began; convergences are shown for 48 hours. Tap a coin for its chart with the traders' entries.</p>
    </div>
  );
}
