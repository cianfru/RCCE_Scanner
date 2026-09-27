import { Link } from "react-router-dom";
import { T } from "../theme.js";
import useViewport from "../hooks/useViewport.js";
import PageTitle from "./PageTitle.jsx";

// Unknown address: shown inside the app shell, so the header stays in reach.
export default function NotFound() {
  const { isMobile } = useViewport();
  return (
    <div>
      <div className="scanner-head" style={{
        padding: `${isMobile ? T.sp4 : T.sp3}px 0 ${T.sp1}px`,
        display: "flex", alignItems: "center", justifyContent: "flex-start", flexWrap: "wrap", gap: "12px 20px",
      }}>
        <PageTitle>Page not found</PageTitle>
      </div>
      <p style={{ fontSize: 14, color: T.text3, margin: "12px 0 16px" }}>This link may have moved.</p>
      <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
        <Link className="te-link" to="/scanner">Open the scanner</Link>
        <Link className="te-link" to="/radar">Open the Radar</Link>
      </div>
    </div>
  );
}
