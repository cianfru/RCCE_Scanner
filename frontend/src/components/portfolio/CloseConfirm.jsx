// The close sheet: the confirm before a close (TradingPanel.jsx used window.confirm). Desktop: a 320 px
// glass card by the Close button, following it when the page scrolls; phone: in place of the sheet's
// action row. Focus starts on Keep once the card is on screen and stays inside it (Tab and Shift+Tab
// go round its two buttons); Escape or a click outside is Keep, and focus goes back to the Close
// button (PortfolioPage.endSheet). The size shown is the one the close is sent with: |szi| floored to
// the market's szDecimals, as hlOrder.formatVolume sends it.
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { displayName } from "../../utils/portfolio/displayNames.js";
import { usd, size as fmtSize } from "../../utils/portfolio/format.js";
import { formatVolume } from "../../utils/hlOrder.js";
import { useAssetCtx } from "./assetCtx.js";
import { ROWS, SHEET } from "./copy.js";

// Tab and Shift+Tab stay on the card's buttons.
function trapTab(e, root) {
  if (e.key !== "Tab" || !root) return;
  const list = [...root.querySelectorAll("button:not([disabled])")];
  if (!list.length) return;
  const first = list[0], last = list[list.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
}

// ready: the card is on screen (a hidden element cannot take focus).
export function CloseBody({ row, onConfirm, onKeep, szDecimals, ready = true }) {
  const keep = useRef(null);
  const box = useRef(null);
  useEffect(() => { if (ready) keep.current?.focus(); }, [ready]);
  const name = displayName(row.coin).name;
  const a = useAssetCtx(row.coin);
  const dec = szDecimals ?? a?.szDecimals ?? null;
  const sent = dec != null ? formatVolume(Math.abs(row.szi), dec) : Math.abs(row.szi);
  return <div ref={box} className="pf-sheet" role="dialog" aria-modal="false" aria-label={SHEET.title(name, row.side)} onKeyDown={e => trapTab(e, box.current)}>
    <div className="pf-sheet-t">{SHEET.title(name, row.isLong ? ROWS.long.toLowerCase() : ROWS.short.toLowerCase())}</div>
    <div className="pf-sheet-d">{SHEET.detail(fmtSize(sent, dec), name, usd(row.value))}</div>
    <div className="pf-sheet-a">
      <button type="button" className="pf-sheet-go" onClick={onConfirm}>{SHEET.go}</button>
      <button ref={keep} type="button" className="pf-textbtn pf-sheet-keep" onClick={onKeep}>{SHEET.keep}</button>
    </div>
  </div>;
}

export default function CloseConfirm({ row, anchor, onConfirm, onKeep, szDecimals }) {
  const card = useRef(null);
  const [pos, setPos] = useState(null);
  useLayoutEffect(() => {
    if (!anchor) return undefined;
    // By the Close button: below it when there is room, above it otherwise; again on scroll and resize.
    const place = () => {
      const r = anchor.getBoundingClientRect();
      const w = 320, h = card.current?.getBoundingClientRect().height || 120;
      const left = Math.max(12, Math.min(window.innerWidth - w - 12, r.right - w));
      const below = r.bottom + 8 + h < window.innerHeight - 8;
      setPos({ left, top: below ? r.bottom + 8 : r.top - 8 - h });
    };
    place();
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place);
    return () => { window.removeEventListener("scroll", place, true); window.removeEventListener("resize", place); };
  }, [anchor]);
  useEffect(() => {
    const onKey = e => { if (e.key === "Escape") onKeep(); };
    const onDown = e => { if (card.current && !card.current.contains(e.target) && !anchor?.contains(e.target)) onKeep(); };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onDown);
    return () => { document.removeEventListener("keydown", onKey); document.removeEventListener("pointerdown", onDown); };
  }, [onKeep, anchor]);
  return createPortal(<div ref={card} className="pf-sheet-pop" style={{ ...pos, visibility: pos ? "visible" : "hidden" }}>
    <CloseBody row={row} onConfirm={onConfirm} onKeep={onKeep} szDecimals={szDecimals} ready={!!pos} />
  </div>, anchor?.closest?.(".pf-page") || document.body);
}
