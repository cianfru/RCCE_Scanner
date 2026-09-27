import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { MAIN_TABS } from "../utils/mainNav.js";
import { NavIcon } from "./navIcons.jsx";
import useSetupMap from "../hooks/useSetupMap.js";

const prefetchRadar = () => { import("../pages/RadarPage.jsx").catch(() => {}); };
const reducedMotion = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

// The main tabs inside the capsule (900px and wider). One lit indicator slides under the active
// tab's icon and label and sits on the capsule's bottom edge; none shows on More pages.
// "Radar 19": coins in the Watch box on the last scanner timeframe, from the shared setup-map
// store (no extra request). Hidden while unknown or zero.
export default function HeaderTabs({ activeKey, targets, showIcons, radarTf = "1d" }) {
  const location = useLocation();
  const { data: radarMap } = useSetupMap(radarTf === "4h" ? "4h" : "1d");
  const radarCount = useMemo(() => (radarMap?.coins ? radarMap.coins.filter(c => c.zone === "watch").length : 0), [radarMap]);
  const navRef = useRef(null);
  const [bar, setBar] = useState({ x: 0, w: 0, visible: false, animate: false });

  const measure = useCallback(() => {
    const nav = navRef.current;
    const el = nav && activeKey ? nav.querySelector(`[data-tab="${activeKey}"] .tab-inner`) : null;
    if (!nav || !el) { setBar(b => (b.visible ? { ...b, visible: false, animate: false } : b)); return; }
    const n = nav.getBoundingClientRect(), r = el.getBoundingClientRect();
    const x = Math.round((r.left - n.left) * 10) / 10, w = Math.round(r.width * 10) / 10;
    // Slide only between two tabs; appear in place when coming from a page with no tab.
    setBar(b => (b.visible && b.x === x && b.w === w ? b : { x, w, visible: true, animate: b.visible }));
  }, [activeKey]);

  useLayoutEffect(() => { measure(); }, [measure, showIcons, radarCount]);

  useEffect(() => {
    const nav = navRef.current;
    if (!nav || typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(() => measure());
    ro.observe(nav);
    nav.querySelectorAll(".tab-inner").forEach(el => ro.observe(el));
    document.fonts?.ready?.then(measure).catch(() => {});
    return () => ro.disconnect();
  }, [measure, showIcons]);

  const onClick = key => e => {
    // Already on the page: go back to its top instead of reloading the view.
    const here = (key === "scanner" && location.pathname === "/scanner") || (key === "radar" && location.pathname === "/radar");
    if (here && !e.metaKey && !e.ctrlKey && !e.shiftKey) {
      e.preventDefault();
      window.scrollTo({ top: 0, behavior: reducedMotion() ? "auto" : "smooth" });
    }
  };

  return (
    <nav aria-label="Main" className="header-tabs" ref={navRef}>
      {MAIN_TABS.map(t => {
        const active = t.key === activeKey;
        const radar = t.key === "radar";
        return (
          <Link key={t.key} to={targets[t.key]} data-tab={t.key} aria-current={active ? "page" : undefined}
            onClick={onClick(t.key)}
            onMouseEnter={radar ? prefetchRadar : undefined} onFocus={radar ? prefetchRadar : undefined}>
            <span className="tab-inner">
              {showIcons && <span className="tab-icon"><NavIcon name={t.icon} /></span>}
              <span className="tab-label" data-text={t.label}>{t.label}</span>
              {radar && radarCount > 0 && <span className="tab-count" aria-label={`${radarCount} in the Watch box`}>{radarCount}</span>}
            </span>
          </Link>
        );
      })}
      <span className="header-tab-indicator" aria-hidden="true" style={{
        width: bar.w, transform: `translateX(${bar.x}px)`, opacity: bar.visible ? 1 : 0,
        transition: bar.animate ? undefined : "none",
      }} />
    </nav>
  );
}
