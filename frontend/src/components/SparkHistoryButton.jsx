import { useEffect, useMemo, useState } from "react";
import HistoryButton, { noteHistoryOpened, useHistoryDot } from "./HistoryButton.jsx";
import { sparkGeometry } from "../utils/marketSpark.js";
import "./SparkHistoryButton.css";

const API_BASE = import.meta.env.VITE_API_URL || "";
const HOUR = 3_600_000;
const NARROW = "(max-width: 767px)";                 // phones: the eyebrow shares its row with the dial's column
let cached = null;                                   // { at, promise }: one fetch per hour per tab

function loadSpark() {
  if (!cached || Date.now() - cached.at > HOUR) {
    cached = { at: Date.now(), promise: fetch(`${API_BASE}/api/market-history/spark`).then(r => (r.ok ? r.json() : null)).catch(() => null) };
  }
  return cached.promise;
}

function useNarrow() {
  const query = () => (typeof window !== "undefined" && window.matchMedia ? window.matchMedia(NARROW) : null);
  const [narrow, setNarrow] = useState(() => !!query()?.matches);
  useEffect(() => {
    const mq = query();
    if (!mq?.addEventListener) return undefined;
    const on = () => setNarrow(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return narrow;
}

// The Market consensus card's history button drawn as a tiny chart: the Uptrend share over the last 90 days, and
// after today a faint band from the lowest to the highest of the past paths the drawer shows (up to +30 days).
// Until the data arrives, or if it fails, it is the plain chart icon, so the card never shows an empty box.
export default function SparkHistoryButton({ label, onClick }) {
  const [spark, setSpark] = useState(null);
  const dot = useHistoryDot();
  useEffect(() => {
    let alive = true;
    const get = () => loadSpark().then(d => { if (alive && d) setSpark(d); });
    get();
    const id = setInterval(get, HOUR);
    return () => { alive = false; clearInterval(id); };
  }, []);
  const narrow = useNarrow();
  const g = useMemo(() => sparkGeometry(spark, narrow ? { w: 40 } : undefined), [spark, narrow]);
  if (!g) return <HistoryButton label={label} onClick={onClick} dot={dot} />;
  return <button type="button" className="spark-btn" aria-label={label} title={label}
    onClick={e => { noteHistoryOpened(); onClick?.(e); }}>
    <svg viewBox={`0 0 ${g.w} ${g.h}`} width={g.w} height={g.h} aria-hidden="true">
      {g.stub && <path className="spark-stub" d={g.stub} />}
      <path className="spark-line" d={g.line} />
      <circle className="spark-end" cx={g.end[0]} cy={g.end[1]} r="1.6" />
    </svg>
    {dot && <span className="history-dot" aria-hidden="true" />}
  </button>;
}
