import { useEffect, useMemo, useRef, useState } from "react";
import useHistoryDot, { noteHistoryOpened } from "../hooks/useHistoryDot.js";
import { sparkGeometry } from "../utils/marketSpark.js";
import "./SparkHistoryButton.css";
import { apiFetch } from "../edge.js";

const API_BASE = import.meta.env.VITE_API_URL || "";
const HOUR = 3_600_000;
const MIN_CHART = 22;                                // px of chart below which the button shows the plain icon
let cached = null;                                   // { at, promise }: one fetch per hour per tab

function loadSpark() {
  if (!cached || Date.now() - cached.at >= HOUR) {
    cached = { at: Date.now(), promise: apiFetch("/api/market-history/spark").then(r => (r.ok ? r.json() : null)).catch(() => null) };
  }
  return cached.promise;
}

const Icon = () => <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true">
  <polyline points="1,9 4,5.5 6.5,7.5 11,2" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
</svg>;

// The Market consensus card's history button drawn as a tiny chart: the Uptrend share over the last 90 days, and
// after today a faint band from the lowest to the highest of the past paths the drawer shows (up to +30 days).
// Until the data arrives, or if it fails, it is the plain chart icon, so the card never shows an empty box. One
// <button> in every state, so keyboard focus survives the swap. The chart shrinks with the room the eyebrow has
// (phones) and falls back to the icon when too little is left.
export default function SparkHistoryButton({ label, onClick }) {
  const [spark, setSpark] = useState(null);
  const [tight, setTight] = useState(false);
  const ref = useRef(null);
  const dot = useHistoryDot();
  useEffect(() => {
    let alive = true;
    const get = () => loadSpark().then(d => { if (alive && d) setSpark(d); });
    const onVisible = () => { if (!document.hidden) get(); };
    get();
    const id = setInterval(onVisible, HOUR);         // hidden tabs do not poll (nor wake an idle backend)
    document.addEventListener("visibilitychange", onVisible);
    return () => { alive = false; clearInterval(id); document.removeEventListener("visibilitychange", onVisible); };
  }, []);
  const g = useMemo(() => sparkGeometry(spark), [spark]);
  useEffect(() => {
    const el = ref.current;
    if (!g || !el || typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(([e]) => setTight(e.contentRect.width < MIN_CHART));
    ro.observe(el);
    return () => ro.disconnect();
  }, [g]);
  const title = g ? (g.stub ? "Uptrend share, last 90 days. Faint band after today: lowest to highest of the past paths from similar days"
    : "Uptrend share, last 90 days") : label;
  return <button ref={ref} type="button" className={g ? "spark-btn" : "history-btn"} aria-label={label} title={title}
    onClick={e => { noteHistoryOpened(); onClick?.(e); }}>
    {g && !tight
      ? <svg viewBox={`0 0 ${g.w} ${g.h}`} preserveAspectRatio="none" aria-hidden="true">
        {g.stub && <path className="spark-stub" d={g.stub} />}
        <path className="spark-area" d={g.area} />
        <path className="spark-line" d={g.line} />
        <path className="spark-end" d={`M${g.end[0]},${g.end[1]}h0`} />
      </svg>
      : <Icon />}
    {dot && <span className="history-dot" aria-hidden="true" />}
  </button>;
}
