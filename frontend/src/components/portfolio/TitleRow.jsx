// B0. Title row: "Portfolio", then on one line the wallet, read-only, the close clock and freshness
// (or the feeds that failed, with one Retry).
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import PageTitle from "../PageTitle.jsx";
import WalletTag from "../WalletTag.jsx";
import { shortAddr } from "../../utils/walletName.js";
import { profilePath } from "../../utils/traderBoard.js";
import { ago, closeClock, clockText } from "../../utils/portfolio/format.js";
import { IDENTITY, INFO, TITLE } from "./copy.js";

export const STALE_SOFT_MS = 45_000;
export const STALE_HARD_MS = 120_000;

export default function TitleRow({ address, readOnly, onStopViewing, lastMainAt, failedNames = [], onRetry, onCopied, phone }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 5000); return () => clearInterval(t); }, []);
  const clk = closeClock(now);
  const age = lastMainAt ? now - lastMainAt : null;
  const hard = age != null && age > STALE_HARD_MS;
  const soft = age != null && age > STALE_SOFT_MS;
  const copy = async () => {
    try { await navigator.clipboard.writeText(address); } catch { /* clipboard blocked */ }
    onCopied?.();
  };
  const failed = failedNames.length > 0;
  const status = failed ? (
    <span className="pf-feedfail" title={failedNames.join(", ")}>
      {failedNames.length === 1 ? IDENTITY.failed(failedNames[0]) : IDENTITY.nFailed(failedNames.length)}
      <span className="pf-sep" aria-hidden="true"> · </span>
      <button type="button" className="pf-textbtn" onClick={onRetry}>{IDENTITY.retry}</button>
    </span>
  ) : hard ? (
    <span className="pf-feedfail">{IDENTITY.stale}<span className="pf-sep" aria-hidden="true"> · </span>
      <button type="button" className="pf-textbtn" onClick={onRetry}>{IDENTITY.retry}</button></span>
  ) : lastMainAt ? <span className="freshness pf-fresh" data-soft={soft ? "" : undefined}>{ago(lastMainAt, now)}</span> : null;

  return <div className="pf-title">
    <PageTitle>{TITLE}</PageTitle>
    <div className="pf-id">
      <Link to={profilePath(address)} className="pf-wtag"><WalletTag address={address} size={phone ? 18 : 20} /></Link>
      {!phone && <button type="button" className="pf-addr" onClick={copy} title={address}>{shortAddr(address)}</button>}
      {readOnly && !phone && <><span className="pf-sep" aria-hidden="true">·</span><span>{IDENTITY.readOnly}</span>
        <span className="pf-sep" aria-hidden="true">·</span>
        <button type="button" className="pf-textbtn" onClick={onStopViewing}>{IDENTITY.stopViewing}</button></>}
      {!phone && <span className="pf-clock" title={`1D ${clockText(clk.d1)} · 1W ${clockText(clk.w1)}\n${INFO.clock}`}>4H {clockText(clk.h4)}</span>}
      {status}
    </div>
    {readOnly && phone && <div className="pf-id pf-id-2">
      <span>{IDENTITY.readOnly}</span><span className="pf-sep" aria-hidden="true">·</span>
      <button type="button" className="pf-textbtn" onClick={onStopViewing}>{IDENTITY.stopViewing}</button>
    </div>}
  </div>;
}
