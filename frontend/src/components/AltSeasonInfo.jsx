import { useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

export default function AltSeasonInfo({ gauge }) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState(null);
  const anchor = useRef(null);
  const tooltip = useRef(null);
  const closeTimer = useRef(null);
  const id = useId();
  const show = () => { clearTimeout(closeTimer.current); setOpen(true); };
  const hide = () => { closeTimer.current = setTimeout(() => setOpen(false), 150); };

  useLayoutEffect(() => {
    if (!open) { setPosition(null); return; }
    const place = () => {
      const rect = anchor.current.getBoundingClientRect();
      const width = Math.min(400, window.innerWidth - 32);
      const height = tooltip.current?.getBoundingClientRect().height || 300;
      const left = Math.max(16, Math.min(rect.left - width / 2 + rect.width / 2, window.innerWidth - width - 16));
      const below = rect.bottom + 10;
      const top = below + height <= window.innerHeight - 16 ? below : Math.max(16, rect.top - height - 10);
      setPosition({ left, top, width });
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
  }, [open]);

  return <span className="alt-season-info" onMouseEnter={show} onMouseLeave={hide}>
    <button ref={anchor} type="button" aria-label="How alt season is calculated" aria-expanded={open} aria-describedby={open ? id : undefined}
      onFocus={show} onBlur={hide} onClick={show}>i</button>
    {open && createPortal(<div ref={tooltip} id={id} role="tooltip" className="alt-season-explanation" onMouseEnter={show} onMouseLeave={hide}
      style={{ ...position, visibility: position ? 'visible' : 'hidden' }}>
      <strong>{gauge.label} · {gauge.score?.toFixed(1)} / 100</strong>
      <p>{gauge.alts_up} of {gauge.total_alts} scanned altcoins are in markup or re-accumulation.</p>
      <p>When market-cap data is available, the score blends bullish breadth (60%) with normalized non-Bitcoin dominance (40%). Otherwise it uses breadth alone. It is reduced when Bitcoin is bullish but fewer than 30% of alts are bullish.</p>
      <p>Active: 50–74.9. Hot: 75+. This measures the scanner’s market breadth, not 90-day outperformance against Bitcoin.</p>
    </div>, document.body)}
  </span>;
}
