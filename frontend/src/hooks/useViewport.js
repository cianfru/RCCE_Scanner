import { useState, useEffect } from "react";

export default function useViewport() {
  const [vp, setVp] = useState(() => {
    const w = typeof window !== "undefined" ? window.innerWidth : 1280;
    return { width: w, isMobile: w < 768, isTablet: w >= 768 && w < 1024, isDesktop: w >= 1024 };
  });

  useEffect(() => {
    let ticking = false;
    const update = () => {
      const w = window.innerWidth;
      setVp({ width: w, isMobile: w < 768, isTablet: w >= 768 && w < 1024, isDesktop: w >= 1024 });
    };
    const onResize = () => {
      if (!ticking) {
        requestAnimationFrame(() => { update(); ticking = false; });
        ticking = true;
      }
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  return vp;
}
