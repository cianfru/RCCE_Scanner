import { useEffect, useRef, useState } from "react";

// Phone only: the followed coin in a bottom sheet above the tab bar. Escape, Clear or a
// swipe down closes it. It stays mounted so it can slide out with its content.
export default function RadarSheet({ open, onClose, labelledBy, children }) {
  const ref = useRef(null);
  const drag = useRef(null);
  const [dy, setDy] = useState(0);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = e => { if (e.key === "Escape") { e.preventDefault(); onClose(); } };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  useEffect(() => { if (!open) setDy(0); }, [open]);

  // Swipe down on the sheet (from its top while its content is scrolled to the top).
  const onTouchStart = e => {
    const body = ref.current?.querySelector(".radar-sheet-body");
    if (body && body.scrollTop > 0 && !e.target.closest(".radar-sheet-grab")) { drag.current = null; return; }
    drag.current = { y: e.touches[0].clientY };
  };
  const onTouchMove = e => {
    if (!drag.current) return;
    const d = e.touches[0].clientY - drag.current.y;
    setDy(Math.max(0, d));
  };
  const onTouchEnd = () => {
    if (!drag.current) return;
    drag.current = null;
    if (dy > 70) onClose(); else setDy(0);
  };

  return <div ref={ref} className="radar-sheet" data-open={open ? "" : undefined} role="dialog" aria-modal="false" aria-labelledby={labelledBy} aria-hidden={open ? undefined : "true"} inert={open ? undefined : ""}
    style={dy ? { transform: `translateY(${dy}px)`, transition: "none" } : undefined}
    onTouchStart={onTouchStart} onTouchMove={onTouchMove} onTouchEnd={onTouchEnd} onTouchCancel={onTouchEnd}>
    <div className="radar-sheet-grab" aria-hidden="true"><i /></div>
    <div className="radar-sheet-body">{children}</div>
  </div>;
}
