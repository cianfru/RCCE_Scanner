import { Fragment, useEffect, useMemo, useState } from "react";
import TokenLogo from "./TokenLogo.jsx";
import WalletTag from "./WalletTag.jsx";
import { T } from "../theme.js";
import { fmtUsd, fmtSignedUsd } from "../utils/hyperlens.js";
import { nameIn, viewNames } from "../utils/walletName.js";
import { summaryRows, entryGap, dayChange, moneyBar, topWallets, fmtDelta, fmtGap } from "../utils/traderSummary.js";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";
const logoKey = (coin) => `${String(coin || "").split(":").pop()}/USDT`;
const fmtPx = (v) => `$${Number(v || 0).toLocaleString(undefined, { maximumFractionDigits: v >= 100 ? 0 : v >= 1 ? 2 : 5 })}`;

function Chevron({ open }) {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"
      style={{ transform: open ? "rotate(180deg)" : "none", transition: "transform 0.2s ease" }}>
      <path d="M2.5 4.5 6 8l3.5-3.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// Dollars long (green) and short (red) on a track as long as the list's largest coin.
function MoneyBar({ bar }) {
  return (
    <span className="ts-bar" aria-hidden="true">
      <i style={{ width: `${bar.long * 100}%`, background: T.green }} />
      <i style={{ width: `${bar.short * 100}%`, background: T.red }} />
    </span>
  );
}

function Counts({ r }) {
  return (
    <span className="ts-counts">
      <b style={{ color: T.green }}>{r.long?.n || 0}</b>
      <span className="ts-slash">/</span>
      <b style={{ color: T.red }}>{r.short?.n || 0}</b>
    </span>
  );
}

function Gap({ r, compact }) {
  const g = entryGap(r);
  if (!g) return <span className="ts-dim">--</span>;
  const who = g.side === "long" ? "longs'" : "shorts'";
  return (
    <span title={`Price ${fmtPx(r.mark)} against the ${who} median entry ${fmtPx(g.entry)}. ${g.winning ? "That side is in profit." : "That side is at a loss."}`}>
      <b style={{ color: g.winning ? T.green : T.red }}>{fmtGap(g.pct)}</b>
      {!compact && <span className="ts-dim"> {g.pct >= 0 ? "above" : "below"} entry</span>}
    </span>
  );
}

function Change({ r }) {
  const c = dayChange(r);
  if (!c) return <span className="ts-dim">--</span>;
  const tone = (v, color) => (v ? color : T.text4);
  return (
    <span className="ts-counts" title="Traders long and short now, against a day ago">
      <span style={{ color: tone(c.long, T.green) }}>{fmtDelta(c.long)}</span>
      <span className="ts-slash">/</span>
      <span style={{ color: tone(c.short, T.red) }}>{fmtDelta(c.short)}</span>
    </span>
  );
}

// The open row: the group's three largest wallets on each side, then every wallet.
function TopWallets({ coin, cohortTag, isMobile, onWalletClick, onAllWallets }) {
  const [state, setState] = useState({ loading: true, positions: [] });
  useEffect(() => {
    let cancelled = false;
    setState({ loading: true, positions: [] });
    fetch(`${API}/api/hyperlens/positions/${encodeURIComponent(coin)}`)
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(r.status))))
      .then(d => { if (!cancelled) setState({ loading: false, positions: d.positions || [] }); })
      .catch(() => { if (!cancelled) setState({ loading: false, positions: [], error: true }); });
    return () => { cancelled = true; };
  }, [coin]);
  const top = useMemo(() => topWallets(state.positions, cohortTag), [state.positions, cohortTag]);
  const names = useMemo(() => viewNames([...top.long, ...top.short].map(p => p.address)), [top]);

  const side = (key, label, color) => {
    const list = top[key];
    return (
      <div className="ts-side">
        <div className="ts-side-head" style={{ color }}>{label}</div>
        {list.length === 0 && <div className="ts-dim ts-wallet">None</div>}
        {list.map(p => (
          <button key={p.address} type="button" className="ts-wallet" onClick={() => onWalletClick(p.address)}>
            <WalletTag className="ts-addr" address={p.address} name={nameIn(names, p.address)} />
            <span className="ts-size">{fmtUsd(p.size_usd)}</span>
            {!isMobile && <span className="ts-dim ts-entry">@ {fmtPx(p.entry_px)}</span>}
            <span className="ts-pnl" style={{ color: (p.unrealized_pnl || 0) >= 0 ? T.green : T.red }}>{fmtSignedUsd(p.unrealized_pnl || 0)}</span>
          </button>
        ))}
      </div>
    );
  };

  return (
    <div className="ts-open">
      {state.loading ? <div className="ts-dim ts-note">Loading...</div>
        : state.error ? <div className="ts-dim ts-note">Wallets unavailable</div>
        : <div className="ts-sides">{side("long", "Largest long", T.green)}{side("short", "Largest short", T.red)}</div>}
      <div className="ts-open-foot">
        <button type="button" className="te-link" onClick={onAllWallets}>All wallets</button>
      </div>
    </div>
  );
}

export default function TraderSummary({ rows, filter, cohort, isMobile, onWalletClick, onSymbolClick }) {
  const [open, setOpen] = useState(null);
  const [showMore, setShowMore] = useState(false);
  const { shown, more } = useMemo(() => summaryRows(rows, filter), [rows, filter]);
  const list = showMore ? [...shown, ...more] : shown;
  const has24h = useMemo(() => (rows || []).some(r => r.day_ago), [rows]);
  const cohortTag = cohort === "large" ? "smart_money" : "money_printer";
  const cols = 3 + (isMobile ? 0 : 1 + (has24h ? 1 : 0)) + 1;
  const toggle = (coin) => setOpen(o => (o === coin ? null : coin));

  if (!list.length) {
    return <div className="ts-empty">{filter ? "No matching coins" : "Waiting for wallet data..."}</div>;
  }

  return (
    <div className="ts">
      <table className={`ts-table${isMobile ? " ts-phone" : ""}`}>
        <thead>
          <tr>
            <th className="ts-coin-h">Coin</th>
            <th className="ts-counts-h" title="Traders long / short">{isMobile ? "L / S" : "Long / short"}</th>
            {!isMobile && <th className="ts-money-h" title="Their dollars long / short">Dollars</th>}
            <th className="ts-gap-h" title="Price against the median entry of the side most of them are on">{isMobile ? "Vs entry" : "Price vs entry"}</th>
            {!isMobile && has24h && <th className="ts-day-h" title="Change in traders long / short since a day ago">24h</th>}
            <th className="ts-chev" aria-label="Open" />
          </tr>
        </thead>
        <tbody>
          {list.map((r, i) => {
            const isOpen = open === r.coin;
            return (
              <Fragment key={r.coin}>
                <tr data-coin-row className={`ts-row${i % 2 ? " ts-stripe" : ""}${isOpen ? " ts-row-open" : ""}`} tabIndex={0} aria-expanded={isOpen}
                  onClick={() => toggle(r.coin)}
                  onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(r.coin); } }}>
                  <td>
                    <span className="ts-coin"><TokenLogo symbol={logoKey(r.coin)} size={20} />{r.coin}</span>
                    {isMobile && (
                      <div className="ts-sub">{fmtUsd(r.long?.usd)} / {fmtUsd(r.short?.usd)}</div>
                    )}
                  </td>
                  <td><Counts r={r} /></td>
                  {!isMobile && (
                    <td>
                      <span className="ts-money">
                        <span className="ts-money-t">{fmtUsd(r.long?.usd)} / {fmtUsd(r.short?.usd)}</span>
                        <MoneyBar bar={moneyBar(r, list)} />
                      </span>
                    </td>
                  )}
                  <td><Gap r={r} compact={isMobile} /></td>
                  {!isMobile && has24h && <td><Change r={r} /></td>}
                  <td className="ts-chev"><Chevron open={isOpen} /></td>
                </tr>
                {isOpen && (
                  <tr className="ts-open-row">
                    <td colSpan={cols}>
                      <TopWallets coin={r.coin} cohortTag={cohortTag} isMobile={isMobile}
                        onWalletClick={onWalletClick} onAllWallets={() => onSymbolClick(r.coin)} />
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
      {more.length > 0 && (
        <div className="ts-more">
          <button type="button" className="te-link" aria-expanded={showMore} onClick={() => setShowMore(v => !v)}>
            {showMore ? "Show fewer" : `Show ${more.length} more`}
          </button>
        </div>
      )}
    </div>
  );
}
