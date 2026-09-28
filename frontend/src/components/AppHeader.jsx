import { useEffect, useRef, useState } from "react";
import { T } from "../theme.js";
import ReflexBrand from "./ReflexBrand.jsx";
import HeaderTabs from "./HeaderTabs.jsx";
import FreshnessClock from "./FreshnessClock.jsx";
import NotificationBell from "./NotificationBell.jsx";
import SettingsDropdown from "./SettingsDropdown.jsx";
import Tabs from "./Tabs.jsx";

// Pages reached through More: the hamburger's bars turn accent while one is open.
const MORE_PAGES = new Set(["signals", "analytics", "tradfi", "bridge", "backtest", "executor", "chat"]);
const TF_ITEMS = [{ key: "4h", label: "4H" }, { key: "1d", label: "1D" }];

// The floating metal capsule: More, the brand, the main tabs (900px and wider), and the
// right cluster (data clock, rescan, alerts, settings, theme). The page-colour mask above it
// hides rows scrolling up once the page moves.
export default function AppHeader({
  width, isMobile, mode, onToggleTheme,
  activeTab, activeMainTab, tabTargets, radarTf,
  drawerOpen, onOpenDrawer, onBrand,
  lastRefresh, cacheAge, error, scanRunning, onRefresh, rescanNeedsKey,
  timeframe, onTimeframe, compactTfRoute,
}) {
  const headerRef = useRef(null);
  const showTabs = width >= 900;
  const clock = width >= 1280 ? "long" : width >= 1024 ? "medium" : width >= 900 ? "dot" : isMobile ? "phone" : "medium";

  // Scrolled state on the page root: shows the top mask and the plate's page-colour scrim.
  useEffect(() => {
    const root = headerRef.current?.closest(".reflex-terminal");
    if (!root) return undefined;
    let frame = 0;
    const update = () => { frame = 0; root.toggleAttribute("data-scrolled", window.scrollY > 4); };
    const onScroll = () => { if (!frame) frame = requestAnimationFrame(update); };
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => { window.removeEventListener("scroll", onScroll); cancelAnimationFrame(frame); root.removeAttribute("data-scrolled"); };
  }, []);

  // Compact 4H | 1D once the page's own title row has scrolled under the capsule (1280+, scanner and Radar).
  const compactOn = width >= 1280 && !!compactTfRoute;
  const [headHidden, setHeadHidden] = useState(false);
  useEffect(() => {
    setHeadHidden(false);
    if (!compactOn || typeof IntersectionObserver === "undefined") return undefined;
    let io = null, mo = null;
    const attach = () => {
      const el = document.querySelector("#content .scanner-head");
      if (!el) return false;
      io = new IntersectionObserver(([e]) => setHeadHidden(!e.isIntersecting && e.boundingClientRect.top < 100),
        { rootMargin: "-80px 0px 0px 0px" });
      io.observe(el);
      return true;
    };
    if (!attach()) {
      mo = new MutationObserver(() => { if (attach()) { mo.disconnect(); mo = null; } });
      mo.observe(document.getElementById("content") || document.body, { childList: true, subtree: true });
    }
    return () => { io?.disconnect(); mo?.disconnect(); };
  }, [compactOn, compactTfRoute]);

  const moreActive = MORE_PAGES.has(activeTab);
  const refreshLabel = scanRunning ? "Scan running" : rescanNeedsKey ? "Rescan needs the admin key" : "Refresh scan";
  const freshnessProps = { lastRefresh, cacheAge, error, scanRunning };

  return (
    <>
      <div className="header-mask" aria-hidden="true" />
      <header className="terminal-header" ref={headerRef}>
        <div className="header-left" style={{ gap: isMobile ? 8 : 12 }}>
          <button type="button" className="header-more" onClick={onOpenDrawer} aria-label="More" aria-expanded={drawerOpen}
            title="More">
            {[0, 1, 2].map(i => <span key={i} style={{ background: moreActive ? T.accent : T.text2 }} />)}
          </button>
          <ReflexBrand compact={isMobile} metal className="header-brand" onClick={onBrand} />
        </div>

        {showTabs && <>
          <span className="header-divider" aria-hidden="true" />
          <HeaderTabs activeKey={activeMainTab} targets={tabTargets} showIcons={width >= 1280} radarTf={radarTf} />
        </>}

        <div className="header-spacer" />

        <div className="header-right">
          {compactOn && headHidden && (
            <div className="header-tf"><Tabs small label="Timeframe" items={TF_ITEMS} value={timeframe} onChange={onTimeframe} /></div>
          )}
          {clock !== "phone" && <FreshnessClock {...freshnessProps} variant={clock} />}
          <span className="header-refresh-wrap">
            <button type="button" className="header-refresh" onClick={onRefresh} disabled={scanRunning}
              title={refreshLabel} aria-label={refreshLabel}>
              <svg width="13" height="13" viewBox="0 0 16 16" fill="none" aria-hidden="true"
                style={scanRunning ? { animation: "spin 1s linear infinite" } : undefined}>
                <path d="M13.65 2.35A7.96 7.96 0 0 0 8 0a8 8 0 1 0 8 8h-2a6 6 0 1 1-1.76-4.24L10 6h6V0l-2.35 2.35z" fill="currentColor" />
              </svg>
            </button>
            {clock === "phone" && <FreshnessClock {...freshnessProps} variant="phone" />}
          </span>
          <NotificationBell />
          <SettingsDropdown />
          <button type="button" className="header-theme" onClick={onToggleTheme}
            title={mode === "dark" ? "Switch to light mode" : "Switch to dark mode"}>
            {mode === "dark" ? "Light" : "Dark"}
          </button>
        </div>
      </header>
    </>
  );
}
