import { useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { placeTooltip } from '../utils/tooltipPosition.js';

/**
 * HelpTip — the one shared help card behind every ⓘ button in the terminal.
 *
 * Portals to <body>, positions `fixed` from the anchor's bounding rect, clamps
 * to the viewport, flips above the anchor when there is no room below, and
 * repositions on scroll/resize — so it can never be clipped by a scrolling or
 * backdrop-filtered container (the detail drawer, table wrappers, cards).
 *
 * Props:
 *   title    — heading shown in the card; also feeds the default aria-label.
 *   children — card body (<p>s, lists, anything).
 *   width    — max card width in px (default 400); shrinks on narrow viewports.
 *   trigger  — "hover" (default: hover/focus/click opens) | "click" (toggle only).
 *   label    — aria-label override for the button (defaults to `About ${title}`).
 */
export default function HelpTip({ title, children, width = 400, trigger = 'hover', label }) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState(null);
  const anchor = useRef(null);
  const tooltip = useRef(null);
  const closeTimer = useRef(null);
  const id = useId();
  const hoverable = trigger !== 'click';
  const show = () => { clearTimeout(closeTimer.current); setOpen(true); };
  const hide = () => { clearTimeout(closeTimer.current); closeTimer.current = setTimeout(() => setOpen(false), 150); };
  const hoverProps = hoverable ? { onMouseEnter: show, onMouseLeave: hide } : {};

  useLayoutEffect(() => {
    if (!open) { setPosition(null); return; }
    const place = () => {
      if (!anchor.current) return;
      const rect = anchor.current.getBoundingClientRect();
      const height = tooltip.current?.getBoundingClientRect().height || 300;
      const { left, top, width: w } = placeTooltip({
        anchor: rect, width, height,
        viewport: { width: window.innerWidth, height: window.innerHeight },
      });
      setPosition({ left, top, width: w });
    };
    const dismiss = e => {
      if (e.key === 'Escape' || (e.type === 'pointerdown' && !anchor.current?.contains(e.target) && !tooltip.current?.contains(e.target))) setOpen(false);
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

  return <span className="help-tip" {...hoverProps}>
    <button ref={anchor} type="button" aria-label={label || (title ? `About ${title}` : 'More information')}
      aria-expanded={open} aria-describedby={open ? id : undefined}
      onFocus={hoverable ? show : undefined} onBlur={hoverable ? hide : undefined}
      onClick={e => { e.stopPropagation(); hoverable ? show() : setOpen(o => !o); }}>i</button>
    {open && createPortal(<div ref={tooltip} id={id} role="tooltip" className="help-tip-card" {...hoverProps}
      style={{ ...position, visibility: position ? 'visible' : 'hidden' }}>
      {title && <strong>{title}</strong>}
      {children}
    </div>, document.body)}
  </span>;
}
