import { useMemo } from "react";
import { Link } from "react-router-dom";
import { T } from "../theme.js";
import useViewport from "../hooks/useViewport.js";
import useSetupMap from "../hooks/useSetupMap.js";
import { MAIN_TABS, mainTabTargets } from "../utils/mainNav.js";
import { NavIcon } from "./navIcons.jsx";
import PageTitle from "./PageTitle.jsx";

const DESC = {
  scanner: "Signals and regimes for every market",
  radar: "Coins setting up now",
  traders: "How profitable traders are positioned",
  portfolio: "Your Hyperliquid positions",
};

// Unknown address: shown inside the app shell, so the header stays in reach. Under the copy,
// the four main pages as flat rows with their nav glyphs (same targets as the tabs).
export default function NotFound({ targets = mainTabTargets(), radarTf = "1d" }) {
  const { isMobile } = useViewport();
  // Same shared setup-map store as the header's "Radar 21" count; no extra request on desktop.
  const { data: radarMap } = useSetupMap(radarTf === "4h" ? "4h" : "1d");
  const watchCount = useMemo(() => (radarMap?.coins ? radarMap.coins.filter(c => c.zone === "watch").length : 0), [radarMap]);
  return (
    <div>
      <div className="scanner-head" style={{
        padding: `${isMobile ? T.sp4 : T.sp3}px 0 ${T.sp1}px`,
        display: "flex", alignItems: "center", justifyContent: "flex-start", flexWrap: "wrap", gap: "12px 20px",
      }}>
        <PageTitle>Page not found</PageTitle>
      </div>
      <p style={{ fontSize: 14, color: T.text3, margin: "12px 0 20px" }}>This link may have moved.</p>
      <nav aria-label="Main pages">
        <ul className="nf-list">
          {MAIN_TABS.map(t => (
            <li key={t.key}>
              <Link className="nf-row" to={targets[t.key]}>
                <span className="nf-icon"><NavIcon name={t.icon} /></span>
                <span className="nf-text">
                  <span className="nf-label">{t.label}</span>
                  <span className="nf-desc">
                    {t.key === "radar" && watchCount > 0
                      ? <><span className="nf-count">{watchCount}</span> in the Watch box</>
                      : DESC[t.key]}
                  </span>
                </span>
                <svg className="nf-go" width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true" focusable="false">
                  <path d="M6 3.5L10.5 8L6 12.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </Link>
            </li>
          ))}
        </ul>
      </nav>
    </div>
  );
}
