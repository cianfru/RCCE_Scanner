import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { track } from "../usage.js";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import TokenLogo from "./TokenLogo.jsx";
import { WalletAvatar } from "./WalletTag.jsx";
import useSetupMap from "../hooks/useSetupMap.js";
import useSearchData from "../hooks/useSearchData.js";
import { coinEntries, searchAll } from "../utils/search.js";
import { formatPrice } from "../utils/marketPresentation.js";
import { marketHref } from "../utils/researchNavigation.js";
import { compactUsd } from "../utils/money.js";
import { shortAddr } from "../utils/walletName.js";
import "./GlobalSearch.css";

// Typing in a field (or a rich-text box) keeps its own "/".
const typing = t => t instanceof HTMLElement && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName));

const pct = v => (v == null || !Number.isFinite(v) ? "—" : `${v >= 0 ? "+" : "−"}${Math.abs(v * 100).toFixed(2)}%`);
const tone = v => (v == null || !Number.isFinite(v) || Math.abs(v) < 0.00005 ? "" : v > 0 ? " up" : " down");

const Glass = ({ size = 16 }) => (
  <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="10.5" cy="10.5" r="7" /><path d="m16 16 5 5" /></svg>
);

// The part of a name that matched the query, in full ink.
function Hit({ text, q }) {
  const i = q ? text.toLowerCase().indexOf(q.trim().toLowerCase()) : -1;
  if (i < 0) return text;
  const n = q.trim().length;
  return <>{text.slice(0, i)}<span className="gs-hit">{text.slice(i, i + n)}</span>{text.slice(i + n)}</>;
}

function CoinRow({ e, q, statusCol, id, active, phone, onPick, onHover }) {
  return (
    <div id={id} role="option" aria-selected={active} className="gs-row gs-coin" onMouseDown={ev => ev.preventDefault()}
      onClick={() => onPick(e)} onMouseMove={onHover}>
      <TokenLogo symbol={e.row.symbol} size={phone ? 28 : 24} fallback="monogram" />
      <span className="gs-id">
        <span className="gs-line"><b className="gs-ticker">{e.ticker}</b>{e.name && e.name.toLowerCase() !== e.ticker.toLowerCase() && <span className="gs-name"><Hit text={e.name} q={q} /></span>}</span>
        {phone && e.status && <span className="gs-status">{e.status}</span>}
      </span>
      {phone
        ? <span className="gs-fig"><span className="gs-price">{formatPrice(e.price)}</span><span className={`gs-chg${tone(e.change)}`}>{pct(e.change)}</span></span>
        : <>
          <span className="gs-price">{formatPrice(e.price)}</span>
          <span className={`gs-chg${tone(e.change)}`}>{pct(e.change)}</span>
          {statusCol && <span className="gs-status">{e.status || ""}</span>}
        </>}
    </div>
  );
}

function TraderRow({ e, id, active, phone, onPick, onHover }) {
  const addressRow = e.kind === "address";
  return (
    <div id={id} role="option" aria-selected={active} className={`gs-row gs-trader${addressRow ? " gs-address" : ""}`}
      onMouseDown={ev => ev.preventDefault()} onClick={() => onPick(e)} onMouseMove={onHover}>
      <WalletAvatar address={e.address} size={phone ? 28 : 24} />
      <span className="gs-id">
        {addressRow
          ? <span className="gs-line"><span className="gs-open">Open trader</span><span className="gs-addr">{shortAddr(e.address)}</span></span>
          : <span className="gs-line"><b className="gs-ticker gs-codename">{e.name}</b><span className="gs-addr">{shortAddr(e.address)}</span></span>}
      </span>
      {addressRow
        ? <span className="gs-pnl"><span className="gs-aside">{e.name}</span>{e.pnl != null && <><span className={`gs-chg${tone(e.pnl)}`}>{compactUsd(e.pnl, { sign: true })}</span><span className="gs-unit">30d</span></>}</span>
        : <span className="gs-pnl"><span className={`gs-chg${tone(e.pnl)}`}>{compactUsd(e.pnl, { sign: true })}</span><span className="gs-unit">30d</span></span>}
    </div>
  );
}

// The search for coins and traders, in the header on every page: a field (narrower from 900 to
// 1279px: compact), a search button on phones. Results open under the field, a full-screen sheet
// on phones. Coins are Hyperliquid's perps and spot markets; rows: the scanner's rows where loaded.
export default function GlobalSearch({ rows, radarTf = "1d", phone = false, compact = false, onOpenCoin }) {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [sheet, setSheet] = useState(false);
  const [hi, setHi] = useState(0);
  const input = useRef(null);
  const sheetInput = useRef(null);
  const wrap = useRef(null);
  const listId = useId();
  const { markets, traders } = useSearchData(open || sheet);
  const { data: radarMap } = useSetupMap(radarTf === "4h" ? "4h" : "1d");

  const radar = useMemo(() => new Map((radarMap?.coins || []).map(c => [c.coin, c])), [radarMap]);
  const coins = useMemo(() => coinEntries(markets, rows, radar), [markets, rows, radar]);
  const res = useMemo(() => searchAll(q, { coins, traders: traders || [] }), [q, coins, traders]);
  const flat = useMemo(() => (res.address ? [res.address] : [...res.coins, ...res.traders]), [res]);
  const hasStatus = res.coins.some(c => c.status);
  useEffect(() => { setHi(0); }, [q]);

  // "/" opens the search from any page.
  useEffect(() => {
    const onKey = e => {
      if (e.key !== "/" || e.ctrlKey || e.metaKey || e.altKey || e.defaultPrevented || typing(e.target)) return;
      e.preventDefault();
      if (phone) setSheet(true); else input.current?.focus();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [phone]);

  // A click outside closes the list.
  useEffect(() => {
    if (!open) return undefined;
    const onDown = e => { if (!wrap.current?.contains(e.target)) setOpen(false); };
    document.addEventListener("pointerdown", onDown);
    return () => document.removeEventListener("pointerdown", onDown);
  }, [open]);

  useEffect(() => { if (sheet) requestAnimationFrame(() => sheetInput.current?.focus()); }, [sheet]);

  const close = useCallback(() => { setOpen(false); setSheet(false); input.current?.blur(); }, []);
  const pick = useCallback(e => {
    if (!e) return;
    track("search");
    close();
    setQ("");
    if (e.kind === "coin") onOpenCoin ? onOpenCoin(e.row) : navigate(marketHref(e.row));
    else navigate(`/trader/${e.address.toLowerCase()}`);
  }, [close, navigate, onOpenCoin]);

  const onKeyDown = e => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      if (!flat.length) return;
      e.preventDefault();
      setOpen(true);
      setHi(h => (h + (e.key === "ArrowDown" ? 1 : -1) + flat.length) % flat.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      pick(flat[hi]);
    } else if (e.key === "Escape") {
      e.preventDefault();
      if (q && !sheet && !open) setQ(""); else close();
    }
  };

  const showList = !!q.trim();
  const optId = i => `${listId}-o${i}`;
  const list = (
    <div className={`gs-list${phone ? " gs-list-phone" : ""}`} id={listId} role="listbox" aria-label="Search results">
      {res.address && <TraderRow e={res.address} id={optId(0)} active={hi === 0} phone={phone} onPick={pick} onHover={() => setHi(0)} />}
      {res.coins.length > 0 && <div className={`gs-group gs-coins${hasStatus ? " has-status" : ""}`} role="group" aria-label="Coins">
        {res.traders.length > 0 && <div className="gs-label" aria-hidden="true">Coins</div>}
        {res.coins.map((c, i) => <CoinRow key={c.key} e={c} q={q} statusCol={hasStatus} id={optId(i)} active={hi === i} phone={phone} onPick={pick} onHover={() => setHi(i)} />)}
      </div>}
      {res.traders.length > 0 && <div className="gs-group gs-traders" role="group" aria-label="Traders">
        <div className="gs-label" aria-hidden="true">Traders</div>
        {res.traders.map((t, j) => { const i = res.coins.length + j; return <TraderRow key={t.key} e={t} id={optId(i)} active={hi === i} phone={phone} onPick={pick} onHover={() => setHi(i)} />; })}
      </div>}
      {!flat.length && <div className="gs-empty">No matches</div>}
    </div>
  );

  const field = (ref, extra = {}) => (
    <input ref={ref} type="search" value={q} placeholder={compact ? "Search" : "Search coins and traders"} aria-label="Search coins and traders"
      role="combobox" aria-expanded={showList} aria-controls={listId} aria-autocomplete="list"
      aria-activedescendant={showList && flat.length ? optId(hi) : undefined} autoComplete="off" spellCheck={false}
      onChange={e => { setQ(e.target.value); setOpen(true); }} onKeyDown={onKeyDown} {...extra} />
  );

  if (phone) {
    return <>
      <button type="button" className="header-search-btn" aria-label="Search coins and traders" aria-keyshortcuts="/" onClick={() => setSheet(true)}><Glass size={18} /></button>
      {sheet && createPortal(
        <div className="gs-sheet" role="dialog" aria-modal="true" aria-label="Search">
          <div className="gs-sheet-top">
            <div className="gs-field gs-field-sheet"><Glass />{field(sheetInput)}
              {q && <button type="button" className="gs-clear" aria-label="Clear" onClick={() => { setQ(""); sheetInput.current?.focus(); }}>×</button>}
            </div>
            <button type="button" className="gs-cancel" onClick={() => { close(); setQ(""); }}>Cancel</button>
          </div>
          {showList && list}
        </div>, document.querySelector(".reflex-terminal") || document.body)}
    </>;
  }

  return (
    <div ref={wrap} className={`gs gs-header${compact ? " gs-compact" : ""}${open && showList ? " is-open" : ""}`}>
      <div className="gs-field">
        <Glass />
        {field(input, { onFocus: () => setOpen(true), "aria-keyshortcuts": "/" })}
        {q
          ? <button type="button" className="gs-clear" aria-label="Clear search" onClick={() => { setQ(""); input.current?.focus(); }}>×</button>
          : <kbd className="gs-kbd" aria-hidden="true" title="Press / to search">/</kbd>}
      </div>
      {open && showList && list}
    </div>
  );
}
