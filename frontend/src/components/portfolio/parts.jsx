// Small shared pieces of the Portfolio page: the (i) label, the glass hover card, tweened numbers,
// the price flash and the coin's name.
import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import HelpTip from "../HelpTip.jsx";
import TokenLogo from "../TokenLogo.jsx";
import tokenLogos from "../../data/tokenLogos.json";
import xyzLogos from "../../data/xyzLogos.json";
import { displayName, logoSymbol, venueOf } from "../../utils/portfolio/displayNames.js";

const hasTokenLogo = sym => !!tokenLogos[sym]?.src;

// An 11px uppercase label with a dotted underline; hover, focus or a tap opens its (i).
export function Label({ children, info, width = 320, title }) {
  if (!info) return <span className="pf-lbl pf-lbl-plain">{children}</span>;
  return <HelpTip title={title} width={width} anchor={children} anchorClass="pf-lbl" className="pf-lbl-wrap" longPress>
    <p>{info}</p>
  </HelpTip>;
}

// A glass card that follows its anchor (portaled, kept inside the viewport). Hover or focus opens it.
// align "start": the card's left edge on the anchor's (a number set at a card's padding).
export function Hover({ content, children, className = "", width = 240, as: Tag = "span", onClick, align = "center", ...rest }) {
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
    const want = align === "start" ? r.left : r.left + r.width / 2 - w / 2;
    const left = Math.max(12, Math.min(window.innerWidth - w - 12, want));
    const below = r.bottom + 8 + h < window.innerHeight - 8;
    setPos({ left, top: below ? r.bottom + 8 : Math.max(8, r.top - 8 - h), width: w });
  }, [open, width, content, align]);
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

// A coin's logo: the app's cached Hyperliquid artwork; TradFi (xyz) markets use Hyperliquid's own
// xyz icons (data/xyzLogos.json, cached the same way), clipped round as Hyperliquid shows them. No
// artwork: the first two letters, unboxed.
export function CoinLogo({ coin, size = 18 }) {
  const [failed, setFailed] = useState(false);
  const xyz = xyzLogos[coin];
  const sym = logoSymbol(coin);
  if (xyz && !failed) {
    return <span className="pf-xlogo" style={{ width: size, height: size }}>
      <img src={xyz} alt="" width={size} height={size} loading="lazy" onError={() => setFailed(true)} />
    </span>;
  }
  if (venueOf(coin) === "main" && hasTokenLogo(sym)) return <TokenLogo symbol={sym} size={size} fallback="none" />;
  return <span className="pf-mono" aria-hidden="true" style={{ width: size, fontSize: Math.max(11, Math.round(size * 0.55)) }}>{displayName(coin).name.slice(0, 2)}</span>;
}

// Logo and name (the suffix, "TradFi", is printed by the caller where there is room).
export function CoinName({ coin, names, size = 18, strong = true }) {
  const d = displayName(coin, names);
  return <span className="pf-cn">
    <CoinLogo coin={coin} size={size} />
    <span className={strong ? "pf-cn-n" : "pf-cn-s"}>{d.name}</span>
  </span>;
}

// A coin's name with its venue suffix in text3 ("TSLA TradFi").
export function NameSfx({ coin, names }) {
  const d = displayName(coin, names);
  return <>{d.name}{d.suffix && <span className="pf-t3 pf-sfx"> {d.suffix}</span>}</>;
}

// The liquidation glyph (the rail's red tick over its hatch): every liquidation fact carries it, so
// it never reads as a loss figure (in light theme the red is the loss red).
export function LiqGlyph({ h = 12 }) {
  const id = useId().replace(/:/g, "");
  return <svg className="pf-liqg" width="9" height={h} viewBox={`0 0 9 ${h}`} aria-hidden="true">
    <defs><pattern id={id} width="3" height="3" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
      <line x1="0" y1="0" x2="0" y2="3" stroke="var(--rd-red)" strokeOpacity=".45" strokeWidth="1.5" /></pattern></defs>
    <rect x="0" y={h / 2 - 3.5} width="6" height="7" fill={`url(#${id})`} />
    <rect x="6" y="0" width="2" height={h} fill="var(--rd-red)" />
  </svg>;
}

// A text's width in px for the page's fonts (canvas; an estimate where there is no canvas).
let measureCtx = null;
export function textWidth(text, size = 11, family = "mono", weight = 500) {
  const s = String(text ?? "");
  if (typeof document !== "undefined") {
    try {
      measureCtx = measureCtx || document.createElement("canvas").getContext("2d");
      const css = getComputedStyle(document.documentElement);
      const fam = family === "mono" ? css.getPropertyValue("--font-geist-mono") || "monospace" : css.getPropertyValue("--font-geist-sans") || "sans-serif";
      measureCtx.font = `${weight} ${size}px ${fam}`;
      return measureCtx.measureText(s).width;
    } catch { /* no canvas */ }
  }
  return s.length * size * (family === "mono" ? 0.6 : 0.56);
}

export const pnlClass = v => (v > 0 ? "pf-up" : v < 0 ? "pf-dn" : "pf-flat");
