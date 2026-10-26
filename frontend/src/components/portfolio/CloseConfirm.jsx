// The close sheet (needs the owner's OK before it replaces window.confirm; PF_CONFIRM_SHEET in
// tradeActions.js). Desktop: a 320 px glass card by the Close button; phone: in place of the sheet's
// action row. Focus starts on Keep; Escape or a click outside is Keep.
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { displayName } from "../../utils/portfolio/displayNames.js";
import { usd, size as fmtSize } from "../../utils/portfolio/format.js";
import { useAssetCtx } from "./assetCtx.js";
import { ROWS, SHEET } from "./copy.js";

export function CloseBody({ row, onConfirm, onKeep, preview, szDecimals }) {
  const keep = useRef(null);
  useEffect(() => { keep.current?.focus(); }, []);
  const name = displayName(row.coin).name;
  // Display only: the size at the market's own decimals, as in the facts (the close call reads row.szi).
  const a = useAssetCtx(row.coin);
  const dec = szDecimals ?? a?.szDecimals ?? null;
  return <div className="pf-sheet" role="dialog" aria-modal="false" aria-label={SHEET.title(name, row.side)}>
    <div className="pf-sheet-t">{SHEET.title(name, row.isLong ? ROWS.long.toLowerCase() : ROWS.short.toLowerCase())}</div>
    <div className="pf-sheet-d">{SHEET.detail(fmtSize(Math.abs(row.szi), dec), name, usd(row.value))}</div>
    <div className="pf-sheet-a">
      <button type="button" className="pf-sheet-go" disabled={preview} onClick={onConfirm}>{SHEET.go}</button>
      <button ref={keep} type="button" className="pf-textbtn pf-sheet-keep" onClick={onKeep}>{SHEET.keep}</button>
      {preview && <span className="pf-t3 pf-sheet-pv">{ROWS.preview}</span>}
    </div>
  </div>;
}

export default function CloseConfirm({ row, anchor, onConfirm, onKeep, preview, szDecimals }) {
  const card = useRef(null);
  const [pos, setPos] = useState(null);
  useLayoutEffect(() => {
    if (!anchor) return;
    const r = anchor.getBoundingClientRect();
    const w = 320, h = card.current?.getBoundingClientRect().height || 120;
    const left = Math.max(12, Math.min(window.innerWidth - w - 12, r.right - w));
    const below = r.bottom + 8 + h < window.innerHeight - 8;
    setPos({ left, top: below ? r.bottom + 8 : r.top - 8 - h });
  }, [anchor]);
  useEffect(() => {
    const onKey = e => { if (e.key === "Escape") onKeep(); };
    const onDown = e => { if (card.current && !card.current.contains(e.target) && !anchor?.contains(e.target)) onKeep(); };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onDown);
    return () => { document.removeEventListener("keydown", onKey); document.removeEventListener("pointerdown", onDown); };
  }, [onKeep, anchor]);
  return createPortal(<div ref={card} className="pf-sheet-pop" style={{ ...pos, visibility: pos ? "visible" : "hidden" }}>
    <CloseBody row={row} onConfirm={onConfirm} onKeep={onKeep} preview={preview} szDecimals={szDecimals} />
  </div>, anchor?.closest?.(".pf-page") || document.body);
}
