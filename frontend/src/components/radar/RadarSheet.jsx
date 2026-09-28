import { useEffect, useRef, useState } from "react";

// Phone only: the followed coin in a bottom sheet above the tab bar. It opens at a peek height
// (the coin, its readings and actions) so the map, the tapped dot and its trail stay in view
// above it; a swipe up (or a tap on the grab bar) raises it for the chart. Escape, Clear or a
// swipe down closes it. It stays mounted so it can slide out with its content.
export default function RadarSheet({ open, onClose, labelledBy, children }) {
  const ref = useRef(null);
  const drag = useRef(null);
  const [dy, setDy] = useState(0);
  const [tall, setTall] = useState(false);

  useEffect(() => {
    if (!open) return undefined;
    // Escape belongs to whatever sits above the sheet (the Full detail drawer, More): leave it be.
    const onKey = e => {
      if (e.key !== "Escape" || document.querySelector('[aria-modal="true"], .more-drawer')) return;
      e.preventDefault(); onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  useEffect(() => { if (!open) { setDy(0); setTall(false); } }, [open]);

  // Swipe down on the sheet (from its top while its content is scrolled to the top).
  const onTouchStart = e => {
    const body = ref.current?.querySelector(".radar-sheet-body");
    if (body && body.scrollTop > 0 && !e.target.closest(".radar-sheet-grab")) { drag.current = null; return; }
    drag.current = { y: e.touches[0].clientY };
  };
  const onTouchMove = e => {
    if (!drag.current) return;
    const d = e.touches[0].clientY - drag.current.y;
    if (d < -24 && !tall) { setTall(true); drag.current = null; return; }
    // A raised sheet first drops back to its peek height, then closes on the next swipe.
    if (d > 60 && tall) { setTall(false); drag.current = null; return; }
    setDy(Math.max(0, d));
  };
  const onTouchEnd = () => {
    if (!drag.current) return;
    drag.current = null;
    if (dy > 70) onClose(); else setDy(0);
  };

  return <div ref={ref} className="radar-sheet" data-open={open ? "" : undefined} data-tall={tall ? "" : undefined} role="dialog" aria-modal="false" aria-labelledby={labelledBy} aria-hidden={open ? undefined : "true"} inert={open ? undefined : ""}
    style={dy ? { transform: `translateY(${dy}px)`, transition: "none" } : undefined}
    onTouchStart={onTouchStart} onTouchMove={onTouchMove} onTouchEnd={onTouchEnd} onTouchCancel={onTouchEnd}>
    <div className="radar-sheet-grab" aria-hidden="true" onClick={() => setTall(t => !t)}><i /></div>
    <div className="radar-sheet-body">{children}</div>
  </div>;
}
