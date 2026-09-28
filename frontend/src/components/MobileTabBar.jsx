import { Link, useLocation } from "react-router-dom";
import { MAIN_TABS } from "../utils/mainNav.js";
import { NavIcon } from "./navIcons.jsx";

const prefetchRadar = () => { import("../pages/RadarPage.jsx").catch(() => {}); };

// Below 900px: the four main tabs in a floating glass bar, the capsule's twin at the bottom.
// No More item: the hamburger in the capsule is More.
export default function MobileTabBar({ activeKey, targets }) {
  const location = useLocation();
  const onClick = key => e => {
    const here = (key === "scanner" && location.pathname === "/scanner") || (key === "radar" && location.pathname === "/radar");
    if (here) { e.preventDefault(); window.scrollTo({ top: 0 }); }
  };
  return (
    <nav aria-label="Main" className="mobile-tabbar">
      {MAIN_TABS.map(t => (
        <Link key={t.key} to={targets[t.key]} className="mobile-tab" aria-current={t.key === activeKey ? "page" : undefined}
          onClick={onClick(t.key)} onTouchStart={t.key === "radar" ? prefetchRadar : undefined}>
          <NavIcon name={t.icon} size={20} />
          <span>{t.label}</span>
        </Link>
      ))}
    </nav>
  );
}
