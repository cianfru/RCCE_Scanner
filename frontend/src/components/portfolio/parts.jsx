// Small shared pieces of the Portfolio page: the (i) label, the glass hover card, tweened numbers,
// the price flash and the coin's name.
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import HelpTip from "../HelpTip.jsx";
import TokenLogo from "../TokenLogo.jsx";
import { displayName, logoSymbol } from "../../utils/portfolio/displayNames.js";

// An 11px uppercase label with a dotted underline; hover, focus or a tap opens its (i).
export function Label({ children, info, width = 320, title }) {
  if (!info) return <span className="pf-lbl pf-lbl-plain">{children}</span>;
  return <HelpTip title={title} width={width} anchor={children} anchorClass="pf-lbl" className="pf-lbl-wrap" longPress>
    <p>{info}</p>
  </HelpTip>;
}

// A glass card that follows its anchor (portaled, kept inside the viewport). Hover or focus opens it.
export function Hover({ content, children, className = "", width = 240, as: Tag = "span", onClick, ...rest }) {
  const [open, setOpenNow] = useState(false);
  const [pos, setPos] = useState(null);
  const ref = useRef(null);
  const card = useRef(null);
  const timer = useRef(null);
  // Closing waits a moment, so the pointer can move into the card (its rows can be clicked).
  const setOpen = v => { clearTimeout(timer.current); if (v) setOpenNow(true); else timer.current = setTimeout(() => setOpenNow(false), 120); };
  useEffect(() => () => clearTimeout(timer.current), []);
  useLayoutEffect(() => {
    if (!open || !ref.current) { setPos(null); return; }
    const r = ref.current.getBoundingClientRect();
    const h = card.current?.getBoundingClientRect().height || 120;
    const w = Math.min(width, window.innerWidth - 24);
    const left = Math.max(12, Math.min(window.innerWidth - w - 12, r.left + r.width / 2 - w / 2));
    const below = r.bottom + 8 + h < window.innerHeight - 8;
    setPos({ left, top: below ? r.bottom + 8 : Math.max(8, r.top - 8 - h), width: w });
  }, [open, width, content]);
  useEffect(() => {
    if (!open) return undefined;
    const close = e => { if (!card.current?.contains(e.target)) setOpenNow(false); };
    const esc = e => { if (e.key === "Escape") setOpenNow(false); };
    window.addEventListener("scroll", close, true);
    document.addEventListener("keydown", esc);
    return () => { window.removeEventListener("scroll", close, true); document.removeEventListener("keydown", esc); };
  }, [open]);
  return <Tag ref={ref} className={`pf-hov ${className}`} onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}
    onFocus={() => setOpen(true)} onBlur={() => setOpen(false)} onClick={onClick} {...rest}>
    {children}
    {open && content && createPortal(<div ref={card} className="pf-tip" role="tooltip" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}
      style={{ ...pos, visibility: pos ? "visible" : "hidden", width: pos?.width ?? width }}>{content}</div>, ref.current?.closest(".pf-page") || document.body)}
  </Tag>;
}

// A number that tweens to its new value over 300 ms when it refreshes.
export function useTween(value, ms = 300) {
  const [shown, setShown] = useState(value);
  const from = useRef(value);
  useEffect(() => {
    if (value == null || !Number.isFinite(value) || from.current == null || !Number.isFinite(from.current)
      || typeof window === "undefined" || window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      from.current = value; setShown(value); return undefined;
    }
    const a = from.current, t0 = performance.now();
    let raf = 0;
    const step = now => {
      const k = Math.min(1, (now - t0) / ms);
      const v = a + (value - a) * (1 - (1 - k) ** 3);
      setShown(v);
      if (k < 1) raf = requestAnimationFrame(step); else from.current = value;
    };
    raf = requestAnimationFrame(step);
    return () => { cancelAnimationFrame(raf); from.current = value; };
  }, [value, ms]);
  return shown;
}

export function Tween({ value, format, className, style }) {
  const v = useTween(value);
  return <span className={className} style={style}>{format(v)}</span>;
}

// The mark price: flashes in the direction of a change, then settles.
export function useFlash(value) {
  const prev = useRef(value);
  const [dir, setDir] = useState(null);
  useEffect(() => {
    if (prev.current != null && value != null && value !== prev.current) {
      setDir(value > prev.current ? "up" : "down");
      const t = setTimeout(() => setDir(null), 1200);
      prev.current = value;
      return () => clearTimeout(t);
    }
    prev.current = value;
    return undefined;
  }, [value]);
  return dir;
}

// Logo, name and suffix ("MSTR TradFi").
export function CoinName({ coin, names, size = 18, strong = true }) {
  const d = displayName(coin, names);
  return <span className="pf-cn">
    <TokenLogo symbol={logoSymbol(coin)} size={size} fallback="monogram" />
    <span className={strong ? "pf-cn-n" : "pf-cn-s"}>{d.name}</span>
  </span>;
}

export const pnlClass = v => (v > 0 ? "pf-up" : v < 0 ? "pf-dn" : "pf-flat");
