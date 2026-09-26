import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { col } from "../theme.js";
import useFollowed from "../hooks/useFollowed.js";
import { SIDE_COLOR, changeLine, fmtPx, fmtUsd, fmtWhen, shortAddr } from "../utils/traderFormat.js";

const COHORT_NAME = { money_printer: "profitable trader", smart_money: "large account", elite: "both" };

// Followed traders: current positions and recorded changes; changes also go to Telegram.
export default function FollowingView() {
  const { data, toggle, reload } = useFollowed();
  const [addr, setAddr] = useState("");
  const [msg, setMsg] = useState("");
  const navigate = useNavigate();
  const traders = data?.traders || [];

  const add = async e => {
    e.preventDefault();
    const a = addr.trim();
    if (!/^0x[0-9a-fA-F]{40}$/.test(a)) { setMsg("Enter a 0x wallet address."); return; }
    const ok = await toggle(a);
    setMsg(ok ? "" : "Could not follow: set the admin key in Settings.");
    if (ok) setAddr("");
  };

  return (
    <div className="fol">
      <p className="coh-intro">
        {traders.length ? `${traders.length} followed trader${traders.length > 1 ? "s" : ""}.` : "No followed traders yet."}{" "}
        {data && (data.telegram === "ready"
          ? "Opens, closes, adds and cuts of $10K or more are sent to Telegram."
          : data.telegram === "no-chat"
          ? "Telegram has no chat to send to yet: send /watch followed by your wallet address to the bot once, and changes will arrive there."
          : "The Telegram bot is not running on the server, so changes show here only.")}
        {" "}Follow a trader from a coin's chart, or add an address.
      </p>
      <form className="fol-add" onSubmit={add}>
        <input value={addr} onChange={e => setAddr(e.target.value)} placeholder="0x wallet address" aria-label="Wallet address to follow" spellCheck={false} />
        <button type="submit" className="te-link">Follow</button>
        {msg && <span className="fol-msg">{msg}</span>}
      </form>
      {traders.map(t => (
        <section key={t.address} className="fol-card">
          <div className="fol-top">
            <span className="fol-name">{shortAddr(t.address)}{t.note ? <span className="fol-note"> · {t.note}</span> : null}</span>
            <span className="fol-meta">
              {t.tracked ? t.cohorts.map(c => COHORT_NAME[c] || c).filter(c => c !== "both").join(", ") : "not in the tracked roster"}
              {t.account_value ? ` · account ${fmtUsd(t.account_value)}` : ""}
              {t.ts ? ` · read ${fmtWhen(t.ts)}` : ""}
            </span>
            <button type="button" className="te-follow on" onClick={() => toggle(t.address).then(reload)}>Unfollow</button>
          </div>
          {!t.tracked && <p className="te-note">Only wallets in the tracked roster (profitable traders and large accounts) are read, so this one gets no updates while it is outside it.</p>}
          {t.positions?.length ? (
            <table className="te-table">
              <thead><tr><th>Coin</th><th>Position</th><th>Avg entry</th><th>P&amp;L</th></tr></thead>
              <tbody>
                {t.positions.map(p => (
                  <tr key={`${p.coin}-${p.side}`} onClick={() => navigate(`/scanner/${encodeURIComponent(p.coin)}`)}>
                    <td>{p.coin}</td>
                    <td><span style={{ color: col(SIDE_COLOR[p.side]) }}>{p.side === "long" ? "Long" : "Short"}</span> {fmtUsd(p.size_usd)}</td>
                    <td>{fmtPx(p.entry_px)}</td>
                    <td className={p.pnl_pct >= 0 ? "te-up" : "te-down"}>{p.pnl_pct >= 0 ? "+" : ""}{Math.round(p.pnl_pct)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : t.tracked ? <p className="te-note">No open positions.</p> : null}
          {t.events?.length > 0 && (
            <ul className="fol-events">
              {t.events.slice(0, 5).map((e, i) => <li key={i}><span className="te-dim">{fmtWhen(e.ts)}</span> {changeLine(e)}</li>)}
            </ul>
          )}
        </section>
      ))}
    </div>
  );
}
