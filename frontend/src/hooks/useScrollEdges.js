import { useCallback, useLayoutEffect, useState } from "react";

const reducedMotion = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

// For a sideways-scrolling strip: whether more content sits past the left and right edges
// (drives the .edge-fade masks and the chevrons), plus a page-by-page scroll helper.
// `key` re-measures when the content changes without the strip itself resizing.
export default function useScrollEdges(ref, key) {
  const [edges, setEdges] = useState({ left: false, right: false });
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    let frame = 0;
    const read = () => {
      frame = 0;
      const left = el.scrollLeft > 1;
      const right = el.scrollLeft + el.clientWidth < el.scrollWidth - 1;
      setEdges(e => (e.left === left && e.right === right ? e : { left, right }));
    };
    const soon = () => { if (!frame) frame = requestAnimationFrame(read); };
    read();
    el.addEventListener("scroll", soon, { passive: true });
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(soon);
    observer?.observe(el);
    if (!observer) window.addEventListener("resize", soon);
    return () => {
      cancelAnimationFrame(frame);
      el.removeEventListener("scroll", soon);
      observer?.disconnect();
      if (!observer) window.removeEventListener("resize", soon);
    };
  }, [ref, key]);
  // One step is 80% of the visible width, so the chip cut at the edge comes fully into view.
  const scrollPage = useCallback(dir => {
    const el = ref.current;
    if (el) el.scrollBy({ left: dir * 0.8 * el.clientWidth, behavior: reducedMotion() ? "auto" : "smooth" });
  }, [ref]);
  return { ...edges, scrollPage };
}

// Attributes for an element carrying the .edge-fade mask.
export const fadeAttrs = e => ({ "data-fade-l": e.left ? "" : undefined, "data-fade-r": e.right ? "" : undefined });
