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
 *   label    accessible name override for the "i" button
 *
 * Label mode (grid headers, toolbar links), all optional:
 *   anchor       render this content as the button instead of the "i" circle (no circle size)
 *   anchorClass  class for that button
 *   hoverDelay   ms of hover before the card opens (hover trigger)
 *   onActivate   a click runs this instead of opening the card (e.g. sort)
 *   longPress    holding a touch 500ms opens the card
 */
const cardWidth = width => Math.min(width, (typeof window === 'undefined' ? 1440 : window.innerWidth) - TOOLTIP_MARGIN * 2);

// The fixed chrome a card must not cover: it stays under the header capsule and above the phone tab bar.
const CHROME_GAP = 8;
const chromeEdges = () => {
  const edges = {};
  const capsule = document.querySelector('.terminal-header')?.getBoundingClientRect();
  if (capsule && capsule.height > 0) edges.top = capsule.bottom + CHROME_GAP;
  const tabbar = document.querySelector('.mobile-tabbar')?.getBoundingClientRect();
  if (tabbar && tabbar.height > 0) edges.bottom = tabbar.top - CHROME_GAP;
  return edges;
};

export default function HelpTip({ title, children, width = 400, trigger = 'hover', size = 14, label, icon, buttonStyle, className = "",
  anchor: anchorContent, anchorClass, hoverDelay = 0, onActivate, longPress = false, buttonProps }) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState(null);
  const anchor = useRef(null);
  const tooltip = useRef(null);
  const closeTimer = useRef(null);
  const openTimer = useRef(null);
  const pressTimer = useRef(null);
  const pressed = useRef(false);
  const id = useId();
  const hover = trigger === 'hover';
  const labelMode = anchorContent != null;
  // A tap pins the card open: touch browsers send mouseleave right after the tap, which would close it.
  // It closes on a tap outside, a second tap on the (i), or Escape.
  const touch = useRef(false);
  const pinned = useRef(false);
  const openNow = useRef(false);
  openNow.current = open;
  const show = () => { clearTimeout(closeTimer.current); clearTimeout(openTimer.current); setOpen(true); };
  const showSoon = () => {
    clearTimeout(closeTimer.current);
    if (!hoverDelay) return show();
    clearTimeout(openTimer.current);
    openTimer.current = setTimeout(() => setOpen(true), hoverDelay);
  };
  const hide = () => { clearTimeout(openTimer.current); if (!pinned.current) closeTimer.current = setTimeout(() => setOpen(false), 150); };
  const toggle = e => { e.stopPropagation(); clearTimeout(closeTimer.current); clearTimeout(openTimer.current); setOpen(o => !o); };

  useLayoutEffect(() => {
    if (!open) { setPosition(null); pinned.current = false; return; }
    const place = () => {
      const rect = anchor.current.getBoundingClientRect();
      const w = cardWidth(width);
      // The card already has its final width (set in render), so this is its real height;
      // scrollHeight is the full height even while a maxHeight caps it.
      const h = tooltip.current ? Math.max(tooltip.current.getBoundingClientRect().height, tooltip.current.scrollHeight) : 300;
      setPosition({ left: clampLeft(rect.left, rect.width, w, window.innerWidth), ...placeVertical(rect.top, rect.bottom, h, window.innerHeight, undefined, undefined, chromeEdges()), width: w });
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
  useLayoutEffect(() => () => { clearTimeout(openTimer.current); clearTimeout(pressTimer.current); clearTimeout(closeTimer.current); }, []);

  const hoverProps = hover ? { onMouseEnter: showSoon, onMouseLeave: hide } : {};
  const tip = open && createPortal(<div ref={tooltip} id={id} role="tooltip" className={`alt-season-explanation${width < 300 ? ' is-compact' : ''}`} {...(hover ? { onMouseEnter: show, onMouseLeave: hide } : {})}
    style={{ width: cardWidth(width), ...position, visibility: position ? 'visible' : 'hidden' }}>
    {title && <strong>{title}</strong>}
    {children}
  </div>, document.body);

  if (labelMode) {
    // Touch: a held press opens the card; the click that ends it is then swallowed.
    const pressProps = longPress ? {
      onPointerDown: e => {
        pressed.current = false;
        if (e.pointerType === 'mouse') return;
        clearTimeout(pressTimer.current);
        pressTimer.current = setTimeout(() => { pressed.current = true; show(); }, 500);
      },
      onPointerUp: () => clearTimeout(pressTimer.current),
      onPointerCancel: () => clearTimeout(pressTimer.current),
      onPointerLeave: () => clearTimeout(pressTimer.current),
      onContextMenu: e => { if (pressed.current || open) e.preventDefault(); },
    } : {};
    const onClick = e => {
      e.stopPropagation();
      if (pressed.current) { pressed.current = false; return; }
      if (onActivate) { clearTimeout(openTimer.current); setOpen(false); onActivate(e); return; }
      if (hover) show(); else toggle(e);
    };
    // Keyboard focus opens the card; a mouse click that focuses the button does not.
    const onFocus = e => { if (hover && e.currentTarget.matches?.(':focus-visible')) show(); };
    return <span className={className} {...hoverProps}>
      <button ref={anchor} type="button" className={anchorClass} aria-label={label} aria-expanded={onActivate ? undefined : open}
        aria-describedby={open ? id : undefined} style={buttonStyle}
        onFocus={onFocus} onBlur={hover ? hide : undefined} onClick={onClick} {...pressProps} {...buttonProps}>{anchorContent}</button>
      {tip}
    </span>;
  }

  return <span className={`alt-season-info ${className}`} {...hoverProps}>
    <button ref={anchor} type="button" aria-label={label || `About ${title || 'this'}`} aria-expanded={open} aria-describedby={open ? id : undefined}
      style={{ width: size, height: size, fontSize: Math.max(9, Math.round(size * 0.7)), ...buttonStyle }}
      onPointerDown={e => { touch.current = e.pointerType !== 'mouse'; }}
      onFocus={hover ? show : undefined} onBlur={hover ? hide : undefined}
      onClick={hover ? (e => {
        e.stopPropagation();
        if (touch.current && pinned.current && openNow.current) { pinned.current = false; clearTimeout(closeTimer.current); setOpen(false); return; }
        if (touch.current) pinned.current = true;
        show();
      }) : toggle}>{icon || 'i'}</button>
    {tip}
  </span>;
}
