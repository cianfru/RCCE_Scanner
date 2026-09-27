import { useCallback, useMemo } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { T } from "../theme.js";
import useViewport from "../hooks/useViewport.js";
import { timeframeFrom } from "../utils/researchNavigation.js";
import PageTitle from "../components/PageTitle.jsx";
import Tabs from "../components/Tabs.jsx";
import SetupMap from "../components/SetupMap.jsx";

// The Radar page: today's setup map, whole, on its own address (/radar?tf=1d).
export default function RadarPage({ results4h, results1d, onSelect }) {
  const { isMobile } = useViewport();
  const location = useLocation();
  const navigate = useNavigate();
  const tf = timeframeFrom(location.search);
  const rows = tf === "4h" ? results4h : results1d;
  const perps = useMemo(() => (rows || []).filter(r => (r.market_kind || "perpetual") === "perpetual"), [rows]);
  const setTf = useCallback(k => {
    const params = new URLSearchParams(location.search);
    params.set("tf", k);
    navigate(`${location.pathname}?${params}`, { replace: true, state: location.state });
  }, [navigate, location.pathname, location.search, location.state]);
  // A coin opened from here comes back to this view (tf, focus, sector).
  const select = useCallback((row, event) => onSelect(row, event, `${location.pathname}${location.search}`),
    [onSelect, location.pathname, location.search]);
  return (
    <div>
      <div className="scanner-head" style={{
        padding: `${isMobile ? T.sp4 : T.sp3}px 0 ${T.sp1}px`,
        display: "flex", alignItems: "center", justifyContent: "flex-start", flexWrap: "wrap", gap: "12px 20px",
      }}>
        <PageTitle>Radar</PageTitle>
        <Tabs small label="Timeframe" items={[{ key: "4h", label: "4H" }, { key: "1d", label: "1D" }]} value={tf} onChange={setTf} />
      </div>
      <SetupMap results={perps} timeframe={tf} onSelect={select} />
    </div>
  );
}
