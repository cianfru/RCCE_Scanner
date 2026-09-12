import { useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { clampLeft, placeVertical, TOOLTIP_MARGIN } from '../utils/tooltipPosition.js';

/**
 * The one info tooltip. Portaled to <body>, fixed-positioned from the anchor,
 * clamped inside the viewport and flipped above the anchor when there's no
 * room below — so it can never be clipped by a scrolling or backdrop-filtered
 * container. Replaces the former InfoPopover and the two inline InfoTips.
 *
 *   title    optional heading
 *   width    card width (px); < 300 renders the compact variant
 *   trigger  'hover' (default; also focus) or 'click' (toggles, stays open)
 *   size     the "i" button size (px)
 */
export default function HelpTip({ title, children, width = 400, trigger = 'hover', size = 14 }) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState(null);
  const anchor = useRef(null);
  const tooltip = useRef(null);
  const closeTimer = useRef(null);
  const id = useId();
  const hover = trigger === 'hover';
  const show = () => { clearTimeout(closeTimer.current); setOpen(true); };
  const hide = () => { closeTimer.current = setTimeout(() => setOpen(false), 150); };
  const toggle = e => { e.stopPropagation(); clearTimeout(closeTimer.current); setOpen(o => !o); };

  useLayoutEffect(() => {
    if (!open) { setPosition(null); return; }
    const place = () => {
      const rect = anchor.current.getBoundingClientRect();
      const w = Math.min(width, window.innerWidth - TOOLTIP_MARGIN * 2);
      const h = tooltip.current?.getBoundingClientRect().height || 300;
      setPosition({ left: clampLeft(rect.left, rect.width, w, window.innerWidth), ...placeVertical(rect.top, rect.bottom, h, window.innerHeight), width: w });
    };
    const dismiss = e => {
      if (e.key === 'Escape' || (e.type === 'pointerdown' && !anchor.current.contains(e.target) && !tooltip.current?.contains(e.target))) setOpen(false);
    };
    place();
    window.addEventListener('resize', place);
    window.addEventListener('scroll', place, true);
    document.addEventListener('keydown', dismiss);
    document.addEventListener('pointerdown', dismiss);
    return () => {
      clearTimeout(closeTimer.current);
      window.removeEventListener('resize', place);
      window.removeEventListener('scroll', place, true);
      document.removeEventListener('keydown', dismiss);
      document.removeEventListener('pointerdown', dismiss);
    };
  }, [open, width]);

  const hoverProps = hover ? { onMouseEnter: show, onMouseLeave: hide } : {};
  return <span className="alt-season-info" {...hoverProps}>
    <button ref={anchor} type="button" aria-label={`About ${title || 'this'}`} aria-expanded={open} aria-describedby={open ? id : undefined}
      style={{ width: size, height: size, fontSize: Math.max(9, Math.round(size * 0.7)) }}
      onFocus={hover ? show : undefined} onBlur={hover ? hide : undefined} onClick={hover ? show : toggle}>i</button>
    {open && createPortal(<div ref={tooltip} id={id} role="tooltip" className={`alt-season-explanation${width < 300 ? ' is-compact' : ''}`} {...hoverProps}
      style={{ ...position, visibility: position ? 'visible' : 'hidden' }}>
      {title && <strong>{title}</strong>}
      {children}
    </div>, document.body)}
  </span>;
}
