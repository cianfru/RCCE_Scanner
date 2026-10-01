// The public landing at "/". The first screen (the headline, the floating R, the coverage
// line) is complete on its own; everything under it is in Sections.jsx, loaded after it.
// Live visuals come from one small public payload (/api/public/landing, through the CDN;
// useLandingData.js), with a bundled snapshot when it cannot be read. The screen crops in
// public/landing/ are dated stills of the app. Copy stays generic: no counts that change;
// numbers appear only as readouts inside visuals.
import { lazy, Suspense, useEffect, useRef, useState } from "react";
import LogoSculpture from "./LogoSculpture.jsx";
import { Mark, LogoLettering } from "./Mark";
import { applyTheme, themeVars } from "../theme.js";
import useLandingData from "./useLandingData.js";
import "./palette.css";
import "./landing.css";

const Sections = lazy(() => import("./Sections.jsx"));

const DARK_VARS = themeVars("dark");
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const dayLabel = sec => { const d = new Date(sec * 1000); return `${WEEKDAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}`; };
const hm = sec => { const d = new Date(sec * 1000); return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; };
const reducedMotion = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
const TITLE = "Reflex: market regimes and trader positioning for Hyperliquid";
const ACCESS = "/scanner";      // the access-code screen (the app's login gate)

function Nav() {
  return <header className="lp-nav lp-width">
    <a className="lp-brand" href="/" aria-label="Reflex home"><Mark size={34} /><LogoLettering /></a>
    <nav aria-label="Sections"><a href="#engine">Engine</a><a href="#radar">Radar</a><a href="#traders">Traders</a><a href="#history">History</a></nav>
    <a className="lp-cta lp-cta-ghost" href={ACCESS}>Open Reflex</a>
  </header>;
}

function Coverage({ asOf }) {
  return <section className="lp-coverage lp-width" aria-label="Coverage">
    <div><b>Hyperliquid</b><span>perps and spot markets</span></div>
    <div><b>Traders</b><span>profitable and large wallets</span></div>
    <div><b>Since 2021</b><span>daily history</span></div>
    <div><b className="lp-mono">{asOf ? hm(asOf) : "—"}</b><span>{asOf ? `last scan, ${dayLabel(asOf)}` : "last scan"}</span></div>
  </section>;
}

// The floating ribbon at the top: the 3D R turns, bobs and leans toward the pointer, with its
// halo and floor shadow, only while it is on screen and the tab is visible; under reduced
// motion it is a still frame.
function HeroArt({ reduced }) {
  const ref = useRef(null), tilt = useRef(null);
  const [seen, setSeen] = useState(true);
  const [shown, setShown] = useState(true);
  const active = !reduced && seen && shown;
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === "undefined") return undefined;
    const io = new IntersectionObserver(([e]) => setSeen(e.isIntersecting), { rootMargin: "80px" });
    io.observe(el);
    const vis = () => setShown(!document.hidden);
    document.addEventListener("visibilitychange", vis);
    return () => { io.disconnect(); document.removeEventListener("visibilitychange", vis); };
  }, []);
  // Pointer lean, eased toward the pointer (mouse only), back to rest when motion stops.
  useEffect(() => {
    const el = tilt.current;
    if (!el) return undefined;
    if (!active) { el.style.transform = ""; return undefined; }
    let goal = [0, 0], now = [0, 0], frame = 0;
    const step = () => {
      now = [now[0] + (goal[0] - now[0]) * 0.06, now[1] + (goal[1] - now[1]) * 0.06];
      el.style.transform = `translate3d(${(now[0] * 16).toFixed(2)}px,${(now[1] * 11).toFixed(2)}px,0) rotate(${(now[0] * 0.8).toFixed(3)}deg)`;
      frame = Math.abs(goal[0] - now[0]) + Math.abs(goal[1] - now[1]) > 0.002 ? requestAnimationFrame(step) : 0;
    };
    const move = e => {
      if (e.pointerType !== "mouse") return;
      goal = [Math.max(-1, Math.min(1, (e.clientX / window.innerWidth - 0.5) * 2)), Math.max(-1, Math.min(1, (e.clientY / window.innerHeight - 0.5) * 2))];
      if (!frame) frame = requestAnimationFrame(step);
    };
    window.addEventListener("pointermove", move, { passive: true });
    return () => { window.removeEventListener("pointermove", move); cancelAnimationFrame(frame); el.style.transform = ""; };
  }, [active]);
  return <div className="lp-hero-art" ref={ref} data-moving={active ? "true" : "false"}>
    <div className="lp-r" aria-hidden="true" ref={tilt}>
      <div className="lp-r-float">
        <div className="lp-r-halo" />
        <LogoSculpture active={active} />
      </div>
      <div className="lp-r-shadow" />
    </div>
  </div>;
}

export function Landing() {
  // The landing is always dark: reset what a light-mode session in the app may have left,
  // before the first render.
  useState(() => applyTheme("dark"));
  useEffect(() => { document.title = TITLE; }, []);
  const [reduced] = useState(reducedMotion);
  const state = useLandingData();
  return <div className="lp" style={DARK_VARS}>
    <a href="#main" className="lp-skip">Skip to content</a>
    <div className="lp-first">
      <Nav />
      <section className="lp-hero lp-width" aria-labelledby="lp-h1">
        <div className="lp-hero-copy">
          <h1 id="lp-h1">One read of where <span>the market is.</span></h1>
          <p>Regime, entry checks and profitable-trader positioning for every Hyperliquid perp.</p>
          <a className="lp-cta" href={ACCESS}>Open Reflex</a>
        </div>
        <HeroArt reduced={reduced} />
      </section>
      <Coverage asOf={state?.body?.as_of} />
    </div>
    <main id="main">
      <Suspense fallback={<div className="lp-pending" />}><Sections /></Suspense>
    </main>
    <footer className="lp-footer lp-width">
      <a className="lp-brand" href="/" aria-label="Reflex home"><Mark size={26} /><LogoLettering /></a>
      <span>Market data and positioning for research. Not investment advice.</span>
    </footer>
  </div>;
}
