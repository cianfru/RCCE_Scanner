// Pure positioning math for the shared tooltip, kept free of React/DOM so it
// can be unit-tested with node --test.
export const TOOLTIP_MARGIN = 12;

/** Horizontal position: center on the anchor, then clamp inside the viewport. */
export function clampLeft(anchorLeft, anchorWidth, width, viewportWidth, margin = TOOLTIP_MARGIN) {
  const centered = anchorLeft + anchorWidth / 2 - width / 2;
  return Math.max(margin, Math.min(centered, viewportWidth - width - margin));
}

/**
 * Vertical position: below the anchor if it fits, otherwise above. When it fits on neither
 * side it takes the roomier one with a maxHeight (the card scrolls inside), so it never
 * covers its own anchor and never runs off the viewport.
 *
 * edges.top / edges.bottom narrow the usable band (default: margin from each viewport edge),
 * e.g. to keep a card under the header capsule and above the phone tab bar.
 */
export function placeVertical(anchorTop, anchorBottom, height, viewportHeight, gap = 10, margin = 16, edges = {}) {
  const topEdge = Math.max(margin, edges.top ?? margin);
  const bottomEdge = Math.min(viewportHeight - margin, edges.bottom ?? viewportHeight - margin);
  const below = anchorBottom + gap;
  const roomBelow = bottomEdge - below;
  const roomAbove = anchorTop - gap - topEdge;
  if (height <= roomBelow) return { top: below };
  if (height <= roomAbove) return { top: anchorTop - height - gap };
  if (roomBelow >= roomAbove) return { top: below, maxHeight: Math.max(0, roomBelow) };
  return { top: topEdge, maxHeight: Math.max(0, roomAbove) };
}
