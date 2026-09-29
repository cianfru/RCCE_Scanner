import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { profilePath } from "../utils/traderBoard.js";
import useFollowed from "../hooks/useFollowed.js";
import { sideBarColor, sideColor, fmtPx, fmtUsd, fmtWhen } from "../utils/traderFormat.js";
import { openedAgo, pnlPct, sizeShare, vsNowLabel } from "../utils/traderRow.js";
import { nameIn, viewNames } from "../utils/walletName.js";
import WalletTag from "./WalletTag.jsx";

const sideWord = s => (s === "long" ? "Long" : "Short");

function openedTitle(tr) {
  if (tr.opened_at) return `Opened ${fmtWhen(tr.opened_at)}`;
  if (tr.covered_from) return `Opened before ${fmtWhen(tr.covered_from)}, the earliest fill on hand`;
  return tr.pending ? "Loading fills" : "Opening not found in the available fills";
}

// Profitable traders holding a coin: the largest few, one row each; their fills and other
// positions on click, the rest behind "Show all". price: the coin's price now, for the hint
// under each entry. footer: extra links for the footer row (the card's "New positions").
export default function TraderEntries({ entries, onShow, loading = false, limit = 5, price = null, footer = null }) {
  const [open, setOpen] = useState(null);
  const [all, setAll] = useState(false);
  const { followed, toggle } = useFollowed();
  const names = useMemo(() => viewNames((entries?.traders || []).map(t => t.address)), [entries]);
  if (loading && !entries) {
    return (
      <div className="te" aria-busy="true">
        <p className="te-loading">Loading traders…</p>
        {[0, 1, 2].map(i => <div key={i} className="te-skel shimmer-loading" aria-hidden="true" />)}
      </div>
    );
  }
  if (!entries) return null;
  const traders = entries.traders || [];
  const coin = entries.symbol;
  if (!traders.length) return <div className="te"><p className="te-note">No profitable traders hold {coin} right now.</p></div>;
  const shown = all ? traders : traders.slice(0, limit);
  const maxSize = Math.max(...traders.map(t => t.size_usd || 0));
  const now = Date.now();

  return (
    <div className="te">
      <div className="te-head">
        <strong>Largest profitable traders</strong>
        {onShow && <button type="button" className="te-link" onClick={onShow}>Show on chart</button>}
      </div>
      <ul className="te-list">
        <li className="te-cols-head" aria-hidden="true">
          <span>Trader</span><span>Position</span><span className="te-r">Avg entry</span>
          <span className="te-r">P&amp;L</span><span className="te-r">Opened</span><span />
        </li>
        {shown.map(tr => {
          const isOpen = open === tr.address;
          const isFollowed = followed.has(String(tr.address).toLowerCase());
          const name = nameIn(names, tr.address);
          const opened = openedAgo(tr, now) || "—";
          const pnl = pnlPct(tr.pnl_pct);
          const vsNow = vsNowLabel(tr.entry_px, price);
          const share = sizeShare(tr.size_usd, maxSize);
          const flip = () => setOpen(isOpen ? null : tr.address);
          return (
            <li key={tr.address} className={`te-row${isOpen ? " te-open" : ""}`}>
              <div className="te-main" role="button" tabIndex={0} aria-expanded={isOpen}
                aria-label={`${name}: ${tr.side} ${fmtUsd(tr.size_usd)}, average entry ${fmtPx(tr.entry_px)}, P&L ${pnl}, opened ${opened}. ${isOpen ? "Hide" : "Show"} fills and other positions`}
                onClick={flip} onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); flip(); } }}>
                <span className="te-c te-who">
                  {/* The name opens the trader's profile; the rest of the row opens the fills below. */}
                  <Link className="te-who-link" to={profilePath(tr.address)} onClick={e => e.stopPropagation()} onKeyDown={e => e.stopPropagation()}>
                    <WalletTag className="te-addr" address={tr.address} name={name} size={34} sub />
                  </Link>
                </span>
                <span className="te-c te-pos">
                  <span className="te-pos-t"><span className="te-side" style={{ color: sideColor(tr.side) }}>{sideWord(tr.side)}</span> <span className="te-size">{fmtUsd(tr.size_usd)}</span></span>
                  <span className="te-sbar" aria-hidden="true"><i style={{ width: `${share * 100}%`, background: sideBarColor(tr.side) }} /></span>
                </span>
                <span className="te-c te-entry te-r">
                  <span className="te-k">Entry </span><span className="te-num">{fmtPx(tr.entry_px)}</span>
                  {vsNow && <span className="te-vs" title={`${coin} now ${fmtPx(price)}`}>{vsNow}</span>}
                </span>
                <span className={`te-c te-pnl te-r ${tr.pnl_pct >= 0 ? "te-up" : "te-down"}`} title="Unrealised P&L on margin">{pnl}</span>
                <span className="te-c te-when te-r" title={openedTitle(tr)}>{opened}</span>
              </div>
              <button type="button" className={`te-fbtn${isFollowed ? " on" : ""}`} aria-pressed={isFollowed}
                aria-label={`${isFollowed ? "Unfollow" : "Follow"} ${name}`}
                title={isFollowed ? "Stop following this trader" : "Follow: Telegram alert when this trader opens, closes, adds or cuts a position"}
                onClick={() => toggle(tr.address, `${tr.side} ${coin}`)}>
                {isFollowed ? "Following" : "Follow"}
              </button>
              {isOpen && (
                <div className="te-detail">
                  <div className="te-cols">
                    <div>
                      <h4>{coin} fills</h4>
                      {tr.buying_now && <p className="te-live">{tr.side === "long" ? "Still buying" : "Still selling"} (timed order)</p>}
                      {(tr.bursts || []).length ? (
                        <ul>
                          {tr.bursts_total > tr.bursts.length && <li className="te-note">{tr.bursts_total - tr.bursts.length} earlier bursts not shown</li>}
                          {[...tr.bursts].reverse().map((b, i) => {
                            const buy = (b.kind === "open") === (b.side === "long");
                            return (
                              <li key={i}>
                                <span className={b.kind === "close" ? "te-dim" : buy ? "te-up" : "te-down"}>{b.kind === "close" ? "Reduced" : buy ? "Bought" : "Sold"}</span>
                                {" "}{fmtUsd(b.usd)} at {fmtPx(b.px)} · {fmtWhen(b.t)}{b.t_end - b.t >= 600 ? ` to ${fmtWhen(b.t_end)}` : ""}{b.twap ? " · timed order" : ""}
                              </li>
                            );
                          })}
                        </ul>
                      ) : <p className="te-note">{tr.pending ? "Loading fills…" : "No fills in the available history."}</p>}
                    </div>
                    <div>
                      <h4>Other positions{tr.account_value ? ` · account ${fmtUsd(tr.account_value)}` : ""}</h4>
                      {(tr.others || []).length ? (
                        <ul>
                          {tr.others.slice(0, 8).map(p => (
                            <li key={`${p.coin}-${p.side}`}>
                              <span style={{ color: sideColor(p.side) }}>{p.side}</span> {p.coin} {fmtUsd(p.size_usd)} at {fmtPx(p.entry_px)}
                              <span className={p.pnl_pct >= 0 ? "te-up" : "te-down"}> {pnlPct(p.pnl_pct)}</span>
                            </li>
                          ))}
                          {tr.others.length > 8 && <li className="te-dim">+{tr.others.length - 8} smaller positions</li>}
                        </ul>
                      ) : <p className="te-note">No other open positions.</p>}
                    </div>
                  </div>
                </div>
              )}
            </li>
          );
        })}
      </ul>
      {(traders.length > limit || footer) && (
        <div className="te-foot">
          {traders.length > limit && <button type="button" className="te-link" aria-expanded={all} onClick={() => setAll(v => !v)}>{all ? "Show fewer" : `Show all ${traders.length}`}</button>}
          {footer}
        </div>
      )}
    </div>
  );
}
