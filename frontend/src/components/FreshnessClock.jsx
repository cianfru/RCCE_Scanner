import { useEffect, useState } from "react";
import { col } from "../theme.js";
import { freshness, freshnessText } from "../utils/freshness.js";

// Text only, no status dot: amber once the data is 15 minutes old, red when the feed is down.
const TONE = { live: () => undefined, stale: () => col("#fbbf24"), down: () => col("#f87171") };
const SHORT = { stale: "Data late", down: "Feed down" };

// The header's data clock: the scan time with its age ("Updated 15:31 · 2m").
// variant: "long" (1280+), "medium", "compact" (900-1023) or "phone". The last two show
// nothing while the data is fresh, and a short "Data late" / "Feed down" when it is not.
export default function FreshnessClock({ lastRefresh, cacheAge, error, variant = "long" }) {
  const [, tick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => tick(n => n + 1), 30000);
    return () => clearInterval(id);
  }, []);

  const f = freshness({ lastRefresh, cacheAge, error, now: Date.now() });
  if (!f.state) return null;
  const text = freshnessText(f);
  if (!f.dataTime) Object.assign(text, { title: "The scanner feed is unavailable", aria: "The scanner feed is unavailable" });
  const color = TONE[f.state]();

  if (variant === "phone" || variant === "compact") {
    if (f.state === "live") return null;
    return <span className="freshness" title={text.title} style={{ color }}>{SHORT[f.state]}</span>;
  }
  const label = variant === "long" ? text.long : text.medium;
  if (!label) return <span className="freshness" title={text.title} style={{ color }}>{SHORT[f.state] || ""}</span>;
  return <span className="freshness" title={text.title} style={{ color }}>{label}</span>;
}
