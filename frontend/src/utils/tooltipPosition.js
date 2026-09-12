// Pure placement math for portaled, position:fixed help cards.
// Keeps the card inside the viewport (with a margin), prefers rendering below
// the anchor and flips above when there is no room, centred on the anchor.

export const TOOLTIP_MARGIN = 16;
export const TOOLTIP_GAP = 10;

export function placeTooltip({ anchor, width, height, viewport, margin = TOOLTIP_MARGIN, gap = TOOLTIP_GAP }) {
  const usable = Math.max(0, viewport.width - margin * 2);
  const w = Math.min(width, usable);
  const centred = anchor.left + anchor.width / 2 - w / 2;
  const left = Math.max(margin, Math.min(centred, viewport.width - w - margin));
  const below = anchor.bottom + gap;
  const fitsBelow = below + height <= viewport.height - margin;
  const above = anchor.top - height - gap;
  const top = fitsBelow ? below : Math.max(margin, above);
  return { left, top, width: w, placement: fitsBelow ? 'below' : 'above' };
}
