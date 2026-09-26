import { Fragment, useState } from "react";
import { T, col } from "../theme.js";
import useFollowed from "../hooks/useFollowed.js";
import { SIDE_COLOR, activitySummary, fmtPx, fmtUsd, fmtWhen, holdingsLine, shortAddr } from "../utils/traderFormat.js";

// Profitable traders holding a coin: one row each, details on click.
export default function TraderEntries({ entries, onShow }) {
  const [open, setOpen] = useState(null);
  const { followed, toggle } = useFollowed();
  const traders = entries.traders || [];
  const coin = entries.symbol;
  if (!traders.length) return <div className="te"><p className="te-note">No profitable traders hold {coin} right now.</p></div>;
  const side = k => entries.sides?.[k] || { n: 0 };
  const summary = ["long", "short"].filter(k => side(k).n)
    .map(k => `${side(k).n} ${k}, median entry ${fmtPx(side(k).median_entry)}`).join(" · ");

  return (
    <div className="te">
      <div className="te-head">
        <span><strong>Profitable traders in {coin}</strong> · {summary}</span>
        {onShow && <button type="button" className="te-link" onClick={onShow}>Show entries</button>}
      </div>
      <table className="te-table">
        <thead>
          <tr>
            <th>Trader</th><th>Position</th><th className="te-wide">Avg entry</th><th>P&amp;L</th>
            <th className="te-wide">Opened</th><th className="te-wide">On this coin</th><th className="te-wide">Also holds</th><th />
          </tr>
        </thead>
        <tbody>
          {traders.map(tr => {
            const isOpen = open === tr.address;
            const isFollowed = followed.has(tr.address);
            return (
              <Fragment key={tr.address}>
                <tr className={isOpen ? "te-open" : ""} onClick={() => setOpen(isOpen ? null : tr.address)} tabIndex={0}
                  onKeyDown={e => { if (e.key === "Enter") setOpen(isOpen ? null : tr.address); }} aria-expanded={isOpen}>
                  <td>
                    <b className="te-label" style={{ color: col(SIDE_COLOR[tr.side]) }}>{tr.label}</b>
                    <span className="te-addr">{shortAddr(tr.address)}</span>
                  </td>
                  <td><span style={{ color: col(SIDE_COLOR[tr.side]) }}>{tr.side === "long" ? "Long" : "Short"}</span> {fmtUsd(tr.size_usd)}</td>
                  <td className="te-wide">{fmtPx(tr.entry_px)}</td>
                  <td className={tr.pnl_pct >= 0 ? "te-up" : "te-down"}>{tr.pnl_pct >= 0 ? "+" : ""}{Math.round(tr.pnl_pct)}%</td>
                  <td className="te-wide">{tr.pending ? "loading…" : tr.opened_at ? fmtWhen(tr.opened_at) : tr.covered_from ? `before ${fmtWhen(tr.covered_from)}` : "—"}</td>
                  <td className="te-wide">
                    {tr.pending ? "loading…" : activitySummary(tr.bursts)}
                    {tr.buying_now && <div className="te-live">{tr.side === "long" ? "still buying" : "still selling"} (timed order)</div>}
                  </td>
                  <td className="te-wide">{holdingsLine(tr.others)}</td>
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
                    <td colSpan={8}>
                      <div className="te-cols">
                        <div>
                          <h4>{coin} fills</h4>
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
                                  <span style={{ color: col(SIDE_COLOR[p.side]) }}>{p.side}</span> {p.coin} {fmtUsd(p.size_usd)} at {fmtPx(p.entry_px)}
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
      <p className="te-note">From Hyperliquid's public fills (each trader's latest 2,000). P&amp;L is on margin. Click a trader for the fills and their other positions; Follow sends their changes to Telegram.</p>
    </div>
  );
}
