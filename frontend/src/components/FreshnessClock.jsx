import { useEffect, useState } from "react";
import { col } from "../theme.js";
import { freshness, freshnessText } from "../utils/freshness.js";

const DOT = { live: () => "var(--t-accent)", stale: () => col("#fbbf24"), down: () => col("#f87171") };

// The header's data clock: a status dot (mint live, amber from 15 minutes, red when the feed
// is down) and the scan time with its age. variant: "long" (1280+), "medium", "dot" (900-1023)
// or "phone" (the dot alone, placed on the refresh icon by the caller).
export default function FreshnessClock({ lastRefresh, cacheAge, error, scanRunning, variant = "long" }) {
  const [, tick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => tick(n => n + 1), 30000);
    return () => clearInterval(id);
  }, []);

  const f = freshness({ lastRefresh, cacheAge, error, now: Date.now() });
  if (!f.state) return null;
  const text = freshnessText(f);
  if (!f.dataTime) Object.assign(text, { title: "The scanner feed is unavailable", aria: "The scanner feed is unavailable" });
  const dot = <span className={`freshness-dot${scanRunning ? " is-scanning" : ""}`} style={{ background: DOT[f.state]() }} />;

  if (variant === "phone") {
    return <span className="freshness freshness-phone" role="img" aria-label={text.aria} title={text.title}>{dot}</span>;
  }
  const label = variant === "long" ? text.long : variant === "medium" ? text.medium : "";
  return (
    <span className="freshness" title={text.title} role={label ? undefined : "img"} aria-label={label ? undefined : text.aria}>
      {dot}
      {label && <span>{label}</span>}
    </span>
  );
}
