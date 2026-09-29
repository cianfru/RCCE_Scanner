import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import BMSBChart from "../components/BMSBChart.jsx";
import EquityChart from "../components/EquityChart.jsx";
import HelpTip from "../components/HelpTip.jsx";
import TokenLogo from "../components/TokenLogo.jsx";
import { WalletAvatar } from "../components/WalletTag.jsx";
import { WindowSwitch } from "../components/TraderLeaderboard.jsx";
import useFollowed from "../hooks/useFollowed.js";
import useViewport from "../hooks/useViewport.js";
import { T } from "../theme.js";
import { sideColor } from "../utils/traderFormat.js";
import { codename, shortAddr } from "../utils/walletName.js";
import {
  chartTimeframe, fmtDay, fmtDuration, fmtMoney, fmtPnl, fmtPrice, fmtRate, fmtRoi, kindCounts, tripRange,
  WINDOW_KEYS, windowLabel,
} from "../utils/traderBoard.js";
import { pollWhileVisible } from "../utils/visiblePoll.js";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";
const HISTORY_PAGE = 20;
const logoKey = coin => `${coin}/USDT`;
const tone = v => (v > 0 ? "tp-up" : v < 0 ? "tp-down" : "");
const sideWord = s => (s === "long" ? "Long" : "Short");

function Chevron({ open }) {
  return (
    <svg className="tp-chev" width="14" height="14" viewBox="0 0 12 12" aria-hidden="true"
      style={{ transform: open ? "rotate(180deg)" : "none" }}>
      <path d="M2.5 4.5 6 8l3.5-3.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// The chart's legend: the same glyphs the marks use, with how many of each are on hand.
function Glyph({ kind, color }) {
  const s = { width: 14, height: 14, viewBox: "0 0 14 14", "aria-hidden": true };
  if (kind === "trim") return <svg {...s}><circle cx="7" cy="7" r="4" fill="none" stroke={color} strokeWidth="1.6" /></svg>;
  if (kind === "close") return <svg {...s}><path d="M3.5 3.5l7 7M10.5 3.5l-7 7" stroke={color} strokeWidth="2" strokeLinecap="round" /></svg>;
  if (kind === "flip") return <svg {...s}><path d="M7 2l5 5-5 5-5-5z" fill={color} /></svg>;
  if (kind === "entry") return <svg {...s}><path d="M1 7h12" stroke={color} strokeWidth="1.6" strokeDasharray="3 2" /></svg>;
  return <svg {...s}><path d="M7 2.5l4.5 8h-9z" fill={color} /></svg>;
}

function Legend({ fills, side }) {
  const c = kindCounts(fills);
  const color = sideColor(side || "long");
  const n = v => (v ? `${v} ` : "");
  const items = [
    ["open", `${n(c.open + c.add)}open / add`],
    ["trim", `${n(c.trim)}trim`],
    ["close", `${n(c.close)}close`],
    ...(c.flip ? [["flip", `${c.flip} flip`]] : []),
    ["entry", "Avg entry"],
  ];
  return (
    <div className="tp-legend">
      {items.map(([k, label]) => <span key={k}><Glyph kind={k} color={color} />{label}</span>)}
      <span className="tp-legend-note">Arrows point up for buys, down for sells</span>
    </div>
  );
}

// A coin chart with this trader's fills in a time range; fills load when the chart opens.
function FillsChart({ address, coin, hlCoin, since, until, focus, entry, side, isMobile }) {
  const [state, setState] = useState({ loading: true, fills: [] });
  useEffect(() => {
    let cancelled = false;
    const q = new URLSearchParams({ coin: hlCoin || coin, limit: "2000" });
    if (since) q.set("since", String(Math.floor(since)));
    if (until) q.set("until", String(Math.ceil(until)));
    fetch(`${API}/api/traders/${address}/fills?${q}`)
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(d => { if (!cancelled) setState({ loading: false, fills: d.fills || [], truncated: d.truncated }); })
      .catch(() => { if (!cancelled) setState({ loading: false, fills: [], error: true }); });
    return () => { cancelled = true; };
  }, [address, coin, hlCoin, since, until]);
  const tf = chartTimeframe(focus?.from);
  return (
    <div className="tp-chart">
      <BMSBChart symbol={logoKey(coin)} timeframe={tf} height={isMobile ? 260 : 340} compact fills={state.fills}
        focusRange={focus} myEntry={entry ? { price: entry, side } : null} entryLabel="Avg entry" showSetup={false} />
      <div className="tp-chart-foot">
        <Legend fills={state.fills} side={side} />
        {state.loading && <span className="tp-dim">Loading fills…</span>}
        {state.error && <span className="tp-dim">Fills unavailable</span>}
      </div>
    </div>
  );
}

function LiqBar({ pct }) {
  if (pct == null) return <span className="tp-dim">—</span>;
  const c = Math.min(100, pct);
  const color = c > 50 ? T.green : c > 20 ? T.yellow : T.red;
  return (
    <span className="tp-liq" title={`Price would have to move ${pct.toFixed(1)}% to reach liquidation`}>
      <span className="tp-liq-n">{pct >= 100 ? ">100" : pct.toFixed(0)}%</span>
      <span className="tp-liq-bar" aria-hidden="true"><i style={{ width: `${Math.max(3, c)}%`, background: color }} /></span>
    </span>
  );
}

function PositionCard({ p, address, open, onToggle, isMobile }) {
  const since = p.opened_at || null;
  // The position's life so far (the last 30 days when it opened before the fills on hand).
  const focus = useMemo(() => ({ from: p.opened_at || Date.now() / 1000 - 30 * 86400, to: Date.now() / 1000 }), [p.opened_at]);
  return (
    <li className={`tp-pos${open ? " tp-open" : ""}`}>
      <button type="button" className="tp-pos-main" aria-expanded={open} onClick={onToggle}>
        <span className="tp-coin">
          <TokenLogo symbol={logoKey(p.coin)} size={28} />
          <span className="tp-coin-t">
            <b>{p.coin}</b>
            <span style={{ color: sideColor(p.side) }}>{sideWord(p.side)} {p.leverage ? `${Math.round(p.leverage)}x` : ""}</span>
          </span>
        </span>
        <span className="tp-cell tp-r"><span className="tp-k">Size</span><span className="tp-v">{fmtMoney(p.size_usd)}</span></span>
        <span className="tp-cell tp-r"><span className="tp-k">Entry</span><span className="tp-v">{fmtPrice(p.entry_px)}</span></span>
        <span className="tp-cell tp-r"><span className="tp-k">Mark</span><span className="tp-v">{fmtPrice(p.mark_px)}</span></span>
        <span className="tp-cell tp-r"><span className="tp-k">uPnL</span>
          <span className={`tp-v tp-pnl ${tone(p.upnl)}`}>{fmtPnl(p.upnl)}{p.roe_pct != null && <small> {fmtRoi(p.roe_pct)}</small>}</span></span>
        <span className="tp-cell"><span className="tp-k">To liq.</span><LiqBar pct={p.liq_distance_pct} /></span>
        <Chevron open={open} />
      </button>
      {open && (
        <div className="tp-pos-detail">
          <div className="tp-facts">
            {p.opened_at ? <span>Opened <b>{fmtDay(p.opened_at)}</b> · {fmtDuration(Date.now() / 1000 - p.opened_at)} ago</span>
              : <span>Opened before the fills on hand</span>}
            {p.adds != null && <span><b>{p.adds}</b> adds</span>}
            {p.trims != null && <span><b>{p.trims}</b> trims</span>}
            {p.realized ? <span>Realised so far <b className={tone(p.realized)}>{fmtPnl(p.realized)}</b></span> : null}
            {p.liq_px ? <span>Liquidation <b>{fmtPrice(p.liq_px)}</b></span> : null}
          </div>
          <FillsChart address={address} coin={p.coin} hlCoin={p.hl_coin} since={since} focus={focus}
            entry={p.entry_px} side={p.side} isMobile={isMobile} />
        </div>
      )}
    </li>
  );
}

function TripRow({ t, address, open, onToggle, isMobile }) {
  const r = useMemo(() => tripRange(t), [t.opened_at, t.closed_at]);  // eslint-disable-line react-hooks/exhaustive-deps
  const focus = useMemo(() => ({ from: r.from, to: r.to }), [r]);
  const held = t.opened_at ? t.closed_at - t.opened_at : null;
  return (
    <li className={`tp-trip${open ? " tp-open" : ""}`}>
      <button type="button" className="tp-trip-main" aria-expanded={open} onClick={onToggle}>
        <span className="tp-coin">
          <TokenLogo symbol={logoKey(t.coin)} size={24} />
          <span className="tp-coin-t"><b>{t.coin}</b><span style={{ color: sideColor(t.side) }}>{sideWord(t.side)}</span></span>
        </span>
        <span className="tp-cell"><span className="tp-k">Closed</span><span className="tp-v tp-when">{fmtDay(t.closed_at)}<small>{held != null ? ` · ${fmtDuration(held)}` : ""}</small></span></span>
        <span className="tp-cell tp-r"><span className="tp-k">Entry → exit</span><span className="tp-v">
          {t.entry_px != null ? fmtPrice(t.entry_px) : <span className="tp-dim" title="Opened before the fills on hand">…</span>} <span className="tp-dim">→</span> {fmtPrice(t.exit_px)}</span></span>
        <span className="tp-cell tp-r"><span className="tp-k">Peak size</span><span className="tp-v">{t.peak_usd ? fmtMoney(t.peak_usd) : "—"}</span></span>
        <span className="tp-cell tp-r"><span className="tp-k">PnL</span>
          <span className={`tp-v tp-pnl ${tone(t.pnl)}${t.partial ? " tp-partial" : ""}`}
            title={t.partial ? "Opened before the fills on hand: the PnL covers only the part seen" : undefined}>
            {fmtPnl(t.pnl)}{t.pnl_pct != null && <small> {fmtRoi(t.pnl_pct)}</small>}</span></span>
        <Chevron open={open} />
      </button>
      {open && (
        <div className="tp-pos-detail">
          <div className="tp-facts">
            <span>{t.opened_at ? <>Opened <b>{fmtDay(t.opened_at)}</b></> : "Opened before the fills on hand"}</span>
            <span><b>{t.fills}</b> fills</span>
            <span><b>{t.adds}</b> adds</span>
            <span><b>{t.trims}</b> trims</span>
          </div>
          <FillsChart address={address} coin={t.coin} hlCoin={t.hl_coin} since={r.since} until={r.until}
            focus={focus} entry={t.entry_px} side={t.side} isMobile={isMobile} />
        </div>
      )}
    </li>
  );
}

function History({ address, isMobile }) {
  const [coin, setCoin] = useState(null);
  const [count, setCount] = useState(HISTORY_PAGE);
  const [data, setData] = useState({ loading: true, trips: [], total: 0, coins: [] });
  const [open, setOpen] = useState(null);
  useEffect(() => { setCount(HISTORY_PAGE); setOpen(null); }, [coin]);
  useEffect(() => {
    let cancelled = false;
    const q = new URLSearchParams({ offset: "0", limit: String(Math.min(count, 100)) });
    if (coin) q.set("coin", coin);
    setData(d => ({ ...d, loading: true }));
    fetch(`${API}/api/traders/${address}/history?${q}`)
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(d => { if (!cancelled) setData({ loading: false, trips: d.trips || [], total: d.total || 0, coins: d.coins || [], earliest: d.earliest_fill }); })
      .catch(() => { if (!cancelled) setData(d => ({ ...d, loading: false, error: true })); });
    return () => { cancelled = true; };
  }, [address, coin, count]);
  const coins = data.coins.slice(0, isMobile ? 4 : 8);
  return (
    <section className="tp-section">
      <div className="tp-section-head">
        <h2>Trade history <HelpTip title="Trade history" width={360}>
          <p>Closed positions, most recent first: from the first fill that opened the coin to the one that left it flat (a flip closes one side and opens the other).</p>
          <p>Built from the trader's latest 2,000 fills on Hyperliquid{data.earliest ? `, back to ${fmtDay(data.earliest)}` : ""}. PnL is realised, after fees. Open a row for the chart.</p>
        </HelpTip></h2>
        {coins.length > 1 && (
          <div className="lb-win tp-coin-filter" role="group" aria-label="Coin">
            <span><button type="button" aria-pressed={!coin} onClick={() => setCoin(null)}>All</button></span>
            {coins.map(c => (
              <span key={c.coin}><span className="lb-win-dot" aria-hidden="true">·</span>
                <button type="button" aria-pressed={coin === c.coin} onClick={() => setCoin(c.coin)}>{c.coin}</button></span>
            ))}
          </div>
        )}
      </div>
      {data.loading && !data.trips.length ? <div className="tp-skel shimmer-loading" />
        : data.error && !data.trips.length ? <p className="tp-empty">History unavailable.</p>
        : !data.trips.length ? <p className="tp-empty">No closed positions in the fills on hand.</p>
        : (
          <ul className="tp-trips">
            <li className="tp-head tp-trip-cols" aria-hidden="true">
              <span>Coin</span><span>Closed · held</span><span className="tp-r">Entry → exit</span><span className="tp-r">Peak size</span>
              <span className="tp-r">PnL</span><span />
            </li>
            {data.trips.map((t, i) => {
              const key = `${t.coin}-${t.closed_at}-${i}`;
              return <TripRow key={key} t={t} address={address} isMobile={isMobile} open={open === key} onToggle={() => setOpen(o => (o === key ? null : key))} />;
            })}
          </ul>
        )}
      {data.trips.length > 0 && (
        <div className="lb-foot">
          {data.total > data.trips.length && count < 100 && (
            <button type="button" className="te-link" onClick={() => setCount(c => c + HISTORY_PAGE)}>Show more</button>
          )}
          <span className="lb-dim">{data.trips.length} of {data.total}</span>
        </div>
      )}
    </section>
  );
}

function Kpi({ label, children, sub }) {
  return (
    <div className="tp-kpi">
      <span className="tp-kpi-k">{label}</span>
      <span className="tp-kpi-v">{children}</span>
      {sub && <span className="tp-kpi-sub">{sub}</span>}
    </div>
  );
}

export default function TraderPage({ address }) {
  const { isMobile } = useViewport();
  const [params, setParams] = useSearchParams();
  const win = WINDOW_KEYS.has(params.get("window")) ? params.get("window") : "30d";
  const setWin = w => {
    const next = new URLSearchParams(params);
    if (w === "30d") next.delete("window"); else next.set("window", w);
    setParams(next, { replace: true });
  };
  const [data, setData] = useState({ loading: true });
  const [openPos, setOpenPos] = useState(null);
  const [copied, setCopied] = useState(false);
  const { followed, toggle } = useFollowed();
  const [followBusy, setFollowBusy] = useState(false);
  const [followFailed, setFollowFailed] = useState(false);
  const isFollowing = followed.has(address);
  const name = codename(address);

  useEffect(() => {
    let cancelled = false;
    setData({ loading: true });
    setOpenPos(null);
    const load = () => fetch(`${API}/api/traders/${address}`)
      .then(async r => {
        if (r.status === 404) return { missing: true };
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(d => { if (!cancelled) setData({ loading: false, ...d }); })
      .catch(() => { if (!cancelled) setData(prev => ({ ...prev, loading: false, error: !prev.address })); });
    load();
    const stop = pollWhileVisible(load, 60_000);
    return () => { cancelled = true; stop(); };
  }, [address]);


  const toggleFollow = async () => {
    if (followBusy) return;
    setFollowBusy(true);
    setFollowFailed(false);
    const ok = await toggle(address);
    setFollowBusy(false);
    if (!ok) { setFollowFailed(true); setTimeout(() => setFollowFailed(false), 2500); }
  };
  const copy = () => navigator.clipboard?.writeText(address).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1200); }).catch(() => {});

  const w = data.windows?.[win] || {};
  const wr = data.win?.[win] || {};
  const rank = data.ranks?.[win];
  const equity = useMemo(() => (data.equity?.[win] || []).map(([t, v]) => ({ timestamp: t, value: v })), [data.equity, win]);
  const positions = data.positions || [];
  const exposure = positions.reduce((s, p) => s + (p.size_usd || 0), 0);
  const upnl = positions.reduce((s, p) => s + (p.upnl || 0), 0);

  return (
    <div className="tp">
      <nav className="tp-crumbs"><Link to="/traders/leaderboard">Leaderboard</Link><span aria-hidden="true">/</span><span>{name}</span></nav>

      <section className="tp-card tp-headcard">
        <div className="tp-id">
          <WalletAvatar address={address} size={56} />
          <div className="tp-id-t">
            <h1 title={address}>{name}</h1>
            <div className="tp-id-sub">
              <span className="tp-addr" title={address}>{shortAddr(address)}</span>
              <button type="button" className="tp-copy" onClick={copy} aria-label="Copy the full address">{copied ? "Copied" : "Copy"}</button>
              {data.band && <span className="tp-dim">{data.band} account</span>}
              {rank && <span className="tp-dim">#{rank} of {data.board_size}</span>}
            </div>
            {data.entity?.note && <div className="tp-dim" title="These wallets hold the same coins and trade them together, so trader counts take them once">{data.entity.note}</div>}
          </div>
          <div className="tp-actions">
            {followFailed && <span role="status" className="tp-warn">Not saved</span>}
            <button type="button" className={`te-fbtn tp-follow${isFollowing ? " on" : ""}`} aria-pressed={isFollowing} disabled={followBusy}
              title={isFollowing ? "Stop following this trader" : "Follow: Telegram alert when this trader opens, closes, adds or cuts a position"}
              onClick={toggleFollow}>{isFollowing ? "Following" : "Follow"}</button>
          </div>
        </div>

        {data.missing ? <p className="tp-empty">No Hyperliquid activity for this address.</p>
          : data.error ? <p className="tp-empty">Profile unavailable. Retrying.</p> : <>
          <div className="tp-kpis-head">
            <WindowSwitch value={win} onChange={setWin} />
            <HelpTip title="These figures" width={380} label="About these figures">
              <p>PnL and ROI: {w.source === "account" ? "from the trader's Hyperliquid account history (not on the leaderboard, so no ROI)." : "Hyperliquid's leaderboard figures for the window, refreshed daily."}</p>
              <p>Win rate: positions closed in the window that made money after fees, from the trader's fills. Positions opened before the fills on hand are left out.</p>
              <p>Account: the perp account now; the curve is its value over the window.</p>
            </HelpTip>
          </div>
          <div className="tp-kpis" aria-busy={data.loading}>
            <Kpi label={`PnL ${windowLabel(win)}`}><span className={`tp-big ${tone(w.pnl)}`}>{data.loading ? "…" : fmtPnl(w.pnl)}</span></Kpi>
            <Kpi label="ROI"><span className={tone(w.roi)}>{data.loading ? "…" : fmtRoi(w.roi)}</span></Kpi>
            <Kpi label="Win rate" sub={wr.n ? `${wr.wins} of ${wr.n} closed` : wr.n === 0 ? "none closed" : null}>{data.loading ? "…" : fmtRate(wr.rate)}</Kpi>
            <Kpi label="Account">{data.loading ? "…" : fmtMoney(data.account_value)}</Kpi>
          </div>
          <div className="tp-equity">
            <EquityChart data={equity} height={isMobile ? 110 : 150} emptyText={data.loading ? "Loading…" : "No account history"} />
          </div>
        </>}
      </section>

      {!data.missing && (
        <section className="tp-section">
          <div className="tp-section-head">
            <h2>Open positions <HelpTip title="Open positions" width={360}>
              <p>Live from Hyperliquid. Open one for the coin's chart with this trader's fills on it.</p>
              <p>Arrows: opening or adding, up for buys and down for sells. Hollow circles: trims. Crosses: closes. Diamonds: flips. The dashed line is the current average entry. Bigger marks, more dollars.</p>
            </HelpTip></h2>
            {positions.length > 0 && <span className="tp-sum">{fmtMoney(exposure)} · <span className={tone(upnl)}>{fmtPnl(upnl)}</span></span>}
          </div>
          {data.loading && !positions.length ? <div className="tp-skel shimmer-loading" />
            : !positions.length ? <p className="tp-empty">No open positions.</p>
            : (
              <ul className="tp-positions">
                <li className="tp-head tp-pos-cols" aria-hidden="true">
                  <span>Coin</span><span className="tp-r">Size</span><span className="tp-r">Entry</span><span className="tp-r">Mark</span>
                  <span className="tp-r">uPnL</span><span>To liquidation</span><span />
                </li>
                {positions.map(p => (
                  <PositionCard key={p.hl_coin} p={p} address={address} isMobile={isMobile}
                    open={openPos === p.hl_coin} onToggle={() => setOpenPos(o => (o === p.hl_coin ? null : p.hl_coin))} />
                ))}
              </ul>
            )}
        </section>
      )}

      {!data.missing && !data.loading && <History address={address} isMobile={isMobile} />}
    </div>
  );
}
