import { useLayoutEffect, useState } from "react";

// The element's clientWidth, kept current by a ResizeObserver and throttled to one update
// per animation frame. Measured before the first paint, so layouts that depend on it do not flash.
export default function useElementWidth(ref) {
  const [width, setWidth] = useState(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    let frame = 0;
    const read = () => { frame = 0; setWidth(el.clientWidth); };
    read();
    if (typeof ResizeObserver === "undefined") {
      const onResize = () => { if (!frame) frame = requestAnimationFrame(read); };
      window.addEventListener("resize", onResize);
      return () => { cancelAnimationFrame(frame); window.removeEventListener("resize", onResize); };
    }
    const observer = new ResizeObserver(() => { if (!frame) frame = requestAnimationFrame(read); });
    observer.observe(el);
    return () => { cancelAnimationFrame(frame); observer.disconnect(); };
  }, [ref]);
  return width;
}
