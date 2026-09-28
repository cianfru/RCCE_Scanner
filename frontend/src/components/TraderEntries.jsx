import { Fragment, useState } from "react";
import useFollowed from "../hooks/useFollowed.js";
import { sideColor, fmtPx, fmtUsd, fmtWhen, shortAddr } from "../utils/traderFormat.js";

// Profitable traders holding a coin: the largest few, one row each; their fills and other
// positions on click, the rest behind "Show all".
export default function TraderEntries({ entries, onShow, loading = false, limit = 5 }) {
  const [open, setOpen] = useState(null);
  const [all, setAll] = useState(false);
  const { followed, toggle } = useFollowed();
  if (loading && !entries) {
    return (
      <div className="te" aria-busy="true">
        <p className="te-loading">Loading fills…</p>
        {[0, 1, 2].map(i => <div key={i} className="te-skel shimmer-loading" aria-hidden="true" />)}
      </div>
    );
  }
  if (!entries) return null;
  const traders = entries.traders || [];
  const coin = entries.symbol;
  if (!traders.length) return <div className="te"><p className="te-note">No profitable traders hold {coin} right now.</p></div>;
  const shown = all ? traders : traders.slice(0, limit);

  return (
    <div className="te">
      <div className="te-head">
        <strong>Largest profitable traders</strong>
        {onShow && <button type="button" className="te-link" onClick={onShow}>Show on chart</button>}
      </div>
      <table className="te-table">
        <thead>
          <tr>
            <th>Trader</th><th>Position</th><th className="te-wide">Avg entry</th><th>P&amp;L</th>
            <th className="te-wide">Opened</th><th />
          </tr>
        </thead>
        <tbody>
          {shown.map(tr => {
            const isOpen = open === tr.address;
            const isFollowed = followed.has(String(tr.address).toLowerCase());
            return (
              <Fragment key={tr.address}>
                <tr className={isOpen ? "te-open" : ""} onClick={() => setOpen(isOpen ? null : tr.address)} tabIndex={0}
                  onKeyDown={e => { if (e.key === "Enter") setOpen(isOpen ? null : tr.address); }} aria-expanded={isOpen}>
                  <td>
                    <b className="te-label" style={{ color: sideColor(tr.side) }}>{tr.label}</b>
                    <span className="te-addr">{shortAddr(tr.address)}</span>
                  </td>
                  <td><span style={{ color: sideColor(tr.side) }}>{tr.side === "long" ? "Long" : "Short"}</span> {fmtUsd(tr.size_usd)}</td>
                  <td className="te-wide">{fmtPx(tr.entry_px)}</td>
                  <td className={tr.pnl_pct >= 0 ? "te-up" : "te-down"}>{tr.pnl_pct >= 0 ? "+" : ""}{Math.round(tr.pnl_pct)}%</td>
                  <td className="te-wide">{tr.pending ? "loading…" : tr.opened_at ? fmtWhen(tr.opened_at) : tr.covered_from ? `before ${fmtWhen(tr.covered_from)}` : "—"}</td>
                  <td>
                    <button type="button" className={`te-follow${isFollowed ? " on" : ""}`} aria-pressed={isFollowed}
                      title={isFollowed ? "Stop following this trader" : "Follow: Telegram alert when this trader opens, closes, adds or cuts a position"}
                      onClick={e => { e.stopPropagation(); toggle(tr.address, `${tr.side} ${coin}`); }}>
                      {isFollowed ? "Following" : "Follow"}
                    </button>
                  </td>
                </tr>
                {isOpen && (
                  <tr className="te-detail">
                    <td colSpan={6}>
                      <div className="te-cols">
                        <div>
                          <h4>{coin} fills</h4>
                          {tr.buying_now && <p className="te-live">{tr.side === "long" ? "Still buying" : "Still selling"} (timed order)</p>}
                          <p className="te-mobile">Average entry {fmtPx(tr.entry_px)} · {tr.opened_at ? `opened ${fmtWhen(tr.opened_at)}` : tr.covered_from ? `opened before ${fmtWhen(tr.covered_from)}` : "opening not found"}</p>
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
                                  <span className={p.pnl_pct >= 0 ? "te-up" : "te-down"}> {p.pnl_pct >= 0 ? "+" : ""}{Math.round(p.pnl_pct)}%</span>
                                </li>
                              ))}
                              {tr.others.length > 8 && <li className="te-dim">+{tr.others.length - 8} smaller positions</li>}
                            </ul>
                          ) : <p className="te-note">No other open positions.</p>}
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
      {traders.length > limit && <button type="button" className="te-link te-all" aria-expanded={all} onClick={() => setAll(v => !v)}>{all ? "Show fewer" : `Show all ${traders.length}`}</button>}
    </div>
  );
}
