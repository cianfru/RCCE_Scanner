import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import HelpTip from "./HelpTip.jsx";
import AsOf from "./AsOf.jsx";
import { apiFetch } from "../edge.js";
import TokenLogo from "./TokenLogo.jsx";
import { WalletAvatar } from "./WalletTag.jsx";
import { nameIn, shortAddr, viewNames } from "../utils/walletName.js";
import { coinStrip, fmtPnl, fmtRate, fmtRoi, profilePath, sizeBand, windowLabel, WINDOWS } from "../utils/traderBoard.js";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";
const PAGE = 50;
const logoKey = coin => `${coin}/USDT`;

// "7d · 30d · All time": underlined text, no pills.
export function WindowSwitch({ value, onChange, label = "PnL window" }) {
  return (
    <div className="lb-win" role="group" aria-label={label}>
      {WINDOWS.map((w, i) => (
        <span key={w.key}>
          {i > 0 && <span className="lb-win-dot" aria-hidden="true">·</span>}
          <button type="button" aria-pressed={value === w.key} onClick={() => onChange(w.key)}>{w.label}</button>
        </span>
      ))}
    </div>
  );
}

export function LeaderboardHelp() {
  return (
    <HelpTip title="How the leaderboard is built" width={400} label="About the leaderboard">
      <p>Profitable traders: Hyperliquid wallets with at least 30% and $10K profit this month, already in profit before it, and at least $5K in their perp account. Market makers are left out.</p>
      <p>Ranked by PnL over the window, from Hyperliquid's own leaderboard (refreshed daily). ROI is Hyperliquid's for the same window; it is blank when the account started the window nearly empty.</p>
      <p>Win rate: positions closed in the last 30 days that made money after fees, from each trader's public fills. Positions: open now.</p>
    </HelpTip>
  );
}

function Coins({ row }) {
  const { shown, more } = coinStrip(row.coins, 5);
  if (!row.positions) return <span className="lb-flat">{row.positions === 0 ? "Flat" : "—"}</span>;
  return (
    <span className="lb-coins" title={(row.coins || []).join(", ")}>
      <span className="lb-n">{row.positions}</span>
      <span className="lb-logos">
        {shown.map((c, i) => (
          <span key={c} className="lb-logo" style={{ zIndex: 10 - i }}><TokenLogo symbol={logoKey(c)} size={20} /></span>
        ))}
      </span>
      {more > 0 && <span className="lb-more">+{more}</span>}
    </span>
  );
}

function WinRate({ row }) {
  if (row.win_rate == null) {
    return <span className="lb-dim" title={row.closed_30d === 0 ? "No positions closed in the last 30 days" : "Being computed from the trader's fills"}>—</span>;
  }
  // Fewer than five closed positions: the rate is shown faint, it says little.
  const thin = (row.closed_30d || 0) < 5;
  return (
    <span className={`lb-wr${thin ? " lb-thin" : ""}`} title={`${row.closed_30d} positions closed in the last 30 days`}>
      <span className="lb-wr-n">{fmtRate(row.win_rate)}</span>
      <span className="lb-wr-bar" aria-hidden="true"><i style={{ width: `${Math.max(2, row.win_rate)}%` }} /></span>
      <span className="lb-wr-of">{row.closed_30d}</span>
    </span>
  );
}

function Row({ row, name }) {
  const pnlClass = row.pnl > 0 ? "lb-up" : row.pnl < 0 ? "lb-down" : "";
  const band = row.band || sizeBand(row.account_value) || "—";
  return (
    <li>
      <Link className={`lb-row${row.rank <= 3 ? " lb-top" : ""}`} to={profilePath(row.address)} title={`${name}\n${row.address}`}>
        <span className="lb-rank">{row.rank}</span>
        <span className="lb-who">
          <WalletAvatar address={row.address} size={32} />
          <span className="lb-names"><span className="lb-name">{name}</span><span className="lb-addr">{shortAddr(row.address)}</span></span>
        </span>
        <span className={`lb-pnl ${pnlClass}`}>{fmtPnl(row.pnl)}<span className="lb-band-m">{band}</span></span>
        <span className="lb-roi">{fmtRoi(row.roi)}</span>
        <span className="lb-win-c"><WinRate row={row} /></span>
        <span className="lb-pos"><Coins row={row} /></span>
        <span className="lb-band">{band}</span>
        {/* Phones: the rest of the row as one line under the name. */}
        <span className="lb-mline">
          <span><span className="lb-k">ROI</span>{fmtRoi(row.roi)}</span>
          <span><span className="lb-k">Win</span><WinRate row={row} /></span>
          <Coins row={row} />
        </span>
      </Link>
    </li>
  );
}

// Profitable traders ranked by PnL over the window; a row opens the trader's profile.
export default function TraderLeaderboard({ window: win = "30d", onWindow, showSwitch = true }) {
  const [state, setState] = useState({ rows: [], total: 0, loading: true, error: false, window: win, meta: null });
  const [count, setCount] = useState(PAGE);
  const polls = useRef(0);

  useEffect(() => { setCount(PAGE); polls.current = 0; }, [win]);

  // The top `count` rows (the server caches the ranking for a minute, so "Show more" refetches).
  useEffect(() => {
    let cancelled = false;
    let timer = null;
    const load = () => {
      apiFetch(`/api/traders/leaderboard?window=${win}&offset=0&limit=${count}`)
        .then(r => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
        .then(d => {
          if (cancelled) return;
          setState({ rows: d.rows || [], total: d.total || 0, loading: false, error: false, window: win,
            meta: { as_of: d.as_of, stale: d.stale } });
          // Win rates arrive over a few minutes: look again while some are missing.
          if ((d.win_rate_pending || 0) > 0 && polls.current < 8) {
            polls.current += 1;
            timer = setTimeout(load, 30_000);
          }
        })
        .catch(() => { if (!cancelled) setState(s => ({ ...s, loading: false, error: true })); });
    };
    setState(s => ({ ...s, loading: true }));
    load();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [win, count]);

  const names = useMemo(() => viewNames(state.rows.map(r => r.address)), [state.rows]);
  // A window switch keeps the old rows (dimmed) until the new ones land.
  const rows = state.rows;
  const stale = state.loading && state.window !== win;

  return (
    <div className="lb">
      <div className="lb-top-line">
        <span className="lb-title">Profitable traders <LeaderboardHelp /></span>
        <AsOf data={state.meta} />
        {showSwitch && <WindowSwitch value={win} onChange={onWindow} />}
      </div>
      {state.loading && !rows.length ? (
        <ul className="lb-list" aria-busy="true">
          {Array.from({ length: 8 }, (_, i) => <li key={i}><div className="lb-skel shimmer-loading" /></li>)}
        </ul>
      ) : state.error && !rows.length ? (
        <p className="lb-empty">Leaderboard unavailable.</p>
      ) : !rows.length ? (
        <p className="lb-empty">No traders yet. The roster loads after the daily Hyperliquid leaderboard download.</p>
      ) : (
        <ul className={`lb-list${stale ? " lb-stale" : ""}`}>
          <li className="lb-head" aria-hidden="true">
            <span>#</span><span>Trader</span><span className="lb-r">PnL {windowLabel(win)}</span><span className="lb-r">ROI</span>
            <span>Win rate 30d</span><span>Positions</span><span className="lb-r">Account</span>
          </li>
          {rows.map(r => <Row key={r.address} row={r} name={nameIn(names, r.address)} />)}
        </ul>
      )}
      {rows.length > 0 && state.total > rows.length && (
        <div className="lb-foot">
          <button type="button" className="te-link" onClick={() => setCount(c => c + PAGE)}>Show more</button>
          <span className="lb-dim">{rows.length} of {state.total}</span>
        </div>
      )}
    </div>
  );
}
