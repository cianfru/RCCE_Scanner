// Pure positioning math for the shared tooltip, kept free of React/DOM so it
// can be unit-tested with node --test.
export const TOOLTIP_MARGIN = 12;

/** Horizontal position: center on the anchor, then clamp inside the viewport. */
export function clampLeft(anchorLeft, anchorWidth, width, viewportWidth, margin = TOOLTIP_MARGIN) {
  const centered = anchorLeft + anchorWidth / 2 - width / 2;
  return Math.max(margin, Math.min(centered, viewportWidth - width - margin));
}

/** Vertical position: below the anchor if it fits, otherwise above. */
export function placeVertical(anchorTop, anchorBottom, height, viewportHeight, gap = 10, margin = 16) {
  const below = anchorBottom + gap;
  if (below + height <= viewportHeight - margin) return { top: below };
  return { top: Math.max(margin, anchorTop - height - gap) };
}
